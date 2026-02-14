from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
import uuid

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from .config import load_settings
from .logging_setup import setup_logging
from .storage import Storage
from .openai_client import OpenAIService
from .worker import process_task

log = logging.getLogger("lecturebot")

def _new_task_id() -> str:
    return uuid.uuid4().hex[:12]

def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def _user_allowed(user_id: int, allowed: set[int]) -> bool:
    return (not allowed) or (user_id in allowed)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = context.application.bot_data["settings"]
    uid = update.effective_user.id if update.effective_user else 0
    if not _user_allowed(uid, s.allowed_user_ids):
        await update.message.reply_text("⛔️ Доступ запрещён. Добавьте ваш user_id в ALLOWED_USER_IDS.")
        return

    storage: Storage = context.application.bot_data["storage"]
    pref = storage.get_pref_target_lang(uid) or s.default_target_lang
    await update.message.reply_text(
        "🧠📚 *Lecture Translator Bot*\n\n"
        "Кидай текст/документ/аудио, а я верну `.txt` с переводом.\n\n"
        f"Текущий целевой язык: *{pref}*\n\n"
        "Команды:\n"
        "/settarget ru|en|de|...\n"
        "/status\n"
        "/cancel <task_id>\n",
        parse_mode="Markdown",
    )

async def cmd_settarget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = context.application.bot_data["settings"]
    uid = update.effective_user.id if update.effective_user else 0
    if not _user_allowed(uid, s.allowed_user_ids):
        await update.message.reply_text("⛔️ Доступ запрещён.")
        return

    if not context.args:
        await update.message.reply_text("Напиши: /settarget ru (или en, de, ...)")
        return
    lang = context.args[0].strip().lower()
    if len(lang) < 2 or len(lang) > 12:
        await update.message.reply_text("Странный код языка. Пример: ru, en, de")
        return
    storage: Storage = context.application.bot_data["storage"]
    storage.set_pref_target_lang(uid, lang)
    await update.message.reply_text(f"✅ Ок. Теперь целевой язык: {lang}")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = context.application.bot_data["settings"]
    uid = update.effective_user.id if update.effective_user else 0
    if not _user_allowed(uid, s.allowed_user_ids):
        await update.message.reply_text("⛔️ Доступ запрещён.")
        return

    storage: Storage = context.application.bot_data["storage"]
    tasks = storage.list_tasks(uid, limit=10)
    if not tasks:
        await update.message.reply_text("Пока задач нет.")
        return
    lines = ["Последние задачи:"]
    for t in tasks:
        lines.append(f"- `{t['id']}` • {t['status']} • {t['input_type']} • {t['created_at']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = context.application.bot_data["settings"]
    uid = update.effective_user.id if update.effective_user else 0
    if not _user_allowed(uid, s.allowed_user_ids):
        await update.message.reply_text("⛔️ Доступ запрещён.")
        return
    if not context.args:
        await update.message.reply_text("Напиши: /cancel <task_id>")
        return
    task_id = context.args[0].strip()
    storage: Storage = context.application.bot_data["storage"]
    ok = storage.cancel_task(task_id, uid)
    await update.message.reply_text("✅ Отменено." if ok else "Не получилось отменить (нет задачи или она уже завершена).")

async def _enqueue_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    task_id: str | None = None,
    input_type: str,
    input_path: str | None,
) -> str:
    s = context.application.bot_data["settings"]
    storage: Storage = context.application.bot_data["storage"]

    uid = update.effective_user.id if update.effective_user else 0
    if not _user_allowed(uid, s.allowed_user_ids):
        await update.message.reply_text("⛔️ Доступ запрещён.")
        return ""

    target = storage.get_pref_target_lang(uid) or s.default_target_lang
    task_id = task_id or _new_task_id()

    storage.add_task({
        "id": task_id,
        "chat_id": update.effective_chat.id,
        "user_id": uid,
        "created_at": _now_iso(),
        "status": "queued",
        "input_type": input_type,
        "input_path": input_path,
        "target_lang": target,
    })

    q: asyncio.Queue[str] = context.application.bot_data["queue"]
    await q.put(task_id)

    await update.message.reply_text(
        f"🧾 Принято. Задача `{task_id}` в очереди.\n"
        f"Целевой язык: *{target}*",
        parse_mode="Markdown",
    )
    return task_id

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    s = context.application.bot_data["settings"]
    storage: Storage = context.application.bot_data["storage"]
    uid = update.effective_user.id if update.effective_user else 0
    if not _user_allowed(uid, s.allowed_user_ids):
        await update.message.reply_text("⛔️ Доступ запрещён.")
        return

    task_id = _new_task_id()
    inbox = s.data_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / f"{task_id}.txt"
    path.write_text(update.message.text, encoding="utf-8")

    target = storage.get_pref_target_lang(uid) or s.default_target_lang
    storage.add_task({
        "id": task_id,
        "chat_id": update.effective_chat.id,
        "user_id": uid,
        "created_at": _now_iso(),
        "status": "queued",
        "input_type": "text",
        "input_path": str(path),
        "target_lang": target,
    })
    q: asyncio.Queue[str] = context.application.bot_data["queue"]
    await q.put(task_id)

    await update.message.reply_text(
        f"🧾 Принято. Задача `{task_id}` в очереди.\n"
        f"Целевой язык: *{target}*",
        parse_mode="Markdown",
    )

