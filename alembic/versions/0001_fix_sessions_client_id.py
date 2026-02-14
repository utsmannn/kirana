"""fix sessions client_id nullable

Revision ID: 0001_fix_sessions
Revises: 6865959170f6
Create Date: 2026-02-14

"""
from alembic import op


revision = '0001_fix_sessions'
down_revision = '6865959170f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make client_id nullable in sessions
    op.alter_column('sessions', 'client_id',
        existing_type=None,
        nullable=True
    )


def downgrade() -> None:
    # Make client_id NOT NULL again
    op.alter_column('sessions', 'client_id',
        existing_type=None,
        nullable=False
    )
