"""OCR parser for image-based financial documents and receipts."""

from pathlib import Path
import logging
from typing import List, Union

from PIL import Image
import pytesseract

from ..models import FinancialChunk


PathLike = Union[str, Path]
logger = logging.getLogger(__name__)


def parse_image(file_path: PathLike) -> List[FinancialChunk]:
    """Extract searchable OCR text while retaining image metadata."""
    path = Path(file_path)
    with Image.open(path) as image:
        metadata = {
            "format": image.format,
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
        }
        try:
            content = pytesseract.image_to_string(image).strip()
        except (OSError, pytesseract.TesseractNotFoundError):
            logger.warning("ocr_fallback filename=%s reason=ocr_unavailable", path.name)
            content = ""

    if content:
        return [
            FinancialChunk(
                chunk_id=path.name,
                content=content,
                chunk_type="image_ocr",
                source_file=str(path),
                metadata={**metadata, "ocr": True},
            )
        ]

    return [
        FinancialChunk(
            chunk_id=path.name,
            content=f"Image document: {path.name}",
            chunk_type="image_metadata",
            source_file=str(path),
            metadata={**metadata, "ocr": False},
        )
    ]