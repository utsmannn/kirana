import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("channels.id"), nullable=True)
    name = Column(String(255), nullable=True)
    extra_metadata = Column("metadata", JSONB, default=lambda: {})
    message_count = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    last_activity = Column(DateTime(timezone=True), default=_utcnow, index=True)

    @property
    def expires_at(self):
        return self.last_activity + timedelta(days=3)

    client = relationship("Client", back_populates="sessions")
    channel = relationship("Channel", lazy="joined")
    conversation_logs = relationship("ConversationLog", back_populates="session", cascade="all, delete-orphan")
