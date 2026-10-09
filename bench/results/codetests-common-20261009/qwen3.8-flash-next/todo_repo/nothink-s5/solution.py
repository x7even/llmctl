import sqlite3


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                priority INTEGER NOT NULL,
                done BOOLEAN NOT NULL DEFAULT 0
            )
        """)
        self.conn.commit()

    def add(self, title: str, priority: int = 3) -> int:
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an int from 1 to 5")
        if priority < 1 or priority > 5:
            raise ValueError("priority must be an int from 1 to 5")
        stripped = title.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace-only")
        cursor = self.conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, 0)",
            (stripped, priority)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get(self, todo_id: int) -> dict | None:
        cursor = self.conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "priority": row[2],
            "done": bool(row[3])
        }

    def list(self, done: bool | None = None) -> list[dict]:
        if done is None:
            cursor = self.conn.execute(
                "SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC"
            )
        else:
            done_val = 1 if done else 0
            cursor = self.conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = ? ORDER BY priority ASC, id ASC",
                (done_val,)
            )
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "title": row[1],
                "priority": row[2],
                "done": bool(row[3])
            })
        return results

    def mark_done(self, todo_id: int) -> bool:
        cursor = self.conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?",
            (todo_id,)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def delete(self, todo_id: int) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        if done is None:
            cursor = self.conn.execute("SELECT COUNT(*) FROM todos")
        else:
            done_val = 1 if done else 0
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?",
                (done_val,)
            )
        return cursor.fetchone()[0]

    def close(self) -> None:
        self.conn.close()
