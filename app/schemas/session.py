import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SessionBase(BaseModel):
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default={}, alias="metadata")

    model_config = ConfigDict(populate_by_name=True)


class SessionCreate(SessionBase):
    channel_id: Optional[uuid.UUID] = None


class SessionUpdate(SessionBase):
    is_active: Optional[bool] = None


class SessionResponse(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None
    # Use extra_metadata to match model, alias to metadata for JSON output
    extra_metadata: Optional[Dict[str, Any]] = Field(default={}, serialization_alias="metadata")
    message_count: int
    total_tokens: int
    is_active: bool
    created_at: datetime
    last_activity: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SessionListResponse(BaseModel):
    items: List[SessionResponse]
    total: int
    page: int
    limit: int
    pages: int


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionMessagesResponse(BaseModel):
    session_id: uuid.UUID
    messages: List[MessageResponse]
    total: int
    page: int
    limit: int