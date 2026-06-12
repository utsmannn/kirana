from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import tiktoken

from app.config import settings
from app.services.liteparse_parser import ParsedDocument, ParsedPage, ParsedTextItem

_MAX_BBOXES_PER_CHUNK = 80
_MAX_BBOX_TEXT_CHARS = 180


@dataclass
class RagChunk:
    text: str
    chunk_index: int
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


_encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding.encode(text or ""))


def chunk_text(
    text: str,
    *,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
    base_metadata: dict[str, Any] | None = None,
) -> list[RagChunk]:
    max_tokens = max_tokens or settings.RAG_CHUNK_MAX_TOKENS
    overlap_tokens = (
        overlap_tokens
        if overlap_tokens is not None
        else settings.RAG_CHUNK_OVERLAP_TOKENS
    )
    base_metadata = base_metadata or {}

    paragraphs = [p.strip() for p in (text or "").splitlines() if p.strip()]
    if not paragraphs:
        return []

    chunks: list[RagChunk] = []
    current_parts: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current_parts, current_tokens
        if not current_parts:
            return
        chunk_body = "\n\n".join(current_parts).strip()
        if chunk_body:
            chunks.append(
                RagChunk(
                    text=chunk_body,
                    chunk_index=len(chunks),
                    token_count=count_tokens(chunk_body),
                    metadata=dict(base_metadata),
                )
            )
        if overlap_tokens > 0 and chunk_body:
            overlap_ids = _encoding.encode(chunk_body)[-overlap_tokens:]
            overlap_text = _encoding.decode(overlap_ids).strip()
            current_parts = [overlap_text] if overlap_text else []
            current_tokens = count_tokens(overlap_text) if overlap_text else 0
        else:
            current_parts = []
            current_tokens = 0

    for paragraph in paragraphs:
        para_tokens = count_tokens(paragraph)
        if para_tokens > max_tokens:
            flush()
            token_ids = _encoding.encode(paragraph)
            start = 0
            while start < len(token_ids):
                end = min(start + max_tokens, len(token_ids))
                piece = _encoding.decode(token_ids[start:end]).strip()
                if piece:
                    chunks.append(
                        RagChunk(
                            text=piece,
                            chunk_index=len(chunks),
                            token_count=count_tokens(piece),
                            metadata=dict(base_metadata),
                        )
                    )
                if end >= len(token_ids):
                    break
                start = max(end - overlap_tokens, start + 1)
            current_parts = []
            current_tokens = 0
            continue

        if current_parts and current_tokens + para_tokens > max_tokens:
            flush()

        current_parts.append(paragraph)
        current_tokens += para_tokens

    flush()
    return chunks


def chunk_document(
    document: ParsedDocument,
    *,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
    base_metadata: dict[str, Any] | None = None,
) -> list[RagChunk]:
    segments = _document_segments(document)
    if not segments:
        return chunk_text(
            document.text,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            base_metadata={
                **(base_metadata or {}),
                "extraction": {
                    "parser": document.parser,
                    "parsing_status": document.parsing_status,
                    "coordinate_system": "pdf_points",
                },
            },
        )

    max_tokens = max_tokens or settings.RAG_CHUNK_MAX_TOKENS
    overlap_tokens = (
        overlap_tokens
        if overlap_tokens is not None
        else settings.RAG_CHUNK_OVERLAP_TOKENS
    )
    base_metadata = base_metadata or {}

    chunks: list[RagChunk] = []
    current: list[dict[str, Any]] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        text = "\n".join(seg["text"] for seg in current if seg["text"].strip()).strip()
        if text:
            metadata = {
                **base_metadata,
                **_source_metadata(current, document),
            }
            chunks.append(
                RagChunk(
                    text=text,
                    chunk_index=len(chunks),
                    token_count=count_tokens(text),
                    metadata=metadata,
                )
            )

        if overlap_tokens <= 0 or not text:
            current = []
            current_tokens = 0
            return

        overlap: list[dict[str, Any]] = []
        tokens = 0
        for seg in reversed(current):
            seg_tokens = seg["token_count"]
            if overlap and tokens + seg_tokens > overlap_tokens:
                break
            overlap.insert(0, seg)
            tokens += seg_tokens
        current = overlap
        current_tokens = tokens

    for segment in segments:
        seg_tokens = segment["token_count"]
        if seg_tokens > max_tokens:
            flush()
            for piece in chunk_text(
                segment["text"],
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
                base_metadata={
                    **base_metadata,
                    **_source_metadata([segment], document),
                },
            ):
                piece.chunk_index = len(chunks)
                chunks.append(piece)
            current = []
            current_tokens = 0
            continue

        if current and current_tokens + seg_tokens > max_tokens:
            flush()
        current.append(segment)
        current_tokens += seg_tokens

    flush()
    return chunks


def _document_segments(document: ParsedDocument) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for page in document.pages:
        segments.extend(_page_segments(page))
    return segments


def _page_segments(page: ParsedPage) -> list[dict[str, Any]]:
    if page.text_items:
        return [
            {
                "text": item.text,
                "token_count": count_tokens(item.text),
                "page": page.page_num,
                "bbox": _bbox_from_item(item),
            }
            for item in page.text_items
            if item.text.strip()
        ]
    if page.text.strip():
        return [
            {
                "text": page.text,
                "token_count": count_tokens(page.text),
                "page": page.page_num,
                "bbox": None,
            }
        ]
    return []


def _source_metadata(
    segments: list[dict[str, Any]], document: ParsedDocument
) -> dict[str, Any]:
    pages = [seg["page"] for seg in segments if seg.get("page") is not None]
    source_spans = []
    bboxes = []

    for seg in segments[:_MAX_BBOXES_PER_CHUNK]:
        text = seg.get("text", "")
        source_spans.append({
            "page": seg.get("page"),
            "text": text[:_MAX_BBOX_TEXT_CHARS],
        })
        if seg.get("bbox"):
            bboxes.append({"page": seg.get("page"), **seg["bbox"]})

    metadata: dict[str, Any] = {
        "extraction": {
            "parser": document.parser,
            "parsing_status": document.parsing_status,
            "coordinate_system": "pdf_points",
        },
        "source_spans": source_spans,
        "bboxes": bboxes[:_MAX_BBOXES_PER_CHUNK],
        "bbox_coordinate_system": "pdf_points",
    }
    if pages:
        metadata["page"] = pages[0]
        metadata["page_start"] = min(pages)
        metadata["page_end"] = max(pages)
    return metadata


def _bbox_from_item(item: ParsedTextItem) -> dict[str, float] | None:
    if item.x is None or item.y is None or item.width is None or item.height is None:
        return None
    return {
        "x": item.x,
        "y": item.y,
        "width": item.width,
        "height": item.height,
    }
