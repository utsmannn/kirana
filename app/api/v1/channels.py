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
    # Context guard fields
    context: Optional[str] = Field(None, max_length=255, description="Context/entity name for AI scope limitation")
    context_description: Optional[str] = Field(None, description="Detailed context description")


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    provider_id: Optional[UUID] = None
    system_prompt: Optional[str] = None
    personality_name: Optional[str] = None
    # Context guard fields
    context: Optional[str] = Field(None, max_length=255, description="Context/entity name for AI scope limitation")
    context_description: Optional[str] = Field(None, description="Detailed context description")


class ChannelResponse(BaseModel):
    id: UUID
    name: str
    provider_id: UUID
    provider_name: Optional[str] = None
    system_prompt: Optional[str]
    personality_name: Optional[str]
    # Context guard fields
    context: Optional[str] = None
    context_description: Optional[str] = None
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
            context=obj.context,
            context_description=obj.context_description,
            is_default=obj.is_default,
            created_at=obj.created_at.isoformat() if obj.created_at else None,
            embed_enabled=obj.embed_enabled,
            embed_config=obj.embed_config,
        )


class EmbedConfigUpdate(BaseModel):
    public: bool = Field(default=True, description="If true, no token required")
    save_history: bool = Field(default=True, description="Save chat history to localStorage")
    stream_mode: bool = Field(default=True, description="If true, stream responses; if false, wait for complete response")
    regenerate_token: bool = Field(default=False, description="Generate new embed token")
    # Header settings
    header_title: Optional[str] = Field(default=None, max_length=50, description="Header title (optional, max 50 chars)")
    # Theme settings
    theme: str = Field(default="dark", description="Theme preset: 'light' or 'dark'")
    primary_color: str = Field(default="#6366f1", description="Primary/accent color (hex)")
    bg_color: Optional[str] = Field(default=None, description="Background color (hex, optional)")
    text_color: Optional[str] = Field(default=None, description="Text color (hex, optional)")
    font_family: Optional[str] = Field(default=None, description="Font family (optional)")
    # Bubble style
    bubble_style: str = Field(default="rounded", description="Bubble shape: 'rounded', 'square', 'minimal'")
    # Custom styling
    custom_css_url: Optional[str] = Field(default=None, description="URL to custom CSS file for radical styling")


