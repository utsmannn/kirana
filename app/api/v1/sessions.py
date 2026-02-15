import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.channel import Channel
from app.models.conversation import ConversationLog
from app.models.session import Session
from app.schemas.session import (
    SessionCreate,
    SessionListResponse,
    SessionMessagesResponse,
    SessionResponse,
    SessionUpdate,
)

router = APIRouter()


@router.post("/", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_in: SessionCreate,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    # Determine channel_id
    channel_id = session_in.channel_id
    if not channel_id:
        # Get default channel
        result = await db.execute(
            select(Channel).where(Channel.is_default == True)
        )
        default_channel = result.scalar_one_or_none()
        channel_id = default_channel.id if default_channel else None

    session = Session(
        name=session_in.name,
        channel_id=channel_id,
        extra_metadata=session_in.metadata or {},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/", response_model=SessionListResponse)
async def list_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    query = select(Session)
    if is_active is not None:
        query = query.where(Session.is_active == is_active)

    # Count total
    total_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0

    # Get items
    query = (
        query.order_by(desc(Session.created_at))
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


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: uuid.UUID,
    session_in: SessionUpdate,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    update_data = session_in.model_dump(exclude_unset=True)
    if "metadata" in update_data:
        update_data["extra_metadata"] = update_data.pop("metadata")

    for field, value in update_data.items():
        setattr(session, field, value)

    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete(session)
    await db.commit()
    return None


@router.get("/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_session_messages(
    session_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    # Verify session exists
    s_result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    if not s_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    query = select(ConversationLog).where(ConversationLog.session_id == session_id)

    # Count total
    total_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0

    # Get items
    query = (
        query.order_by(ConversationLog.created_at)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)
    messages = result.scalars().all()

    return {
        "session_id": session_id,
        "messages": messages,
        "total": total,
        "page": page,
        "limit": limit,
    }
