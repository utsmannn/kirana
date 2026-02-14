from datetime import datetime
from typing import Any, Dict

import pytz

from app.tools.base import BaseTool


class DateTimeTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_current_datetime"

    @property
    def description(self) -> str:
        return "Get current date and time in specified timezone"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "Timezone name (e.g., 'UTC', 'Asia/Jakarta')"
                },
                "format": {
                    "type": "string",
                    "description": "Output format ('ISO', 'human')"
                }
            }
        }

    async def execute(self, timezone: str = "UTC", format: str = "ISO") -> Any:
        try:
            tz = pytz.timezone(timezone)
        except Exception:
            tz = pytz.UTC
            
        now = datetime.now(tz)
        
        if format == "human":
            formatted = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
        else:
            formatted = now.isoformat()
            
        return {
            "datetime": formatted,
            "timestamp": int(now.timestamp()),
            "timezone": timezone
        }
