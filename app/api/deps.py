from fastapi import Depends, HTTPException, Security, status
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


async def get_db_session(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    """Get database session."""
    return db
