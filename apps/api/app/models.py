from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text,
                        UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

STATUSES = ("MATCHED", "SUGGESTED", "AMBIGUOUS", "UNMATCHED", "REJECTED")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReconciliationBatch(Base):
    """An import (BANK / DEPOSIT) or a reconciliation RUN."""

    __tablename__ = "reconciliation_batches"
    __table_args__ = (UniqueConstraint("kind", "file_hash", name="uq_batch_kind_file_hash"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # BANK | DEPOSIT | RUN
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_batches.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    tx_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    description: Mapped[str] = mapped_column(String(255), default="")
    document: Mapped[str] = mapped_column(String(11), default="")  # CUIT/DNI digits
    voucher: Mapped[str] = mapped_column(String(40), default="")  # normalised comprobante
    row_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="UNMATCHED", index=True)


class SystemDeposit(Base):
    __tablename__ = "system_deposits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_batches.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    deposit_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    description: Mapped[str] = mapped_column(String(255), default="")
    document: Mapped[str] = mapped_column(String(11), default="")
    voucher: Mapped[str] = mapped_column(String(40), default="")
    row_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="UNMATCHED", index=True)


class MatchCandidate(Base):
    __tablename__ = "match_candidates"
    __table_args__ = (
        UniqueConstraint("bank_id", "deposit_id", name="uq_candidate_pair"),
        # At most one effective link per bank transaction and per deposit, enforced by the database.
        Index("uq_effective_bank", "bank_id", unique=True,
              sqlite_where=text("status = 'MATCHED'"), postgresql_where=text("status = 'MATCHED'")),
        Index("uq_effective_deposit", "deposit_id", unique=True,
              sqlite_where=text("status = 'MATCHED'"), postgresql_where=text("status = 'MATCHED'")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_batches.id"), index=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("bank_transactions.id"), index=True)
    deposit_id: Mapped[int] = mapped_column(ForeignKey("system_deposits.id"), index=True)
    rule: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), index=True)  # SUGGESTED|AMBIGUOUS|MATCHED|REJECTED
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ReconciliationDecision(Base):
    """Immutable record of every state-changing decision (auto, human)."""

    __tablename__ = "reconciliation_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("match_candidates.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))  # AUTO_MATCH | APPROVE | REJECT
    actor: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """Append-only and hash-chained. `seq` is unique, so concurrent writers cannot fork the chain."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, unique=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64))


class InferenceLog(Base):
    """One row per inference call (real or mock). Immutable."""

    __tablename__ = "inference_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("reconciliation_batches.id"), nullable=True, index=True)
    bank_id: Mapped[int | None] = mapped_column(ForeignKey("bank_transactions.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(8))  # mock | vllm
    is_mock: Mapped[bool] = mapped_column(Boolean)
    model: Mapped[str] = mapped_column(String(128))
    hardware_label: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16))  # ok | invalid_output | error
    error: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    text_sha256: Mapped[str] = mapped_column(String(64))
    original_text: Mapped[str] = mapped_column(Text)  # evidence
    extraction: Mapped[dict] = mapped_column(JSON, default=dict)
    dropped: Mapped[list] = mapped_column(JSON, default=list)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)  # produced a deterministic-verified candidate
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvolusExecution(Base):
    """Every call made to Evolus (workflow run or AI tool) with remote ids, status and errors."""

    __tablename__ = "evolus_executions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    kind: Mapped[str] = mapped_column(String(16))  # workflow | ai_tool
    mode: Mapped[str] = mapped_column(String(8))  # live | mock  (mock = SIMULATED, never real Evolus)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("match_candidates.id"), nullable=True, index=True)
    remote_execution_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16))  # Pending|Running|Completed|Failed|Error
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    advisory_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    credits_consumed: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentRecommendation(Base):
    """Advisory output of the external agent. Immutable; it can never change a candidate's state."""

    __tablename__ = "agent_recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("match_candidates.id"), index=True)
    recommendation: Mapped[str] = mapped_column(String(16))  # APPROVE | REJECT | NEEDS_HUMAN
    rationale: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="agent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
