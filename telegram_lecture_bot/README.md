# Telegram Lecture Translator Bot (TXT output)

Бот принимает **текст / .txt / .docx / .pdf (текстовый)** и **аудио (voice/audio/video_note/video)**, затем:
1) (если аудио) делает **транскрипт** через OpenAI Whisper
2) автоматически определяет язык (по тексту)
3) переводит в целевой язык
4) отправляет вам готовый **.txt** файлом в Telegram

## Важно про безопасность
- **НЕ** вставляйте ключи в код.
- Храните секреты в `.env` (chmod 600) или в `systemd EnvironmentFile`.
- Ограничьте доступ к боту по `ALLOWED_USER_IDS` (только ваши Telegram user_id).
- Если вы где-то уже публиковали ключ (например, в коде/чате), **срочно отзовите его** и создайте новый.

## Быстрый старт (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg
mkdir -p ~/lecturebot && cd ~/lecturebot

# Скопируйте сюда файлы проекта (или распакуйте zip)
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

cp .env.example .env
nano .env
chmod 600 .env

python -m bot
```

## .env настройки
Минимум нужно:
- `TELEGRAM_BOT_TOKEN` (у BotFather)
- `OPENAI_API_KEY`
- `ALLOWED_USER_IDS` (например: `123456789,987654321`)
- `DEFAULT_TARGET_LANG` (например `ru` или `en`)

## Команды
- `/start` помощь
- `/settarget ru|en|de|...` установить целевой язык
- `/status` показать очередь
- `/cancel <task_id>` отменить задачу

## Запуск как сервис (systemd)
Смотрите `deploy/systemd/lecturebot.service` и `deploy/systemd/lecturebot.env`.
