import secrets
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api import deps
from app.config import settings
from app.models.channel import Channel
from app.models.provider import ProviderCredential

router = APIRouter()


class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    provider_id: UUID
    system_prompt: Optional[str] = None
    personality_name: Optional[str] = None


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    provider_id: Optional[UUID] = None
    system_prompt: Optional[str] = None
    personality_name: Optional[str] = None


class ChannelResponse(BaseModel):
    id: UUID
    name: str
    provider_id: UUID
    provider_name: Optional[str] = None
    system_prompt: Optional[str]
    personality_name: Optional[str]
    is_default: bool
    created_at: str
    # Embed fields
    embed_enabled: Optional[bool] = False
    embed_config: Optional[dict] = None

    @classmethod
    def from_orm(cls, obj, provider_name=None):
        return cls(
            id=obj.id,
            name=obj.name,
            provider_id=obj.provider_id,
            provider_name=provider_name,
            system_prompt=obj.system_prompt,
            personality_name=obj.personality_name,
            is_default=obj.is_default,
            created_at=obj.created_at.isoformat() if obj.created_at else None,
            embed_enabled=obj.embed_enabled,
            embed_config=obj.embed_config,
        )


class EmbedConfigUpdate(BaseModel):
    public: bool = Field(default=True, description="If true, no token required")
    save_history: bool = Field(default=True, description="Save chat history to localStorage")
    regenerate_token: bool = Field(default=False, description="Generate new embed token")


class EmbedConfigResponse(BaseModel):
    embed_enabled: bool
    embed_url: Optional[str] = None
    public: bool
    save_history: bool
    has_token: bool


class ChannelListResponse(BaseModel):
    channels: List[ChannelResponse]
    default_channel: Optional[ChannelResponse] = None


@router.get("/", response_model=ChannelListResponse)
async def list_channels(
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """List all channels."""
    result = await db.execute(
        select(Channel, ProviderCredential.name.label("provider_name"))
        .join(ProviderCredential, Channel.provider_id == ProviderCredential.id)
        .order_by(Channel.created_at.desc())
    )
    rows = result.all()

    channels = []
    default = None
    for row in rows:
        channel, provider_name = row
        ch_resp = ChannelResponse.from_orm(channel, provider_name)
        channels.append(ch_resp)
        if channel.is_default:
            default = ch_resp

    return {"channels": channels, "default_channel": default}


@router.post("/", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    data: ChannelCreate,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """Create a new channel."""
    # Verify provider exists
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.id == data.provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    channel = Channel(
        name=data.name,
        provider_id=data.provider_id,
        system_prompt=data.system_prompt,
        personality_name=data.personality_name,
        is_default=False,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return ChannelResponse.from_orm(channel, provider.name)


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: UUID,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """Get a specific channel."""
    result = await db.execute(
        select(Channel, ProviderCredential.name.label("provider_name"))
        .join(ProviderCredential, Channel.provider_id == ProviderCredential.id)
        .where(Channel.id == channel_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel, provider_name = row
    return ChannelResponse.from_orm(channel, provider_name)


@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: UUID,
    data: ChannelUpdate,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """Update a channel."""
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    update_data = data.model_dump(exclude_unset=True)

    # If changing provider, verify it exists
    if data.provider_id:
        prov_result = await db.execute(
            select(ProviderCredential).where(ProviderCredential.id == data.provider_id)
        )
        if not prov_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Provider not found")

    for field, value in update_data.items():
        setattr(channel, field, value)

    await db.commit()
    await db.refresh(channel)

    # Get provider name
    prov_result = await db.execute(
        select(ProviderCredential.name).where(ProviderCredential.id == channel.provider_id)
    )
    provider_name = prov_result.scalar()

    return ChannelResponse.from_orm(channel, provider_name)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: UUID,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """Delete a channel. Cannot delete default channel."""
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if channel.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default channel")

    await db.delete(channel)
    await db.commit()


@router.post("/{channel_id}/set-default", response_model=ChannelResponse)
async def set_default_channel(
    channel_id: UUID,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """Set a channel as default."""
    # First, unset all defaults
    await db.execute(
        select(Channel).where(Channel.is_default == True)
    )
    result = await db.execute(select(Channel))
    for ch in result.scalars():
        ch.is_default = False

    # Set new default
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel.is_default = True
    await db.commit()
    await db.refresh(channel)

    # Get provider name
    prov_result = await db.execute(
        select(ProviderCredential.name).where(ProviderCredential.id == channel.provider_id)
    )
    provider_name = prov_result.scalar()

    return ChannelResponse.from_orm(channel, provider_name)


@router.post("/{channel_id}/embed", response_model=EmbedConfigResponse)
async def configure_embed(
    channel_id: UUID,
    data: EmbedConfigUpdate,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """Configure embed settings for a channel."""
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Get current config
    config = channel.embed_config or {}

    # Generate new token if requested or not exists
    if data.regenerate_token or not channel.embed_token:
        channel.embed_token = secrets.token_urlsafe(32)

    # Update config
    config["public"] = data.public
    config["save_history"] = data.save_history
    channel.embed_config = config
    channel.embed_enabled = True

    # Flag JSONB column as modified so SQLAlchemy detects the change
    flag_modified(channel, "embed_config")

    await db.commit()
    await db.refresh(channel)

    # Build embed URL
    embed_url = f"/embed/{channel.id}"
    if not data.public:
        embed_url += f"?token={channel.embed_token}"

    return EmbedConfigResponse(
        embed_enabled=True,
        embed_url=embed_url,
        public=data.public,
        save_history=data.save_history,
        has_token=bool(channel.embed_token),
    )


@router.get("/{channel_id}/embed", response_model=EmbedConfigResponse)
async def get_embed_config(
    channel_id: UUID,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """Get embed configuration for a channel."""
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    config = channel.embed_config or {}
    embed_url = None

    if channel.embed_enabled:
        embed_url = f"/embed/{channel.id}"
        if not config.get("public", True):
            embed_url += f"?token={channel.embed_token}"

    return EmbedConfigResponse(
        embed_enabled=channel.embed_enabled,
        embed_url=embed_url,
        public=config.get("public", True),
        save_history=config.get("save_history", True),
        has_token=bool(channel.embed_token),
    )


@router.delete("/{channel_id}/embed", status_code=status.HTTP_204_NO_CONTENT)
async def disable_embed(
    channel_id: UUID,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db),
):
    """Disable embed for a channel."""
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel.embed_enabled = False
    # Keep the token for future re-enable

    await db.commit()
