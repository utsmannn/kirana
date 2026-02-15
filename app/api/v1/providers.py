from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.provider import ProviderCredential

router = APIRouter()


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field(..., min_length=1)
    base_url: Optional[str] = None


class ProviderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    model: Optional[str] = Field(None, min_length=1, max_length=100)
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class ProviderResponse(BaseModel):
    id: UUID
    name: str
    model: str
    base_url: Optional[str]
    is_active: bool
    is_default: bool
    priority_order: int
    created_at: str

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        # Convert datetime to string
        data = {
            "id": obj.id,
            "name": obj.name,
            "model": obj.model,
            "base_url": obj.base_url,
            "is_active": obj.is_active,
            "is_default": obj.is_default,
            "priority_order": obj.priority_order,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
        }
        return cls(**data)


class ProviderListResponse(BaseModel):
    providers: List[ProviderResponse]
    active_provider: Optional[ProviderResponse] = None


@router.get("/", response_model=ProviderListResponse)
async def list_providers(
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """List all provider credentials ordered by priority."""
    result = await db.execute(
        select(ProviderCredential).order_by(ProviderCredential.priority_order.asc())
    )
    providers = result.scalars().all()

    active = None
    for p in providers:
        if p.is_active:
            active = ProviderResponse.from_orm(p)
            break

    return {
        "providers": [ProviderResponse.from_orm(p) for p in providers],
        "active_provider": active
    }


@router.post("/", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    data: ProviderCreate,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Add a new provider credential."""
    # Get max priority order
    result = await db.execute(
        select(ProviderCredential).order_by(ProviderCredential.priority_order.desc()).limit(1)
    )
    max_provider = result.scalar_one_or_none()
    next_order = (max_provider.priority_order + 1) if max_provider else 1

    provider = ProviderCredential(
        name=data.name,
        model=data.model,
        api_key=data.api_key,
        base_url=data.base_url,
        priority_order=next_order,
        is_active=False,
        is_default=False,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return ProviderResponse.from_orm(provider)


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Get a specific provider credential."""
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return ProviderResponse.from_orm(provider)


@router.patch("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: UUID,
    data: ProviderUpdate,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Update a provider credential. Cannot update default provider."""
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if provider.is_default:
        raise HTTPException(status_code=400, detail="Cannot modify default provider from .env")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(provider, field, value)

    await db.commit()
    await db.refresh(provider)
    return ProviderResponse.from_orm(provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Delete a provider credential. Cannot delete default provider."""
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if provider.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default provider from .env")

    await db.delete(provider)
    await db.commit()


@router.post("/{provider_id}/activate", response_model=ProviderResponse)
async def activate_provider(
    provider_id: UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Set a provider as active (deactivates others)."""
    # First, deactivate all providers
    await db.execute(
        update(ProviderCredential).values(is_active=False)
    )

    # Then activate the selected one
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    provider.is_active = True
    await db.commit()
    await db.refresh(provider)
    return ProviderResponse.from_orm(provider)


@router.post("/{provider_id}/reorder", response_model=ProviderResponse)
async def reorder_provider(
    provider_id: UUID,
    new_order: int,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db),
):
    """Change the priority order of a provider (for fallback)."""
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    provider.priority_order = new_order
    await db.commit()
    await db.refresh(provider)
    return ProviderResponse.from_orm(provider)
