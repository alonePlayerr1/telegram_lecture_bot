from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import uuid

from .audio_tools import to_mp3, split_audio_mp3
from .lang import detect_language
from .openai_client import OpenAIService
from .text_extract import extract_text

log = logging.getLogger("worker")

@dataclass
class TaskResult:
    task_id: str
    result_path: Path
    source_lang: str | None

def _safe_stem(name: str) -> str:
    import re
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._")
    return name[:80] if name else "lecture"

def process_task(
    *,
    task_id: str,
    input_type: str,
    input_path: str | None,
    target_lang: str,
    oai: OpenAIService,
    work_dir: Path,
    keep_temp: bool,
) -> TaskResult:
    work_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = work_dir / "tmp" / task_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    src_lang: str | None = None
    translated: str = ""

    if input_type == "text":
        assert input_path is not None
        text = Path(input_path).read_text(encoding="utf-8", errors="replace")
        src_lang = detect_language(text)
        translated = oai.translate_text(text, target_lang=target_lang, source_lang=src_lang)

    elif input_type == "document":
        assert input_path is not None
        text = extract_text(Path(input_path))
        if not text.strip():
            raise RuntimeError("Не смог извлечь текст из документа (возможно, это скан без OCR).")
        src_lang = detect_language(text)
        translated = oai.translate_text(text, target_lang=target_lang, source_lang=src_lang)

    elif input_type == "audio":
        assert input_path is not None
        src = Path(input_path)
        mp3 = temp_dir / f"{src.stem}.mp3"
        to_mp3(src, mp3)

        # chunk to avoid big uploads
        chunk_min = max(2, int(os.getenv("MAX_AUDIO_CHUNK_MIN", "8")))
        parts = split_audio_mp3(mp3, chunk_minutes=chunk_min)

        transcript_parts: list[str] = []
        for i, p in enumerate(parts, start=1):
            log.info("Task %s: transcribing part %s/%s", task_id, i, len(parts))
            transcript_parts.append(oai.transcribe(str(p), language=None))

        transcript = "\n\n".join([t.strip() for t in transcript_parts if t.strip()]).strip()
        if not transcript:
            raise RuntimeError("Транскрипт пустой. Проверьте качество аудио/формат.")

        src_lang = detect_language(transcript)
        translated = oai.translate_text(transcript, target_lang=target_lang, source_lang=src_lang)

    else:
        raise ValueError(f"Unknown input_type: {input_type}")

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_name = f"{_safe_stem(task_id)}_{stamp}_{(src_lang or 'auto')}_to_{target_lang}.txt"
    out_path = work_dir / "out" / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(translated.strip() + "\n", encoding="utf-8")

    if not keep_temp:
        # best-effort cleanup
        try:
            for p in sorted(temp_dir.rglob("*"), reverse=True):
                if p.is_file():
                    p.unlink()
                else:
                    p.rmdir()
        except Exception:
            pass

    return TaskResult(task_id=task_id, result_path=out_path, source_lang=src_lang)
