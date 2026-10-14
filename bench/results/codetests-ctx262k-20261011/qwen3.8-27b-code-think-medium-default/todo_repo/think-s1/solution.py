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

    def add(self, title: str, priority: int = 3) -> int:
        if not isinstance(title, str):
            raise ValueError("title must be a string")
        stripped = title.strip()
        if not stripped:
            raise ValueError("title must not be empty")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an int")
        if not (1 <= priority <= 5):
            raise ValueError("priority must be between 1 and 5")
        cur = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (stripped, priority),
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
        return {"id": row[0], "title": row[1], "priority": row[2], "done": bool(row[3])}

    def list(self, done: bool | None = None) -> list[dict]:
        query = "SELECT id, title, priority, done FROM todos"
        params: tuple = ()
        if done is not None:
            query += " WHERE done = ?"
            params = (1 if done else 0,)
        query += " ORDER BY priority ASC, id ASC"
        cur = self._conn.execute(query, params)
        return [
            {"id": r[0], "title": r[1], "priority": r[2], "done": bool(r[3])}
            for r in cur.fetchall()
        ]

    def mark_done(self, todo_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete(self, todo_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        query = "SELECT COUNT(*) FROM todos"
        params: tuple = ()
        if done is not None:
            query += " WHERE done = ?"
            params = (1 if done else 0,)
        cur = self._conn.execute(query, params)
        return cur.fetchone()[0]

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()
