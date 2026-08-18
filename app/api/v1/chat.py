import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.config import settings
from app.db.session import get_db
from app.schemas.chat import ChatCompletionRequest
from app.services import event_bus
from app.services.chat_service import ChatService
from app.services.stream_buffer import StreamBuffer

router = APIRouter()
logger = logging.getLogger(__name__)

# Shared stream buffer instance
_stream_buffer = StreamBuffer()


@router.get("/stream/{stream_id}")
async def get_stream_chunks(
    stream_id: str,
    offset: int = Query(default=0, ge=0),
    api_key: str = Depends(deps.verify_api_key),
):
    """Get buffered stream chunks for polling-based resume."""
    try:
        chunks, is_done, exists = await _stream_buffer.get_chunks(stream_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stream not found or expired",
        ) from None

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stream not found or expired",
        )

    return {
        "stream_id": stream_id,
        "chunks": chunks[offset:],
        "offset": offset,
        "total": len(chunks),
        "done": is_done,
    }


async def verify_chat_auth(
    token: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    embed_token: Optional[str] = Query(None, description="Embed token for embed access"),
    channel_id: Optional[str] = Query(None, description="Channel ID for public embed"),
    db: AsyncSession = Depends(deps.get_db_session),
) -> tuple[str, bool]:
    """Verify authentication for chat endpoint.

    Supports:
    1. API key via Authorization header - full access
    2. Embed token via query param - access to that channel
    3. Public embed via channel_id (no auth) - if channel has public embed

    Returns (auth_value, is_embed)
    """
    from app.api.v1.admin import verify_admin_token
    from app.models.channel import Channel

    # Try API key first
    if token:
        if token.credentials == settings.KIRANA_API_KEY:
            return (token.credentials, False)
        # Also accept admin token (from admin panel login)
        if verify_admin_token(token.credentials):
            return (token.credentials, False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key or admin token",
        )

    # Try embed token
    if embed_token:
        result = await db.execute(
            select(Channel).where(Channel.embed_token == embed_token)
        )
        channel = result.scalar_one_or_none()

        if not channel:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid embed token",
            )

        if not channel.embed_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Embed is not enabled for this channel",
            )

        return (embed_token, True)

    # Try public embed (no auth, but channel_id must be provided and have public embed)
    if channel_id:
        try:
            import uuid
            ch_uuid = uuid.UUID(channel_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid channel_id format",
            )

        result = await db.execute(
            select(Channel).where(Channel.id == ch_uuid)
        )
        channel = result.scalar_one_or_none()

        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Channel not found",
            )

        if not channel.embed_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Embed is not enabled for this channel",
            )

        # Check if embed is public
        config = channel.embed_config or {}
        if not config.get("public", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This embed requires a token",
            )

        return (channel_id, True)

    # No auth provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (API key, embed token, or channel_id for public embed)",
    )


@router.post("/send")
async def create_chat_completion(
    request: ChatCompletionRequest,
    auth_info: tuple[str, bool] = Depends(verify_chat_auth),
    db: AsyncSession = Depends(deps.get_db_session),
    http_request: Request = None,
):
    """Chat completion endpoint - logs all requests.

    Authentication:
    - API key via Authorization header
    - Embed token via ?embed_token= query param
    - Public embed via ?channel_id= query param (if embed is public)
    """
    auth_value, is_embed = auth_info
    start_time = time.time()
    client_ip = http_request.client.host if http_request else "unknown"

    # Log incoming request
    logger.info(
        "[CHAT REQUEST] IP=%s Model=%s Stream=%s Messages=%d IsEmbed=%s",
        client_ip,
        request.model,
        request.stream,
        len(request.messages),
        "yes" if is_embed else "no",
    )

    chat_service = ChatService(db)
    try:
        if request.stream:
            # Use client-provided stream_id if available (for resume support)
            stream_id = request.stream_id or str(uuid.uuid4())
            stream_buffer = _stream_buffer

            async def logged_stream():
                # Send stream_id as first SSE event
                yield f"data: {json.dumps({'stream_id': stream_id})}\n\n"

                token_count = 0
                try:
                    async for chunk in chat_service.create_chat_completion_stream(request):
                        token_count += 1
                        # Buffer content to Redis for resume support
                        if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                            try:
                                payload = json.loads(chunk[6:].strip())
                                content = (
                                    payload.get("choices", [{}])[0]
                                    .get("delta", {})
                                    .get("content", "")
                                )
                                if content:
                                    try:
                                        await stream_buffer.append(stream_id, content)
                                    except Exception:
                                        pass  # Redis down - skip buffering
                            except json.JSONDecodeError:
                                pass
                        yield chunk
                except HTTPException as e:
                    detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
                    detail["status_code"] = e.status_code
                    yield f"data: {json.dumps({'error': detail})}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception:
                    logger.exception("[CHAT STREAM ERROR] IP=%s", client_ip)
                    yield f"data: {json.dumps({'error': {'code': 'chat_stream_error', 'message': 'An error occurred while streaming the chat response.'}})}\n\n"
                    yield "data: [DONE]\n\n"
                finally:
                    try:
                        await stream_buffer.mark_done(stream_id)
                    except Exception:
                        pass  # Redis down
                    duration = time.time() - start_time
                    logger.info(
                        "[CHAT STREAM COMPLETE] IP=%s Duration=%.2fs Tokens=%d StreamID=%s",
                        client_ip,
                        duration,
                        token_count,
                        stream_id,
                    )

            return StreamingResponse(
                logged_stream(),
                media_type="text/event-stream",
            )
        else:
            response = await chat_service.create_chat_completion(request)
            duration = time.time() - start_time

            # Log completion
            usage = response.usage if hasattr(response, "usage") else None
            logger.info(
                "[CHAT COMPLETE] IP=%s Duration=%.2fs Tokens=%s",
                client_ip,
                duration,
                usage.total_tokens if usage else "unknown",
            )
            return response

    except HTTPException:
        duration = time.time() - start_time
        logger.warning("[CHAT ERROR] IP=%s Duration=%.2fs HTTPException", client_ip, duration)
        raise
    except Exception:
        duration = time.time() - start_time
        logger.exception("[CHAT ERROR] IP=%s Duration=%.2fs", client_ip, duration)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request.",
        ) from None


