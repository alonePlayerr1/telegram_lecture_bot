import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  chat_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  input_type TEXT NOT NULL,
  input_path TEXT,
  source_lang TEXT,
  target_lang TEXT NOT NULL,
  result_path TEXT,
  error TEXT
);

CREATE TABLE IF NOT EXISTS prefs (
  user_id INTEGER PRIMARY KEY,
  target_lang TEXT NOT NULL
);
"""

class Storage:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def add_task(self, task: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO tasks (id, chat_id, user_id, created_at, status, input_type, input_path, target_lang)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task["id"],
                    task["chat_id"],
                    task["user_id"],
                    task["created_at"],
                    task["status"],
                    task["input_type"],
                    task.get("input_path"),
                    task["target_lang"],
                ),
            )
            conn.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(row) if row else None

    def list_tasks(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if user_id < 0:
                rows = conn.execute(
                    """SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM tasks
                       WHERE user_id=?
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (user_id, limit),
                ).fetchall()
            return [dict(r) for r in rows]

    def list_queued_ids(self, limit: int = 200) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id FROM tasks WHERE status='queued' ORDER BY created_at ASC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [str(r["id"]) for r in rows]

    def claim_task(self, task_id: str) -> bool:
        """Atomically move queued -> processing. Returns True if claimed."""
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE tasks SET status='processing'
                   WHERE id=? AND status='queued'""",
                (task_id,),
            )
            conn.commit()
            return cur.rowcount == 1

    def set_status(self, task_id: str, status: str, *, error: str | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE tasks SET status=?, error=? WHERE id=?""",
                (status, error, task_id),
            )
            conn.commit()

    def set_result(self, task_id: str, result_path: str, source_lang: str | None) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE tasks SET status='done', result_path=?, source_lang=? WHERE id=?""",
                (result_path, source_lang, task_id),
            )
            conn.commit()

    def reset_stuck_processing(self) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE tasks SET status='queued' WHERE status='processing'"""
            )
            conn.commit()
            return cur.rowcount

    def get_pref_target_lang(self, user_id: int) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT target_lang FROM prefs WHERE user_id=?""",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return str(row["target_lang"])

    def set_pref_target_lang(self, user_id: int, lang: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO prefs(user_id, target_lang)
                   VALUES(?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET target_lang=excluded.target_lang""",
                (user_id, lang),
            )
            conn.commit()

    def cancel_task(self, task_id: str, user_id: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT status FROM tasks WHERE id=? AND user_id=?""",
                (task_id, user_id),
            ).fetchone()
            if not row:
                return False
            if row["status"] in ("done", "failed", "canceled"):
                return False
            conn.execute(
                """UPDATE tasks SET status='canceled' WHERE id=? AND user_id=?""",
                (task_id, user_id),
            )
            conn.commit()
            return True
