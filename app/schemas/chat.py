import uuid
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    model: str = "default"
    messages: List[ChatMessage] = Field(..., min_length=1)
    stream: Optional[bool] = False
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=128000)
    top_p: Optional[float] = Field(1.0, ge=0.0, le=1.0)
    presence_penalty: Optional[float] = Field(0.0, ge=-2.0, le=2.0)
    frequency_penalty: Optional[float] = Field(0.0, ge=-2.0, le=2.0)
    tools: Optional[Union[str, List[Dict[str, Any]]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = "auto"

    # Kirana extensions
    session_id: Optional[uuid.UUID] = None
    channel_id: Optional[uuid.UUID] = None  # Channel to use for system prompt
    stream_id: Optional[str] = None
    kirana: Optional[Dict[str, Any]] = None

class ChatCompletionResponseChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None

class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionResponseChoice]
    usage: ChatCompletionUsage

    # Kirana extensions
    session: Optional[Dict[str, Any]] = None
