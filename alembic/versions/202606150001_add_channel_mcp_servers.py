"""add channel mcp servers

Revision ID: 202606150001
Revises: 254c9993411a
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '202606150001'
down_revision = '254c9993411a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'channel_mcp_servers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('server_url', sa.String(), nullable=False),
        sa.Column('transport', sa.String(length=20), nullable=False, server_default='sse'),
        sa.Column('auth_type', sa.String(length=20), nullable=False, server_default='none'),
        sa.Column('auth_config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_channel_mcp_servers_channel_id'), 'channel_mcp_servers', ['channel_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_channel_mcp_servers_channel_id'), table_name='channel_mcp_servers')
    op.drop_table('channel_mcp_servers')
