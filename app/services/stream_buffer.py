import asyncio
import json
import logging
from typing import AsyncGenerator, List, Tuple

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

# TTL for stream data in Redis (5 minutes)
STREAM_TTL = 300


class StreamBuffer:
    """Redis-backed buffer for WebSocket stream resume support.

    Stores stream chunks in Redis lists so clients can reconnect
    and resume from where they left off.
    """

    def __init__(self):
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
            )
        return self._redis

    def _chunks_key(self, stream_id: str) -> str:
        return f"stream:{stream_id}:chunks"

    def _done_key(self, stream_id: str) -> str:
        return f"stream:{stream_id}:done"

    def _channel(self, stream_id: str) -> str:
        return f"stream:{stream_id}:live"

    async def append(self, stream_id: str, content: str) -> None:
        """Append a chunk to the stream buffer and publish to subscribers."""
        r = await self._get_redis()
        pipe = r.pipeline()
        pipe.rpush(self._chunks_key(stream_id), content)
        pipe.expire(self._chunks_key(stream_id), STREAM_TTL)
        pipe.publish(self._channel(stream_id), json.dumps({"type": "chunk", "content": content}))
        await pipe.execute()

    async def get_chunks(self, stream_id: str) -> Tuple[List[str], bool, bool]:
        """Get all buffered chunks, whether the stream is done, and whether it exists."""
        r = await self._get_redis()
        pipe = r.pipeline()
        pipe.lrange(self._chunks_key(stream_id), 0, -1)
        pipe.exists(self._done_key(stream_id))
        pipe.exists(self._chunks_key(stream_id))
        results = await pipe.execute()
        chunks = results[0] or []
        is_done = bool(results[1])
        exists = bool(results[2]) or is_done
        return chunks, is_done, exists

    async def mark_done(self, stream_id: str) -> None:
        """Mark stream as complete."""
        r = await self._get_redis()
        pipe = r.pipeline()
        pipe.set(self._done_key(stream_id), "1", ex=STREAM_TTL)
        pipe.expire(self._chunks_key(stream_id), STREAM_TTL)
        pipe.publish(self._channel(stream_id), json.dumps({"type": "done"}))
        await pipe.execute()

    async def subscribe(self, stream_id: str) -> AsyncGenerator[str, None]:
        """Subscribe to live chunks for a stream that's still running."""
        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(self._channel(stream_id))

        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    data = json.loads(msg["data"])
                    if data["type"] == "done":
                        break
                    if data["type"] == "chunk":
                        yield data["content"]
                else:
                    # Check if stream finished while we were waiting
                    done = await r.exists(self._done_key(stream_id))
                    if done:
                        break
                    await asyncio.sleep(0.05)
        finally:
            await pubsub.unsubscribe(self._channel(stream_id))
            await pubsub.aclose()
