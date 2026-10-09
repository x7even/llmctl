from __future__ import annotations

import sqlite3


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
                done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1))
            )
            """
        )
        self._conn.commit()

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        return {
            "id": row[0],
            "title": row[1],
            "priority": row[2],
            "done": bool(row[3]),
        }

    def add(self, title: str, priority: int = 3) -> int:
        if not isinstance(title, str):
            raise ValueError("title must be a string")

        title = title.strip()
        if not title:
            raise ValueError("title must not be empty")

        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an int")
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
        return self._row_to_dict(row) if row is not None else None

    def list(self, done: bool | None = None) -> list[dict]:
        query = "SELECT id, title, priority, done FROM todos"
        params = []

        if done is not None:
            query += " WHERE done = ?"
            params.append(1 if done else 0)

        query += " ORDER BY priority ASC, id ASC"

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def mark_done(self, todo_id: int) -> bool:
        row = self._conn.execute(
            "SELECT done FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()

        if row is None:
            return False

        if not row[0]:
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
        params = []

        if done is not None:
            query += " WHERE done = ?"
            params.append(1 if done else 0)

        return self._conn.execute(query, params).fetchone()[0]

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.commit()
            except sqlite3.Error:
                pass
            finally:
                self._conn.close()
                self._conn = None
