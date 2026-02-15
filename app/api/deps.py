from typing import Optional

from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db

security_scheme = HTTPBearer()


async def verify_api_key(
    token: HTTPAuthorizationCredentials = Security(security_scheme)
) -> str:
    """Verify the API key matches the configured KIRANA_API_KEY."""
    api_key = token.credentials

    if api_key != settings.KIRANA_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return api_key


async def verify_api_key_optional(
    token: Optional[HTTPAuthorizationCredentials] = Security(
        HTTPBearer(auto_error=False)
    ),
    api_key: Optional[str] = Query(None, description="API key (alternative to header)")
) -> str:
    """
    Verify API key from either Authorization header or query parameter.

    This is useful for endpoints that need to be accessible from img tags,
    iframes, etc. where custom headers cannot be set.
    """
    # Try header first
    if token:
        key = token.credentials
    elif api_key:
        key = api_key
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required (via Authorization header or api_key query param)",
        )

    if key != settings.KIRANA_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return key


async def verify_api_key_or_embed_token(
    token: Optional[HTTPAuthorizationCredentials] = Security(
        HTTPBearer(auto_error=False)
    ),
    embed_token: Optional[str] = Query(None, description="Embed token for embed access"),
    db: AsyncSession = Depends(get_db),
) -> tuple[str, bool]:
    """Verify API key OR embed token.

    Returns tuple of (auth_value, is_embed) where:
    - auth_value is the API key or embed token
    - is_embed is True if authenticated via embed_token

    For embed tokens, also validates:
    - Token exists in a channel
    - Embed is enabled for that channel
    """
    # Try API key first
    if token:
        if token.credentials == settings.KIRANA_API_KEY:
            return (token.credentials, False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Try embed token
    if embed_token:
        from app.models.channel import Channel

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

    # No auth provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (API key or embed token)",
    )


async def get_db_session(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    """Get database session."""
    return db