@router.websocket("/ws")
async def chat_websocket(
    websocket: WebSocket,
    token: str = Query(default="", description="API key"),
    embed_token: str = Query(default="", description="Embed token for embed access"),
    channel_id: str = Query(default="", description="Channel ID for public embed"),
):
    """WebSocket chat endpoint with stream resume support.

    Authentication (one of):
    - API key via ?token=<API_KEY>
    - Embed token via ?embed_token=<token>
    - Public embed via ?channel_id=<uuid> (if embed is public)

    Send message:
      {"action": "chat", "data": {<ChatCompletionRequest fields>}}

    Resume a stream:
      {"action": "resume", "stream_id": "<stream_id>"}

    Server sends:
      {"type": "stream_start", "stream_id": "..."}
      {"type": "chunk", "content": "..."}
      {"type": "stream_end"}
      {"type": "error", "message": "..."}
    """
    from app.api.v1.admin import verify_admin_token
    from app.models.channel import Channel

    # Verify authentication
    is_embed = False
    authorized_channel_id: uuid.UUID | None = None
    if token and token == settings.KIRANA_API_KEY:
        pass  # Valid API key
    elif token and verify_admin_token(token):
        pass  # Valid admin token
    elif embed_token:
        # Verify embed token
        async for db in get_db():
            result = await db.execute(
                select(Channel).where(Channel.embed_token == embed_token)
            )
            channel = result.scalar_one_or_none()
            if not channel or not channel.embed_enabled:
                await websocket.close(code=4001, reason="Invalid embed token")
                return
            is_embed = True
            authorized_channel_id = channel.id
            break
    elif channel_id:
        # Verify public embed
        try:
            ch_uuid = uuid.UUID(channel_id)
        except ValueError:
            await websocket.close(code=4001, reason="Invalid channel_id")
            return

        async for db in get_db():
            result = await db.execute(
                select(Channel).where(Channel.id == ch_uuid)
            )
            channel = result.scalar_one_or_none()
            if not channel:
                await websocket.close(code=4001, reason="Channel not found")
                return
            if not channel.embed_enabled:
                await websocket.close(code=4001, reason="Embed not enabled")
                return
            config = channel.embed_config or {}
            if not config.get("public", True):
                await websocket.close(code=4001, reason="This embed requires a token")
                return
            is_embed = True
            authorized_channel_id = channel.id
            break
    else:
        await websocket.close(code=4001, reason="Authentication required")
        return

    await websocket.accept()
    logger.info("[WS] Client connected (is_embed=%s)", is_embed)

    stream_buffer = StreamBuffer()
    current_stream_id: str | None = None

    # Session event interception: while the socket sits idle waiting for the
    # user, forward human-agent replies injected via the API (e.g. the
    # Telegram bridge) to this socket as a regular chunk stream — no extra
    # socket needed on the widget side.
    events_queue = None
    events_session_id: str | None = None

    try:
        while True:
            recv_task = asyncio.create_task(websocket.receive_text())
            event_task = (
                asyncio.create_task(events_queue.get())
                if events_queue
                else None
            )
            wait_set = {recv_task, event_task} if event_task else {recv_task}
            done, _ = await asyncio.wait(
                wait_set,
                return_when=asyncio.FIRST_COMPLETED,
            )
            event_ready = event_task is not None and event_task in done
            receive_ready = recv_task in done

            # Both tasks may complete in the same event-loop turn. Process both;
            # discarding an already-completed receive would lose a user message.
            if event_ready and event_task is not None:
                await _forward_agent_event(
                    websocket,
                    events_session_id,
                    event_task.result(),
                )

            if not receive_ready:
                recv_task.cancel()
                await asyncio.gather(recv_task, return_exceptions=True)
                continue

            if event_task is not None and not event_ready:
                event_task.cancel()
                await asyncio.gather(event_task, return_exceptions=True)
            raw = recv_task.result()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action")

            if action == "subscribe":
                requested_session_id = msg.get("session_id")
                try:
                    requested_uuid = uuid.UUID(str(requested_session_id))
                except (TypeError, ValueError):
                    await websocket.send_json(
                        {"type": "error", "message": "Invalid session_id"}
                    )
                    continue

                from app.db.session import async_session
                from app.models.conversation import ConversationLog
                from app.models.session import Session

                async with async_session() as db:
                    result = await db.execute(
                        select(Session).where(Session.id == requested_uuid)
                    )
                    requested_session = result.scalar_one_or_none()

                visitor_id = str(msg.get("visitor_id") or "")
                session_visitor_id = str(
                    (requested_session.extra_metadata or {}).get("visitor_id")
                    if requested_session else ""
                )
                if not requested_session or (
                    is_embed
                    and (
                        requested_session.channel_id != authorized_channel_id
                        or not visitor_id
                        or visitor_id != session_visitor_id
                    )
                ):
                    await websocket.send_json(
                        {"type": "error", "message": "Session not found"}
                    )
                    continue

                requested_id = str(requested_session.id)
                if events_queue is None or events_session_id != requested_id:
                    if events_queue is not None and events_session_id:
                        event_bus.unsubscribe(events_session_id, events_queue)
                    events_session_id = requested_id
                    events_queue = event_bus.subscribe(events_session_id)

                # Subscribe before reading history. Then remove only queued agent
                # events already represented by that snapshot; events committed
                # after the query stay queued and cannot fall into a reconnect gap.
                async with async_session() as db:
                    result = await db.execute(
                        select(ConversationLog)
                        .where(ConversationLog.session_id == requested_session.id)
                        .order_by(ConversationLog.created_at.desc())
                        .limit(200)
                    )
                    history_logs = list(reversed(result.scalars().all()))

                history_ids = {str(log.id) for log in history_logs}
                buffered_events = []
                while events_queue is not None:
                    try:
                        event = events_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    event_message_id = str(
                        (event.get("data") or {}).get("message_id") or ""
                    )
                    if (
                        event.get("type") == "message.agent"
                        and event_message_id in history_ids
                    ):
                        continue
                    buffered_events.append(event)
                for event in buffered_events:
                    events_queue.put_nowait(event)

                await websocket.send_json(
                    {
                        "type": "subscribed",
                        "session_id": events_session_id,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "history",
                        "session_id": events_session_id,
                        "messages": [
                            {
                                "id": str(log.id),
                                "role": log.role,
                                "content": log.content,
                                "fromAgent": log.model == "human_agent",
                            }
                            for log in history_logs
                        ],
                    }
                )
                logger.info(
                    "[WS] Restored session event interception for %s",
                    events_session_id,
                )

            elif action == "resume":
                # Resume an existing stream
                stream_id = msg.get("stream_id")
                if not stream_id:
                    await websocket.send_json({"type": "error", "message": "Missing stream_id"})
                    continue

                logger.info("[WS] Resuming stream %s", stream_id)
                chunks, is_done, _ = await stream_buffer.get_chunks(stream_id)

                await websocket.send_json({"type": "stream_start", "stream_id": stream_id, "resumed": True})

                for chunk_content in chunks:
                    await websocket.send_json({"type": "chunk", "content": chunk_content})

                if is_done:
                    await websocket.send_json({"type": "stream_end"})
                else:
                    # Stream still running, subscribe to new chunks
                    current_stream_id = stream_id
                    async for chunk_content in stream_buffer.subscribe(stream_id):
                        try:
                            await websocket.send_json({"type": "chunk", "content": chunk_content})
                        except WebSocketDisconnect:
                            break
                    await websocket.send_json({"type": "stream_end"})
                    current_stream_id = None

            elif action == "chat":
                # New chat request
                data = msg.get("data", {})
                try:
                    request = ChatCompletionRequest(**data)
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"Invalid request: {e}"})
                    continue

                stream_id = str(uuid.uuid4())
                current_stream_id = stream_id
                session_id = None  # Track session_id from stream

                await websocket.send_json({"type": "stream_start", "stream_id": stream_id})

                # Get DB session manually (not via dependency injection)
                async for db in get_db():
                    chat_service = ChatService(db)

                    try:
                        async for sse_chunk in chat_service.create_chat_completion_stream(request):
                            # Parse SSE chunk to extract content or session_id
                            if sse_chunk.startswith("data: ") and sse_chunk.strip() != "data: [DONE]":
                                try:
                                    payload = json.loads(sse_chunk[6:].strip())

                                    # Attach interception as soon as ChatService
                                    # announces the session. Events arriving while
                                    # the AI stream is active stay queued here.
                                    if "session_id" in payload:
                                        session_id = str(payload["session_id"])
                                        if session_id != events_session_id:
                                            if (
                                                events_queue is not None
                                                and events_session_id
                                            ):
                                                event_bus.unsubscribe(
                                                    events_session_id,
                                                    events_queue,
                                                )
                                            events_queue = event_bus.subscribe(
                                                session_id
                                            )
                                            events_session_id = session_id
                                            logger.info(
                                                "[WS] Intercepting session "
                                                "events for %s",
                                                session_id,
                                            )
                                        continue

                                    # Forward tool lifecycle events so WebSocket
                                    # clients can inspect tool usage.
                                    if payload.get("type", "").startswith("tool_call_"):
                                        try:
                                            await websocket.send_json(payload)
                                        except (WebSocketDisconnect, RuntimeError):
                                            logger.info(
                                                "[WS] Client disconnected "
                                                "mid-tool-event, buffering %s",
                                                stream_id,
                                            )
                                        continue

                                    # Regular content chunk
                                    content = payload.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if content:
                                        try:
                                            await stream_buffer.append(stream_id, content)
                                        except Exception:
                                            pass  # Redis down - skip buffering
                                        try:
                                            await websocket.send_json({"type": "chunk", "content": content})
                                        except (WebSocketDisconnect, RuntimeError):
                                            # Client disconnected - keep streaming to buffer
                                            logger.info("[WS] Client disconnected mid-stream, buffering %s", stream_id)
                                except json.JSONDecodeError:
                                    pass

                        try:
                            await stream_buffer.mark_done(stream_id)
                        except Exception:
                            pass  # Redis down
                    except Exception as e:
                        logger.exception("[WS] Chat error: %s", e)
                        try:
                            await stream_buffer.mark_done(stream_id)
                        except Exception:
                            pass  # Redis down
                        try:
                            await websocket.send_json({"type": "error", "message": str(e)})
                        except WebSocketDisconnect:
                            pass

                try:
                    # Send stream_end with session_id if available
                    end_payload = {"type": "stream_end"}
                    if session_id:
                        end_payload["session_id"] = session_id
                    await websocket.send_json(end_payload)
                except WebSocketDisconnect:
                    pass

                current_stream_id = None

                # Start (or switch) intercepting events for this session so
                # injected agent replies reach this widget.
                if session_id and session_id != events_session_id:
                    if events_queue is not None:
                        event_bus.unsubscribe(events_session_id, events_queue)
                    events_queue = event_bus.subscribe(session_id)
                    events_session_id = session_id
                    logger.info("[WS] Intercepting session events for %s", session_id)

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected")
    except Exception:
        logger.exception("[WS] Unexpected error")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if events_queue is not None and events_session_id:
            event_bus.unsubscribe(events_session_id, events_queue)


async def _forward_agent_event(
    websocket: WebSocket,
    session_id: str | None,
    event: dict,
) -> None:
    """Render an injected human-agent reply as a normal chunk stream."""
    if not event or not session_id or event.get("session_id") != session_id:
        return
    if event.get("type") != "message.agent":
        return
    content = (event.get("data") or {}).get("content")
    if not content:
        return
    try:
        await websocket.send_json({
            "type": "stream_start",
            "stream_id": str(uuid.uuid4()),
            "from_agent": True,
        })
        await websocket.send_json({"type": "chunk", "content": content})
        await websocket.send_json({"type": "stream_end", "session_id": session_id})
        logger.info("[WS] Forwarded injected agent reply for session %s", session_id)
    except Exception:
        pass  # socket died; the message is already persisted in the session log
