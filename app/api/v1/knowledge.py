import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

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
)
from app.services.file_processor import FileProcessor, get_mime_type
from app.services.zai_vision import get_zai_vision_service, is_zai_vision_configured

logger = logging.getLogger(__name__)

router = APIRouter()

# Upload directory for knowledge files
UPLOAD_DIR = Path("/app/uploads/knowledge")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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
    api_key: str = Depends(deps.verify_api_key),
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
        logger.info("[UPLOAD] %s detected, analyzing with Z.AI Vision API (GLM-4.6V)...",
                   "PDF" if is_pdf else "Image")

        # Check if Z.AI Vision is configured
        if is_zai_vision_configured():
            try:
                # Get Z.AI Vision service
                zai_vision = get_zai_vision_service()

                # For PDFs, convert to concatenated image first
                if is_pdf:
                    logger.info("[UPLOAD] Converting PDF to image for Vision analysis...")
                    try:
                        # Convert PDF pages to images
                        pages = FileProcessor.pdf_to_images(content, dpi=150)
                        metadata["pdf_pages"] = len(pages)

                        # Concatenate into one long image
                        if len(pages) > 1:
                            concatenated = FileProcessor.concatenate_images_vertically(
                                pages, max_height=10000, padding=20
                            )
                            image_bytes = FileProcessor.image_to_bytes(concatenated)
                            metadata["pdf_concatenated"] = True
                        else:
                            image_bytes = FileProcessor.image_to_bytes(pages[0])
                            metadata["pdf_concatenated"] = False

                        logger.info("[UPLOAD] PDF converted to image (%d bytes), sending to Vision...",
                                   len(image_bytes))

                        # Analyze with Vision
                        result = await asyncio.wait_for(
                            zai_vision.analyze_image(
                                image_source=image_bytes,
                                prompt="Analyze this document image thoroughly. Extract and transcribe ALL text content accurately. Include: 1) Document structure (headers, sections, paragraphs), 2) All visible text, 3) Tables with their data, 4) Any charts or diagrams descriptions, 5) Important numbers, dates, and key information. Be comprehensive and accurate.",
                            ),
                            timeout=120.0  # 2 minute timeout for PDFs (larger images)
                        )

                    except ImportError as e:
                        logger.error("[UPLOAD] PDF conversion failed: %s", e)
                        extracted_text = f"[PDF Analysis Failed: {str(e)}]"
                        metadata["analysis_success"] = False
                        metadata["analysis_error"] = str(e)
                        result = None

                else:
                    # Direct image analysis
                    result = await asyncio.wait_for(
                        zai_vision.analyze_image(
                            image_source=str(file_path),
                            prompt="Describe this image in detail. Include: 1) Main subjects/objects, 2) Colors and composition, 3) Any text visible in the image, 4) Overall mood/atmosphere, 5) Any other relevant details.",
                        ),
                        timeout=60.0  # 60 second timeout
                    )

                if result:
                    if result["success"]:
                        extracted_text = result["content"]
                        metadata["content_type"] = "pdf" if is_pdf else "image"
                        metadata["analysis_source"] = "zai_vision_api_glm46v"
                        metadata["analysis_success"] = True
                        if result.get("usage"):
                            metadata["token_usage"] = result["usage"]
                        logger.info("[UPLOAD] Z.AI Vision analysis complete. Result length: %d chars",
                                   len(extracted_text))
                    else:
                        logger.warning("[UPLOAD] Z.AI Vision analysis failed: %s", result.get("error"))
                        extracted_text = f"[{'PDF' if is_pdf else 'Image'} Analysis Failed: {result.get('error', 'Unknown error')}]"
                        metadata["analysis_success"] = False
                        metadata["analysis_error"] = result.get("error")

            except asyncio.TimeoutError:
                logger.error("[UPLOAD] Z.AI Vision analysis timed out")
                extracted_text = f"[{'PDF' if is_pdf else 'Image'} Analysis Failed: Timeout - analysis took too long]"
                metadata["analysis_success"] = False
                metadata["analysis_error"] = "timeout"

            except Exception as e:
                logger.exception("[UPLOAD] Z.AI Vision analysis error: %s", e)
                extracted_text = f"[{'PDF' if is_pdf else 'Image'} Analysis Failed: {str(e)}]"
                metadata["analysis_success"] = False
                metadata["analysis_error"] = str(e)
        else:
            logger.warning("[UPLOAD] Z.AI Vision not configured (ZAI_API_KEY not set)")
            extracted_text = f"[{'PDF' if is_pdf else 'Image'} uploaded but Z.AI Vision not configured. Set ZAI_API_KEY to enable analysis.]"
            metadata["analysis_success"] = False
            metadata["analysis_error"] = "zai_vision_not_configured"

    else:
        # Non-image files: use file processor
        try:
            logger.info("[UPLOAD] Starting text extraction for MIME type: %s", mime_type)
            extracted_text, proc_metadata = await FileProcessor.extract_text(
                content, mime_type, file.filename
            )
            metadata.update(proc_metadata)
            logger.info("[UPLOAD] Text extraction complete. Extracted %d characters", len(extracted_text))
        except ValueError as e:
            logger.error("[UPLOAD] Text extraction failed (ValueError): %s", e)
            # Clean up saved file
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception("[UPLOAD] Text extraction failed with unexpected error: %s", e)
            # Clean up saved file
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

    metadata['extracted_length'] = len(extracted_text)

    # Create knowledge entry
    logger.info("[UPLOAD] Creating knowledge entry in database...")
    knowledge = Knowledge(
        title=title or file.filename,
        content=extracted_text,
        content_type=mime_type.split('/')[-1] if '/' in mime_type else mime_type,
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


@router.get("/{knowledge_id}/download")
async def download_knowledge_file(
    knowledge_id: uuid.UUID,
    api_key: str = Depends(deps.verify_api_key),
    db: AsyncSession = Depends(deps.get_db_session),
):
    """Download the original file for a knowledge item."""
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
