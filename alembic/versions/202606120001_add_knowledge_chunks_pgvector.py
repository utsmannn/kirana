"""add knowledge chunks pgvector

Revision ID: 202606120001
Revises: 20260215083000
Create Date: 2026-06-12

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '202606120001'
down_revision = '20260215083000'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    op.create_table(
        'knowledge_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('knowledge_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('client_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(length=50), nullable=True),
        sa.Column('source_type', sa.String(length=20), nullable=True),
        sa.Column('source_url', sa.String(length=1000), nullable=True),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id']),
        sa.ForeignKeyConstraint(['knowledge_id'], ['knowledge.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_knowledge_chunks_client_id'), 'knowledge_chunks', ['client_id'], unique=False)
    op.create_index(op.f('ix_knowledge_chunks_knowledge_id'), 'knowledge_chunks', ['knowledge_id'], unique=False)
    op.create_index(
        'ix_knowledge_chunks_knowledge_chunk_index',
        'knowledge_chunks',
        ['knowledge_id', 'chunk_index'],
        unique=False,
    )
    op.execute(
        'CREATE INDEX ix_knowledge_chunks_embedding_hnsw '
        'ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)'
    )


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw')
    op.drop_index('ix_knowledge_chunks_knowledge_chunk_index', table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_knowledge_id'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_client_id'), table_name='knowledge_chunks')
    op.drop_table('knowledge_chunks')
