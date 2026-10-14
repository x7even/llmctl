"""A lightweight to-do repository backed by SQLite (standard library only)."""

import sqlite3


class TodoRepo:
    """Stores to-do items in a SQLite database."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                title    TEXT    NOT NULL,
                priority INTEGER NOT NULL,
                done     INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, title: str, priority: int = 3) -> int:
        """Insert a new to-do item and return its auto-generated id."""
        title = title.strip()
        if not title:
            raise ValueError("title must not be empty or whitespace-only")
        if isinstance(priority, bool) or not isinstance(priority, int) or not 1 <= priority <= 5:
            raise ValueError("priority must be an int from 1 to 5")

        cur = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (title, priority),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get(self, todo_id: int) -> dict | None:
        """Return a single item as a dict, or None if it doesn't exist."""
        row = self._conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list(self, done: bool | None = None) -> list[dict]:
        """Return all items (optionally filtered by *done*), sorted by priority then id."""
        if done is None:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = ? "
                "ORDER BY priority ASC, id ASC",
                (int(done),),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def mark_done(self, todo_id: int) -> bool:
        """Mark an item as done. Returns True if the item exists, False otherwise."""
        row = self._conn.execute(
            "SELECT 1 FROM todos WHERE id = ?", (todo_id,)
        ).fetchone()
        if row is None:
            return False
        self._conn.execute("UPDATE todos SET done = 1 WHERE id = ?", (todo_id,))
        self._conn.commit()
        return True

    def delete(self, todo_id: int) -> bool:
        """Delete an item. Returns True if it existed, False otherwise."""
        cur = self._conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        """Return the number of items, optionally filtered by *done*."""
        if done is None:
            row = self._conn.execute("SELECT COUNT(*) FROM todos").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?", (int(done),)
            ).fetchone()
        return row[0]  # type: ignore[index]

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        return {
            "id": row[0],
            "title": row[1],
            "priority": row[2],
            "done": bool(row[3]),
        }
