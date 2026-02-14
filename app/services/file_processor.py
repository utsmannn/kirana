"""File processing service for extracting text from various document formats."""

import io
import logging
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)


class FileProcessor:
    """Extract text content from various file formats."""

    SUPPORTED_IMAGE_TYPES = {
        'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'
    }
    SUPPORTED_DOCUMENT_TYPES = {
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # docx
        'application/msword',  # doc
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # xlsx
        'application/vnd.ms-excel',  # xls
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # pptx
        'application/vnd.ms-powerpoint',  # ppt
        'text/plain',
        'text/markdown',
        'text/csv',
    }
    # Types that require Vision AI analysis (converted to images)
    VISION_TYPES = {
        'application/pdf',
        *SUPPORTED_IMAGE_TYPES,
    }

    @classmethod
    def is_supported(cls, mime_type: str) -> bool:
        """Check if file type is supported."""
        return mime_type in cls.SUPPORTED_IMAGE_TYPES or mime_type in cls.SUPPORTED_DOCUMENT_TYPES

    @classmethod
    async def extract_text(
        cls,
        file_content: bytes,
        mime_type: str,
        file_name: Optional[str] = None
    ) -> Tuple[str, dict]:
        """
        Extract text from file content.

        Returns:
            Tuple of (extracted_text, metadata_dict)
        """
        logger.info("[FILE_PROCESSOR] Starting text extraction for: %s (MIME: %s, Size: %d bytes)",
                    file_name, mime_type, len(file_content))

        metadata = {
            'original_filename': file_name,
            'mime_type': mime_type,
            'file_size': len(file_content),
        }

        try:
            if mime_type in cls.SUPPORTED_IMAGE_TYPES:
                logger.info("[FILE_PROCESSOR] Processing as IMAGE")
                text = await cls._extract_from_image(file_content, mime_type)
                metadata['content_type'] = 'image'
            elif mime_type == 'application/pdf':
                logger.info("[FILE_PROCESSOR] Processing as PDF")
                text = await cls._extract_from_pdf(file_content)
                metadata['content_type'] = 'pdf'
            elif mime_type in (
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/msword'
            ):
                logger.info("[FILE_PROCESSOR] Processing as WORD")
                text = await cls._extract_from_word(file_content)
                metadata['content_type'] = 'word'
            elif mime_type in (
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.ms-excel'
            ):
                logger.info("[FILE_PROCESSOR] Processing as EXCEL")
                text = await cls._extract_from_excel(file_content)
                metadata['content_type'] = 'excel'
            elif mime_type in (
                'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                'application/vnd.ms-powerpoint'
            ):
                logger.info("[FILE_PROCESSOR] Processing as POWERPOINT")
                text = await cls._extract_from_powerpoint(file_content)
                metadata['content_type'] = 'powerpoint'
            elif mime_type in ('text/plain', 'text/markdown', 'text/csv'):
                logger.info("[FILE_PROCESSOR] Processing as TEXT")
                text = file_content.decode('utf-8', errors='ignore')
                metadata['content_type'] = 'text'
            else:
                logger.error("[FILE_PROCESSOR] Unsupported MIME type: %s", mime_type)
                raise ValueError(f"Unsupported file type: {mime_type}")

            metadata['extracted_length'] = len(text)
            logger.info("[FILE_PROCESSOR] Extraction complete. Extracted %d characters", len(text))
            return text, metadata

        except Exception as e:
            logger.exception("[FILE_PROCESSOR] Failed to extract text from file: %s - Error: %s", file_name, e)
            raise ValueError(f"Failed to process file: {str(e)}") from e

    @classmethod
    async def _extract_from_image(cls, content: bytes, mime_type: str) -> str:
        """Store image info for later analysis via MCP GLM Vision.

        Note: We don't use OCR here. Use the 'analyze_image' tool via MCP
        for AI-powered image analysis with GLM Vision.
        """
        logger.info("[FILE_PROCESSOR] Processing image (%s, %d bytes) - use analyze_image tool for AI analysis", mime_type, len(content))
        try:
            from PIL import Image
            image = Image.open(io.BytesIO(content))
            width, height = image.size
            mode = image.mode
            logger.info("[FILE_PROCESSOR] Image info: %dx%d, mode=%s", width, height, mode)
            return f"[Image: {width}x{height} pixels, {mime_type} - Use 'analyze_image' tool for AI-powered analysis]"
        except Exception as e:
            logger.warning("[FILE_PROCESSOR] Could not read image info: %s", e)
            return f"[Image file: {mime_type} - Use 'analyze_image' tool for AI-powered analysis]"

    @classmethod
    async def _extract_from_pdf(cls, content: bytes) -> str:
        """PDF processing is handled by Z.AI Vision in knowledge.py.

        This method is kept for backwards compatibility but should not be called
        for new uploads. PDFs are converted to images and analyzed with Vision AI.
        """
        logger.info("[FILE_PROCESSOR] PDF should be processed by Z.AI Vision, not text extraction")
        return "[PDF document - Will be analyzed with Z.AI Vision for better accuracy]"

    @classmethod
    async def _extract_from_word(cls, content: bytes) -> str:
        """Extract text from Word document."""
        try:
            from docx import Document

            doc = Document(io.BytesIO(content))
            text_parts = []

            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)

            # Also extract from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = ' | '.join(cell.text.strip() for cell in row.cells)
                    if row_text:
                        text_parts.append(row_text)

            return '\n\n'.join(text_parts)
        except ImportError:
            logger.warning("Word processing not installed. Install with: pip install python-docx")
            return "[Word document - processing not available]"

    @classmethod
    async def _extract_from_excel(cls, content: bytes) -> str:
        """Extract text from Excel spreadsheet."""
        try:
            import pandas as pd

            # Read all sheets
            excel_file = pd.ExcelFile(io.BytesIO(content))
            text_parts = []

            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                text_parts.append(f"--- Sheet: {sheet_name} ---")
                text_parts.append(df.to_string(index=False))
                text_parts.append('')

            return '\n'.join(text_parts)
        except ImportError:
            logger.warning("Excel processing not installed. Install with: pip install pandas openpyxl")
            return "[Excel spreadsheet - processing not available]"

    @classmethod
    async def _extract_from_powerpoint(cls, content: bytes) -> str:
        """Extract text from PowerPoint presentation."""
        try:
            from pptx import Presentation

            prs = Presentation(io.BytesIO(content))
            text_parts = []

            for slide_num, slide in enumerate(prs.slides, 1):
                slide_text = [f"--- Slide {slide_num} ---"]
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_text.append(shape.text.strip())
                if len(slide_text) > 1:
                    text_parts.append('\n'.join(slide_text))

            return '\n\n'.join(text_parts)
        except ImportError:
            logger.warning("PowerPoint processing not installed. Install with: pip install python-pptx")
            return "[PowerPoint presentation - processing not available]"

    @classmethod
    def is_vision_type(cls, mime_type: str) -> bool:
        """Check if file type should be processed with Vision AI."""
        return mime_type in cls.VISION_TYPES

    @classmethod
    def pdf_to_images(cls, content: bytes, dpi: int = 150) -> List[Image.Image]:
        """
        Convert PDF pages to a list of PIL Images.

        Args:
            content: PDF file content as bytes
            dpi: Resolution for rendering (higher = better quality but larger)

        Returns:
            List of PIL Image objects, one per page
        """
        try:
            from pdf2image import convert_from_bytes

            logger.info("[FILE_PROCESSOR] Converting PDF to images at %d DPI", dpi)
            images = convert_from_bytes(content, dpi=dpi)
            logger.info("[FILE_PROCESSOR] Converted %d pages", len(images))
            return images

        except ImportError:
            logger.error("[FILE_PROCESSOR] pdf2image not installed. Install with: pip install pdf2image")
            raise ImportError("pdf2image not installed. Install with: pip install pdf2image")
        except Exception as e:
            logger.exception("[FILE_PROCESSOR] Failed to convert PDF to images: %s", e)
            raise

    @classmethod
    def concatenate_images_vertically(
        cls,
        images: List[Image.Image],
        max_height: int = 8000,
        padding: int = 20
    ) -> Image.Image:
        """
        Concatenate multiple images into one long vertical image.

        Args:
            images: List of PIL Image objects
            max_height: Maximum height in pixels (to avoid huge images)
            padding: Pixels between images

        Returns:
            Single concatenated PIL Image
        """
        if not images:
            raise ValueError("No images to concatenate")

        if len(images) == 1:
            return images[0]

        # Calculate total height
        total_height = sum(img.height for img in images) + padding * (len(images) - 1)

        # If too tall, scale down
        scale = 1.0
        if total_height > max_height:
            scale = max_height / total_height
            logger.info("[FILE_PROCESSOR] Scaling images by %.2f to fit max height %d", scale, max_height)

        # Find max width (after scaling)
        max_width = max(int(img.width * scale) for img in images)

        # Create new image
        final_height = int(total_height * scale)
        concatenated = Image.new('RGB', (max_width, final_height), color='white')

        y_offset = 0
        for img in images:
            if scale != 1.0:
                new_width = int(img.width * scale)
                new_height = int(img.height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Center horizontally if widths differ
            x_offset = (max_width - img.width) // 2
            concatenated.paste(img, (x_offset, y_offset))
            y_offset += img.height + padding

        logger.info("[FILE_PROCESSOR] Concatenated %d images into %dx%d",
                   len(images), max_width, final_height)
        return concatenated

    @classmethod
    def image_to_bytes(cls, image: Image.Image, format: str = 'PNG') -> bytes:
        """Convert PIL Image to bytes."""
        buffer = io.BytesIO()
        # Convert to RGB if necessary (for PNG compatibility)
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')
        image.save(buffer, format=format)
        return buffer.getvalue()


def get_mime_type(filename: str) -> str:
    """Get MIME type from filename extension."""
    import mimetypes
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'
