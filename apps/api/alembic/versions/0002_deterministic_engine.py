"""deterministic engine schema (replaces the MVP scoring tables)

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_EFFECTIVE = sa.text("status = 'MATCHED'")


def upgrade() -> None:
    for t in ("audit_log", "engine_configs", "matches", "ledger_entries", "bank_transactions"):
        op.drop_table(t)

    op.create_table(
        "reconciliation_batches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False, index=True),
        sa.Column("filename", sa.String(255)),
        sa.Column("file_hash", sa.String(64)),
        sa.Column("stats", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "file_hash", name="uq_batch_kind_file_hash"),
    )
    for table, datecol in (("bank_transactions", "tx_date"), ("system_deposits", "deposit_date")):
        op.create_table(
            table,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("batch_id", sa.Integer, sa.ForeignKey("reconciliation_batches.id"), nullable=False, index=True),
            sa.Column("external_id", sa.String(64), nullable=False, unique=True),
            sa.Column(datecol, sa.Date, nullable=False, index=True),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("description", sa.String(255), nullable=False),
            sa.Column("document", sa.String(11), nullable=False),
            sa.Column("voucher", sa.String(40), nullable=False),
            sa.Column("row_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, index=True),
        )
    op.create_table(
        "match_candidates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("reconciliation_batches.id"), nullable=False, index=True),
        sa.Column("bank_id", sa.Integer, sa.ForeignKey("bank_transactions.id"), nullable=False, index=True),
        sa.Column("deposit_id", sa.Integer, sa.ForeignKey("system_deposits.id"), nullable=False, index=True),
        sa.Column("rule", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, index=True),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("bank_id", "deposit_id", name="uq_candidate_pair"),
    )
    op.create_index("uq_effective_bank", "match_candidates", ["bank_id"], unique=True,
                    sqlite_where=_EFFECTIVE, postgresql_where=_EFFECTIVE)
    op.create_index("uq_effective_deposit", "match_candidates", ["deposit_id"], unique=True,
                    sqlite_where=_EFFECTIVE, postgresql_where=_EFFECTIVE)
    op.create_table(
        "reconciliation_decisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("match_candidates.id"), nullable=False, index=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("seq", sa.Integer, nullable=False, unique=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False, index=True),
        sa.Column("entity", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.Integer),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
    )
    op.create_table(
        "inference_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("reconciliation_batches.id"), index=True),
        sa.Column("bank_id", sa.Integer, sa.ForeignKey("bank_transactions.id"), index=True),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("is_mock", sa.Boolean, nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("hardware_label", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.String(128)),
        sa.Column("latency_ms", sa.Float, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("original_text", sa.Text, nullable=False),
        sa.Column("extraction", sa.JSON, nullable=False),
        sa.Column("dropped", sa.JSON, nullable=False),
        sa.Column("raw_output", sa.Text),
        sa.Column("accepted", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    raise NotImplementedError("0002 replaces the MVP schema destructively; restore from backup instead")
