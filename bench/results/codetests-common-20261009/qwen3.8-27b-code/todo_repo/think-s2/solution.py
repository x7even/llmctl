import sqlite3


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
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

    def _row_to_dict(self, row) -> dict:
        return {
            "id": row[0],
            "title": row[1],
            "priority": row[2],
            "done": bool(row[3]),
        }

    def _validate_title(self, title: str) -> str:
        if not isinstance(title, str):
            raise ValueError("title must be a string")
        title = title.strip()
        if not title:
            raise ValueError("title must not be empty")
        return title

    def _validate_priority(self, priority: int) -> int:
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError("priority must be an integer between 1 and 5")
        if not 1 <= priority <= 5:
            raise ValueError("priority must be an integer between 1 and 5")
        return priority

    def add(self, title: str, priority: int = 3) -> int:
        title = self._validate_title(title)
        priority = self._validate_priority(priority)
        cur = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (title, priority),
        )
        new_id = cur.lastrowid
        self._conn.commit()
        return new_id

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
                (1 if done else 0,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def mark_done(self, todo_id: int) -> bool:
        row = self._conn.execute(
            "SELECT done FROM todos WHERE id = ?",
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
        cur = self._conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,),
        )
        deleted = cur.rowcount
        self._conn.commit()
        return deleted > 0

    def count(self, done: bool | None = None) -> int:
        if done is None:
            row = self._conn.execute("SELECT COUNT(*) FROM todos").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?",
                (1 if done else 0,),
            ).fetchone()
        return row[0]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None
