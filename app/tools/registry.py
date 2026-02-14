from typing import Any, Dict, List

from app.tools.base import BaseTool
from app.tools.datetime_tool import DateTimeTool
from app.tools.knowledge_tool import KnowledgeTool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register(DateTimeTool())
        self.register(KnowledgeTool())

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool:
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        return list(self._tools.values())

    def to_openai_tools(self, enabled_tools: List[str] = None) -> List[Dict[str, Any]]:
        return [
            tool.to_openai_tool()
            for name, tool in self._tools.items()
            if enabled_tools is None or name in enabled_tools
        ]


tool_registry = ToolRegistry()