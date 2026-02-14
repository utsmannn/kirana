from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.usage import UsageLog

router = APIRouter()


@router.get("/")
async def get_usage(
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db)
):
    """Get global usage stats for the last 30 days."""
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    result = await db.execute(
        select(
            func.count(UsageLog.id).label("total_requests"),
            func.sum(UsageLog.tokens_input).label("total_input_tokens"),
            func.sum(UsageLog.tokens_output).label("total_output_tokens")
        ).where(
            UsageLog.created_at >= thirty_days_ago
        )
    )
    stats = result.first()

    return {
        "period": "last_30_days",
        "totals": {
            "requests": stats.total_requests or 0,
            "tokens_input": int(stats.total_input_tokens or 0),
            "tokens_output": int(stats.total_output_tokens or 0),
            "total_tokens": int((stats.total_input_tokens or 0) + (stats.total_output_tokens or 0))
        }
    }
