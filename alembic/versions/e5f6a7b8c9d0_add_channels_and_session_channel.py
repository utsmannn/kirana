"""Add channels table and session channel_id

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-12 15:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create channels table
    op.create_table('channels',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('provider_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('system_prompt', sa.String(), nullable=True),
        sa.Column('personality_name', sa.String(length=100), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['provider_id'], ['provider_credentials.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Add channel_id to sessions
    op.add_column('sessions', sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(None, 'sessions', 'channels', ['channel_id'], ['id'])

    # Remove personality fields from provider_credentials
    op.drop_column('provider_credentials', 'personality_slug')
    op.drop_column('provider_credentials', 'system_prompt')


def downgrade() -> None:
    # Add personality fields back to provider_credentials
    op.add_column('provider_credentials', sa.Column('system_prompt', sa.String(), nullable=True))
    op.add_column('provider_credentials', sa.Column('personality_slug', sa.String(length=100), nullable=True))

    # Remove channel_id from sessions
    op.drop_constraint(None, 'sessions', type_='foreignkey')
    op.drop_column('sessions', 'channel_id')

    # Drop channels table
    op.drop_table('channels')
