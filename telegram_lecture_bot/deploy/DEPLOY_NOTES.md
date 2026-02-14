## Systemd deployment (пример)

```bash
# 1) Пользователь без sudo
sudo useradd --system --home /opt/lecturebot --shell /usr/sbin/nologin lecturebot

# 2) Код
sudo mkdir -p /opt/lecturebot
sudo chown -R lecturebot:lecturebot /opt/lecturebot

# 3) Python + ffmpeg
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg

# 4) Виртуальное окружение
sudo -u lecturebot python3 -m venv /opt/lecturebot/.venv
sudo -u lecturebot /opt/lecturebot/.venv/bin/pip install -U pip
sudo -u lecturebot /opt/lecturebot/.venv/bin/pip install -r /opt/lecturebot/requirements.txt

# 5) Секреты
sudo nano /opt/lecturebot/deploy/systemd/lecturebot.env
sudo chown lecturebot:lecturebot /opt/lecturebot/deploy/systemd/lecturebot.env
sudo chmod 600 /opt/lecturebot/deploy/systemd/lecturebot.env

# 6) Сервис
sudo cp /opt/lecturebot/deploy/systemd/lecturebot.service /etc/systemd/system/lecturebot.service
sudo systemctl daemon-reload
sudo systemctl enable --now lecturebot

sudo systemctl status lecturebot --no-pager
journalctl -u lecturebot -f
```

### Мини-харднинг
- Убедитесь, что каталог `/opt/lecturebot` доступен только `lecturebot`.
- В идеале запускайте на отдельном VPS/контейнере.
- Не публикуйте `.env` и `lecturebot.env`.
