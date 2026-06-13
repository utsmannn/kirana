"""Background knowledge processor — runs heavy upload work outside the request lifecycle.

Upload requests return immediately with status "processing". This module
runs the actual parse / vision / chunk / embed pipeline and updates the
knowledge row status to "ready" or "failed".
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session
from app.models.knowledge import Knowledge
from app.services.file_processor import FileProcessor
from app.services.liteparse_parser import (
    ParsedDocument,
    parse_document_generic,
    parse_document_smart,
)
from app.services.rag_ingestion import index_knowledge
from app.services.zai_vision import get_zai_vision_service, is_zai_vision_configured

logger = logging.getLogger(__name__)

LITEPARSE_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

VISION_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp",
    "application/pdf",
}

SUPPORTED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp",
}

CONTENT_TYPE_MAP = {
    "application/pdf": "pdf",
    "application/msword": "word",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
    "application/vnd.ms-excel": "excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",
    "application/vnd.ms-powerpoint": "powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "powerpoint",
    "text/plain": "text",
    "text/markdown": "markdown",
    "text/csv": "csv",
    "image/jpeg": "jpeg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}


def _try_liteparse(file_path: Path, mime_type: str) -> ParsedDocument | None:
    if not settings.LITEPARSE_ENABLED or mime_type not in LITEPARSE_TYPES:
        return None
    try:
        return parse_document_smart(file_path)
    except Exception as e:
        logger.warning("[PROCESSOR] LiteParse smart failed, trying generic: %s", e)
    try:
        return parse_document_generic(file_path)
    except Exception as e:
        logger.warning("[PROCESSOR] LiteParse generic failed: %s", e)
        return None


async def _ai_analyze(prompt: str, model: str | None = None) -> str:
    from openai import AsyncOpenAI

    api_key = settings.OPENAI_API_KEY
    base_url = settings.OPENAI_BASE_URL or None
    client_kwargs: Dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = AsyncOpenAI(**client_kwargs)
    model_name = model or settings.DEFAULT_MODEL or "gpt-4o-mini"
    response = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2048,
    )
    return response.choices[0].message.content or ""


async def process_upload(knowledge_id: uuid.UUID) -> None:
    """Process an uploaded knowledge item in the background.

    1. Load the Knowledge row.
    2. Set status → processing.
    3. Parse / extract text (LiteParse, Vision, native extraction).
    4. Chunk, embed, and index via pgvector.
    5. Set status → ready (or failed).
    """
    async with async_session() as db:
        # ----- load row -----
        result = await db.execute(
            select(Knowledge).where(Knowledge.id == knowledge_id)
        )
        knowledge = result.scalar_one_or_none()
        if not knowledge:
            logger.error("[PROCESSOR] Knowledge %s not found", knowledge_id)
            return

        knowledge.processing_status = "processing"
        await db.commit()

        meta: Dict[str, Any] = dict(knowledge.extra_metadata or {})
        file_path = Path(knowledge.file_path) if knowledge.file_path else None
        mime_type = knowledge.mime_type or "application/octet-stream"

        try:
            extracted_text = ""
            parsed_document: ParsedDocument | None = None

            # ---------- LiteParse ----------
            if file_path and file_path.exists():
                parsed_document = _try_liteparse(file_path, mime_type)
                if parsed_document is not None:
                    extracted_text = parsed_document.text
                    meta["analysis_method"] = "liteparse"
                    meta["analysis_success"] = True
                    meta["parser"] = parsed_document.parser
                    meta["parsing_status"] = parsed_document.parsing_status
                    meta["pages"] = len(parsed_document.pages)
                    meta["raw_text_length"] = len(parsed_document.text)

            if extracted_text:
                # LiteParse succeeded — optional AI analysis for PDFs/DOCX
                if mime_type == "application/pdf" and settings.OPENAI_API_KEY:
                    try:
                        raw_text = meta.get("raw_text") or extracted_text
                        model = settings.DEFAULT_MODEL or "gpt-4o-mini"
                        analysis_prompt = _make_analysis_prompt(raw_text[:16000])
                        ai_summary = await _ai_analyze(analysis_prompt, model)
                        extracted_text = f"{ai_summary}\n\n---\n\n## Original Document\n\n{raw_text}"
                        meta["analysis_method"] = "liteparse_ai_analyze"
                        meta["analysis_model"] = model
                    except Exception as e:
                        logger.warning("[PROCESSOR] AI analysis skipped: %s", e)

            elif mime_type in VISION_TYPES:
                # ---------- Vision / native extraction ----------
                content = _read_file(file_path) if file_path else None
                if not content:
                    raise ValueError("File content is empty or file missing on disk")

                is_pdf = mime_type == "application/pdf"
                is_image = mime_type in SUPPORTED_IMAGE_TYPES

                if is_pdf:
                    # Step 1: native extraction
                    pdf_text, pdf_meta = await FileProcessor.extract_pdf_text(content)
                    meta.update(pdf_meta)

                    if pdf_text and pdf_text.strip():
                        extracted_text = pdf_text
                        meta["raw_text"] = pdf_text
                        meta["raw_text_length"] = len(pdf_text)
                        try:
                            model = settings.DEFAULT_MODEL or "gpt-4o-mini"
                            analysis_prompt = _make_analysis_prompt(pdf_text[:16000])
                            ai_summary = await _ai_analyze(analysis_prompt, model)
                            extracted_text = f"{ai_summary}\n\n---\n\n## Original Document\n\n{pdf_text}"
                            meta["analysis_method"] = "native_extract_ai_analyze"
                            meta["analysis_model"] = model
                        except Exception as e:
                            logger.warning("[PROCESSOR] AI analysis skipped: %s", e)
                            meta["analysis_method"] = "native_extract_only"
                    elif is_zai_vision_configured():
                        # Scanned PDF → Vision
                        pages = await FileProcessor.pdf_to_images(content, dpi=150, timeout=60.0)
                        meta["pdf_pages"] = len(pages)
                        if len(pages) > 15:
                            pages = pages[:15]
                        zai = get_zai_vision_service()
                        result = await asyncio.wait_for(
                            zai.analyze_multiple_images(
                                images=pages,
                                prompt=_pdf_vision_prompt(len(pages)),
                            ),
                            timeout=120.0,
                        )
                        if result["success"] and result.get("content"):
                            extracted_text = result["content"]
                            meta["analysis_method"] = "vision_api_multimodal"
                            meta["analysis_success"] = True
                        else:
                            raise RuntimeError(result.get("error", "Vision API returned no content"))
                    else:
                        raise RuntimeError(
                            "Document appears to be scanned (no extractable text) "
                            "and no vision backend is configured."
                        )

                elif is_image:
                    if not is_zai_vision_configured():
                        raise RuntimeError("No vision backend configured for image analysis.")
                    img_src = str(file_path) if file_path and file_path.exists() else (
                        _read_file(file_path) if file_path else content
                    )
                    zai = get_zai_vision_service()
                    result = await asyncio.wait_for(
                        zai.analyze_image(
                            image_source=img_src,
                            prompt="Describe this image in detail. Include: 1) Main subjects/objects, 2) Colors and composition, 3) Any text visible, 4) Overall mood/atmosphere, 5) Any other relevant details.",
                        ),
                        timeout=60.0,
                    )
                    if result["success"] and result.get("content"):
                        extracted_text = result["content"]
                        meta["analysis_method"] = "vision_api"
                        meta["analysis_success"] = True
                    else:
                        raise RuntimeError(result.get("error", "Vision API returned no content"))

                meta["content_type"] = "pdf" if is_pdf else "image"

            elif mime_type in (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "application/vnd.ms-powerpoint",
                "text/plain", "text/markdown", "text/csv",
            ):
                # ---------- Word / Excel / PPT / Text ----------
                content = _read_file(file_path) if file_path else None
                if not content:
                    raise ValueError("Document content not available")

                is_excel = "spreadsheetml" in mime_type or "ms-excel" in mime_type
                is_word = "wordprocessingml" in mime_type or "msword" in mime_type
                is_ppt = "presentationml" in mime_type or "ms-powerpoint" in mime_type

                if is_excel:
                    if not is_zai_vision_configured():
                        raise RuntimeError("Excel requires a vision backend (Z.AI or LLM provider).")
                    images, img_meta = await FileProcessor.excel_to_images(content, max_rows_per_sheet=50)
                    meta.update(img_meta)
                    if not images:
                        raise RuntimeError("No data found in Excel file")
                    zai = get_zai_vision_service()
                    result = await asyncio.wait_for(
                        zai.analyze_multiple_images(
                            images=images,
                            prompt=_excel_vision_prompt(len(images)),
                        ),
                        timeout=120.0,
                    )
                    if result["success"] and result.get("content"):
                        extracted_text = result["content"]
                        meta["analysis_method"] = "vision_api_excel"
                        meta["analysis_success"] = True
                    else:
                        raise RuntimeError(result.get("error", "Vision API returned no content"))

                else:
                    # Word / PPT / Text
                    if is_word:
                        doc_text, doc_meta = await FileProcessor.extract_word_text(content)
                    elif is_ppt:
                        doc_text, doc_meta = await FileProcessor.extract_powerpoint_text(content)
                    else:
                        doc_text = content.decode("utf-8", errors="ignore")
                        doc_meta = {"extraction_method": "direct_decode"}

                    meta.update(doc_meta)

                    if not doc_text or not doc_text.strip():
                        raise RuntimeError(doc_meta.get("error", "No text content could be extracted"))

                    extracted_text = doc_text
                    try:
                        model = settings.DEFAULT_MODEL or "gpt-4o-mini"
                        doc_type_name = {True: "Word", False: ""}.get(is_word, "PowerPoint" if is_ppt else "text")
                        analysis_prompt = _make_analysis_prompt(doc_text[:16000], doc_type_name)
                        ai_summary = await _ai_analyze(analysis_prompt, model)
                        extracted_text = f"{ai_summary}\n\n---\n\n## Original Document\n\n{doc_text}"
                        meta["analysis_method"] = "extract_ai_analyze"
                        meta["analysis_model"] = model
                    except Exception as e:
                        logger.warning("[PROCESSOR] AI analysis skipped: %s", e)
                        meta["analysis_method"] = "extract_only"

            meta["extracted_length"] = len(extracted_text) if extracted_text else 0

            # safeguard
            if extracted_text is None:
                extracted_text = ""

            # ----- update knowledge row -----
            knowledge.content = extracted_text
            short_ct = CONTENT_TYPE_MAP.get(mime_type, mime_type.split("/")[-1][:50])
            knowledge.content_type = short_ct
            knowledge.extra_metadata = meta

            await db.flush()

            # ----- chunk & embed -----
            await index_knowledge(db, knowledge, parsed_document=parsed_document)

            # ----- mark ready -----
            knowledge.processing_status = "ready"
            await db.commit()

            logger.info("[PROCESSOR] Knowledge %s processed successfully (%d chars)", knowledge_id, len(extracted_text))

        except Exception as e:
            logger.exception("[PROCESSOR] Knowledge %s failed: %s", knowledge_id, e)

            # reload in case session is dirty from the error
            try:
                result2 = await db.execute(
                    select(Knowledge).where(Knowledge.id == knowledge_id)
                )
                knowledge2 = result2.scalar_one_or_none()
                if knowledge2:
                    knowledge2.processing_status = "failed"
                    meta2 = dict(knowledge2.extra_metadata or {})
                    meta2["processing_error"] = str(e)
                    knowledge2.extra_metadata = meta2
                    await db.commit()
            except Exception as inner:
                logger.exception("[PROCESSOR] Failed to update error status for %s: %s", knowledge_id, inner)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _read_file(file_path: Path | None) -> bytes | None:
    if file_path and file_path.exists():
        return file_path.read_bytes()
    return None


def _make_analysis_prompt(text: str, doc_type: str = "document") -> str:
    return f"""Analyze the following {doc_type} and provide:

