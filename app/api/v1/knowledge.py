import logging
import os
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.config import settings
from app.models.knowledge import Knowledge
from app.schemas.knowledge import (
    KnowledgeCreate,
    KnowledgeListResponse,
    KnowledgeResponse,
    KnowledgeUpdate,
    WebCrawlRequest,
    WebCrawlResponse,
    WebScrapeRequest,
    WebScrapeResponse,
)
from app.services.file_processor import FileProcessor, get_mime_type
from app.services.rag_ingestion import index_knowledge
from app.services.web_scraper import crawl_website, scrape_single_url

logger = logging.getLogger(__name__)

router = APIRouter()

# Upload directory for knowledge files (from config, defaults to /app/uploads)
UPLOAD_DIR = Path(settings.UPLOAD_DIR) / "knowledge"
try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass  # handled later during actual upload
logger.info("[KNOWLEDGE] Upload directory: %s", UPLOAD_DIR)

@router.post(
    "/", response_model=KnowledgeResponse, status_code=status.HTTP_201_CREATED
)
async def create_knowledge(
    knowledge_in: KnowledgeCreate,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    knowledge = Knowledge(
        title=knowledge_in.title,
        content=knowledge_in.content,
        content_type=knowledge_in.content_type,
        extra_metadata=knowledge_in.metadata or {},
        processing_status="ready",
    )
    db.add(knowledge)
    await db.flush()
    await index_knowledge(db, knowledge)
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
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
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
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
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
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
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

    should_reindex = any(
        field in update_data
        for field in ("title", "content", "content_type", "extra_metadata", "is_active")
    )

    for field, value in update_data.items():
        setattr(knowledge, field, value)

    if should_reindex:
        await index_knowledge(db, knowledge)

    await db.commit()
    await db.refresh(knowledge)
    return knowledge


@router.delete("/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge(
    knowledge_id: uuid.UUID,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    result = await db.execute(
        select(Knowledge).where(Knowledge.id == knowledge_id)
    )
    knowledge = result.scalar_one_or_none()
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    # Delete associated file if exists
    if knowledge.file_path and os.path.exists(knowledge.file_path):
        os.remove(knowledge.file_path)

    await db.delete(knowledge)
    await db.commit()
    return None


@router.post("/upload", response_model=KnowledgeResponse, status_code=status.HTTP_201_CREATED)
async def upload_knowledge_file(
    file: UploadFile = File(..., description="File to upload (PDF, DOCX, XLSX, PPTX, images, etc.)"),
    title: Optional[str] = Form(None, description="Title for the knowledge item"),
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    """Upload a file and return immediately with status "processing".

    The file is saved and a Knowledge row is created instantly with
    status "processing". Heavy work (parsing, vision analysis, AI
    summarization, chunking, embedding) runs in the background via
    asyncio.create_task.

    Poll GET /v1/knowledge/{id} and check extra_metadata.processing_status:
      - "processing" → still running
      - "ready"      → done, content + chunks available
      - "failed"     → check extra_metadata.processing_error
    """
    import asyncio as _asyncio

    from app.services.knowledge_processor import process_upload

    # ----- validate -----
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    mime_type = file.content_type or get_mime_type(file.filename)

    if not FileProcessor.is_supported(mime_type):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {mime_type}. "
                   "Supported types: images, PDF, Word, Excel, PowerPoint, text files",
        )

    content = await file.read()
    file_size = len(content)
    if file_size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    # ----- save file -----
    file_ext = Path(file.filename).suffix
    stored_name = f"{uuid.uuid4()}{file_ext}"
    file_path = UPLOAD_DIR / stored_name
    with open(file_path, "wb") as f:
        f.write(content)

    # ----- create Knowledge row immediately -----
    knowledge = Knowledge(
        title=title or file.filename,
        content="",                                          # filled by background processor
        content_type=mime_type.split("/")[-1][:50],
        source_type="upload",
        file_path=str(file_path),
        file_name=file.filename,
        file_size=file_size,
        mime_type=mime_type,
        extra_metadata={
            "original_filename": file.filename,
            "mime_type": mime_type,
            "file_size": file_size,
        },
        processing_status="processing",
    )
    db.add(knowledge)
    await db.flush()
    await db.commit()
    await db.refresh(knowledge)

    logger.info("[UPLOAD] Knowledge %s created (status=processing), dispatching background processor", knowledge.id)

    # ----- fire-and-forget background processing -----
    knowledge_id = knowledge.id
    _asyncio.create_task(process_upload(knowledge_id))

    return knowledge


@router.post("/scrape-web", response_model=WebScrapeResponse, status_code=status.HTTP_201_CREATED)
async def scrape_web_url(
    request: WebScrapeRequest,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    """Scrape a single URL and create knowledge entry."""
    logger.info("[WEB_SCRAPE] Scraping URL: %s", request.url)

    try:
        result = await scrape_single_url(request.url)

        if not result.success:
            return WebScrapeResponse(
                success=False,
                url=request.url,
                title="",
                content="",
                content_length=0,
                error=result.error or "Failed to scrape URL",
            )

        # Create knowledge entry
        knowledge = Knowledge(
            title=result.title,
            content=result.content,
            content_type="web",
            source_type="web",
            source_url=result.url,
            extra_metadata={
                "scraped_at": result.url,
                "content_length": len(result.content),
            },
        )
        db.add(knowledge)
        await db.flush()
        await index_knowledge(db, knowledge)
        await db.commit()
        await db.refresh(knowledge)

        logger.info("[WEB_SCRAPE] Created knowledge %s from %s", knowledge.id, request.url)

        return WebScrapeResponse(
            success=True,
            url=result.url,
            title=result.title,
            content=result.content,
            content_length=len(result.content),
        )

    except Exception as e:
        logger.exception("[WEB_SCRAPE] Error scraping %s: %s", request.url, e)
        return WebScrapeResponse(
            success=False,
            url=request.url,
            title="",
            content="",
            content_length=0,
            error=str(e),
        )


@router.post("/crawl-web", response_model=WebCrawlResponse, status_code=status.HTTP_201_CREATED)
async def crawl_web_site(
    request: WebCrawlRequest,
    auth: tuple = Depends(deps.verify_api_key_or_admin_token),
    db: AsyncSession = Depends(deps.get_db_session),
):
    """Crawl a website and create ONE combined knowledge entry with all pages."""
    logger.info(
        "[WEB_CRAWL] Crawling %s (max_pages=%d, max_depth=%d)",
        request.url, request.max_pages, request.max_depth
    )

    try:
        result = await crawl_website(
            start_url=request.url,
            max_pages=request.max_pages,
            max_depth=request.max_depth,
            path_prefix=request.path_prefix,
        )

        # Combine all successful pages into ONE knowledge entry
        successful_pages = [p for p in result.pages if p.success and p.content.strip()]

        if not successful_pages:
            return WebCrawlResponse(
                success=False,
                start_url=request.url,
                total_pages=result.total_pages,
                successful_pages=0,
                failed_pages=result.failed_pages,
                knowledge_ids=[],
                errors=["No content could be extracted from any page"],
            )

        # Build combined content with page separators
        combined_parts = []
        page_urls = []

        for page in successful_pages:
            page_urls.append(page.url)
            combined_parts.append(f"## Page: {page.title}\n**URL:** {page.url}\n\n{page.content}")

        combined_content = "\n\n---\n\n".join(combined_parts)

        # Extract main title from first page or URL
        main_title = successful_pages[0].title if successful_pages else urlparse(request.url).netloc
        if len(successful_pages) > 1:
            main_title = f"{main_title} (and {len(successful_pages) - 1} more pages)"

        # Create SINGLE knowledge entry
        knowledge = Knowledge(
            title=main_title,
            content=combined_content,
            content_type="web",
            source_type="web",
            source_url=request.url,
            extra_metadata={
                "crawl_type": "multi_page",
                "pages_crawled": len(successful_pages),
                "page_urls": page_urls,
                "total_content_length": len(combined_content),
            },
        )
        db.add(knowledge)
        await db.flush()
        await index_knowledge(db, knowledge)
        await db.commit()
        await db.refresh(knowledge)

        logger.info(
            "[WEB_CRAWL] Created 1 combined knowledge entry from %d pages (%s)",
            len(successful_pages), request.url
        )

        return WebCrawlResponse(
            success=True,
            start_url=request.url,
            total_pages=result.total_pages,
            successful_pages=result.successful_pages,
            failed_pages=result.failed_pages,
            knowledge_ids=[knowledge.id],
            errors=result.errors[:5] if result.errors else [],
        )

    except Exception as e:
        logger.exception("[WEB_CRAWL] Error crawling %s: %s", request.url, e)
        return WebCrawlResponse(
            success=False,
            start_url=request.url,
            total_pages=0,
            successful_pages=0,
            failed_pages=1,
            knowledge_ids=[],
            errors=[str(e)],
        )


@router.get("/{knowledge_id}/download")
async def download_knowledge_file(
    knowledge_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db_session),
    api_key: str = Depends(deps.verify_api_key_optional),
):
    """Download the original file for a knowledge item.

    Supports auth via Authorization header or api_key query parameter.
    """
    result = await db.execute(
        select(Knowledge).where(Knowledge.id == knowledge_id)
    )
    knowledge = result.scalar_one_or_none()
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    if not knowledge.file_path or not os.path.exists(knowledge.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=knowledge.file_path,
        filename=knowledge.file_name or "download",
        media_type=knowledge.mime_type or "application/octet-stream"
    )
