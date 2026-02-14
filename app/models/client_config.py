import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class ClientConfig(Base):
    __tablename__ = "client_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), unique=True, nullable=False)
    ai_name = Column(String(100), default="Kirana")
    personality_id = Column(UUID(as_uuid=True), ForeignKey("personalities.id"), nullable=True)
    custom_personality = Column(String, nullable=True)
    thinking_mode = Column(String(20), default="normal")
    restrict_to_knowledge = Column(Boolean, default=False)
    provider_api_key = Column(String(500), nullable=True)
    provider_base_url = Column(String(500), nullable=True)
    model = Column(String(100), default="gpt-4o-mini")
    max_tokens = Column(Integer, default=4096)
    temperature = Column(Float, default=0.7)
    tools_enabled = Column(JSONB, default=lambda: ["datetime", "search", "knowledge"])
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    client = relationship("Client", back_populates="config")
    personality = relationship("Personality")
