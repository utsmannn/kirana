import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field


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

    # File metadata (only present for uploaded files)
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None

    @computed_field
    @property
    def has_file(self) -> bool:
        """Compute has_file based on file_path presence."""
        return bool(self.file_path)

    model_config = ConfigDict(from_attributes=True)


class KnowledgeListResponse(BaseModel):
    items: List[KnowledgeResponse]
    total: int
    page: int
    limit: int
    pages: int
