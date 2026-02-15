import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, computed_field


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


# Web scraping request schemas
class WebScrapeRequest(BaseModel):
    """Request to scrape a single URL."""
    url: str = Field(..., description="URL to scrape")


class WebCrawlRequest(BaseModel):
    """Request to crawl a website (multiple pages)."""
    url: str = Field(..., description="Starting URL to crawl")
    max_pages: int = Field(50, ge=1, le=100, description="Maximum pages to crawl")
    max_depth: int = Field(3, ge=1, le=5, description="Maximum depth to follow links")
    path_prefix: Optional[str] = Field(None, description="Only crawl URLs with this path prefix (e.g., '/blog/')")


class WebScrapeResponse(BaseModel):
    """Response for single URL scrape."""
    success: bool
    url: str
    title: str
    content: str
    content_length: int
    error: Optional[str] = None


class WebCrawlResponse(BaseModel):
    """Response for website crawl."""
    success: bool
    start_url: str
    total_pages: int
    successful_pages: int
    failed_pages: int
    knowledge_ids: List[uuid.UUID] = []
    errors: List[str] = []


class KnowledgeResponse(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    content_type: str
    # Use extra_metadata here to match model, but alias to metadata for JSON output
    extra_metadata: Optional[Dict[str, Any]] = Field(default={}, serialization_alias="metadata")
    is_active: bool
    created_at: datetime

    # Source info
    source_type: str = "manual"
    source_url: Optional[str] = None

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
