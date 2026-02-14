from __future__ import annotations
from pathlib import Path
from pydub import AudioSegment
from pydub.utils import make_chunks

def to_mp3(src: Path, dst: Path) -> Path:
    audio = AudioSegment.from_file(str(src))
    dst.parent.mkdir(parents=True, exist_ok=True)
    audio.export(str(dst), format="mp3", bitrate="64k")
    return dst

def split_audio_mp3(mp3_path: Path, chunk_minutes: int) -> list[Path]:
    audio = AudioSegment.from_file(str(mp3_path))
    chunk_ms = int(chunk_minutes * 60 * 1000)
    chunks = make_chunks(audio, chunk_ms)
    out: list[Path] = []
    for i, c in enumerate(chunks):
        p = mp3_path.parent / f"{mp3_path.stem}_part{i:03d}.mp3"
        c.export(str(p), format="mp3", bitrate="64k")
        out.append(p)
    return out
