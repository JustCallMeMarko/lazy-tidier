"""Content extraction: PDFs, images, DOCX/PPTX/TXT/MD.

Read-only: never executes or renders file contents beyond text extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}
DOC_EXTENSIONS = {".docx", ".pptx", ".txt", ".md"}

MIN_PDF_TEXT = 50
MAX_TEXT = 1500


@dataclass
class ExtractResult:
    text: str | None = None
    image_path: str | None = None
    kind: str = "unknown"  # text | image | ocr | empty | unsupported


def _ocr(image_path: Path) -> str:
    """OCR via rapidocr; returns extracted text (possibly empty)."""
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    result, _ = engine(str(image_path))
    if not result:
        return ""
    return "\n".join(line[1] for line in result)


def extract_pdf(path: Path) -> ExtractResult:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        text = "".join(doc[i].get_text() for i in range(min(2, len(doc))))
        text = text.strip()
        if len(text) >= MIN_PDF_TEXT:
            return ExtractResult(text=text[:MAX_TEXT], kind="text")
        # Scanned PDF: rasterize page 1, OCR; caller may fall back to vision
        pix = doc[0].get_pixmap(dpi=150)
        img = path.parent / f".{path.stem}.page1.png"
        pix.save(img)
        ocr_text = _ocr(img).strip()
        if len(ocr_text) >= MIN_PDF_TEXT:
            img.unlink(missing_ok=True)
            return ExtractResult(text=ocr_text[:MAX_TEXT], kind="ocr")
        return ExtractResult(text=ocr_text or None, image_path=str(img), kind="image")
    finally:
        doc.close()


def extract_image(path: Path) -> ExtractResult:
    ocr_text = _ocr(path).strip()
    if len(ocr_text) >= MIN_PDF_TEXT:
        return ExtractResult(text=ocr_text[:MAX_TEXT], kind="ocr")
    return ExtractResult(text=ocr_text or None, image_path=str(path), kind="image")


def extract_docx(path: Path) -> ExtractResult:
    import docx

    doc = docx.Document(path)
    text = "\n".join(p.text for p in doc.paragraphs).strip()
    return ExtractResult(text=text[:MAX_TEXT] or None, kind="text")


def extract_pptx(path: Path) -> ExtractResult:
    from pptx import Presentation

    prs = Presentation(path)
    parts = [
        shape.text
        for slide in prs.slides
        for shape in slide.shapes
        if shape.has_text_frame
    ]
    text = "\n".join(parts).strip()
    return ExtractResult(text=text[:MAX_TEXT] or None, kind="text")


def extract(path: Path) -> ExtractResult:
    """Extract content from a file. Never raises on corrupt files."""
    ext = path.suffix.lower()
    try:
        if path.stat().st_size == 0:
            return ExtractResult(kind="empty")
        if ext == ".pdf":
            return extract_pdf(path)
        if ext in IMAGE_EXTENSIONS:
            return extract_image(path)
        if ext == ".docx":
            return extract_docx(path)
        if ext == ".pptx":
            return extract_pptx(path)
        if ext in {".txt", ".md"}:
            return ExtractResult(text=path.read_text(errors="replace")[:MAX_TEXT], kind="text")
        return ExtractResult(kind="unsupported")
    except Exception:
        return ExtractResult(kind="corrupt")


def cleanup(result: ExtractResult):
    """Remove any temp rasterization artifacts."""
    if result.image_path:
        p = Path(result.image_path)
        if p.name.startswith(".") and p.suffix == ".png":
            p.unlink(missing_ok=True)
