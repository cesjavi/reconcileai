"""Evolus integration surface.

Outbound (we call Evolus):  POST /candidates/{id}/evolus-review  -> AI Tool `summarize` + Workflow execute
                            POST /evolus/executions/{id}/refresh -> poll the workflow execution
Inbound  (Evolus calls us): GET  /agent/cases                    -> masked, pending cases only
                            POST /agent/cases/{id}/recommendation -> advisory note, idempotent

Safety rules enforced here, not in the prompt:
  * No endpoint reachable with the agent token can approve, reject or change a candidate.
  * An agent may never recommend APPROVE for an AMBIGUOUS candidate.
  * Evolus output is stored as advisory text; the deterministic engine and a human still decide.
"""
from __future__ import annotations

import hmac
import logging
import re
from functools import lru_cache
from typing import Literal

from evolus import EvolusError, build_evolus
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import audit
from .config import Settings, get_settings
from .db import get_session
from .models import (AgentRecommendation, BankTransaction, EvolusExecution, MatchCandidate, SystemDeposit, utcnow)

log = logging.getLogger("evolus")
router = APIRouter()


@lru_cache
def _evolus():
    return build_evolus(get_settings().evolus_settings())


def get_evolus():
    try:
        return _evolus()
    except ValueError as exc:
        raise HTTPException(503, f"evolus misconfigured: {exc}") from exc


def actor_header(x_actor: str = Header(default="", max_length=64)) -> str:
    if not x_actor.strip():
        raise HTTPException(400, "X-Actor header required")
    return x_actor.strip()


def mask(text: str) -> str:
    """Hide long digit runs (CUIT/DNI/account numbers) before anything leaves for an external agent."""
    return re.sub(r"\d{7,}", lambda m: "***" + m.group(0)[-3:], text or "")


def agent_auth(authorization: str = Header(default=""), s: Settings = Depends(get_settings)) -> str:
    if not s.agent_api_token:
        raise HTTPException(503, "agent API disabled: AGENT_API_TOKEN is not set")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), s.agent_api_token.encode()):
        raise HTTPException(401, "invalid agent token")
    return "evolus-agent"


def case_dict(c: MatchCandidate, b: BankTransaction, d: SystemDeposit) -> dict:
    return {"candidate_id": c.id, "status": c.status, "rule": c.rule, "evidence": c.evidence,
            "bank": {"date": str(b.tx_date), "amount": str(b.amount), "description": mask(b.description),
                     "document": mask(b.document), "voucher": b.voucher},
            "deposit": {"date": str(d.deposit_date), "amount": str(d.amount), "document": mask(d.document),
                        "voucher": d.voucher}}


def case_text(case: dict) -> str:
    b, d = case["bank"], case["deposit"]
    return (f"Candidate {case['candidate_id']} ({case['status']}, rule {case['rule']}). "
            f"Bank: {b['date']} {b['amount']} '{b['description']}' doc {b['document'] or '-'} voucher {b['voucher'] or '-'}. "
            f"Deposit: {d['date']} {d['amount']} doc {d['document'] or '-'} voucher {d['voucher'] or '-'}. "
            f"Engine evidence: {case['evidence']}.")


def exec_out(e: EvolusExecution) -> dict:
    return {"id": e.id, "kind": e.kind, "mode": e.mode, "simulated": e.mode == "mock", "candidate_id": e.candidate_id,
            "remote_execution_id": e.remote_execution_id, "trace_id": e.trace_id, "status": e.status,
            "error": e.error, "advisory_text": e.advisory_text, "credits_consumed": e.credits_consumed,
            "created_at": e.created_at, "updated_at": e.updated_at}


def _load_case(db: Session, candidate_id: int):
    row = db.execute(select(MatchCandidate, BankTransaction, SystemDeposit)
                     .join(BankTransaction, MatchCandidate.bank_id == BankTransaction.id)
                     .join(SystemDeposit, MatchCandidate.deposit_id == SystemDeposit.id)
                     .where(MatchCandidate.id == candidate_id)).first()
    if row is None:
        raise HTTPException(404, "candidate not found")
    return row


