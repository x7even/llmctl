import sqlite3
import os


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                priority INTEGER NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.conn.commit()

    def add(self, title: str, priority: int = 3) -> int:
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an integer")
        if priority < 1 or priority > 5:
            raise ValueError("priority must be between 1 and 5")
        
        stripped_title = title.strip()
        if not stripped_title:
            raise ValueError("title cannot be empty or whitespace-only")
        
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, ?)",
            (stripped_title, priority, 0)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get(self, todo_id: int) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title, priority, done FROM todos WHERE id = ?", (todo_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "priority": row["priority"],
            "done": bool(row["done"])
        }

    def list(self, done: bool | None = None) -> list[dict]:
        cursor = self.conn.cursor()
        if done is None:
            cursor.execute("SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC")
        else:
            done_val = 1 if done else 0
            cursor.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = ? ORDER BY priority ASC, id ASC",
                (done_val,)
            )
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row["id"],
                "title": row["title"],
                "priority": row["priority"],
                "done": bool(row["done"])
            })
        return results

    def mark_done(self, todo_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("UPDATE todos SET done = 1 WHERE id = ?", (todo_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def delete(self, todo_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        cursor = self.conn.cursor()
        if done is None:
            cursor.execute("SELECT COUNT(*) FROM todos")
        else:
            done_val = 1 if done else 0
            cursor.execute("SELECT COUNT(*) FROM todos WHERE done = ?", (done_val,))
        row = cursor.fetchone()
        return row[0]

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()
