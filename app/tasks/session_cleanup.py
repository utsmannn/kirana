import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select, update

from app.config import settings
from app.db.session import async_session
from app.models.conversation import ConversationLog
from app.models.session import Session

logger = logging.getLogger(__name__)


async def cleanup_expired_sessions():
    async with async_session() as db:
        try:
            now = datetime.now(timezone.utc)
            expiry_threshold = now - timedelta(days=settings.SESSION_EXPIRY_DAYS)
            deletion_threshold = now - timedelta(days=settings.SESSION_DELETION_DAYS)

            # Mark as inactive
            result = await db.execute(
                update(Session)
                .where(Session.last_activity < expiry_threshold)
                .where(Session.is_active)
                .values(is_active=False, updated_at=now)
            )
            marked_count = result.rowcount
            await db.commit()

            if marked_count:
                logger.info("Marked %d sessions as inactive", marked_count)

            # Delete old sessions
            sessions_to_delete = await db.execute(
                select(Session.id)
                .where(~Session.is_active)
                .where(Session.last_activity < deletion_threshold)
            )
            session_ids = list(sessions_to_delete.scalars().all())

            if session_ids:
                await db.execute(
                    delete(ConversationLog).where(
                        ConversationLog.session_id.in_(session_ids)
                    )
                )
                await db.execute(delete(Session).where(Session.id.in_(session_ids)))
                await db.commit()
                logger.info("Deleted %d expired sessions", len(session_ids))

        except Exception:
            logger.exception("Session cleanup failed")
            await db.rollback()


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        cleanup_expired_sessions,
        "interval",
        hours=settings.SESSION_CLEANUP_INTERVAL_HOURS,
        id="session_cleanup",
    )
    return scheduler
