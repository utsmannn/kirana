import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBase(BaseModel):
    title: str
    content: str
    content_type: Optional[str] = "text"
    metadata: Optional[Dict[str, Any]] = Field(default={})


class KnowledgeCreate(KnowledgeBase):
    pass


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    content_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class KnowledgeResponse(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    content_type: str
    # Use extra_metadata here to match model, but alias to metadata for JSON output
    extra_metadata: Optional[Dict[str, Any]] = Field(default={}, serialization_alias="metadata")
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeListResponse(BaseModel):
    items: List[KnowledgeResponse]
    total: int
    page: int
    limit: int
    pages: int
