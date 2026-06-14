from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.channel import Channel
from app.models.channel_mcp_server import ChannelMcpServer
from app.services.mcp_http_client import test_mcp_connection

router = APIRouter()

VALID_TRANSPORTS = ("sse", "http", "stdio")
VALID_AUTH_TYPES = ("none", "bearer", "custom_header")
REMOTE_TRANSPORTS = ("sse", "http")


def _validate_transport(value: str) -> str:
    value = value.lower()
    if value not in VALID_TRANSPORTS:
        raise ValueError("transport must be 'sse', 'http', or 'stdio'")
    return value


def _validate_auth_type(value: str) -> str:
    value = value.lower()
    if value not in VALID_AUTH_TYPES:
        raise ValueError("auth_type must be 'none', 'bearer', or 'custom_header'")
    return value


def _validate_server_url(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("server_url must use http:// or https://")
    return value


def _validate_stdio_config(server_config: Dict[str, Any]) -> None:
    command = server_config.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("server_config.command is required for stdio transport")

    args = server_config.get("args", [])
    if args is not None and (
        not isinstance(args, list) or not all(isinstance(arg, str) for arg in args)
    ):
        raise ValueError("server_config.args must be a list of strings")

    env = server_config.get("env", {})
    if env is not None and (
        not isinstance(env, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())
    ):
        raise ValueError("server_config.env must be an object with string keys and values")

    cwd = server_config.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise ValueError("server_config.cwd must be a string")


def _validate_mcp_config(
    transport: str,
    server_url: Optional[str],
    server_config: Optional[Dict[str, Any]],
    auth_type: str,
) -> None:
    if transport in REMOTE_TRANSPORTS:
        if not server_url:
            raise ValueError("server_url is required for sse/http transport")
        _validate_server_url(server_url)
        return

    if transport == "stdio":
        _validate_stdio_config(server_config or {})
        if auth_type != "none":
            raise ValueError("stdio transport must use auth_type 'none'; put credentials in server_config.env")
        return

    raise ValueError("Unsupported MCP transport")


class McpServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    server_url: Optional[str] = Field(default=None, min_length=1)
    transport: str = Field(default="sse")
    auth_type: str = Field(default="none")
    auth_config: Optional[Dict[str, Any]] = Field(default=None)
    server_config: Optional[Dict[str, Any]] = Field(default=None)

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, value: str) -> str:
        return _validate_transport(value)

    @field_validator("auth_type")
    @classmethod
    def validate_auth_type(cls, value: str) -> str:
        return _validate_auth_type(value)

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_server_url(value)

    @model_validator(mode="after")
    def validate_config(self) -> "McpServerCreate":
        _validate_mcp_config(
            self.transport,
            self.server_url,
            self.server_config,
            self.auth_type,
        )
        return self


class McpServerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    server_url: Optional[str] = Field(default=None, min_length=1)
    transport: Optional[str] = Field(default=None)
    auth_type: Optional[str] = Field(default=None)
    auth_config: Optional[Dict[str, Any]] = Field(default=None)
    server_config: Optional[Dict[str, Any]] = Field(default=None)
    is_active: Optional[bool] = None

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_transport(value)

    @field_validator("auth_type")
    @classmethod
    def validate_auth_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_auth_type(value)

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_server_url(value)


class McpServerResponse(BaseModel):
    id: UUID
    channel_id: UUID
    name: str
    server_url: Optional[str]
    transport: str
    auth_type: str
    auth_configured: bool
    server_configured: bool
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_orm(cls, obj: ChannelMcpServer) -> "McpServerResponse":
        server_config = obj.server_config or {}
        return cls(
            id=obj.id,
            channel_id=obj.channel_id,
            name=obj.name,
            server_url=obj.server_url,
            transport=obj.transport,
            auth_type=obj.auth_type,
            auth_configured=bool(obj.auth_config),
            server_configured=bool(server_config.get("command") if obj.transport == "stdio" else server_config),
            is_active=obj.is_active,
            created_at=obj.created_at.isoformat() if obj.created_at else None,
            updated_at=obj.updated_at.isoformat() if obj.updated_at else None,
        )


