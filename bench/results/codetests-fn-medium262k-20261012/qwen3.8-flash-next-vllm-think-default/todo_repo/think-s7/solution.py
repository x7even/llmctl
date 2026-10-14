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
    def add(self, title: str, priority: int = 3) -> int:
        title = title.strip()
        if not title:
            raise ValueError("title must not be empty or whitespace-only")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an int from 1 to 5")
        if not 1 <= priority <= 5:
            raise ValueError("priority must be an int from 1 to 5")

        cur = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (title, priority),
        )
        self._conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    def get(self, todo_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    # ------------------------------------------------------------------
    def list(self, done: bool | None = None) -> list[dict]:
        if done is None:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos "
                "ORDER BY priority ASC, id ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, title, priority, done FROM todos "
                "WHERE done = ? ORDER BY priority ASC, id ASC",
                (int(done),),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    def mark_done(self, todo_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?", (todo_id,)
        )
        self._conn.commit()
        # rowcount > 0 means the id existed (whether it was already done or not)
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    def delete(self, todo_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM todos WHERE id = ?", (todo_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    def count(self, done: bool | None = None) -> int:
        if done is None:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM todos"
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?",
                (int(done),),
            ).fetchone()
        return row[0]

    # ------------------------------------------------------------------
    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        return {
            "id": int(row[0]),
            "title": str(row[1]),
            "priority": int(row[2]),
            "done": bool(row[3]),
        }
