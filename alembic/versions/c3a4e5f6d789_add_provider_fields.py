"""Add provider_api_key and provider_base_url to client_configs

Revision ID: c3a4e5f6d789
Revises: bc21511bb54b
Create Date: 2026-02-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a4e5f6d789'
down_revision: Union[str, None] = 'bc21511bb54b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'client_configs',
        sa.Column('provider_api_key', sa.String(500), nullable=True),
    )
    op.add_column(
        'client_configs',
        sa.Column('provider_base_url', sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('client_configs', 'provider_base_url')
    op.drop_column('client_configs', 'provider_api_key')
