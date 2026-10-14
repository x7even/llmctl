from __future__ import annotations

import sqlite3


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._closed = False

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
        if not isinstance(title, str):
            raise TypeError("title must be a string")

        title = title.strip()
        if not title:
            raise ValueError("title must not be empty")

        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError("priority must be an integer from 1 to 5")
        if priority < 1 or priority > 5:
            raise ValueError("priority must be an integer from 1 to 5")

        cur = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (title, priority),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get(self, todo_id: int) -> dict | None:
        cur = self._conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list(self, done: bool | None = None) -> list[dict]:
        query = "SELECT id, title, priority, done FROM todos"
        params = ()

        if done is not None:
            query += " WHERE done = ?"
            params = (int(bool(done)),)

        query += " ORDER BY priority ASC, id ASC"

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def mark_done(self, todo_id: int) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM todos WHERE id = ?",
            (todo_id,),
        )
        if cur.fetchone() is None:
            return False

        self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return True

    def delete(self, todo_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        query = "SELECT COUNT(*) FROM todos"
        params = ()

        if done is not None:
            query += " WHERE done = ?"
            params = (int(bool(done)),)

        cur = self._conn.execute(query, params)
        return int(cur.fetchone()[0])

    def close(self) -> None:
        if not self._closed:
            self._conn.commit()
            self._conn.close()
            self._closed = True

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        return {
            "id": int(row[0]),
            "title": row[1],
            "priority": int(row[2]),
            "done": bool(row[3]),
        }
