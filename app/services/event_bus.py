"""In-memory session event bus with optional webhook dispatch.

Publishes session-scoped events to:
- local subscribers (WebSocket realtime channel)
- an external webhook URL (if configured) for server-to-server consumers
  such as the Telegram bridge.

Event shape:
    {
        "type": "message.assistant" | "message.user" | "message.agent"
                | "session.mode_changed" | "session.typing",
        "session_id": "<uuid>",
        "channel_id": "<uuid>" | None,
        "data": {...},
        "ts": "<iso8601>",
    }
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Set

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_subscribers: Dict[str, Set[asyncio.Queue]] = {}


def subscribe(session_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.setdefault(session_id, set()).add(queue)
    return queue


def subscribe_all() -> asyncio.Queue:
    """Wildcard subscription: receive events for every session."""
    return subscribe("*")


def unsubscribe(session_id: str, queue: asyncio.Queue) -> None:
    queues = _subscribers.get(session_id)
    if not queues:
        return
    queues.discard(queue)
    if not queues:
        _subscribers.pop(session_id, None)


async def _dispatch_webhook(event: Dict[str, Any]) -> None:
    url = getattr(settings, "WEBHOOK_URL", None)
    if not url:
        return
    headers = {"Content-Type": "application/json"}
    secret = getattr(settings, "WEBHOOK_SECRET", None)
    if secret:
        headers["X-Kirana-Signature"] = secret
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=event, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    "[WEBHOOK] %s returned %d: %s",
                    url,
                    resp.status_code,
                    resp.text[:200],
                )
            else:
                logger.info("[WEBHOOK] %s -> %d", event["type"], resp.status_code)
    except Exception as e:
        logger.warning("[WEBHOOK] delivery failed: %s", e)


async def publish(
    event_type: str,
    session_id,
    channel_id=None,
    data: Dict[str, Any] | None = None,
) -> None:
    event = {
        "type": event_type,
        "session_id": str(session_id),
        "channel_id": str(channel_id) if channel_id else None,
        "data": data or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    # Local subscribers (session-scoped + wildcard)
    targets = list(_subscribers.get(event["session_id"], set()))
    targets += list(_subscribers.get("*", set()))
    for queue in targets:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "[EVENTS] subscriber queue full, dropping event %s", event_type
            )

    # External webhook (fire-and-forget, non-blocking). Avoid creating a task
    # for every event when webhook delivery is disabled.
    if settings.WEBHOOK_URL:
        asyncio.create_task(_dispatch_webhook(event))


async def publish_many(events) -> None:
    for args in events:
        await publish(*args)
