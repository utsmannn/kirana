"""add knowledge processing_status

Revision ID: 254c9993411a
Revises: 202606120001
Create Date: 2026-06-13 13:08:22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "254c9993411a"
down_revision: str | None = "202606120001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge",
        sa.Column(
            "processing_status",
            sa.String(20),
            nullable=False,
            server_default="ready",
            comment="ready | processing | failed",
        ),
    )
    op.create_index(
        "ix_knowledge_processing_status",
        "knowledge",
        ["processing_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_processing_status", table_name="knowledge")
    op.drop_column("knowledge", "processing_status")