class McpServerTestResponse(BaseModel):
    success: bool
    message: str
    tools: List[Dict[str, Any]]


async def _get_channel(channel_id: UUID, db: AsyncSession) -> Channel:
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return channel


async def _get_server(channel_id: UUID, server_id: UUID, db: AsyncSession) -> ChannelMcpServer:
    result = await db.execute(
        select(ChannelMcpServer).where(
            ChannelMcpServer.id == server_id,
            ChannelMcpServer.channel_id == channel_id,
        )
    )
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    return server


@router.get("/", response_model=List[McpServerResponse])
async def list_mcp_servers(
    channel_id: UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """List MCP servers configured for a channel."""
    await _get_channel(channel_id, db)
    result = await db.execute(
        select(ChannelMcpServer)
        .where(ChannelMcpServer.channel_id == channel_id)
        .order_by(ChannelMcpServer.created_at.desc())
    )
    servers = result.scalars().all()
    return [McpServerResponse.from_orm(s) for s in servers]


@router.post("/", response_model=McpServerResponse, status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    channel_id: UUID,
    data: McpServerCreate,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Add an MCP server to a channel."""
    await _get_channel(channel_id, db)
    server = ChannelMcpServer(
        channel_id=channel_id,
        name=data.name,
        server_url=None if data.transport == "stdio" else data.server_url,
        transport=data.transport,
        auth_type=data.auth_type,
        auth_config=data.auth_config or {},
        server_config=data.server_config or {},
        is_active=True,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return McpServerResponse.from_orm(server)


@router.get("/{server_id}", response_model=McpServerResponse)
async def get_mcp_server(
    channel_id: UUID,
    server_id: UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Get a single MCP server configuration."""
    server = await _get_server(channel_id, server_id, db)
    return McpServerResponse.from_orm(server)


@router.patch("/{server_id}", response_model=McpServerResponse)
async def update_mcp_server(
    channel_id: UUID,
    server_id: UUID,
    data: McpServerUpdate,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Update an MCP server configuration."""
    server = await _get_server(channel_id, server_id, db)

    update_data = data.model_dump(exclude_unset=True)
    effective_transport = update_data.get("transport", server.transport)
    effective_url = update_data.get("server_url", server.server_url)
    effective_config = update_data.get("server_config", server.server_config or {})
    effective_auth_type = update_data.get("auth_type", server.auth_type)

    _validate_mcp_config(
        effective_transport,
        effective_url,
        effective_config,
        effective_auth_type,
    )

    for field, value in update_data.items():
        setattr(server, field, value)

    if effective_transport == "stdio":
        server.server_url = None

    await db.commit()
    await db.refresh(server)
    return McpServerResponse.from_orm(server)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    channel_id: UUID,
    server_id: UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Remove an MCP server from a channel."""
    server = await _get_server(channel_id, server_id, db)
    await db.delete(server)
    await db.commit()


@router.post("/{server_id}/activate", response_model=McpServerResponse)
async def activate_mcp_server(
    channel_id: UUID,
    server_id: UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Activate an MCP server."""
    server = await _get_server(channel_id, server_id, db)
    server.is_active = True
    await db.commit()
    await db.refresh(server)
    return McpServerResponse.from_orm(server)


@router.post("/{server_id}/deactivate", response_model=McpServerResponse)
async def deactivate_mcp_server(
    channel_id: UUID,
    server_id: UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Deactivate an MCP server."""
    server = await _get_server(channel_id, server_id, db)
    server.is_active = False
    await db.commit()
    await db.refresh(server)
    return McpServerResponse.from_orm(server)


@router.post("/{server_id}/test", response_model=McpServerTestResponse)
async def test_mcp_server(
    channel_id: UUID,
    server_id: UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Test connectivity to an MCP server and list discovered tools."""
    server = await _get_server(channel_id, server_id, db)
    result = await test_mcp_connection(
        server_url=server.server_url,
        transport=server.transport,
        auth_type=server.auth_type,
        auth_config=server.auth_config or {},
        server_config=server.server_config or {},
    )
    return McpServerTestResponse(**result)
