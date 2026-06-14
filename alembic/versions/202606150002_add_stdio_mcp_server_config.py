"""add stdio mcp server config

Revision ID: 202606150002
Revises: 202606150001
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '202606150002'
down_revision = '202606150001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'channel_mcp_servers',
        sa.Column('server_config', postgresql.JSONB(), nullable=False, server_default='{}'),
    )
    op.alter_column(
        'channel_mcp_servers',
        'server_url',
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade():
    op.execute("DELETE FROM channel_mcp_servers WHERE transport = 'stdio'")
    op.alter_column(
        'channel_mcp_servers',
        'server_url',
        existing_type=sa.String(),
        nullable=False,
    )
    op.drop_column('channel_mcp_servers', 'server_config')
