"""add channel id to knowledge

Revision ID: 202606150003
Revises: 202606150002
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '202606150003'
down_revision = '202606150002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'knowledge',
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_knowledge_channel_id_channels',
        'knowledge',
        'channels',
        ['channel_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_knowledge_channel_id', 'knowledge', ['channel_id'])

    op.add_column(
        'knowledge_chunks',
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_knowledge_chunks_channel_id_channels',
        'knowledge_chunks',
        'channels',
        ['channel_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_knowledge_chunks_channel_id', 'knowledge_chunks', ['channel_id'])

    op.execute(
        """
        UPDATE knowledge
        SET channel_id = (
            SELECT id
            FROM channels
            ORDER BY is_default DESC, created_at ASC
            LIMIT 1
        )
        WHERE channel_id IS NULL
          AND EXISTS (SELECT 1 FROM channels)
        """
    )
    op.execute(
        """
        UPDATE knowledge_chunks AS kc
        SET channel_id = k.channel_id
        FROM knowledge AS k
        WHERE kc.knowledge_id = k.id
          AND kc.channel_id IS NULL
        """
    )


def downgrade():
    op.drop_index('ix_knowledge_chunks_channel_id', table_name='knowledge_chunks')
    op.drop_constraint('fk_knowledge_chunks_channel_id_channels', 'knowledge_chunks', type_='foreignkey')
    op.drop_column('knowledge_chunks', 'channel_id')

    op.drop_index('ix_knowledge_channel_id', table_name='knowledge')
    op.drop_constraint('fk_knowledge_channel_id_channels', 'knowledge', type_='foreignkey')
    op.drop_column('knowledge', 'channel_id')
