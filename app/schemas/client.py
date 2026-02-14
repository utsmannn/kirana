import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class ClientBase(BaseModel):
    name: str
    email: EmailStr

class ClientCreate(ClientBase):
    pass

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None

class ClientConfigSchema(BaseModel):
    ai_name: str
    personality: Optional[str] = None
    thinking_mode: str
    model: str
    tools_enabled: List[str]

    model_config = ConfigDict(from_attributes=True)

class ClientResponse(ClientBase):
    id: uuid.UUID
    api_key_prefix: str
    is_active: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ClientRegisterResponse(ClientResponse):
    api_key: str
    config: ClientConfigSchema

class APIKeyResponse(BaseModel):
    api_key: str
    api_key_prefix: str
    message: str
