import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
            )
        return self._redis

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Skip rate limiting for health check and embed pages
        if request.url.path == "/health":
            return await call_next(request)

        # Skip rate limiting for embed pages, static assets, and chat API
        if request.url.path.startswith("/embed") or request.url.path.startswith("/panel/_app") or request.url.path.startswith("/v1/chat"):
            return await call_next(request)

        # Extract client identifier from Authorization header
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            client_key = auth[7:][:16]  # Use first 16 chars of token as identifier
        else:
            client_key = request.client.host if request.client else "unknown"

        try:
            r = await self._get_redis()
            now = int(time.time())
            window_key = f"ratelimit:{client_key}:{now // 60}"

            pipe = r.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, 120)
            results = await pipe.execute()
            current_count = results[0]

            limit = settings.RATE_LIMIT_REQUESTS_PER_MINUTE
            remaining = max(0, limit - current_count)

            if current_count > limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limit_exceeded",
                            "message": f"Rate limit exceeded. Maximum {limit} requests per minute.",
                            "type": "rate_limit_error",
                            "param": None,
                        }
                    },
                    headers={
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "Retry-After": str(60 - (now % 60)),
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response

        except Exception:
            # If Redis is down, allow the request through
            logger.warning("Rate limiting unavailable (Redis error)")
            return await call_next(request)
