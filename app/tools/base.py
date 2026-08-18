from abc import ABC, abstractmethod
from contextvars import ContextVar
from typing import Any, Dict, Optional

_tool_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "kirana_tool_context",
    default=None,
)


class BaseTool(ABC):
    """Base class for all tools.

    Attributes:
        internal: If True, this tool is for internal system use only and should
                  not be exposed to users in system prompts or tool lists.
                  The AI can still use it but won't advertise it to users.
    """

    # Default: tool is user-facing (not internal)
    internal: bool = False

    # Per-request context injected by ChatService before execution
    # (e.g. {"session_id": ..., "channel_id": ...}). ContextVar keeps
    # singleton tool instances isolated across concurrent request tasks.
    @property
    def context(self) -> Dict[str, Any]:
        return _tool_context.get() or {}

    @context.setter
    def context(self, value: Dict[str, Any]) -> None:
        _tool_context.set(value)

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        pass

    def to_openai_tool(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
