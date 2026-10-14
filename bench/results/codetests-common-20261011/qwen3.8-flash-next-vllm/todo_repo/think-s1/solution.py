from __future__ import annotations

import sqlite3


class TodoRepo:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
        done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1))
    )
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._closed = False

        self._conn.execute(self._SCHEMA)
        self._conn.commit()

    def __enter__(self) -> "TodoRepo":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _check_open(self) -> None:
        if self._closed:
            raise sqlite3.ProgrammingError("TodoRepo is closed")

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        return {
            "id": int(row["id"]),
            "title": row["title"],
            "priority": int(row["priority"]),
            "done": bool(row["done"]),
        }

    def add(self, title: str, priority: int = 3) -> int:
        self._check_open()

        if not isinstance(title, str):
            raise ValueError("title must be a string")

        title = title.strip()
        if not title:
            raise ValueError("title must not be empty")

        if (
            isinstance(priority, bool)
            or not isinstance(priority, int)
            or priority < 1
            or priority > 5
        ):
            raise ValueError("priority must be an int between 1 and 5")

        cursor = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (title, priority),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get(self, todo_id: int) -> dict | None:
        self._check_open()

        row = self._conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_dict(row)

    def list(self, done: bool | None = None) -> list[dict]:
        self._check_open()

        if done is None:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos "
                "ORDER BY priority ASC, id ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = ? "
                "ORDER BY priority ASC, id ASC",
                (1 if done else 0,),
            ).fetchall()

        return [self._row_to_dict(row) for row in rows]

    def mark_done(self, todo_id: int) -> bool:
        self._check_open()

        cursor = self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?",
            (todo_id,),
        )

        if cursor.rowcount > 0:
            self._conn.commit()
            return True

        exists = (
            self._conn.execute(
                "SELECT 1 FROM todos WHERE id = ?",
                (todo_id,),
            ).fetchone()
            is not None
        )

        self._conn.commit()
        return exists

    def delete(self, todo_id: int) -> bool:
        self._check_open()

        cursor = self._conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        self._check_open()

        if done is None:
            row = self._conn.execute("SELECT COUNT(*) FROM todos").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?",
                (1 if done else 0,),
            ).fetchone()

        return int(row[0])

    def close(self) -> None:
        if not self._closed:
            self._conn.commit()
            self._conn.close()
            self._closed = True
