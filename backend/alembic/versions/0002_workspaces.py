"""per-borrower workspaces for the credit memo, Phase 2 and Phase 3

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("borrower_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["borrower_id"], ["borrowers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("borrower_id", "key"),
    )
    op.create_index(op.f("ix_workspaces_borrower_id"), "workspaces", ["borrower_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workspaces_borrower_id"), table_name="workspaces")
    op.drop_table("workspaces")
