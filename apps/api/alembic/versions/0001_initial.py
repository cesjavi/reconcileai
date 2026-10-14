"""initial schema

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tx_date", sa.Date, nullable=False, index=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("reference", sa.String(64), nullable=False, server_default=""),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entry_date", sa.Date, nullable=False, index=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("reference", sa.String(64), nullable=False, server_default=""),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("bank_id", sa.Integer, sa.ForeignKey("bank_transactions.id"), nullable=False, index=True),
        sa.Column("ledger_id", sa.Integer, sa.ForeignKey("ledger_entries.id"), nullable=False, index=True),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("features", sa.JSON, nullable=False),
        sa.Column("explanation", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
        sa.Column("decided_by", sa.String(64)),
        sa.Column("decision_note", sa.Text),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "engine_configs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("weights", sa.JSON, nullable=False),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False, index=True),
        sa.Column("entity", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.Integer),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("hash", sa.String(64), nullable=False),
    )


def downgrade() -> None:
    for t in ("audit_log", "engine_configs", "matches", "ledger_entries", "bank_transactions"):
        op.drop_table(t)
