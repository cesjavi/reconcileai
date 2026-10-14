"""Reconciliation run and human decisions. Every public function works inside the caller's transaction."""
from __future__ import annotations

import logging
from collections import Counter

from reconciliation import Bank, Deposit, RuleConfig, check_invariants, norm_ref, run_rules
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import audit
from .config import Settings
from .models import (BankTransaction, InferenceLog, MatchCandidate, ReconciliationBatch,
                     ReconciliationDecision, SystemDeposit, utcnow)

log = logging.getLogger("matching")
PENDING = ("SUGGESTED", "AMBIGUOUS")


class DecisionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def rule_config(s: Settings) -> RuleConfig:
    return RuleConfig(window_days=s.window_days, ai_window_days=s.ai_window_days)


def _derive(statuses: list[str]) -> str:
    if "MATCHED" in statuses:
        return "MATCHED"
    if "AMBIGUOUS" in statuses:
        return "AMBIGUOUS"
    if "SUGGESTED" in statuses:
        return "SUGGESTED"
    return "REJECTED" if "REJECTED" in statuses else "UNMATCHED"


def refresh_statuses(db: Session, bank_ids: set[int], deposit_ids: set[int]) -> None:
    db.flush()
    for ids, model, col in ((bank_ids, BankTransaction, MatchCandidate.bank_id),
                            (deposit_ids, SystemDeposit, MatchCandidate.deposit_id)):
        if not ids:
            continue
        by: dict[int, list[str]] = {i: [] for i in ids}
        for key, st in db.execute(select(col, MatchCandidate.status).where(col.in_(ids))):
            by[key].append(st)
        for row in db.scalars(select(model).where(model.id.in_(ids))):
            row.status = _derive(by[row.id])


def run_reconciliation(db: Session, actor: str, settings: Settings, extractor=None) -> dict:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(7001)"))  # serialise runs

    cands = list(db.scalars(select(MatchCandidate)))
    matched_b = {c.bank_id for c in cands if c.status == "MATCHED"}
    matched_d = {c.deposit_id for c in cands if c.status == "MATCHED"}
    rejected = {(c.bank_id, c.deposit_id) for c in cands if c.status == "REJECTED"}
    existing = {(c.bank_id, c.deposit_id): c for c in cands if c.status in PENDING}

    banks = {b.id: b for b in db.scalars(select(BankTransaction)) if b.id not in matched_b}
    deps = {d.id: d for d in db.scalars(select(SystemDeposit)) if d.id not in matched_d}

    run = ReconciliationBatch(kind="RUN", created_by=actor)
    db.add(run)
    db.flush()

    logs: dict[int, object] = {}

    def extract(b: Bank) -> list[str]:
        if extractor is None:
            return []
        res = extractor.extract(b.description)
        logs[b.id] = res
        return res.candidate_refs()

    proposals = run_rules(
        [Bank(b.id, b.tx_date, b.amount, b.description, b.document, b.voucher) for b in banks.values()],
        [Deposit(d.id, d.deposit_date, d.amount, d.document, d.voucher) for d in deps.values()],
        rule_config(settings), extract, excluded=rejected,
    )

    auto = set(settings.auto_match_rules.split(","))
    wanted = {(p.bank_id, p.deposit_id) for p in proposals}
    touched_b = {c.bank_id for c in existing.values()} | {p.bank_id for p in proposals}
    touched_d = {c.deposit_id for c in existing.values()} | {p.deposit_id for p in proposals}
    for pair, c in existing.items():
        if pair not in wanted:
            db.delete(c)
    db.flush()

    counts: Counter = Counter()
    accepted_banks = set()
    for p in proposals:
        status = "AMBIGUOUS" if p.ambiguous else "SUGGESTED"
        auto_ok = (not p.ambiguous) and p.rule in auto and p.rule != "R4"  # AI results are never auto-matched
        if auto_ok:
            status = "MATCHED"
        if p.rule == "R4":
            accepted_banks.add(p.bank_id)
        c = existing.get((p.bank_id, p.deposit_id))
        if c is None:
            c = MatchCandidate(run_id=run.id, bank_id=p.bank_id, deposit_id=p.deposit_id, rule=p.rule,
                               status=status, evidence=p.evidence)
            db.add(c)
        else:
            c.run_id, c.rule, c.status, c.evidence = run.id, p.rule, status, p.evidence
        db.flush()
        if status == "MATCHED":
            db.add(ReconciliationDecision(candidate_id=c.id, action="AUTO_MATCH", actor="system",
                                          note=f"rule {p.rule}, unique and exact"))
            audit.record(db, "system", "auto_match", "candidate", c.id,
                         {"rule": p.rule, "bank_id": p.bank_id, "deposit_id": p.deposit_id, "run_id": run.id})
        counts[status] += 1

    for bank_id, res in logs.items():
        d = res.model_dump(mode="json")
        db.add(InferenceLog(
            request_id=res.request_id, run_id=run.id, bank_id=bank_id, source=res.source, is_mock=res.is_mock,
            model=res.model, hardware_label=res.hardware_label, status=res.status, error=res.error,
            latency_ms=res.latency_ms, attempts=res.attempts, text_sha256=res.text_sha256,
            original_text=res.original_text, extraction=d["extraction"], dropped=res.dropped,
            raw_output=res.raw_output, accepted=bank_id in accepted_banks))

    refresh_statuses(db, touched_b | set(banks), touched_d | set(deps))
    run.stats = {"proposed": sum(counts.values()), **{k: counts.get(k, 0) for k in ("MATCHED", "SUGGESTED", "AMBIGUOUS")},
                 "banks_considered": len(banks), "deposits_considered": len(deps), "inference_calls": len(logs)}
    audit.record(db, actor, "reconcile_run", "batch", run.id, run.stats)
    log.info("reconcile_run", extra={"run_id": run.id, **run.stats})
    return {"run_id": run.id, **run.stats}


