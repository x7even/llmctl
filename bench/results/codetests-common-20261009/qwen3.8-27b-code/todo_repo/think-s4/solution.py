from __future__ import annotations

import sqlite3


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
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

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "priority": row["priority"],
            "done": bool(row["done"]),
        }

    def add(self, title: str, priority: int = 3) -> int:
        if not isinstance(title, str):
            raise ValueError("title must be a string")

        title = title.strip()
        if not title:
            raise ValueError("title must not be empty")

        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError("priority must be an integer")
        if not 1 <= priority <= 5:
            raise ValueError("priority must be between 1 and 5")

        cursor = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (title, priority),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get(self, todo_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_dict(row)

    def list(self, done: bool | None = None) -> list[dict]:
        query = "SELECT id, title, priority, done FROM todos"
        params = ()

        if done is not None:
            query += " WHERE done = ?"
            params = (int(done),)

        query += " ORDER BY priority ASC, id ASC"

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def mark_done(self, todo_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()

        if row is None:
            return False

        self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return True

    def delete(self, todo_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        query = "SELECT COUNT(*) FROM todos"
        params = ()

        if done is not None:
            query += " WHERE done = ?"
            params = (int(done),)

        return self._conn.execute(query, params).fetchone()[0]

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.commit()
            except sqlite3.ProgrammingError:
                pass
            finally:
                self._conn.close()
                self._conn = None
