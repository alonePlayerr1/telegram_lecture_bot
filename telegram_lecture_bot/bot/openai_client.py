from __future__ import annotations
import logging
import os
from openai import OpenAI
from .retry import retry

log = logging.getLogger("openai")

def _split_text(text: str, max_chars: int) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    paras = text.split("\n\n")
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0

    def flush():
        nonlocal cur, cur_len
        if cur:
            chunks.append("\n\n".join(cur).strip())
            cur = []
            cur_len = 0

    for para in paras:
        para = para.strip()
        if not para:
            continue
        add_len = len(para) + (2 if cur else 0)
        if cur_len + add_len <= max_chars:
            cur.append(para)
            cur_len += add_len
        else:
            flush()
            if len(para) <= max_chars:
                cur.append(para)
                cur_len = len(para)
            else:
                # Very long paragraph: hard-split
                start = 0
                while start < len(para):
                    chunks.append(para[start:start+max_chars])
                    start += max_chars

    flush()
    return chunks

class OpenAIService:
    def __init__(self, api_key: str, transcribe_model: str, translate_model: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.transcribe_model = transcribe_model
        self.translate_model = translate_model

    def transcribe(self, audio_path: str, language: str | None = None) -> str:
        def _call():
            with open(audio_path, "rb") as f:
                resp = self.client.audio.transcriptions.create(
                    model=self.transcribe_model,
                    file=f,
                    language=language,
                )
                return getattr(resp, "text", str(resp))
        return retry(_call, tries=5)

    def _translate_chunk(self, chunk: str, target_lang: str, source_lang: str | None) -> str:
        system = (
            "You are a careful translator. Output ONLY the translated plain text. "
            "Preserve structure, lists, formulas, and punctuation. Do not add commentary."
        )
        user = (
            f"Translate the following text into '{target_lang}'."
            + (f" Source language is '{source_lang}'." if source_lang else "")
            + "\n\nTEXT:\n"
            + chunk
        )

        def _responses():
            resp = self.client.responses.create(
                model=self.translate_model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            out = getattr(resp, "output_text", None)
            if out:
                return out
            try:
                parts = []
                for item in resp.output:
                    if getattr(item, "type", "") == "message":
                        for c in item.content:
                            if getattr(c, "type", "") in ("output_text", "text"):
                                parts.append(getattr(c, "text", ""))
                joined = "".join(parts).strip()
                return joined or str(resp)
            except Exception:
                return str(resp)

        def _chat():
            resp = self.client.chat.completions.create(
                model=self.translate_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()

        def _call():
            try:
                return _responses()
            except Exception as e:
                log.warning("responses API failed, falling back to chat.completions: %s", e)
                return _chat()

        return retry(_call, tries=5)

    def translate_text(self, text: str, target_lang: str, source_lang: str | None) -> str:
        max_chars = int(os.getenv("MAX_TRANSLATE_CHARS", "12000"))
        chunks = _split_text(text, max_chars=max_chars)
        if len(chunks) == 1:
            return self._translate_chunk(chunks[0], target_lang, source_lang)

        out_parts: list[str] = []
        for i, ch in enumerate(chunks, start=1):
            log.info("Translating chunk %s/%s (%s chars)", i, len(chunks), len(ch))
            out_parts.append(self._translate_chunk(ch, target_lang, source_lang).strip())
        return "\n\n".join([p for p in out_parts if p])