async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.document:
        return

    s = context.application.bot_data["settings"]
    uid = update.effective_user.id if update.effective_user else 0
    if not _user_allowed(uid, s.allowed_user_ids):
        await update.message.reply_text("⛔️ Доступ запрещён.")
        return

    doc = update.message.document
    if doc.file_size and doc.file_size > s.max_telegram_file_mb * 1024 * 1024:
        await update.message.reply_text(f"Файл слишком большой (лимит {s.max_telegram_file_mb} МБ).")
        return

    filename = (doc.file_name or "file").lower()
    if not (filename.endswith(".txt") or filename.endswith(".docx") or filename.endswith(".pdf")):
        await update.message.reply_text("Поддерживаю документы: .txt, .docx, .pdf (текстовый).")
        return

    inbox = s.data_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    task_id = _new_task_id()
    dst = inbox / f"{task_id}_{Path(filename).name}"

    await update.message.chat.send_action(ChatAction.TYPING)
    f = await context.bot.get_file(doc.file_id)
    await f.download_to_drive(custom_path=str(dst))

    await _enqueue_task(update, context, task_id=task_id, input_type="document", input_path=str(dst))

async def on_audioish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    s = context.application.bot_data["settings"]
    uid = update.effective_user.id if update.effective_user else 0
    if not _user_allowed(uid, s.allowed_user_ids):
        await update.message.reply_text("⛔️ Доступ запрещён.")
        return

    file_id = None
    filename = None
    size = None

    if update.message.voice:
        file_id = update.message.voice.file_id
        size = update.message.voice.file_size
        filename = "voice.ogg"
    elif update.message.audio:
        file_id = update.message.audio.file_id
        size = update.message.audio.file_size
        filename = update.message.audio.file_name or "audio"
    elif update.message.video_note:
        file_id = update.message.video_note.file_id
        size = update.message.video_note.file_size
        filename = "video_note.mp4"
    elif update.message.video:
        file_id = update.message.video.file_id
        size = update.message.video.file_size
        filename = update.message.video.file_name or "video.mp4"
    else:
        return

    if size and size > s.max_telegram_file_mb * 1024 * 1024:
        await update.message.reply_text(f"Файл слишком большой (лимит {s.max_telegram_file_mb} МБ).")
        return

    inbox = s.data_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    task_id = _new_task_id()
    ext = Path(filename).suffix or ".bin"
    dst = inbox / f"{task_id}{ext}"

    await update.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
    f = await context.bot.get_file(file_id)
    await f.download_to_drive(custom_path=str(dst))

    await _enqueue_task(update, context, task_id=task_id, input_type="audio", input_path=str(dst))

async def worker_loop(app: Application) -> None:
    s = app.bot_data["settings"]
    storage: Storage = app.bot_data["storage"]
    q: asyncio.Queue[str] = app.bot_data["queue"]
    oai: OpenAIService = app.bot_data["oai"]

    while True:
        task_id = await q.get()
        try:
            task = storage.get_task(task_id)
            if not task:
                continue
            if task["status"] == "canceled":
                continue

            if not storage.claim_task(task_id):
                continue

            chat_id = int(task["chat_id"])
            await app.bot.send_message(chat_id=chat_id, text=f"⚙️ Начал обработку `{task_id}`…", parse_mode="Markdown")

            res = await asyncio.to_thread(
                process_task,
                task_id=task_id,
                input_type=task["input_type"],
                input_path=task.get("input_path"),
                target_lang=task["target_lang"],
                oai=oai,
                work_dir=s.data_dir,
                keep_temp=s.keep_temp_files,
            )

            storage.set_result(task_id, str(res.result_path), res.source_lang)

            bio = BytesIO(res.result_path.read_bytes())
            bio.name = res.result_path.name

            caption = (
                f"✅ Готово: `{task_id}`\n"
                f"Язык источника: `{res.source_lang or 'auto'}`\n"
                f"Перевод: `{task['target_lang']}`"
            )
            await app.bot.send_document(chat_id=chat_id, document=bio, caption=caption, parse_mode="Markdown")

        except Exception as e:
            log.exception("Task %s failed: %s", task_id, e)
            storage.set_status(task_id, "failed", error=str(e))
            try:
                task = storage.get_task(task_id)
                if task:
                    await app.bot.send_message(chat_id=int(task["chat_id"]), text=f"❌ Ошибка в задаче `{task_id}`: {e}", parse_mode="Markdown")
            except Exception:
                pass
        finally:
            q.task_done()

async def on_startup(app: Application) -> None:
    storage: Storage = app.bot_data["storage"]
    n = storage.reset_stuck_processing()
    if n:
        log.warning("Reset %s stuck processing tasks -> queued", n)

    q: asyncio.Queue[str] = app.bot_data["queue"]
    for tid in storage.list_queued_ids(limit=500):
        await q.put(tid)

    app.create_task(worker_loop(app))

def main() -> None:
    load_dotenv()

    s = load_settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(s.data_dir / "logs", level=s.log_level)

    storage = Storage(s.data_dir / "db" / "tasks.sqlite3")
    oai = OpenAIService(
        api_key=s.openai_key,
        transcribe_model=s.transcribe_model,
        translate_model=s.translate_model,
    )

    app = Application.builder().token(s.telegram_token).build()
    app.bot_data["settings"] = s
    app.bot_data["storage"] = storage
    app.bot_data["oai"] = oai
    app.bot_data["queue"] = asyncio.Queue()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("settarget", cmd_settarget))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE | filters.VIDEO, on_audioish))

    app.post_init = on_startup

    log.info("Starting bot…")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
