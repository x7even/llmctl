import sqlite3


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                priority INTEGER NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.conn.commit()

    def add(self, title: str, priority: int = 3) -> int:
        stripped = title.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace-only")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an int")
        if not (1 <= priority <= 5):
            raise ValueError("priority must be between 1 and 5")
        cur = self.conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (stripped, priority),
        )
        self.conn.commit()
        return cur.lastrowid

    def get(self, todo_id: int) -> dict | None:
        cur = self.conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"id": row[0], "title": row[1], "priority": row[2], "done": bool(row[3])}

    def list(self, done: bool | None = None) -> list[dict]:
        if done is None:
            cur = self.conn.execute(
                "SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC"
            )
        else:
            cur = self.conn.execute(
                "SELECT id, title, priority, done FROM todos "
                "WHERE done = ? ORDER BY priority ASC, id ASC",
                (1 if done else 0,),
            )
        return [
            {"id": r[0], "title": r[1], "priority": r[2], "done": bool(r[3])}
            for r in cur.fetchall()
        ]

    def mark_done(self, todo_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?",
            (todo_id,),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete(self, todo_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        if done is None:
            cur = self.conn.execute("SELECT COUNT(*) FROM todos")
        else:
            cur = self.conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?",
                (1 if done else 0,),
            )
        return cur.fetchone()[0]

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()
