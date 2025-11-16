from __future__ import annotations

import io
from typing import Optional

from docx import Document
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except ImportError:
    pdf_extract_text = None


async def read_upload(upload) -> str:
    if upload is None:
        return ""
    data = await upload.read()
    if not data:
        return ""
    filename = (upload.filename or "").lower()
    content_type = (upload.content_type or "").lower()
    if filename.endswith(".pdf") or "pdf" in content_type:
        return extract_pdf(data)
    if filename.endswith(".docx") or "wordprocessingml" in content_type:
        return extract_docx(data)
    if filename.endswith((".png", ".jpg", ".jpeg")) or "image" in content_type:
        return extract_image(data)
    return data.decode("utf-8", errors="ignore")


def extract_pdf(data: bytes) -> str:
    if pdf_extract_text is None:
        return ""
    try:
        return pdf_extract_text(io.BytesIO(data)).strip()
    except Exception:
        return ""


def extract_docx(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs if p.text).strip()
    except Exception:
        return ""


def extract_image(data: bytes) -> str:
    if pytesseract is None:
        return ""
    try:
        image = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(image, lang="eng+rus").strip()
    except Exception:
        return ""
