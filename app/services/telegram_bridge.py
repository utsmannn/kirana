"""Native Telegram human-agent bridge.

Activates automatically when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set.

Responsibilities:
- Reports AI replies to the staff Telegram chat (via the session event bus).
- Notifies staff when a user message is queued for a human agent.
- `escalate_to_human` tool hands a session over: sets mode=human and sends
  a Telegram notification with a "Balas" CTA.
- Long-polls Telegram updates: staff taps "Balas", replies to the prompt,
  and the reply is injected into the session conversation log and pushed to
  realtime subscribers. "Serahkan ke AI" switches the session back to ai.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import select

from app.config import settings
from app.models.conversation import ConversationLog
from app.models.session import Session

logger = logging.getLogger(__name__)

API = "https://api.telegram.org"


def telegram_enabled() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)


def _short(session_id: str) -> str:
    return session_id[:8]


def _is_allowed_chat(chat: Dict[str, Any]) -> bool:
    configured = str(settings.TELEGRAM_CHAT_ID or "").strip()
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    return bool(configured and chat_id is not None and str(chat_id) == configured)


class TelegramBridge:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._event_task: Optional[asyncio.Task] = None
        self._queue: Optional[asyncio.Queue] = None
        self._offset = 0
        # Telegram bot message id -> Kirana session id. Staff can use
        # Telegram's native Reply action on any notification bubble.
        self._message_sessions: Dict[int, str] = {}
        # Backward compatibility for force-reply prompts sent by older builds.
        self._pending_replies: Dict[int, str] = {}

    # ---------------------------------------------------------------- http

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def _call(self, method: str, payload: Dict[str, Any]) -> Optional[Dict]:
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            return None
        try:
            resp = await self._http().post(f"{API}/bot{token}/{method}", json=payload)
            data = resp.json()
            if not data.get("ok"):
                logger.warning("[TG] %s failed: %s", method, data)
                return None
            return data.get("result")
        except Exception as e:
            logger.warning("[TG] %s error: %s", method, e)
            return None

    async def send(
        self,
        text: str,
        reply_markup: Optional[Dict] = None,
        session_id: Optional[str] = None,
    ) -> Optional[int]:
        payload: Dict[str, Any] = {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        result = await self._call("sendMessage", payload)
        message_id = result["message_id"] if result else None
        if message_id and session_id:
            self._message_sessions[message_id] = session_id
            # Bound the in-memory index. New notifications also include a
            # short session marker for recovery after a process restart.
            while len(self._message_sessions) > 2000:
                self._message_sessions.pop(next(iter(self._message_sessions)))
        return message_id

    # ------------------------------------------------------------ notifs

    async def report_ai_reply(self, session: Session, content: str, model: str) -> None:
        session_id = str(session.id)
        text = (
            f"🤖 <b>AI menjawab</b>{_session_label(session)}\n"
            f"<i>{_escape(model)}</i>\n\n{_escape(content[:600])}"
            f"\n\n↩️ <i>Reply pesan ini untuk membalas user.</i>"
        )
        await self.send(
            text,
            reply_markup=_stop_session_keyboard(session_id),
            session_id=session_id,
        )

    async def notify_human_queue(self, session: Session, content: str) -> None:
        session_id = str(session.id)
        text = (
            f"👤 <b>Pesan baru menunggu agent</b>{_session_label(session)}\n\n"
            f"{_escape(content[:600])}"
            f"\n\n↩️ <i>Reply pesan ini untuk membalas user.</i>"
        )
        await self.send(
            text,
            reply_markup=_stop_session_keyboard(session_id),
            session_id=session_id,
        )

    async def escalate(self, session_id: str, reason: str) -> bool:
        existing = await self._get_session(session_id)
        if not existing:
            return False
        previous_mode = existing.mode

        session = await self._set_mode(session_id, "human")
        if not session:
            return False
        text = (
            f"🚨 <b>Eskalasi ke human</b>{_session_label(session)}\n\n"
            f"Alasan: {_escape(reason[:400])}"
            f"\n\n↩️ <i>Reply pesan ini untuk membalas user.</i>"
        )
        message_id = await self.send(
            text,
            reply_markup=_stop_session_keyboard(session_id),
            session_id=session_id,
        )
        if message_id:
            return True

        # Do not strand a conversation in human mode when staff never received
        # the handoff. Preserve an already-human session, otherwise roll back.
        if previous_mode != "human":
            await self._set_mode(session_id, previous_mode)
        logger.error("[TG] escalation delivery failed for session %s", session_id)
        return False

    # ---------------------------------------------------------- telegram

    async def poll_loop(self) -> None:
        logger.info("[TG] long-polling started")
        while True:
            try:
                resp = await self._http().get(
                    f"{API}/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates",
                    params={"timeout": 30, "offset": self._offset},
                    timeout=35,
                )
                data = resp.json()
                for update in data.get("result", []):
                    try:
                        await self._handle_update(update)
                    except Exception as e:
                        logger.exception("[TG] update handling failed: %s", e)
                        # Keep the failed update unacknowledged and retry it
                        # before processing later updates.
                        await asyncio.sleep(3)
                        break
                    else:
                        self._offset = update["update_id"] + 1
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("[TG] poll error: %s", e)
                await asyncio.sleep(3)

    async def _handle_update(self, update: Dict[str, Any]) -> None:
        if "callback_query" in update:
            cb = update["callback_query"]
            callback_message = cb.get("message") or {}
            if not _is_allowed_chat(callback_message.get("chat") or {}):
                logger.warning("[TG] ignored callback from unauthorized chat")
                return
            await self._call("answerCallbackQuery", {"callback_query_id": cb["id"]})
            data = cb.get("data", "")
            if data.startswith("balas:"):
                session_id = data.split(":", 1)[1]
                prompt = await self._call(
                    "sendMessage",
                    {
                        "chat_id": settings.TELEGRAM_CHAT_ID,
                        "text": (
                            "✍️ Ketik balasan untuk sesi "
                            f"<code>{_short(session_id)}</code>:"
                        ),
                        "parse_mode": "HTML",
                        "reply_markup": {"force_reply": True, "selective": True},
                    },
                )
                if prompt:
                    self._pending_replies[prompt["message_id"]] = session_id
            elif data.startswith("selesai:"):
                session_id = data.split(":", 1)[1]
                session = await self._set_mode(session_id, "ai")
                if session:
                    callback_message = cb.get("message") or {}
                    message_id = callback_message.get("message_id")
                    if message_id:
                        await self._call(
                            "editMessageReplyMarkup",
                            {
                                "chat_id": settings.TELEGRAM_CHAT_ID,
                                "message_id": message_id,
                                "reply_markup": {"inline_keyboard": []},
                            },
                        )
                    await self.send(
                        "⏹ Human session "
                        f"<code>#{_short(session_id)}</code> dihentikan. "
                        "Pesan user berikutnya kembali ditangani AI."
                    )
            return

        # Edited staff messages are not new replies and must not be injected
        # a second time.
        message = update.get("message")
        if not message:
            return
        if not _is_allowed_chat(message.get("chat") or {}):
            logger.warning("[TG] ignored message from unauthorized chat")
            return
        reply_to = message.get("reply_to_message") or {}
        reply_to_id = reply_to.get("message_id")
        text = (message.get("text") or "").strip()
        if not text:
            return

        # Native Telegram Reply is the routing key. Resolve from the live
        # message-id index first, then recover from the session marker/email
        # embedded in the quoted bot message (survives bridge restarts).
        session_id = self._pending_replies.get(reply_to_id)
        session_id = session_id or self._message_sessions.get(reply_to_id)
        if not session_id and reply_to:
            session_id = await self._session_id_from_reply(reply_to)

        if not session_id:
            await self.send(
                "⚠️ Reply langsung salah satu bubble notifikasi Kirana "
                "supaya balasan dapat diarahkan ke sesi yang benar."
            )
            return

        self._pending_replies.pop(reply_to_id, None)
        injected = await self._inject_agent_reply(
            session_id,
            text,
            update_id=update.get("update_id"),
        )
        if injected:
            await self.send(
                f"📤 Terkirim ke sesi <code>{_short(session_id)}</code>:"
                f"\n\n{_escape(text[:400])}"
            )
        else:
            await self.send(
                f"⚠️ Gagal mengirim ke sesi <code>{_short(session_id)}</code>."
            )

    async def _session_id_from_reply(
        self, replied_message: Dict[str, Any]
    ) -> Optional[str]:
        """Recover a session from the quoted bot bubble after a restart."""
        from app.db.session import async_session

        quoted = (
            replied_message.get("text") or replied_message.get("caption") or ""
        ).strip()
        short_match = re.search(r"#([0-9a-f]{8})\b", quoted, re.IGNORECASE)
        email_match = re.search(r"<([^<>\s]+@[^<>\s]+)>", quoted)
        short_id = short_match.group(1).lower() if short_match else None
        email = email_match.group(1).lower() if email_match else None
        if not short_id and not email:
            return None

        async with async_session() as db:
            if short_id:
                from sqlalchemy import String, cast

                result = await db.execute(
                    select(Session)
                    .where(
                        Session.is_active.is_(True),
                        cast(Session.id, String).ilike(f"{short_id}%"),
                    )
                    .order_by(Session.last_activity.desc())
                    .limit(1)
                )
                session = result.scalar_one_or_none()
                if session:
                    return str(session.id)
            if email:
                result = await db.execute(
                    select(Session)
                    .where(
                        Session.is_active.is_(True),
                        Session.extra_metadata["visitor_email"].as_string() == email,
                    )
                    .order_by(Session.last_activity.desc())
                    .limit(1)
                )
                session = result.scalar_one_or_none()
                if session:
                    return str(session.id)
        return None

    # -------------------------------------------------------------- db

    async def _set_mode(self, session_id: str, mode: str) -> Optional[Session]:
        from app.db.session import async_session
        from app.services import event_bus

        async with async_session() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            if not session:
                await self.send(
                    f"⚠️ Sesi <code>{_short(session_id)}</code> tidak ditemukan."
                )
                return None
            previous = session.mode
            session.mode = mode
            await db.commit()
            if previous != mode:
                await event_bus.publish(
                    "session.mode_changed",
                    session.id,
                    session.channel_id,
                    {"mode": mode, "previous_mode": previous},
                )
            return session

    async def _get_session(self, session_id: str) -> Optional[Session]:
        from app.db.session import async_session

        async with async_session() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            return result.scalar_one_or_none()

    async def _inject_agent_reply(
        self,
        session_id: str,
        content: str,
        update_id: Optional[int] = None,
    ) -> bool:
        from app.db.session import async_session
        from app.services import event_bus

        source_key = f"telegram:update:{update_id}" if update_id is not None else None
        async with async_session() as db:
            if source_key:
                result = await db.execute(
                    select(ConversationLog.id)
                    .where(ConversationLog.tool_call_id == source_key)
                    .limit(1)
                )
                if result.scalar_one_or_none():
                    logger.info("[TG] skipped replayed update %s", update_id)
                    return True

            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            if not session:
                return False
            previous_mode = session.mode
            session.mode = "human"
            log = ConversationLog(
                session_id=session.id,
                client_id=session.client_id,
                role="assistant",
                content=content,
                model="human_agent",
                tool_call_id=source_key,
                tokens_used=0,
            )
            db.add(log)
            session.message_count += 1
            session.last_activity = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(log)
            if previous_mode != "human":
                await event_bus.publish(
                    "session.mode_changed",
                    session.id,
                    session.channel_id,
                    {
                        "mode": "human",
                        "previous_mode": previous_mode,
                        "source": "telegram",
                    },
                )
            await event_bus.publish(
                "message.agent",
                session.id,
                session.channel_id,
                {
                    "message_id": str(log.id),
                    "role": "assistant",
                    "content": content,
                    "injected": True,
                    "source": "telegram",
                },
            )
            return True

    # ------------------------------------------------------------ events

    async def event_loop(self) -> None:
        from app.services import event_bus

        self._queue = event_bus.subscribe_all()
        logger.info("[TG] subscribed to session events")
        while True:
            event = await self._queue.get()
            try:
                etype = event.get("type")
                data = event.get("data", {})
                session = await self._get_session(event["session_id"])
                if not session:
                    continue
                if etype == "message.assistant" and not data.get("injected"):
                    await self.report_ai_reply(
                        session, data.get("content", ""), data.get("model", "ai")
                    )
                elif etype == "message.user" and data.get("queued_for_human"):
                    await self.notify_human_queue(session, data.get("content", ""))
            except Exception as e:
                logger.warning("[TG] event handling failed: %s", e)

    # --------------------------------------------------------- lifecycle

    def start(self) -> None:
        if not telegram_enabled():
            logger.info("[TG] not configured — Telegram bridge disabled")
            return
        self._poll_task = asyncio.create_task(self.poll_loop())
        self._event_task = asyncio.create_task(self.event_loop())

    async def stop(self) -> None:
        from app.services import event_bus

        if self._queue is not None:
            event_bus.unsubscribe("*", self._queue)
        tasks = [
            task for task in (self._poll_task, self._event_task) if task is not None
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._client:
            await self._client.aclose()


def _session_label(session: Session) -> str:
    meta = session.extra_metadata or {}
    name = meta.get("visitor_name") or session.name
    email = meta.get("visitor_email")
    sid = _short(str(session.id))
    has_identity = bool(name or email)
    who = _escape(str(name or sid))
    if email:
        who = f"{who} &lt;{_escape(str(email))}&gt;"
    if has_identity:
        who = f"{who} · <code>#{sid}</code>"
    else:
        who = f"<code>#{sid}</code>"
    return f" · {who}"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _stop_session_keyboard(session_id: str) -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "⏹ Stop session",
                    "callback_data": f"selesai:{session_id}",
                }
            ]
        ]
    }


telegram_bridge = TelegramBridge()