@router.get("/evolus/status")
def evolus_status(s: Settings = Depends(get_settings), client=Depends(get_evolus)):
    es = s.evolus_settings()
    return {"mode": es.mode, "enabled": client is not None, "simulated": es.mode == "mock",
            "configured": {"api_key": bool(es.api_key.get_secret_value()), "application_id": bool(es.application_id),
                           "workflow_id": bool(es.workflow_id), "extractor": bool(es.extractor_id)},
            "agent_api_enabled": bool(s.agent_api_token), "base_url": es.base_url}


@router.post("/candidates/{candidate_id}/evolus-review")
def evolus_review(candidate_id: int, db: Session = Depends(get_session), actor: str = Depends(actor_header),
                  client=Depends(get_evolus)):
    if client is None:
        raise HTTPException(503, "Evolus is disabled (EVOLUS_MODE=disabled)")
    c, b, d = _load_case(db, candidate_id)
    key = f"review:{c.id}:{c.status}"
    existing = db.scalars(select(EvolusExecution).where(EvolusExecution.idempotency_key == key)).first()
    if existing and existing.status != "Error":
        return {**exec_out(existing), "reused": True}
    case = case_dict(c, b, d)
    text = case_text(case)
    ex = existing or EvolusExecution(idempotency_key=key, kind="workflow", candidate_id=c.id, created_by=actor,
                                     mode="mock" if client.is_mock else "live", status="Pending")
    ex.error, ex.status = None, "Pending"
    try:
        tool = client.run_ai_tool("summarize", text)  # AI Tool: reviewer-facing summary
        ex.advisory_text = tool.output if isinstance(tool.output, str) else str(tool.output)
        ex.credits_consumed = tool.credits_consumed
        start = client.execute_workflow(text, {"candidate_id": c.id, "rule": c.rule, "engine_status": c.status})
        ex.remote_execution_id, ex.trace_id = start.execution_id, start.trace_id
    except EvolusError as err:
        ex.status, ex.error = "Error", f"{err.kind}: {err.message}"[:255]
        log.warning("evolus_review_failed", extra={"candidate_id": c.id, "kind": err.kind})
    db.add(ex)
    db.flush()
    audit.record(db, actor, "evolus_review_started" if ex.status != "Error" else "evolus_review_failed", "candidate",
                 c.id, {"execution": ex.id, "remote_execution_id": ex.remote_execution_id, "mode": ex.mode,
                        "error": ex.error})
    db.commit()
    body = exec_out(ex)
    if ex.status == "Error":
        return JSONResponse(jsonable_encoder(body), status_code=502)
    return {**body, "reused": False}


@router.post("/evolus/executions/{execution_id}/refresh")
def refresh_execution(execution_id: int, db: Session = Depends(get_session), actor: str = Depends(actor_header),
                      client=Depends(get_evolus)):
    ex = db.get(EvolusExecution, execution_id)
    if ex is None or client is None:
        raise HTTPException(404 if ex is None else 503, "execution not found" if ex is None else "Evolus disabled")
    if ex.status in ("Completed", "Failed") or not ex.remote_execution_id:
        return exec_out(ex)
    if (ex.mode == "mock") != client.is_mock:
        raise HTTPException(409, "execution was created in a different Evolus mode")
    try:
        remote = client.get_execution(ex.remote_execution_id)
    except EvolusError as err:
        ex.error = f"{err.kind}: {err.message}"[:255]
        db.commit()
        raise HTTPException(502, ex.error) from err
    ex.status, ex.error = remote.status, None
    ex.result = {k: v for k, v in remote.raw.items() if k != "status"} | {"status": remote.status}
    if remote.terminal:
        audit.record(db, actor, "evolus_execution_" + remote.status.lower(), "evolus_execution", ex.id,
                     {"remote_execution_id": ex.remote_execution_id, "mode": ex.mode})
    db.commit()
    return exec_out(ex)


