import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.knowledge import Knowledge
from app.schemas.knowledge import (
    KnowledgeCreate,
    KnowledgeListResponse,
    KnowledgeResponse,
    KnowledgeUpdate,
)

router = APIRouter()


@router.post(
    "/", response_model=KnowledgeResponse, status_code=status.HTTP_201_CREATED
)
async def create_knowledge(
    knowledge_in: KnowledgeCreate,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db_session),
):
    knowledge = Knowledge(
        title=knowledge_in.title,
        content=knowledge_in.content,
        content_type=knowledge_in.content_type,
        extra_metadata=knowledge_in.metadata or {},
    )
    db.add(knowledge)
    await db.commit()
    await db.refresh(knowledge)
    return knowledge


@router.get("/", response_model=KnowledgeListResponse)
async def list_knowledge(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    content_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db_session),
):
    query = select(Knowledge)

    if search:
        query = query.where(
            or_(
                Knowledge.title.ilike(f"%{search}%"),
                Knowledge.content.ilike(f"%{search}%"),
            )
        )

    if content_type:
        query = query.where(Knowledge.content_type == content_type)

    if is_active is not None:
        query = query.where(Knowledge.is_active == is_active)

    # Count total
    total_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0

    # Get items
    query = (
        query.order_by(desc(Knowledge.created_at))
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/{knowledge_id}", response_model=KnowledgeResponse)
async def get_knowledge(
    knowledge_id: uuid.UUID,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db_session),
):
    result = await db.execute(
        select(Knowledge).where(Knowledge.id == knowledge_id)
    )
    knowledge = result.scalar_one_or_none()
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return knowledge


@router.patch("/{knowledge_id}", response_model=KnowledgeResponse)
async def update_knowledge(
    knowledge_id: uuid.UUID,
    knowledge_in: KnowledgeUpdate,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db_session),
):
    result = await db.execute(
        select(Knowledge).where(Knowledge.id == knowledge_id)
    )
    knowledge = result.scalar_one_or_none()
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    update_data = knowledge_in.model_dump(exclude_unset=True)
    if "metadata" in update_data:
        update_data["extra_metadata"] = update_data.pop("metadata")

    for field, value in update_data.items():
        setattr(knowledge, field, value)

    await db.commit()
    await db.refresh(knowledge)
    return knowledge


@router.delete("/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge(
    knowledge_id: uuid.UUID,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db_session),
):
    result = await db.execute(
        select(Knowledge).where(Knowledge.id == knowledge_id)
    )
    knowledge = result.scalar_one_or_none()
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    await db.delete(knowledge)
    await db.commit()
    return None
