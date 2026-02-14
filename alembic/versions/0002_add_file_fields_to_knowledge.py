"""add file fields to knowledge

Revision ID: 0002_add_file_fields
Revises: 0001_fix_sessions
Create Date: 2026-02-14

"""
from alembic import op
import sqlalchemy as sa


revision = '0002_add_file_fields'
down_revision = '0001_fix_sessions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add file metadata columns to knowledge table
    op.add_column('knowledge', sa.Column('file_path', sa.String(500), nullable=True))
    op.add_column('knowledge', sa.Column('file_name', sa.String(255), nullable=True))
    op.add_column('knowledge', sa.Column('file_size', sa.Integer(), nullable=True))
    op.add_column('knowledge', sa.Column('mime_type', sa.String(100), nullable=True))


def downgrade() -> None:
    # Remove file metadata columns
    op.drop_column('knowledge', 'mime_type')
    op.drop_column('knowledge', 'file_size')
    op.drop_column('knowledge', 'file_name')
    op.drop_column('knowledge', 'file_path')
