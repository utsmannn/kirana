from fastapi import APIRouter

from app.api.v1 import (
    admin,
    channels,
    chat,
    config,
    knowledge,
    personalities,
    providers,
    sessions,
    tools,
    usage,
)

api_router = APIRouter()

api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(providers.router, prefix="/providers", tags=["providers"])
api_router.include_router(channels.router, prefix="/channels", tags=["channels"])
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(personalities.router, prefix="/personalities", tags=["personalities"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(usage.router, prefix="/usage", tags=["usage"])
