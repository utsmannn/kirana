from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.personality import Personality
from app.schemas.personality import PersonalityListResponse, PersonalityResponse

router = APIRouter()


@router.get("/", response_model=PersonalityListResponse)
async def list_personalities(
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db)
):
    """List all personality templates."""
    result = await db.execute(
        select(Personality).where(
            Personality.is_template == True
        )
    )
    personalities = result.scalars().all()
    return {"templates": personalities}


@router.get("/{slug}", response_model=PersonalityResponse)
async def get_personality(
    slug: str,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db)
):
    """Get a specific personality template."""
    result = await db.execute(
        select(Personality).where(
            Personality.slug == slug,
            Personality.is_template == True
        )
    )
    personality = result.scalar_one_or_none()
    if not personality:
        raise HTTPException(status_code=404, detail="Personality template not found")
    return personality
