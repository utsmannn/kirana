"""Add sessions.mode (ai | human)

Revision ID: f6a7b8c9d0e1
Revises: 202606150003
Create Date: 2026-08-18 03:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "202606150003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("mode", sa.String(20), nullable=False, server_default="ai"),
    )


def downgrade() -> None:
    op.drop_column("sessions", "mode")
