import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import litellm
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
from app.services.web_scraper import WebScraper, crawl_website, scrape_single_url
from app.services.zai_vision import get_zai_vision_service, is_zai_vision_configured

logger = logging.getLogger(__name__)

router = APIRouter()

# Upload directory for knowledge files (from config, defaults to /app/uploads)
UPLOAD_DIR = Path(settings.UPLOAD_DIR) / "knowledge"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
logger.info("[KNOWLEDGE] Upload directory: %s", UPLOAD_DIR)

# Supported types for Z.AI Vision analysis (images + PDFs)
VISION_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp',
    'application/pdf',
}

# Supported image types for Z.AI Vision analysis
SUPPORTED_IMAGE_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'
}


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

    for field, value in update_data.items():
        setattr(knowledge, field, value)

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
    """Upload a file and create knowledge entry with extracted text."""
    logger.info("[UPLOAD] Starting file upload process")

    # Validate file
    if not file.filename:
        logger.error("[UPLOAD] No filename provided")
        raise HTTPException(status_code=400, detail="No file provided")

    logger.info("[UPLOAD] File: %s, Content-Type: %s", file.filename, file.content_type)

    # Get mime type
    mime_type = file.content_type or get_mime_type(file.filename)
    logger.info("[UPLOAD] Resolved MIME type: %s", mime_type)

    # Check if file type is supported
    if not FileProcessor.is_supported(mime_type):
        logger.error("[UPLOAD] Unsupported MIME type: %s", mime_type)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {mime_type}. Supported types: images, PDF, Word, Excel, PowerPoint, text files"
        )

    logger.info("[UPLOAD] MIME type supported, reading file content...")

    # Read file content
    try:
        content = await file.read()
        file_size = len(content)
        logger.info("[UPLOAD] File size: %d bytes (%.2f MB)", file_size, file_size / (1024 * 1024))
    except Exception as e:
        logger.error("[UPLOAD] Failed to read file: %s", e)
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    # Validate file size (max 50MB)
    max_size = 50 * 1024 * 1024  # 50MB
    if file_size > max_size:
        logger.error("[UPLOAD] File too large: %d bytes (max %d)", file_size, max_size)
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    # Generate unique filename for storage
    file_ext = Path(file.filename).suffix
    stored_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = UPLOAD_DIR / stored_filename

    logger.info("[UPLOAD] Saving file to: %s", file_path)

    # Save file to disk
    try:
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info("[UPLOAD] File saved successfully")
    except Exception as e:
        logger.error("[UPLOAD] Failed to save file: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Initialize variables
    extracted_text = ""
    metadata = {
        'original_filename': file.filename,
        'mime_type': mime_type,
        'file_size': file_size,
    }

    # Check if file should be analyzed with Vision AI (images + PDFs)
    is_vision_type = mime_type in VISION_TYPES
    is_pdf = mime_type == 'application/pdf'
    is_image = mime_type in SUPPORTED_IMAGE_TYPES

    if is_vision_type:
        logger.info("[UPLOAD] %s detected",
                   "PDF" if is_pdf else "Image")

        # ============ PDF PROCESSING WITH FALLBACK ============
        if is_pdf:
            # Step 1: Try native text extraction with pypdf (fast)
            logger.info("[UPLOAD] Step 1: Attempting native PDF text extraction...")
            pdf_text, pdf_metadata = await FileProcessor.extract_pdf_text(content)
            metadata.update(pdf_metadata)

            if pdf_text and pdf_text.strip():
                # SUCCESS: Got text from native extraction
                logger.info("[UPLOAD] Native extraction successful: %d chars from %d pages",
                           len(pdf_text), pdf_metadata.get('pages_with_text', 0))

                # Step 2: Analyze extracted text with AI
                logger.info("[UPLOAD] Step 2: Analyzing extracted text with AI...")

                # Save raw extracted text to metadata
                metadata["raw_text"] = pdf_text
                metadata["raw_text_length"] = len(pdf_text)

                try:
                    # Use litellm same pattern as chat_service
                    model = settings.DEFAULT_MODEL or "gpt-4o-mini"
                    analysis_prompt = f"""Analisa dokumen berikut dan berikan:

1. RINGKASAN singkat (2-3 kalimat)
2. POIN-POIN PENTING dalam bullet points

Dokumen:
{pdf_text}

Format output:
## Ringkasan
[ringkasan singkat]

## Poin Penting
- [poin 1]
- [poin 2]
- dst..."""

                    completion_kwargs = {
                        "model": model,
                        "messages": [{"role": "user", "content": analysis_prompt}],
                        "temperature": 0.3,
                        "max_tokens": 2048,
                        "api_key": settings.OPENAI_API_KEY,
                        "timeout": 60,
                        "num_retries": 1,
                    }

                    # Add api_base if configured (same pattern as chat_service)
                    if settings.OPENAI_BASE_URL:
                        completion_kwargs["api_base"] = settings.OPENAI_BASE_URL
                        if "/" not in model:
                            completion_kwargs["model"] = f"openai/{model}"

                    response = await litellm.acompletion(**completion_kwargs)
                    ai_summary = response.choices[0].message.content or ""

                    # Combine: AI summary + raw text
                    extracted_text = f"""{ai_summary}

---

## Dokumen Asli

{pdf_text}"""

                    metadata["analysis_method"] = "native_extract_ai_analyze"
                    metadata["analysis_success"] = True
                    metadata["analysis_model"] = model
                    logger.info("[UPLOAD] AI analysis complete: %d chars (summary + raw)", len(extracted_text))

                except Exception as e:
                    # AI analysis failed, save raw text only
                    logger.warning("[UPLOAD] AI analysis failed, saving raw extracted text: %s", e)
                    extracted_text = pdf_text
                    metadata["analysis_method"] = "native_extract_only"
                    metadata["analysis_success"] = True
                    metadata["ai_analysis_error"] = str(e)

            else:
                # FAILED: Native extraction empty - likely scanned PDF
                logger.info("[UPLOAD] Native extraction empty (likely scanned PDF), falling back to Vision API...")

                # Check if Z.AI Vision is configured
                if not is_zai_vision_configured():
                    logger.error("[UPLOAD] Z.AI Vision not configured for scanned PDF fallback")
                    extracted_text = "[PDF Analysis Failed: Document appears to be scanned (no extractable text) and Z.AI Vision is not configured. Set ZAI_API_KEY to enable Vision analysis.]"
                    metadata["analysis_success"] = False
                    metadata["analysis_error"] = "scanned_pdf_no_vision"
                else:
                    # Step 3: Fallback to Vision API
                    try:
                        zai_vision = get_zai_vision_service()

                        logger.info("[UPLOAD] Converting PDF to images for Vision analysis...")
                        pages = await FileProcessor.pdf_to_images(content, dpi=150, timeout=60.0)
                        metadata["pdf_pages"] = len(pages)
                        logger.info("[UPLOAD] PDF has %d pages, sending to Vision API", len(pages))

                        # Limit pages to avoid timeout
                        max_pages = 15
                        if len(pages) > max_pages:
                            logger.warning("[UPLOAD] Limiting to first %d pages", max_pages)
                            pages = pages[:max_pages]

                        pdf_prompt = f"""This is a {len(pages)}-page scanned PDF document. Extract ALL text content from each page.

For each page:
1. Start with "--- Page X ---" header
2. Transcribe ALL visible text exactly as shown
3. For tables: recreate them in markdown format
4. Preserve the reading order

Be exhaustive - capture 100% of the text."""

                        result = await asyncio.wait_for(
                            zai_vision.analyze_multiple_images(images=pages, prompt=pdf_prompt),
                            timeout=120.0
                        )

                        if result["success"] and result.get("content"):
                            extracted_text = result["content"]
                            metadata["analysis_method"] = "vision_api_multimodal"
                            metadata["analysis_success"] = True
                            logger.info("[UPLOAD] Vision API analysis complete: %d chars", len(extracted_text))
                        else:
                            extracted_text = f"[PDF Analysis Failed: Vision API returned no content - {result.get('error', 'Unknown error')}]"
                            metadata["analysis_success"] = False
                            metadata["analysis_error"] = result.get("error", "no_content")

                    except asyncio.TimeoutError:
                        logger.error("[UPLOAD] Vision API timed out")
                        extracted_text = "[PDF Analysis Failed: Vision analysis timed out - PDF may be too large]"
                        metadata["analysis_success"] = False
                        metadata["analysis_error"] = "vision_timeout"
                    except Exception as e:
                        logger.exception("[UPLOAD] Vision API failed: %s", e)
                        extracted_text = f"[PDF Analysis Failed: {str(e)}]"
                        metadata["analysis_success"] = False
                        metadata["analysis_error"] = str(e)

        # ============ IMAGE PROCESSING ============
        else:
            # Direct image analysis
            if not is_zai_vision_configured():
                logger.warning("[UPLOAD] Z.AI Vision not configured for image analysis")
                extracted_text = "[Image uploaded but Z.AI Vision not configured. Set ZAI_API_KEY to enable analysis.]"
                metadata["analysis_success"] = False
                metadata["analysis_error"] = "vision_not_configured"
            else:
                try:
                    zai_vision = get_zai_vision_service()
                    result = await asyncio.wait_for(
                        zai_vision.analyze_image(
                            image_source=str(file_path),
                            prompt="Describe this image in detail. Include: 1) Main subjects/objects, 2) Colors and composition, 3) Any text visible in the image, 4) Overall mood/atmosphere, 5) Any other relevant details.",
                        ),
                        timeout=60.0
                    )

                    if result["success"] and result.get("content"):
                        extracted_text = result["content"]
                        metadata["analysis_method"] = "vision_api"
                        metadata["analysis_success"] = True
                    else:
                        extracted_text = f"[Image Analysis Failed: {result.get('error', 'Unknown error')}]"
                        metadata["analysis_success"] = False
                        metadata["analysis_error"] = result.get("error")

                except asyncio.TimeoutError:
                    extracted_text = "[Image Analysis Failed: Timeout]"
                    metadata["analysis_success"] = False
                    metadata["analysis_error"] = "timeout"
                except Exception as e:
                    extracted_text = f"[Image Analysis Failed: {str(e)}]"
                    metadata["analysis_success"] = False
                    metadata["analysis_error"] = str(e)

        metadata["content_type"] = "pdf" if is_pdf else "image"

    else:
        # ============ DOCUMENT PROCESSING (Word, Excel, PowerPoint, Text) ============

        is_word = mime_type in (
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/msword'
        )
        is_excel = mime_type in (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel'
        )
        is_ppt = mime_type in (
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'application/vnd.ms-powerpoint'
        )
        is_text = mime_type in ('text/plain', 'text/markdown', 'text/csv')

        # ============ EXCEL: Use Vision API (sheets -> images) ============
        if is_excel:
            logger.info("[UPLOAD] Excel detected, converting sheets to images...")

            if not is_zai_vision_configured():
                raise HTTPException(status_code=400, detail="Excel memerlukan Z.AI Vision API. Set ZAI_API_KEY untuk mengaktifkan.")

            try:
                # Step 1: Convert sheets to images
                images, img_metadata = await FileProcessor.excel_to_images(content, max_rows_per_sheet=50)
                metadata.update(img_metadata)

                if not images:
                    raise HTTPException(status_code=400, detail="Tidak ada data di file Excel")

                logger.info("[UPLOAD] Converted %d sheets to images, sending to Vision API", len(images))

                # Step 2: Analyze with Vision API
                zai_vision = get_zai_vision_service()

                excel_prompt = f"""Baca dan ekstrak SEMUA data dari spreadsheet Excel ini yang memiliki {len(images)} sheet.

TUGAS UTAMA: Ekstrak data secara LENGKAP dan AKURAT agar bisa di-query tanpa perlu file asli.

Untuk SETIAP sheet, berikan:

## Sheet: [nama sheet]

### Struktur
- Jumlah kolom: X
- Nama kolom: [list semua kolom]

### Data Lengkap
| Kolom1 | Kolom2 | Kolom3 | ... |
|--------|--------|--------|-----|
| value1 | value2 | value3 | ... |
| ...    | ...    | ...    | ... |

### Catatan
- Total baris: X
- [info penting lainnya]

PENTING:
- Transcribe SEMUA nilai yang terlihat dengan akurat
- Jangan summarize atau skip data apapun
- Format angka dan tanggal persis seperti di gambar
- Jika ada cell kosong, tulis "[kosong]" """

                result = await asyncio.wait_for(
                    zai_vision.analyze_multiple_images(images=images, prompt=excel_prompt),
                    timeout=120.0
                )

                if result["success"] and result.get("content"):
                    extracted_text = result["content"]
                    metadata["analysis_method"] = "vision_api_excel"
                    metadata["analysis_success"] = True
                    logger.info("[UPLOAD] Excel Vision analysis complete: %d chars", len(extracted_text))
                else:
                    raise HTTPException(status_code=400, detail=f"Vision API gagal: {result.get('error', 'Unknown error')}")

            except asyncio.TimeoutError:
                raise HTTPException(status_code=400, detail="Excel analysis timed out")
            except HTTPException:
                raise
            except Exception as e:
                logger.exception("[UPLOAD] Excel processing failed: %s", e)
                raise HTTPException(status_code=400, detail=f"Gagal memproses Excel: {str(e)}")

        # ============ WORD, PPT, TEXT: Extract text -> AI analysis ============
        elif is_word or is_ppt or is_text:
            # Step 1: Extract text from document
            logger.info("[UPLOAD] Step 1: Extracting text from %s...", mime_type)

            if is_word:
                doc_text, doc_metadata = await FileProcessor.extract_word_text(content)
            elif is_ppt:
                doc_text, doc_metadata = await FileProcessor.extract_powerpoint_text(content)
            elif is_text:
                doc_text = content.decode('utf-8', errors='ignore')
                doc_metadata = {'extraction_method': 'direct_decode'}

            metadata.update(doc_metadata)

            # Check if extraction succeeded
            if doc_text and doc_text.strip():
                # Save raw text to metadata
                metadata["raw_text"] = doc_text
                metadata["raw_text_length"] = len(doc_text)

                # Step 2: Analyze with AI
                logger.info("[UPLOAD] Step 2: Analyzing document with AI...")
                try:
                    model = settings.DEFAULT_MODEL or "gpt-4o-mini"

                    doc_type_name = "Word" if is_word else "PowerPoint"

                    analysis_prompt = f"""Analisa dokumen {doc_type_name} berikut dan berikan:

1. RINGKASAN singkat (2-3 kalimat)
2. POIN-POIN PENTING dalam bullet points

Dokumen:
{doc_text}

Format output:
## Ringkasan
[ringkasan singkat]

## Poin Penting
- [poin 1]
- [poin 2]
- dst..."""

                    completion_kwargs = {
                        "model": model,
                        "messages": [{"role": "user", "content": analysis_prompt}],
                        "temperature": 0.3,
                        "max_tokens": 2048,
                        "api_key": settings.OPENAI_API_KEY,
                        "timeout": 60,
                        "num_retries": 1,
                    }

                    if settings.OPENAI_BASE_URL:
                        completion_kwargs["api_base"] = settings.OPENAI_BASE_URL
                        if "/" not in model:
                            completion_kwargs["model"] = f"openai/{model}"

                    response = await litellm.acompletion(**completion_kwargs)
                    ai_summary = response.choices[0].message.content or ""

                    # Combine: AI summary + raw text
                    extracted_text = f"""{ai_summary}

---

## Dokumen Asli

{doc_text}"""

                    metadata["analysis_method"] = "extract_ai_analyze"
                    metadata["analysis_success"] = True
                    metadata["analysis_model"] = model
                    logger.info("[UPLOAD] AI analysis complete: %d chars (summary + raw)", len(extracted_text))

                except Exception as e:
                    logger.warning("[UPLOAD] AI analysis failed, saving raw extracted text: %s", e)
                    extracted_text = doc_text
                    metadata["analysis_method"] = "extract_only"
                    metadata["analysis_success"] = True
                    metadata["ai_analysis_error"] = str(e)

            else:
                # Extraction returned empty
                error_msg = doc_metadata.get('error', 'No text content could be extracted')
                if file_path.exists():
                    file_path.unlink()
                if doc_metadata.get('unsupported_format') == 'doc_legacy':
                    raise HTTPException(status_code=400, detail=error_msg)
                else:
                    raise HTTPException(status_code=400, detail=f"Gagal mengekstrak teks: {error_msg}")

        else:
            # Unsupported file type
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {mime_type}")

    metadata['extracted_length'] = len(extracted_text) if extracted_text else 0

    # Safeguard: ensure extracted_text is never None
    if extracted_text is None:
        logger.warning("[UPLOAD] extracted_text was None, defaulting to empty string")
        extracted_text = ""

    # Create knowledge entry
    logger.info("[UPLOAD] Creating knowledge entry in database...")
    logger.info("[UPLOAD] Content length: %d chars", len(extracted_text))

    # Map MIME types to short content_type (max 50 chars in DB)
    content_type_map = {
        'application/pdf': 'pdf',
        'application/msword': 'word',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'word',
        'application/vnd.ms-excel': 'excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'excel',
        'application/vnd.ms-powerpoint': 'powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'powerpoint',
        'text/plain': 'text',
        'text/markdown': 'markdown',
        'text/csv': 'csv',
        'image/jpeg': 'jpeg',
        'image/png': 'png',
        'image/gif': 'gif',
        'image/webp': 'webp',
    }
    short_content_type = content_type_map.get(mime_type, mime_type.split('/')[-1][:50])

    knowledge = Knowledge(
        title=title or file.filename,
        content=extracted_text,
        content_type=short_content_type,
        file_path=str(file_path),
        file_name=file.filename,
        file_size=file_size,
        mime_type=mime_type,
        extra_metadata=metadata,
    )
    db.add(knowledge)
    await db.commit()
    await db.refresh(knowledge)

    logger.info("[UPLOAD] Upload complete. Knowledge ID: %s", knowledge.id)

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
