"""where a folder scan found each file

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("uploads", sa.Column("source_path", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("uploads", "source_path")
