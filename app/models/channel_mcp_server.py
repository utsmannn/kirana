import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class ChannelMcpServer(Base):
    __tablename__ = "channel_mcp_servers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    server_url = Column(String, nullable=True)
    transport = Column(String(20), nullable=False, default="sse")
    auth_type = Column(String(20), nullable=False, default="none")
    auth_config = Column(JSONB, nullable=False, default=dict, server_default="{}")
    server_config = Column(JSONB, nullable=False, default=dict, server_default="{}")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