@router.get("/evolus/executions")
def list_executions(candidate_id: int | None = None, db: Session = Depends(get_session)):
    q = select(EvolusExecution).order_by(EvolusExecution.id.desc()).limit(100)
    if candidate_id:
        q = q.where(EvolusExecution.candidate_id == candidate_id)
    return [exec_out(e) for e in db.scalars(q)]


# ---------- inbound agent API ----------
@router.get("/agent/cases")
def agent_cases(limit: int = 25, db: Session = Depends(get_session), _: str = Depends(agent_auth)):
    rows = db.execute(select(MatchCandidate, BankTransaction, SystemDeposit)
                      .join(BankTransaction, MatchCandidate.bank_id == BankTransaction.id)
                      .join(SystemDeposit, MatchCandidate.deposit_id == SystemDeposit.id)
                      .where(MatchCandidate.status.in_(("SUGGESTED", "AMBIGUOUS")))
                      .order_by(MatchCandidate.id).limit(min(limit, 100)))
    return [case_dict(*r) for r in rows]


class Recommendation(BaseModel):
    recommendation: Literal["APPROVE", "REJECT", "NEEDS_HUMAN"]
    rationale: str = Field(default="", max_length=1000)


@router.post("/agent/cases/{candidate_id}/recommendation")
def agent_recommend(candidate_id: int, body: Recommendation, idempotency_key: str = Header(min_length=8, max_length=100),
                    db: Session = Depends(get_session), who: str = Depends(agent_auth)):
    key = f"{candidate_id}:{idempotency_key}"
    prior = db.scalars(select(AgentRecommendation).where(AgentRecommendation.idempotency_key == key)).first()
    if prior:
        return {"id": prior.id, "recommendation": prior.recommendation, "reused": True}
    c = db.get(MatchCandidate, candidate_id)
    if c is None:
        raise HTTPException(404, "candidate not found")
    if c.status not in ("SUGGESTED", "AMBIGUOUS"):
        raise HTTPException(409, f"candidate is {c.status}; recommendations only apply to pending cases")
    if c.status == "AMBIGUOUS" and body.recommendation == "APPROVE":
        raise HTTPException(422, "agents cannot recommend approving an ambiguous candidate; use NEEDS_HUMAN")
    rec = AgentRecommendation(idempotency_key=key, candidate_id=c.id, recommendation=body.recommendation,
                              rationale=body.rationale.strip(), source=who)
    db.add(rec)
    try:
        db.flush()
        audit.record(db, who, "agent_recommendation", "candidate", c.id,
                     {"recommendation": body.recommendation, "recommendation_id": rec.id})
        db.commit()
    except IntegrityError:  # concurrent retry with the same key
        db.rollback()
        prior = db.scalars(select(AgentRecommendation).where(AgentRecommendation.idempotency_key == key)).first()
        return {"id": prior.id, "recommendation": prior.recommendation, "reused": True}
    return {"id": rec.id, "recommendation": rec.recommendation, "reused": False}


@router.get("/candidates/{candidate_id}/insights")
def candidate_insights(candidate_id: int, db: Session = Depends(get_session)):
    recs = db.scalars(select(AgentRecommendation).where(AgentRecommendation.candidate_id == candidate_id)
                      .order_by(AgentRecommendation.id))
    execs = db.scalars(select(EvolusExecution).where(EvolusExecution.candidate_id == candidate_id)
                       .order_by(EvolusExecution.id))
    return {"recommendations": [{"id": r.id, "recommendation": r.recommendation, "rationale": r.rationale,
                                 "source": r.source, "created_at": r.created_at} for r in recs],
            "evolus_executions": [exec_out(e) for e in execs]}
