from typing import Any, Dict, List

from app.config import settings
from app.tools.base import BaseTool
from app.tools.datetime_tool import DateTimeTool
from app.tools.image_analyzer_tool import ImageAnalyzerTool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register(DateTimeTool())
        self.register(ImageAnalyzerTool())

        # Telegram human-agent bridge (optional — only when configured)
        if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
            from app.tools.telegram_tools import EscalateToHumanTool, ReportToStaffTool

            self.register(EscalateToHumanTool())
            self.register(ReportToStaffTool())

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool:
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_user_tools(self) -> List[BaseTool]:
        """List only user-facing tools (excludes internal tools)."""
        return [tool for tool in self._tools.values() if not tool.internal]

    def to_openai_tools(self, enabled_tools: List[str] = None, include_internal: bool = True) -> List[Dict[str, Any]]:
        """Convert tools to OpenAI format.

        Args:
            enabled_tools: Optional list of tool names to include. If None, includes all.
            include_internal: If False, excludes internal tools from the output.
        """
        return [
            tool.to_openai_tool()
            for name, tool in self._tools.items()
            if (enabled_tools is None or name in enabled_tools)
            and (include_internal or not tool.internal)
        ]

tool_registry = ToolRegistry()
