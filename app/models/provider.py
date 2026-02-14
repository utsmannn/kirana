import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    api_key = Column(String, nullable=False)
    base_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=False)
    is_default = Column(Boolean, default=False)  # The .env default, cannot delete
    priority_order = Column(Integer, default=0)  # For fallback ordering
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
