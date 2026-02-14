import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict


class PersonalityBase(BaseModel):
    name: str
    slug: str
    description: str
    system_prompt: str
    is_template: bool = True

class PersonalityResponse(PersonalityBase):
    id: uuid.UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class PersonalityListResponse(BaseModel):
    templates: List[PersonalityResponse]
