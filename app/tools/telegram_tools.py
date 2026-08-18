"""Telegram bridge tools — registered only when Telegram is configured."""

import logging
from typing import Any, Dict

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class EscalateToHumanTool(BaseTool):
    """Hand the current conversation over to a human agent via Telegram.

    Sets the session to human mode (AI auto-reply paused) and notifies the
    staff Telegram chat with a reply CTA.
    """

    @property
    def name(self) -> str:
        return "escalate_to_human"

    @property
    def description(self) -> str:
        return (
            "Teruskan percakapan ini ke agent manusia lewat Telegram. "
            "Gunakan saat kamu tidak yakin, tidak bisa menjawab, user meminta "
            "berbicara dengan manusia, atau masalahnya butuh tindakan manual "
            "(misal masalah pembayaran). Sesi akan dipindahkan ke mode human: "
            "pesan user berikutnya tidak dijawab AI."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "Ringkasan singkat kenapa perlu agent manusia "
                        "(dalam Bahasa Indonesia)"
                    ),
                }
            },
            "required": ["reason"],
        }

    async def execute(self, reason: str = "") -> Any:
        from app.services.telegram_bridge import telegram_bridge, telegram_enabled

        if not telegram_enabled():
            return {"error": "Telegram bridge is not configured"}

        session_id = self.context.get("session_id")
        if not session_id:
            return {"error": "No active session for escalation"}

        escalated = await telegram_bridge.escalate(str(session_id), reason)
        if not escalated:
            return {
                "error": "Telegram handoff failed; the session remains with AI",
                "escalated": False,
            }
        return {
            "escalated": True,
            "session_id": str(session_id),
            "message": "Sesi sudah diteruskan ke agent manusia.",
        }


class ReportToStaffTool(BaseTool):
    """Send a report note to the staff Telegram chat without escalating."""

    @property
    def name(self) -> str:
        return "report_to_staff"

    @property
    def description(self) -> str:
        return (
            "Kirim laporan singkat ke tim lewat Telegram tanpa mengalihkan "
            "percakapan. Gunakan untuk informasi penting yang perlu diketahui "
            "tim (misal user mengeluh atau menyebut bug) padahal kamu masih "
            "bisa menjawab."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Isi laporan singkat untuk tim (Bahasa Indonesia)",
                }
            },
            "required": ["summary"],
        }

    async def execute(self, summary: str = "") -> Any:
        from app.services.telegram_bridge import (
            _escape,
            telegram_bridge,
            telegram_enabled,
        )

        if not telegram_enabled():
            return {"error": "Telegram bridge is not configured"}

        session_id = self.context.get("session_id")
        message_id = await telegram_bridge.send(
            "📋 <b>Laporan AI</b>"
            + (f" · <code>{str(session_id)[:8]}</code>" if session_id else "")
            + f"\n\n{_escape(summary[:600])}"
        )
        if not message_id:
            return {"error": "Telegram report delivery failed", "reported": False}
        return {"reported": True}
