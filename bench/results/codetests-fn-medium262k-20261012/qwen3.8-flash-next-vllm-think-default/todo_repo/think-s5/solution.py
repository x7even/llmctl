import sqlite3


class TodoRepo:
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
        title = title.strip()
        if not title:
            raise ValueError("title must not be empty")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError("priority must be an int between 1 and 5")
        if priority < 1 or priority > 5:
            raise ValueError("priority must be an int between 1 and 5")

        cur = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (title, priority),
        )
        self._conn.commit()
        return cur.lastrowid

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
        if done is None:
            cur = self._conn.execute(
                "SELECT id, title, priority, done FROM todos "
                "ORDER BY priority ASC, id ASC"
            )
        else:
            cur = self._conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = ? "
                "ORDER BY priority ASC, id ASC",
                (int(done),),
            )
        return [self._row_to_dict(row) for row in cur.fetchall()]

    def mark_done(self, todo_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?", (todo_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete(self, todo_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM todos WHERE id = ?", (todo_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        if done is None:
            cur = self._conn.execute("SELECT COUNT(*) FROM todos")
        else:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?", (int(done),)
            )
        return cur.fetchone()[0]

    def close(self) -> None:
        self._conn.commit()
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
