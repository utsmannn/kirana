from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.config import settings
from app.models.personality import Personality
from app.models.provider import ProviderCredential
from app.schemas.config import ConfigResponse, ConfigUpdate, CustomPersonalityUpdate

router = APIRouter()


@router.get("/")
async def get_config(
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """Get active provider configuration."""
    # Get active provider (limit 1 in case of multiple)
    result = await db.execute(
        select(ProviderCredential)
        .where(ProviderCredential.is_active == True)
        .order_by(ProviderCredential.priority_order.asc())
        .limit(1)
    )
    provider = result.scalar_one_or_none()

    if provider:
        return {
            "provider": {
                "id": str(provider.id),
                "name": provider.name,
                "model": provider.model,
                "base_url": provider.base_url,
                "is_default": provider.is_default,
            },
            "timeout": settings.LLM_TIMEOUT,
            "max_retries": settings.LLM_MAX_RETRIES,
        }

    # Fallback to .env settings if no active provider
    return {
        "provider": {
            "id": None,
            "name": "Default (.env)",
            "model": settings.DEFAULT_MODEL,
            "base_url": settings.OPENAI_BASE_URL,
            "personality_slug": None,
            "system_prompt": None,
            "is_default": True,
        },
        "timeout": settings.LLM_TIMEOUT,
        "max_retries": settings.LLM_MAX_RETRIES,
    }


@router.patch("/")
async def update_config(
    config_in: ConfigUpdate,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """Update configuration - requires restart to take effect."""
    # Get active provider to show current config
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.is_active == True)
    )
    provider = result.scalar_one_or_none()

    current_config = {
        "id": str(provider.id) if provider else None,
        "name": provider.name if provider else "Default (.env)",
        "model": provider.model if provider else settings.DEFAULT_MODEL,
        "base_url": provider.base_url if provider else settings.OPENAI_BASE_URL,
        "is_default": provider.is_default if provider else True,
    }

    return {
        "message": "Use /v1/providers API to manage provider credentials.",
        "current": current_config,
    }


@router.put("/personality")
async def set_custom_personality(
    personality_in: CustomPersonalityUpdate,
    api_key: str = Depends(deps.verify_api_key),
):
    """Set custom personality - requires restart to take effect."""
    return {
        "message": "Use /v1/providers API to update provider personality settings.",
    }
