"""add context guard to channel

Revision ID: 20260215073749
Revises: 0002_add_file_fields_to_knowledge
Create Date: 2025-02-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260215073749'
down_revision = '0002_add_file_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Add context and context_description columns to channels table
    op.add_column('channels', sa.Column('context', sa.String(255), nullable=True))
    op.add_column('channels', sa.Column('context_description', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('channels', 'context_description')
    op.drop_column('channels', 'context')