1. A brief SUMMARY (2-3 sentences)
2. KEY POINTS in bullet points

Document:
{text}

Output format:
## Summary
[brief summary]

## Key Points
- [point 1]
- [point 2]
- etc..."""


def _pdf_vision_prompt(page_count: int) -> str:
    return f"""This is a {page_count}-page scanned PDF document. Extract ALL text content from each page.

For each page:
1. Start with "--- Page X ---" header
2. Transcribe ALL visible text exactly as shown
3. For tables: recreate them in markdown format
4. Preserve the reading order

Be exhaustive - capture 100% of the text."""


def _excel_vision_prompt(sheet_count: int) -> str:
    return f"""Read and extract ALL data from this Excel spreadsheet which has {sheet_count} sheets.

MAIN TASK: Extract data COMPLETELY and ACCURATELY so it can be queried without the original file.

For EACH sheet, provide:

## Sheet: [sheet name]

### Structure
- Column count: X
- Column names: [list all columns]

### Complete Data
| Col1 | Col2 | Col3 | ... |
|------|------|------|-----|
| val1 | val2 | val3 | ... |
| ...  | ...  | ...  | ... |

### Notes
- Total rows: X
- [other important info]

IMPORTANT:
- Transcribe ALL visible values accurately
- Do NOT summarize or skip any data
- Format numbers and dates exactly as shown in the image
- If a cell is empty, write "[empty]" """
