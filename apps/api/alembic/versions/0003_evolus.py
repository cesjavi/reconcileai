"""evolus executions and agent recommendations

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evolus_executions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("match_candidates.id"), index=True),
        sa.Column("remote_execution_id", sa.String(128)),
        sa.Column("trace_id", sa.String(128)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.String(255)),
        sa.Column("advisory_text", sa.Text),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("credits_consumed", sa.Float),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_recommendations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("match_candidates.id"), nullable=False, index=True),
        sa.Column("recommendation", sa.String(16), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_recommendations")
    op.drop_table("evolus_executions")
