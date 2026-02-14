import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models.base import Base


async def init_db():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        # For simplicity in this demo, we drop and recreate
        # In production, use migrations
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_db())
