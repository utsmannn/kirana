import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.config import settings
from app.core.exceptions import (
    KiranaException,
    generic_exception_handler,
    http_exception_handler,
    kirana_exception_handler,
)
from app.core.rate_limit import RateLimitMiddleware
from app.db.session import engine
from app.models.channel import Channel
from app.models.provider import ProviderCredential
from app.tasks.session_cleanup import setup_scheduler

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PANEL_DIR = Path(__file__).resolve().parent.parent / "web" / "build"


def run_migrations():
    """Run database migrations on startup.

    Uses subprocess to avoid async event loop conflicts with alembic's asyncio runner.
    """
    import subprocess
    import sys

    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Database migrations applied successfully")
    except subprocess.CalledProcessError as e:
        logger.error("Failed to run migrations: %s", e.stderr)
        raise


async def seed_default_data():
    """Seed default provider and channel from .env if not exists."""
    from sqlalchemy import select, text
    from app.db.session import async_session

    async with async_session() as db:
        try:
            # Try to acquire advisory lock
            lock_result = await db.execute(text("SELECT pg_try_advisory_lock(12345)"))
            has_lock = lock_result.scalar()

            if not has_lock:
                logger.debug("Another worker is seeding, skipping")
                return

            try:
                # Check if default provider exists
                result = await db.execute(
                    select(ProviderCredential).where(ProviderCredential.is_default == True)
                )
                default_provider = result.scalar_one_or_none()

                if not default_provider:
                    # Create default provider from .env
                    default_provider = ProviderCredential(
                        name="Default (.env)",
                        model=settings.DEFAULT_MODEL,
                        api_key=settings.OPENAI_API_KEY or "",
                        base_url=settings.OPENAI_BASE_URL,
                        is_active=True,
                        is_default=True,
                        priority_order=0,
                    )
                    db.add(default_provider)
                    await db.commit()
                    await db.refresh(default_provider)
                    logger.info("Created default provider from .env settings")

                # Check if default channel exists
                result = await db.execute(
                    select(Channel).where(Channel.is_default == True)
                )
                default_channel = result.scalar_one_or_none()

                if not default_channel:
                    # Create default channel
                    channel = Channel(
                        name="Default Channel",
                        provider_id=default_provider.id,
                        system_prompt=None,
                        personality_name=None,
                        is_default=True,
                    )
                    db.add(channel)
                    await db.commit()
                    logger.info("Created default channel")
            finally:
                await db.execute(text("SELECT pg_advisory_unlock(12345)"))
        except Exception as e:
            logger.warning("Failed to seed default data: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (env=%s)", settings.APP_NAME, settings.APP_ENV)

    # Run database migrations
    try:
        run_migrations()
    except Exception as e:
        logger.warning("Failed to run migrations: %s", e)

    # Seed default provider and channel
    try:
        await seed_default_data()
    except Exception as e:
        logger.warning("Failed to seed default data: %s", e)

    scheduler = setup_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()
    logger.info("Shutdown complete")

app = FastAPI(
    title=settings.APP_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if not settings.is_production else None,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Exception handlers
app.add_exception_handler(KiranaException, kirana_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# Admin panel (static SvelteKit build with SPA fallback)
if PANEL_DIR.exists():
    from starlette.responses import FileResponse

    class SPAStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except Exception:
                # File not found - serve index.html for SPA routing
                # Skip for _app/ assets and files with extensions
                if not path.startswith("_app/") and "." not in path.split("/")[-1]:
                    return await super().get_response("index.html", scope)
                raise

    app.mount(
        "/panel",
        SPAStaticFiles(directory=str(PANEL_DIR), html=True),
        name="panel",
    )

    # Embed HTML file path
    EMBED_HTML = Path(__file__).resolve().parent / "static" / "embed" / "index.html"

    @app.get("/embed/{channel_id}", response_class=HTMLResponse)
    async def embed_page(channel_id: str):
        """Serve embed chat page."""
        return HTMLResponse(content=EMBED_HTML.read_text(), status_code=200)


@app.get("/health")
async def health_check():
    status_detail = {"app": settings.APP_NAME, "status": "ok"}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        status_detail["database"] = "ok"
    except Exception:
        status_detail["database"] = "unavailable"
        status_detail["status"] = "degraded"

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        status_detail["redis"] = "ok"
    except Exception:
        status_detail["redis"] = "unavailable"
        status_detail["status"] = "degraded"

    return status_detail
