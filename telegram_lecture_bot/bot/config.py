import os
from dataclasses import dataclass
from pathlib import Path

def _getenv(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name, default)
    if val is None:
        return None
    return val.strip()

def _parse_int(name: str, default: int) -> int:
    v = _getenv(name)
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default

def _parse_bool(name: str, default: bool=False) -> bool:
    v = (_getenv(name) or "").lower()
    if v in {"1","true","yes","y","on"}:
        return True
    if v in {"0","false","no","n","off"}:
        return False
    return default

def _parse_user_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            pass
    return out

@dataclass(frozen=True)
class Settings:
    telegram_token: str
    openai_key: str

    transcribe_model: str = "whisper-1"
    translate_model: str = "gpt-4o-mini"

    allowed_user_ids: set[int] = None  # type: ignore
    default_target_lang: str = "ru"

    data_dir: Path = Path("./data")
    log_level: str = "INFO"

    max_telegram_file_mb: int = 49
    max_audio_chunk_min: int = 8
    keep_temp_files: bool = False

def load_settings() -> Settings:
    telegram_token = _getenv("TELEGRAM_BOT_TOKEN")
    openai_key = _getenv("OPENAI_API_KEY")

    if not telegram_token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN in environment/.env")
    if not openai_key:
        raise RuntimeError("Missing OPENAI_API_KEY in environment/.env")

    s = Settings(
        telegram_token=telegram_token,
        openai_key=openai_key,
        transcribe_model=_getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1") or "whisper-1",
        translate_model=_getenv("OPENAI_TRANSLATE_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
        allowed_user_ids=_parse_user_ids(_getenv("ALLOWED_USER_IDS")),
        default_target_lang=_getenv("DEFAULT_TARGET_LANG", "ru") or "ru",
        data_dir=Path(_getenv("DATA_DIR", "./data") or "./data"),
        log_level=_getenv("LOG_LEVEL", "INFO") or "INFO",
        max_telegram_file_mb=_parse_int("MAX_TELEGRAM_FILE_MB", 49),
        max_audio_chunk_min=_parse_int("MAX_AUDIO_CHUNK_MIN", 8),
        keep_temp_files=_parse_bool("KEEP_TEMP_FILES", False),
    )
    return s
