"""Session-scoped realtime event channel.

WebSocket endpoint a custom widget can subscribe to in order to receive
all session events (user messages, AI replies, injected human agent
replies, mode changes) without using Kirana's embed template.

    ws://<host>/v1/sessions/{session_id}/events?api_key=<KIRANA_API_KEY>

The socket pushes JSON events as they are published to the in-memory
event bus. On reconnect, catch up missed history via
GET /v1/sessions/{session_id}/messages.
"""

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.v1.admin import verify_admin_token
from app.config import settings
from app.services import event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/{session_id}/events")
async def session_events(websocket: WebSocket, session_id: uuid.UUID):
    api_key = websocket.query_params.get("api_key")
    authorized = api_key == settings.KIRANA_API_KEY or (
        api_key and verify_admin_token(api_key)
    )
    if not authorized:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    # Validate session id shape only; nonexistent session simply never emits.
    await websocket.accept()
    queue = event_bus.subscribe(str(session_id))
    logger.info("[EVENTS] subscriber attached to session %s", session_id)
    try:
        await websocket.send_json({"type": "subscribed", "session_id": str(session_id)})
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("[EVENTS] socket error for %s: %s", session_id, e)
    finally:
        event_bus.unsubscribe(str(session_id), queue)
        logger.info("[EVENTS] subscriber detached from session %s", session_id)
