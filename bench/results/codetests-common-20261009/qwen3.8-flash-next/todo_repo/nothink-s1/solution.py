import sqlite3
from typing import Optional


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                priority INTEGER NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.conn.commit()

    def add(self, title: str, priority: int = 3) -> int:
        if not isinstance(title, str):
            raise ValueError("title must be a string")
        stripped = title.strip()
        if not stripped:
            raise ValueError("title cannot be empty or whitespace-only")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an integer")
        if priority < 1 or priority > 5:
            raise ValueError("priority must be between 1 and 5")
        
        cursor = self.conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, ?)",
            (stripped, priority, 0)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get(self, todo_id: int) -> Optional[dict]:
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

    def list(self, done: Optional[bool] = None) -> list:
        if done is None:
            query = "SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC"
            params = ()
        else:
            query = "SELECT id, title, priority, done FROM todos WHERE done = ? ORDER BY priority ASC, id ASC"
            params = (1 if done else 0,)
        
        cursor = self.conn.execute(query, params)
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

    def count(self, done: Optional[bool] = None) -> int:
        if done is None:
            query = "SELECT COUNT(*) FROM todos"
            params = ()
        else:
            query = "SELECT COUNT(*) FROM todos WHERE done = ?"
            params = (1 if done else 0,)
        
        cursor = self.conn.execute(query, params)
        return cursor.fetchone()[0]

    def close(self) -> None:
        self.conn.close()
