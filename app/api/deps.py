from typing import Optional

from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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


async def get_db_session(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    """Get database session."""
    return db
