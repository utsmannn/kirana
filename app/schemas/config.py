import uuid
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConfigUpdate(BaseModel):
    ai_name: Optional[str] = None
    personality_slug: Optional[str] = None
    thinking_mode: Optional[Literal["normal", "extended"]] = None
    restrict_to_knowledge: Optional[bool] = None
    provider_api_key: Optional[str] = None
    provider_base_url: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = Field(None, ge=1, le=128000)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    tools_enabled: Optional[List[str]] = None

class CustomPersonalityUpdate(BaseModel):
    custom_personality: Optional[str] = None

class PersonalitySimple(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str

    model_config = ConfigDict(from_attributes=True)

class ConfigResponse(BaseModel):
    ai_name: str
    personality: Optional[PersonalitySimple] = None
    custom_personality: Optional[str] = None
    thinking_mode: str
    restrict_to_knowledge: bool
    has_custom_provider: bool = False
    provider_base_url: Optional[str] = None
    model: str
    max_tokens: int
    temperature: float
    tools_enabled: List[str]

    model_config = ConfigDict(from_attributes=True)
