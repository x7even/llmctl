import sqlite3
from typing import Optional


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                priority INTEGER NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._conn.commit()

    def add(self, title: str, priority: int = 3) -> int:
        stripped_title = title.strip()
        if not stripped_title:
            raise ValueError("Title cannot be empty or whitespace-only")
        if not isinstance(priority, int) or priority < 1 or priority > 5:
            raise ValueError("Priority must be an int from 1 to 5")
        cursor = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, ?)",
            (stripped_title, priority, 0)
        )
        self._conn.commit()
        return cursor.lastrowid

    def get(self, todo_id: int) -> Optional[dict]:
        cursor = self._conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "priority": row[2],
            "done": bool(row[3])
        }

    def list(self, done: Optional[bool] = None) -> list[dict]:
        if done is None:
            cursor = self._conn.execute(
                "SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC"
            )
        elif done:
            cursor = self._conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = 1 ORDER BY priority ASC, id ASC"
            )
        else:
            cursor = self._conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = 0 ORDER BY priority ASC, id ASC"
            )
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "title": row[1],
                "priority": row[2],
                "done": bool(row[3])
            }
            for row in rows
        ]

    def mark_done(self, todo_id: int) -> bool:
        cursor = self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?",
            (todo_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete(self, todo_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self, done: Optional[bool] = None) -> int:
        if done is None:
            cursor = self._conn.execute("SELECT COUNT(*) FROM todos")
        elif done:
            cursor = self._conn.execute("SELECT COUNT(*) FROM todos WHERE done = 1")
        else:
            cursor = self._conn.execute("SELECT COUNT(*) FROM todos WHERE done = 0")
        return cursor.fetchone()[0]

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()
