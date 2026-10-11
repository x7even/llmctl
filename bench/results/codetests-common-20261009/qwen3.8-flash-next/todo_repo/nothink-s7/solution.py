import sqlite3
from typing import Optional


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
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
        if not isinstance(title, str):
            raise ValueError("Title must be a string")
        stripped_title = title.strip()
        if not stripped_title:
            raise ValueError("Title cannot be empty or whitespace-only")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("Priority must be an integer")
        if priority < 1 or priority > 5:
            raise ValueError("Priority must be between 1 and 5")
        cursor = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, ?)",
            (stripped_title, priority, 0)
        )
        self._conn.commit()
        return cursor.lastrowid

    def get(self, todo_id: int) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "priority": row["priority"],
            "done": bool(row["done"])
        }

    def list(self, done: Optional[bool] = None) -> list[dict]:
        if done is None:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = ? ORDER BY priority ASC, id ASC",
                (int(done),)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "priority": row["priority"],
                "done": bool(row["done"])
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
            row = self._conn.execute("SELECT COUNT(*) FROM todos").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?",
                (int(done),)
            ).fetchone()
        return row[0]

    def close(self) -> None:
        self._conn.close()
