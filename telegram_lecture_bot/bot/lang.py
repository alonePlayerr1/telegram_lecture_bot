from __future__ import annotations

def detect_language(text: str) -> str | None:
    text = (text or "").strip()
    if len(text) < 20:
        return None
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return None
