import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    api_key = Column(String(64), unique=True, nullable=False, index=True)
    api_key_prefix = Column(String(8), nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    config = relationship("ClientConfig", back_populates="client", uselist=False, cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="client", cascade="all, delete-orphan")
    knowledge = relationship("Knowledge", back_populates="client", cascade="all, delete-orphan")
    conversation_logs = relationship("ConversationLog", back_populates="client", cascade="all, delete-orphan")
    usage_logs = relationship("UsageLog", back_populates="client", cascade="all, delete-orphan")
