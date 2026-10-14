"""A minimal to-do repository backed by SQLite (standard library only)."""

import sqlite3
from typing import Optional


class TodoRepo:
    """Stores to-do items in a SQLite database."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                title    TEXT    NOT NULL,
                priority INTEGER NOT NULL DEFAULT 3,
                done     INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, title: str, priority: int = 3) -> int:
        """Insert a new (not-done) to-do item and return its new id."""
        title = title.strip()
        if not title:
            raise ValueError("title must not be empty or whitespace-only")
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 1 or priority > 5:
            raise ValueError("priority must be an int from 1 (highest) to 5 (lowest)")

        cursor = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (title, priority),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get(self, todo_id: int) -> dict | None:
        """Return a single item as a dict, or None if it doesn't exist."""
        cursor = self._conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list(self, done: bool | None = None) -> list[dict]:
        """Return all items ordered by priority ASC then id ASC."""
        if done is None:
            cursor = self._conn.execute(
                "SELECT id, title, priority, done FROM todos "
                "ORDER BY priority ASC, id ASC"
            )
        else:
            cursor = self._conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = ? "
                "ORDER BY priority ASC, id ASC",
                (int(done),),
            )
        return [self._row_to_dict(r) for r in cursor.fetchall()]

    def mark_done(self, todo_id: int) -> bool:
        """Set an item's done flag to True. Returns False if id not found."""
        cursor = self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete(self, todo_id: int) -> bool:
        """Delete an item. Returns False if id not found."""
        cursor = self._conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        """Return the number of items, optionally filtered by done state."""
        if done is None:
            cursor = self._conn.execute("SELECT COUNT(*) FROM todos")
        else:
            cursor = self._conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?",
                (int(done),),
            )
        return cursor.fetchone()[0]

    def close(self) -> None:
        """Commit any pending work and close the database connection."""
        self._conn.commit()
        self._conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        return {
            "id": int(row[0]),
            "title": row[1],
            "priority": int(row[2]),
            "done": bool(row[3]),
        }
