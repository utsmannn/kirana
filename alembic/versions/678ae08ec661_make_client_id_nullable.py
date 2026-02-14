"""make_client_id_nullable

Revision ID: 678ae08ec661
Revises: e5f6a7b8c9d0
Create Date: 2026-02-12 17:57:01.209034

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '678ae08ec661'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make client_id nullable in conversation_logs
    op.alter_column('conversation_logs', 'client_id',
                    existing_type=sa.UUID(),
                    nullable=True)

    # Make client_id nullable in knowledge
    op.alter_column('knowledge', 'client_id',
                    existing_type=sa.UUID(),
                    nullable=True)

    # Fix timestamp types in conversation_logs
    op.alter_column('conversation_logs', 'created_at',
                    existing_type=sa.TIMESTAMP(),
                    type_=sa.TIMESTAMP(timezone=True),
                    existing_nullable=True)

    # Fix timestamp types in knowledge
    op.alter_column('knowledge', 'created_at',
                    existing_type=sa.TIMESTAMP(),
                    type_=sa.TIMESTAMP(timezone=True),
                    existing_nullable=True)
    op.alter_column('knowledge', 'updated_at',
                    existing_type=sa.TIMESTAMP(),
                    type_=sa.TIMESTAMP(timezone=True),
                    existing_nullable=True)


def downgrade() -> None:
    # Revert timestamp types in knowledge
    op.alter_column('knowledge', 'updated_at',
                    existing_type=sa.TIMESTAMP(timezone=True),
                    type_=sa.TIMESTAMP(),
                    existing_nullable=True)
    op.alter_column('knowledge', 'created_at',
                    existing_type=sa.TIMESTAMP(timezone=True),
                    type_=sa.TIMESTAMP(),
                    existing_nullable=True)

    # Revert timestamp types in conversation_logs
    op.alter_column('conversation_logs', 'created_at',
                    existing_type=sa.TIMESTAMP(timezone=True),
                    type_=sa.TIMESTAMP(),
                    existing_nullable=True)

    # Make client_id NOT NULL again in knowledge
    op.alter_column('knowledge', 'client_id',
                    existing_type=sa.UUID(),
                    nullable=False)

    # Make client_id NOT NULL again in conversation_logs
    op.alter_column('conversation_logs', 'client_id',
                    existing_type=sa.UUID(),
                    nullable=False)
