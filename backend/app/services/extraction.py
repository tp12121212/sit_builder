from __future__ import annotations

import io
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExtractionResult:
    text: str
    method: str
    ocr_confidence: float | None
    page_count: int | None
    metadata: dict


def _read_text_fallback(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _ocr_pdf_with_tesseract(doc) -> tuple[str, bool]:
    try:
        import fitz  # type: ignore
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return "", False

    page_texts: list[str] = []
    for page in doc:
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(image)
            page_texts.append(text)
        except Exception:
            page_texts.append("")

    joined = "\n".join(page_texts).strip()
    return joined, bool(joined)


def _extract_pdf(path: Path, force_ocr: bool = False) -> ExtractionResult:
    try:
        import fitz  # type: ignore

        doc = fitz.open(path)
        page_count = len(doc)
        native_text = "\n".join(page.get_text("text") for page in doc).strip()

        if force_ocr:
            ocr_text, ocr_used = _ocr_pdf_with_tesseract(doc)
            return ExtractionResult(
                text=ocr_text if ocr_used else native_text,
                method="OCR" if ocr_used else "NATIVE",
                ocr_confidence=None,
                page_count=page_count,
                metadata={
                    "module": "pymupdf+pytesseract" if ocr_used else "pymupdf-text",
                    "ocr_performed": ocr_used,
                    "force_ocr_requested": True,
                },
            )

        # Auto-detect image/scanned PDFs: no native text -> OCR fallback.
        if not native_text:
            ocr_text, ocr_used = _ocr_pdf_with_tesseract(doc)
            if ocr_used:
                return ExtractionResult(
                    text=ocr_text,
                    method="OCR",
                    ocr_confidence=None,
                    page_count=page_count,
                    metadata={
                        "module": "pymupdf+pytesseract",
                        "ocr_performed": True,
                        "ocr_reason": "auto_image_pdf",
                    },
                )

        return ExtractionResult(
            text=native_text,
            method="NATIVE",
            ocr_confidence=None,
            page_count=page_count,
            metadata={"module": "pymupdf-text", "ocr_performed": False},
        )
    except Exception:
        return ExtractionResult(
            text=_read_text_fallback(path),
            method="NATIVE",
            ocr_confidence=None,
            page_count=None,
            metadata={"module": "fallback-text-reader", "ocr_performed": False},
        )


def _extract_docx(path: Path) -> ExtractionResult:
    try:
        from docx import Document  # type: ignore

        doc = Document(str(path))
        text = "\n".join(p.text for p in doc.paragraphs)
        return ExtractionResult(
            text=text,
            method="NATIVE",
            ocr_confidence=None,
            page_count=None,
            metadata={"module": "python-docx", "ocr_performed": False},
        )
    except Exception:
        return ExtractionResult(
            text=_read_text_fallback(path),
            method="NATIVE",
            ocr_confidence=None,
            page_count=None,
            metadata={"module": "fallback-text-reader", "ocr_performed": False},
        )


def _extract_image(path: Path) -> ExtractionResult:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        image = Image.open(path)
        text = pytesseract.image_to_string(image)
        return ExtractionResult(
            text=text,
            method="OCR",
            ocr_confidence=None,
            page_count=1,
            metadata={"module": "pytesseract-image", "ocr_engine": "tesseract", "ocr_performed": True},
        )
    except Exception:
        return ExtractionResult(
            text="",
            method="OCR",
            ocr_confidence=None,
            page_count=1,
            metadata={"module": "pytesseract-image", "ocr_engine": "unavailable", "ocr_performed": False},
        )


def _extract_json(path: Path) -> ExtractionResult:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        text = json.dumps(payload, indent=2)
    except Exception:
        text = _read_text_fallback(path)
    return ExtractionResult(
        text=text,
        method="NATIVE",
        ocr_confidence=None,
        page_count=None,
        metadata={"module": "json-parser", "ocr_performed": False},
    )


def extract_text(path: str, content_type: str | None = None, force_ocr: bool = False) -> ExtractionResult:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    guessed_type = content_type or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

    if suffix in {".txt", ".csv", ".md", ".log", ".xml", ".yaml", ".yml"}:
        return ExtractionResult(
            text=_read_text_fallback(file_path),
            method="NATIVE",
            ocr_confidence=None,
            page_count=None,
            metadata={"mime": guessed_type, "module": "text-reader", "ocr_performed": False, "force_ocr_requested": force_ocr},
        )

    if suffix == ".json":
        return _extract_json(file_path)

    if suffix == ".pdf":
        return _extract_pdf(file_path, force_ocr=force_ocr)

    if suffix in {".docx"}:
        return _extract_docx(file_path)

    if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"}:
        return _extract_image(file_path)

    return ExtractionResult(
        text=_read_text_fallback(file_path),
        method="NATIVE",
        ocr_confidence=None,
        page_count=None,
        metadata={"mime": guessed_type, "warning": "best-effort extraction", "module": "fallback-text-reader", "ocr_performed": False, "force_ocr_requested": force_ocr},
    )
