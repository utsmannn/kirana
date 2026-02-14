import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Channel(Base):
    __tablename__ = "channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("provider_credentials.id"), nullable=False)
    system_prompt = Column(String, nullable=True)
    personality_name = Column(String(100), nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Embed configuration
    embed_enabled = Column(Boolean, default=False, server_default="false")
    embed_token = Column(String(64), nullable=True, index=True)
    embed_config = Column(JSONB, default={}, server_default="{}")  # {"save_history": true, "public": true}
