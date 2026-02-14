from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.config import settings
from app.core import security
from app.models.client import Client
from app.models.client_config import ClientConfig
from app.models.personality import Personality
from app.schemas.client import (
    APIKeyResponse,
    ClientCreate,
    ClientRegisterResponse,
    ClientResponse,
)

router = APIRouter()


@router.post(
    "/", response_model=ClientRegisterResponse, status_code=status.HTTP_201_CREATED
)
async def register_client(
    client_in: ClientCreate, db: AsyncSession = Depends(deps.get_db)
):
    # Check if email already exists
    result = await db.execute(select(Client).where(Client.email == client_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Generate API key
    raw_key, hashed_key, prefix = security.generate_api_key()

    # Create client
    client = Client(
        name=client_in.name,
        email=client_in.email,
        api_key=hashed_key,
        api_key_prefix=prefix,
    )
    db.add(client)
    await db.flush()  # Get client ID

    # Find default personality template
    p_result = await db.execute(
        select(Personality).where(Personality.slug == "helpful-assistant")
    )
    default_p = p_result.scalar_one_or_none()

    # Create default config
    config = ClientConfig(
        client_id=client.id,
        model=settings.DEFAULT_MODEL,
        personality_id=default_p.id if default_p else None,
    )
    db.add(config)

    await db.commit()
    await db.refresh(client)
    await db.refresh(config)

    return {
        **ClientResponse.model_validate(client).model_dump(),
        "api_key": raw_key,
        "config": {
            "ai_name": config.ai_name,
            "personality": default_p.slug if default_p else None,
            "thinking_mode": config.thinking_mode,
            "model": config.model,
            "tools_enabled": config.tools_enabled,
        },
    }


@router.get("/me", response_model=ClientResponse)
async def get_client_me(client: Client = Depends(deps.get_current_client)):
    return client


@router.post("/me/regenerate-key", response_model=APIKeyResponse)
async def regenerate_api_key(
    client: Client = Depends(deps.get_current_client),
    db: AsyncSession = Depends(deps.get_db),
):
    raw_key, hashed_key, prefix = security.generate_api_key()

    client.api_key = hashed_key
    client.api_key_prefix = prefix

    await db.commit()

    return {
        "api_key": raw_key,
        "api_key_prefix": prefix,
        "message": "New API key generated. Old key is now invalid.",
    }