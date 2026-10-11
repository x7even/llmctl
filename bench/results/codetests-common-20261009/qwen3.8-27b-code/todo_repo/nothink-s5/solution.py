import sqlite3
from typing import Optional


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                priority INTEGER NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()

    def add(self, title: str, priority: int = 3) -> int:
        stripped = title.strip()
        if not stripped:
            raise ValueError("Title must not be empty or whitespace-only")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("Priority must be an integer")
        if priority < 1 or priority > 5:
            raise ValueError("Priority must be between 1 and 5")
        cur = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (stripped, priority),
        )
        self._conn.commit()
        return cur.lastrowid

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "priority": row["priority"],
            "done": bool(row["done"]),
        }

    def get(self, todo_id: int) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list(self, done: Optional[bool] = None) -> list[dict]:
        if done is None:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC"
            ).fetchall()
        else:
            done_int = 1 if done else 0
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = ? ORDER BY priority ASC, id ASC",
                (done_int,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def mark_done(self, todo_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete(self, todo_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def count(self, done: Optional[bool] = None) -> int:
        if done is None:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM todos").fetchone()
        else:
            done_int = 1 if done else 0
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM todos WHERE done = ?",
                (done_int,),
            ).fetchone()
        return row["c"]

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()
