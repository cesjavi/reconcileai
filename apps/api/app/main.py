import logging
import statistics
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from inference import build_client
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from . import audit, evolus_routes, importing, matching, models
from .config import Settings, get_settings
from .db import Base, get_engine, get_session
from .logging_conf import setup_logging
from .models import (AuditEvent, BankTransaction, InferenceLog, MatchCandidate, ReconciliationBatch,
                     ReconciliationDecision, SystemDeposit)

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Alembic owns the schema in Postgres. For SQLite (dev/tests) create tables directly.
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(get_engine())
    yield


app = FastAPI(title="ReconcileAI API", version="0.2.0", lifespan=lifespan)
app.include_router(evolus_routes.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log.info("request", extra={"method": request.method, "path": request.url.path, "status": response.status_code,
                               "ms": round((time.perf_counter() - start) * 1000, 1)})
    return response


@app.exception_handler(importing.ImportError_)
async def import_error(_: Request, exc: importing.ImportError_):
    return JSONResponse({"detail": {"message": exc.message, "errors": exc.errors}}, status_code=exc.status)


@app.exception_handler(matching.DecisionError)
async def decision_error(_: Request, exc: matching.DecisionError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError):
    log.warning("integrity_conflict")
    return JSONResponse({"detail": "conflict with concurrent change; retry"}, status_code=409)


@app.exception_handler(OperationalError)
async def operational_error(_: Request, exc: OperationalError):
    log.warning("db_operational_error")
    return JSONResponse({"detail": "database busy; retry"}, status_code=409)


def actor_header(x_actor: str = Header(default="", max_length=64)) -> str:
    if not x_actor.strip():
        raise HTTPException(400, "X-Actor header required: every change must be attributable")
    return x_actor.strip()


def cfg() -> Settings:
    return get_settings()


@lru_cache
def _extractor():
    return build_client(get_settings().inference_settings())


def get_extractor():
    try:
        return _extractor()
    except ValueError as exc:  # misconfigured vllm: fail loudly, never degrade to mock silently
        raise HTTPException(503, f"inference misconfigured: {exc}") from exc


# ---------- health ----------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(db: Session = Depends(get_session)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "database unavailable") from exc
    return {"status": "ready"}


# ---------- imports ----------
def _do_import(db: Session, kind: str, name: str, raw: bytes, actor: str) -> dict:
    try:
        result = importing.import_file(db, kind, name, raw, actor)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()  # a concurrent identical upload won the race: report it as the duplicate it is
        import hashlib
        existing = db.scalars(select(ReconciliationBatch).where(
            ReconciliationBatch.kind == kind,
            ReconciliationBatch.file_hash == hashlib.sha256(raw).hexdigest())).first()
        if existing is None:
            raise
        return {"batch_id": existing.id, "duplicate_file": True, **existing.stats}


@app.post("/imports/{kind}")
async def import_csv(kind: Literal["bank", "deposits"], file: UploadFile = File(...),
                     db: Session = Depends(get_session), actor: str = Depends(actor_header)):
    raw = await file.read(importing.MAX_BYTES + 1)
    return _do_import(db, "BANK" if kind == "bank" else "DEPOSIT", file.filename or "upload.csv", raw, actor)


@app.post("/demo/seed")
def seed_demo(db: Session = Depends(get_session), actor: str = Depends(actor_header), s: Settings = Depends(cfg)):
    """Load the synthetic demo dataset. Idempotent: re-seeding returns the original batches."""
    demo = Path(s.demo_dir)
    if not (demo / "bank.csv").exists():
        raise HTTPException(404, "demo dataset not found")
    return {"bank": _do_import(db, "BANK", "bank.csv", (demo / "bank.csv").read_bytes(), actor),
            "deposits": _do_import(db, "DEPOSIT", "deposits.csv", (demo / "deposits.csv").read_bytes(), actor)}


# ---------- reconciliation ----------
@app.post("/reconcile/run")
def run_reconciliation(db: Session = Depends(get_session), actor: str = Depends(actor_header),
                       s: Settings = Depends(cfg), extractor=Depends(get_extractor)):
    result = matching.run_reconciliation(db, actor, s, extractor if s.ai_extraction_enabled else None)
    db.commit()
    return result


def _bank_out(b: BankTransaction) -> dict:
    return {"id": b.id, "external_id": b.external_id, "date": b.tx_date, "amount": str(b.amount),
            "description": b.description, "document": b.document, "voucher": b.voucher, "status": b.status}


def _dep_out(d: SystemDeposit) -> dict:
    return {"id": d.id, "external_id": d.external_id, "date": d.deposit_date, "amount": str(d.amount),
            "description": d.description, "document": d.document, "voucher": d.voucher, "status": d.status}


def _cand_out(c: MatchCandidate, b: BankTransaction, d: SystemDeposit) -> dict:
    return {"id": c.id, "rule": c.rule, "status": c.status, "evidence": c.evidence, "run_id": c.run_id,
            "bank": _bank_out(b), "deposit": _dep_out(d)}


@app.get("/candidates")
def list_candidates(status: Literal["SUGGESTED", "AMBIGUOUS", "MATCHED", "REJECTED"] | None = None,
                    bank_id: int | None = None, limit: int = 200, offset: int = 0,
                    db: Session = Depends(get_session)):
    q = (select(MatchCandidate, BankTransaction, SystemDeposit)
         .join(BankTransaction, MatchCandidate.bank_id == BankTransaction.id)
         .join(SystemDeposit, MatchCandidate.deposit_id == SystemDeposit.id)
         .order_by(MatchCandidate.id).limit(min(limit, 500)).offset(max(offset, 0)))
    if status:
        q = q.where(MatchCandidate.status == status)
    if bank_id:
        q = q.where(MatchCandidate.bank_id == bank_id)
    return [_cand_out(*row) for row in db.execute(q)]


class Decision(BaseModel):
    note: str | None = None


@app.post("/candidates/{candidate_id}/approve")
def approve(candidate_id: int, body: Decision, db: Session = Depends(get_session),
            actor: str = Depends(actor_header), s: Settings = Depends(cfg)):
    c = matching.approve(db, candidate_id, actor, body.note, s)
    db.commit()
    return {"id": c.id, "status": c.status}


@app.post("/candidates/{candidate_id}/reject")
def reject(candidate_id: int, body: Decision, db: Session = Depends(get_session),
           actor: str = Depends(actor_header)):
    c = matching.reject(db, candidate_id, actor, body.note)
    db.commit()
    return {"id": c.id, "status": c.status}


def _inf_out(i: InferenceLog) -> dict:
    return {"request_id": i.request_id, "source": i.source, "is_mock": i.is_mock, "model": i.model,
            "hardware_label": i.hardware_label, "status": i.status, "error": i.error, "latency_ms": i.latency_ms,
            "attempts": i.attempts, "original_text": i.original_text, "extraction": i.extraction,
            "dropped": i.dropped, "accepted": i.accepted, "created_at": i.created_at, "bank_id": i.bank_id}


@app.get("/bank-transactions")
def list_bank(status: str | None = None, limit: int = 200, offset: int = 0, db: Session = Depends(get_session)):
    q = select(BankTransaction).order_by(BankTransaction.id).limit(min(limit, 500)).offset(max(offset, 0))
    if status:
        q = q.where(BankTransaction.status == status.upper())
    return [_bank_out(b) for b in db.scalars(q)]


@app.get("/bank-transactions/{bank_id}")
def bank_detail(bank_id: int, db: Session = Depends(get_session)):
    b = db.get(BankTransaction, bank_id)
    if not b:
        raise HTTPException(404, "bank transaction not found")
    rows = db.execute(select(MatchCandidate, SystemDeposit).join(
        SystemDeposit, MatchCandidate.deposit_id == SystemDeposit.id).where(MatchCandidate.bank_id == bank_id))
    cands = [_cand_out(c, b, d) for c, d in rows]
    decisions = db.scalars(select(ReconciliationDecision).where(
        ReconciliationDecision.candidate_id.in_([c["id"] for c in cands] or [0])).order_by(ReconciliationDecision.id))
    logs = db.scalars(select(InferenceLog).where(InferenceLog.bank_id == bank_id).order_by(InferenceLog.id))
    return {"bank": _bank_out(b), "candidates": cands,
            "decisions": [{"candidate_id": x.candidate_id, "action": x.action, "actor": x.actor, "note": x.note,
                           "created_at": x.created_at} for x in decisions],
            "inference": [_inf_out(i) for i in logs]}


@app.get("/deposits")
def list_deposits(status: str | None = None, limit: int = 200, offset: int = 0, db: Session = Depends(get_session)):
    q = select(SystemDeposit).order_by(SystemDeposit.id).limit(min(limit, 500)).offset(max(offset, 0))
    if status:
        q = q.where(SystemDeposit.status == status.upper())
    return [_dep_out(d) for d in db.scalars(q)]


@app.get("/summary")
def summary(db: Session = Depends(get_session)):
    def by_status(model):
        counts = dict(db.execute(select(model.status, func.count()).group_by(model.status)).all())
        return {k: counts.get(k, 0) for k in models.STATUSES}
    bank, dep = by_status(BankTransaction), by_status(SystemDeposit)
    total = sum(bank.values())
    return {"bank": bank, "deposits": dep, "bank_total": total, "deposits_total": sum(dep.values()),
            "match_rate": round(bank["MATCHED"] / total, 4) if total else 0.0,
            "review_queue": db.scalar(select(func.count()).select_from(MatchCandidate).where(
                MatchCandidate.status.in_(matching.PENDING)))}


@app.get("/batches")
def list_batches(db: Session = Depends(get_session)):
    rows = db.scalars(select(ReconciliationBatch).order_by(ReconciliationBatch.id.desc()).limit(100))
    return [{"id": b.id, "kind": b.kind, "filename": b.filename, "stats": b.stats, "created_by": b.created_by,
             "created_at": b.created_at} for b in rows]


# ---------- inference ----------
@app.get("/inference/health")
def inference_health(ex=Depends(get_extractor)):
    return ex.health()


@app.get("/inference/logs")
def inference_logs(limit: int = 50, db: Session = Depends(get_session)):
    return [_inf_out(i) for i in db.scalars(select(InferenceLog).order_by(InferenceLog.id.desc()).limit(min(limit, 200)))]


@app.get("/inference/metrics")
def inference_metrics(db: Session = Depends(get_session)):
    """Aggregates over recorded calls only. `real` excludes mock calls; nothing here is simulated."""
    logs = list(db.scalars(select(InferenceLog)))
    real, mock = [i for i in logs if not i.is_mock], [i for i in logs if i.is_mock]

    def pct(vals, p):
        vals = sorted(vals)
        return round(vals[min(len(vals) - 1, int(p * len(vals)))], 1) if vals else None

    lat = [i.latency_ms for i in real if i.status != "error"]
    return {
        "has_real_inference": bool(real), "mock_calls": len(mock), "real_calls": len(real),
        "real_ok": sum(i.status == "ok" for i in real), "real_invalid_output": sum(i.status == "invalid_output" for i in real),
        "real_errors": sum(i.status == "error" for i in real), "real_retried": sum(i.attempts > 1 for i in real),
        "real_latency_ms": {"avg": round(statistics.fmean(lat), 1) if lat else None, "p50": pct(lat, 0.5),
                            "p95": pct(lat, 0.95), "samples": len(lat)},
        "accepted_by_engine": sum(i.accepted for i in logs), "items_dropped_by_validation": sum(len(i.dropped or []) for i in logs),
        "models": sorted({i.model for i in real}),
    }


# ---------- audit ----------
@app.get("/audit")
def audit_log(limit: int = 100, db: Session = Depends(get_session)):
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(min(limit, 500)))
    return [{"seq": r.seq, "ts": r.ts, "actor": r.actor, "action": r.action, "entity": r.entity,
             "entity_id": r.entity_id, "payload": r.payload, "hash": r.hash} for r in rows]


@app.get("/audit/verify")
def audit_verify(db: Session = Depends(get_session)):
    return audit.verify_chain(db)
