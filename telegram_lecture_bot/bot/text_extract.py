from __future__ import annotations
from pathlib import Path

def extract_text_from_txt(path: Path) -> str:
    # try utf-8, fallback cp1251
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="cp1251", errors="replace")

def extract_text_from_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    parts: list[str] = []
    for p in doc.paragraphs:
        parts.append(p.text)
    return "\n".join(parts).strip()

def extract_text_from_pdf(path: Path) -> str:
    import pdfplumber
    parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if txt.strip():
                parts.append(txt)
    return "\n\n".join(parts).strip()

def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return extract_text_from_txt(path)
    if ext == ".docx":
        return extract_text_from_docx(path)
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    raise ValueError(f"Unsupported document type: {ext}")
