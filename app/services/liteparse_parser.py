from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, SupportsFloat, SupportsIndex, cast

from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)
ParsingStatus = Literal["smart", "generic"]


@dataclass(frozen=True)
class ParsedTextItem:
    text: str
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    font_name: str | None = None
    font_size: float | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class ParsedPage:
    page_num: int
    width: float | None
    height: float | None
    text: str
    text_items: list[ParsedTextItem] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    pages: list[ParsedPage]
    parser: Literal["liteparse"] = "liteparse"
    parsing_status: ParsingStatus = "smart"


def parse_document_smart(path: Path) -> ParsedDocument:
    """Parse a document using LiteParse with OCR enabled."""
    logger.info("Parsing document with LiteParse smart mode: %s", path.name)
    try:
        from liteparse import LiteParse

        parser = LiteParse(
            ocr_enabled=True,
            ocr_language=settings.LITEPARSE_OCR_LANGUAGE,
            max_pages=settings.LITEPARSE_MAX_PAGES,
            dpi=settings.LITEPARSE_DPI,
        )
        result = parser.parse(str(path))
        return _to_parsed_document(result, parsing_status="smart")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.exception("LiteParse smart parsing failed for %s", path.name)
        raise HTTPException(
            status_code=422,
            detail=f"LiteParse smart parsing failed: {e}",
        ) from e


def parse_document_generic(path: Path) -> ParsedDocument:
    """Parse a document using LiteParse with OCR disabled."""
    logger.info("Parsing document with LiteParse generic mode: %s", path.name)
    try:
        from liteparse import LiteParse

        parser = LiteParse(
            ocr_enabled=False,
            max_pages=settings.LITEPARSE_MAX_PAGES,
        )
        result = parser.parse(str(path))
        return _to_parsed_document(result, parsing_status="generic")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.exception("LiteParse generic parsing failed for %s", path.name)
        raise HTTPException(
            status_code=422,
            detail=f"LiteParse generic parsing failed: {e}",
        ) from e


def _to_parsed_document(
    result: object, *, parsing_status: ParsingStatus
) -> ParsedDocument:
    text = str(getattr(result, "text", "") or "").strip()
    if not result or not text:
        raise HTTPException(
            status_code=422,
            detail=f"LiteParse {parsing_status} parsing returned empty text",
        )

    pages = [_to_parsed_page(page) for page in (getattr(result, "pages", None) or [])]
    return ParsedDocument(text=text, pages=pages, parsing_status=parsing_status)


def _to_parsed_page(page: object) -> ParsedPage:
    page_num = _to_int(getattr(page, "page_num", None), default=1)
    text = str(getattr(page, "text", "") or "").strip()
    return ParsedPage(
        page_num=page_num,
        width=_to_float(getattr(page, "width", None)),
        height=_to_float(getattr(page, "height", None)),
        text=text,
        text_items=[
            parsed
            for item in (getattr(page, "text_items", None) or [])
            if (parsed := _to_text_item(item)) is not None
        ],
    )


def _to_text_item(item: object) -> ParsedTextItem | None:
    text = str(getattr(item, "text", "") or "").strip()
    if not text:
        return None
    return ParsedTextItem(
        text=text,
        x=_to_float(getattr(item, "x", None)),
        y=_to_float(getattr(item, "y", None)),
        width=_to_float(getattr(item, "width", None)),
        height=_to_float(getattr(item, "height", None)),
        font_name=_to_str(getattr(item, "font_name", None)),
        font_size=_to_float(getattr(item, "font_size", None)),
        confidence=_to_float(getattr(item, "confidence", None)),
    )


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, (str, bytes, bytearray)):
            return float(value)
        return float(cast(SupportsFloat | SupportsIndex, value))
    except (TypeError, ValueError):
        return None


def _to_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    try:
        if isinstance(value, (str, bytes, bytearray)):
            return int(value)
        return int(cast(SupportsIndex, value))
    except (TypeError, ValueError):
        return default


def _to_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
