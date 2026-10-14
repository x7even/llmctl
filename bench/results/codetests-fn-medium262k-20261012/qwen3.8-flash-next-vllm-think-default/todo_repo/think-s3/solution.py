"""A simple SQLite-backed to-do repository (standard library only)."""

import sqlite3


class TodoRepo:
    """Stores to-do items in a SQLite database."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
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

    # ------------------------------------------------------------------ #
    #  Write operations
    # ------------------------------------------------------------------ #

    def add(self, title: str, priority: int = 3) -> int:
        title = title.strip()
        if not title:
            raise ValueError("title must not be empty")
        if not isinstance(priority, int) or isinstance(priority, bool) or not (1 <= priority <= 5):
            raise ValueError("priority must be an int between 1 and 5")

        cursor = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (title, priority),
        )
        return cursor.lastrowid

    def mark_done(self, todo_id: int) -> bool:
        cursor = self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?", (todo_id,)
        )
        return cursor.rowcount > 0

    def delete(self, todo_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM todos WHERE id = ?", (todo_id,)
        )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------ #
    #  Read operations
    # ------------------------------------------------------------------ #

    def get(self, todo_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list(self, done: bool | None = None) -> list[dict]:
        if done is None:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = ? ORDER BY priority ASC, id ASC",
                (int(done),),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self, done: bool | None = None) -> int:
        if done is None:
            row = self._conn.execute("SELECT COUNT(*) FROM todos").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?", (int(done),)
            ).fetchone()
        return row[0]

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        return {
            "id": row[0],
            "title": row[1],
            "priority": row[2],
            "done": bool(row[3]),
        }