class EmbedConfigResponse(BaseModel):
    embed_enabled: bool
    embed_url: Optional[str] = None
    public: bool
    save_history: bool
    stream_mode: bool
    has_token: bool
    # Header settings
    header_title: Optional[str] = None
    # Theme settings
    theme: str = "dark"
    primary_color: str = "#6366f1"
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    font_family: Optional[str] = None
    # Bubble style
    bubble_style: str = "rounded"
    # Custom styling
    custom_css_url: Optional[str] = None


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
        context=data.context,
        context_description=data.context_description,
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
    config["stream_mode"] = data.stream_mode
    # Header settings
    if data.header_title:
        config["header_title"] = data.header_title
    elif "header_title" in config:
        del config["header_title"]  # Remove if not provided
    # Theme settings
    config["theme"] = data.theme
    config["primary_color"] = data.primary_color
    if data.bg_color:
        config["bg_color"] = data.bg_color
    if data.text_color:
        config["text_color"] = data.text_color
    if data.font_family:
        config["font_family"] = data.font_family
    # Bubble style (shape)
    config["bubble_style"] = data.bubble_style
    # Custom CSS URL for radical styling
    if data.custom_css_url:
        config["custom_css_url"] = data.custom_css_url
    elif "custom_css_url" in config:
        del config["custom_css_url"]
    channel.embed_config = config
    channel.embed_enabled = True

    # Flag JSONB column as modified so SQLAlchemy detects the change
    flag_modified(channel, "embed_config")

    await db.commit()
    await db.refresh(channel)

    # Build embed URL with theme params
    embed_url = f"/embed/{channel.id}"
    params = []
    if not data.public:
        params.append(f"token={channel.embed_token}")
    # Add theme params
    if data.theme and data.theme != "dark":
        params.append(f"theme={data.theme}")
    if data.primary_color and data.primary_color != "#6366f1":
        params.append(f"primaryColor={data.primary_color.replace('#', '%23')}")
    if data.bg_color:
        params.append(f"bgColor={data.bg_color.replace('#', '%23')}")
    if data.text_color:
        params.append(f"textColor={data.text_color.replace('#', '%23')}")
    if data.font_family:
        params.append(f"font={data.font_family.replace(' ', '+')}")
    if data.bubble_style and data.bubble_style != "rounded":
        params.append(f"bubble={data.bubble_style}")

    if params:
        embed_url += "?" + "&".join(params)

    return EmbedConfigResponse(
        embed_enabled=True,
        embed_url=embed_url,
        public=data.public,
        save_history=data.save_history,
        stream_mode=data.stream_mode,
        has_token=bool(channel.embed_token),
        header_title=data.header_title,
        theme=data.theme,
        primary_color=data.primary_color,
        bg_color=data.bg_color,
        text_color=data.text_color,
        font_family=data.font_family,
        bubble_style=data.bubble_style,
        custom_css_url=data.custom_css_url,
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
        params = []
        if not config.get("public", True):
            params.append(f"token={channel.embed_token}")
        # Add theme params
        theme = config.get("theme", "dark")
        primary_color = config.get("primary_color", "#6366f1")
        bg_color = config.get("bg_color")
        text_color = config.get("text_color")
        font_family = config.get("font_family")

        if theme and theme != "dark":
            params.append(f"theme={theme}")
        if primary_color and primary_color != "#6366f1":
            params.append(f"primaryColor={primary_color.replace('#', '%23')}")
        if bg_color:
            params.append(f"bgColor={bg_color.replace('#', '%23')}")
        if text_color:
            params.append(f"textColor={text_color.replace('#', '%23')}")
        if font_family:
            params.append(f"font={font_family.replace(' ', '+')}")
        bubble_style = config.get("bubble_style", "rounded")
        if bubble_style != "rounded":
            params.append(f"bubble={bubble_style}")

        if params:
            embed_url += "?" + "&".join(params)

    return EmbedConfigResponse(
        embed_enabled=channel.embed_enabled,
        embed_url=embed_url,
        public=config.get("public", True),
        save_history=config.get("save_history", True),
        stream_mode=config.get("stream_mode", True),
        has_token=bool(channel.embed_token),
        header_title=config.get("header_title"),
        theme=config.get("theme", "dark"),
        primary_color=config.get("primary_color", "#6366f1"),
        bg_color=config.get("bg_color"),
        text_color=config.get("text_color"),
        font_family=config.get("font_family"),
        bubble_style=config.get("bubble_style", "rounded"),
        custom_css_url=config.get("custom_css_url"),
    )


class PublicEmbedConfig(BaseModel):
    """Public embed config - safe to expose without authentication."""
    save_history: bool = True
    header_title: Optional[str] = None
    theme: str = "dark"
    primary_color: str = "#6366f1"
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    bubble_style: str = "rounded"
    custom_css_url: Optional[str] = None


@router.get("/{channel_id}/embed/public", response_model=PublicEmbedConfig)
async def get_public_embed_config(
    channel_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
):
    """Get public embed configuration - no API key required.

    This endpoint is used by the embed widget to fetch theme/settings.
    Only returns safe, non-sensitive configuration.
    """
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if not channel.embed_enabled:
        raise HTTPException(status_code=403, detail="Embed not enabled for this channel")

    config = channel.embed_config or {}

    return PublicEmbedConfig(
        save_history=config.get("save_history", True),
        header_title=config.get("header_title"),
        theme=config.get("theme", "dark"),
        primary_color=config.get("primary_color", "#6366f1"),
        bg_color=config.get("bg_color"),
        text_color=config.get("text_color"),
        bubble_style=config.get("bubble_style", "rounded"),
        custom_css_url=config.get("custom_css_url"),
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
