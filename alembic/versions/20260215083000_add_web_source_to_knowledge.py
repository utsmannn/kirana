"""add web source to knowledge

Revision ID: 20260215083000
Revises: 20260215073749
Create Date: 2026-02-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260215083000'
down_revision = '20260215073749'
branch_labels = None
depends_on = None


def upgrade():
    # Add source_type and source_url columns to knowledge table
    op.add_column('knowledge', sa.Column('source_type', sa.String(20), nullable=True, server_default='manual'))
    op.add_column('knowledge', sa.Column('source_url', sa.String(1000), nullable=True))

    # Update existing records: those with file_path are 'file' type
    op.execute("UPDATE knowledge SET source_type = 'file' WHERE file_path IS NOT NULL")


def downgrade():
    op.drop_column('knowledge', 'source_url')
    op.drop_column('knowledge', 'source_type')
