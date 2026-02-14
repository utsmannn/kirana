import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str


def _generate_admin_token() -> str:
    raw = f"{settings.SECRET_KEY}:{settings.ADMIN_PASSWORD}:{int(time.time() // 86400)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_admin_token(token: str) -> bool:
    today_token = _generate_admin_token()
    yesterday_raw = f"{settings.SECRET_KEY}:{settings.ADMIN_PASSWORD}:{int(time.time() // 86400) - 1}"
    yesterday_token = hashlib.sha256(yesterday_raw.encode()).hexdigest()
    return hmac.compare_digest(token, today_token) or hmac.compare_digest(token, yesterday_token)


@router.post("/login", response_model=LoginResponse)
async def admin_login(req: LoginRequest):
    if not hmac.compare_digest(req.password, settings.ADMIN_PASSWORD):
        logger.warning("Failed admin login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )

    token = _generate_admin_token()
    logger.info("Admin login successful")
    return LoginResponse(token=token)


@router.get("/verify")
async def verify_token(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = auth[7:]
    if not verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {"valid": True}
