import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Knowledge(Base):
    __tablename__ = "knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)  # Extracted text content
    content_type = Column(String(50), default="text")  # text, image, pdf, docx, xlsx, etc.

    # File metadata (for uploaded files)
    file_path = Column(String(500), nullable=True)  # Path to stored file
    file_name = Column(String(255), nullable=True)  # Original filename
    file_size = Column(Integer, nullable=True)  # File size in bytes
    mime_type = Column(String(100), nullable=True)  # MIME type

    extra_metadata = Column("metadata", JSONB, default=lambda: {})
    embedding = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    client = relationship("Client", back_populates="knowledge")