def _load_pending(db: Session, candidate_id: int) -> MatchCandidate:
    c = db.scalars(select(MatchCandidate).where(MatchCandidate.id == candidate_id).with_for_update()).first()
    if c is None:
        raise DecisionError(404, "candidate not found")
    if c.status not in PENDING:
        raise DecisionError(409, f"candidate already {c.status}")
    return c


def approve(db: Session, candidate_id: int, actor: str, note: str | None, settings: Settings) -> MatchCandidate:
    c = _load_pending(db, candidate_id)
    if c.status == "AMBIGUOUS" and not (note and note.strip()):
        raise DecisionError(422, "a note is required to resolve an ambiguous candidate")
    b, d = db.get(BankTransaction, c.bank_id), db.get(SystemDeposit, c.deposit_id)
    problem = check_invariants(
        Bank(b.id, b.tx_date, b.amount, b.description, b.document, b.voucher),
        Deposit(d.id, d.deposit_date, d.amount, d.document, d.voucher), c.rule, rule_config(settings))
    if problem:
        raise DecisionError(422, f"deterministic validation failed: {problem}")
    rivals = list(db.scalars(select(MatchCandidate).where(
        (MatchCandidate.bank_id == c.bank_id) | (MatchCandidate.deposit_id == c.deposit_id),
        MatchCandidate.id != c.id)))
    if any(r.status == "MATCHED" for r in rivals):
        raise DecisionError(409, "bank transaction or deposit is already matched")
    c.status = "MATCHED"
    db.flush()  # unique partial indexes are the final guard against concurrent approvals
    superseded = [r for r in rivals if r.status in PENDING]
    for r in superseded:
        db.delete(r)
    db.add(ReconciliationDecision(candidate_id=c.id, action="APPROVE", actor=actor, note=note))
    audit.record(db, actor, "candidate_approved", "candidate", c.id,
                 {"rule": c.rule, "bank_id": c.bank_id, "deposit_id": c.deposit_id, "note": note,
                  "superseded_candidates": [r.id for r in superseded]})
    refresh_statuses(db, {c.bank_id} | {r.bank_id for r in superseded},
                     {c.deposit_id} | {r.deposit_id for r in superseded})
    return c


def reject(db: Session, candidate_id: int, actor: str, note: str | None) -> MatchCandidate:
    c = _load_pending(db, candidate_id)
    c.status = "REJECTED"
    db.add(ReconciliationDecision(candidate_id=c.id, action="REJECT", actor=actor, note=note))
    audit.record(db, actor, "candidate_rejected", "candidate", c.id,
                 {"rule": c.rule, "bank_id": c.bank_id, "deposit_id": c.deposit_id, "note": note})
    refresh_statuses(db, {c.bank_id}, {c.deposit_id})
    return c
