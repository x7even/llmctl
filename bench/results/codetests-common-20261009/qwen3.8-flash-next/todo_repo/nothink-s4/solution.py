import sqlite3


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                priority INTEGER NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._conn.commit()

    def add(self, title: str, priority: int = 3) -> int:
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an integer from 1 to 5")
        if priority < 1 or priority > 5:
            raise ValueError("priority must be an integer from 1 to 5")
        
        stripped = title.strip()
        if not stripped:
            raise ValueError("title cannot be empty or whitespace-only")
        
        cursor = self._conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, ?)",
            (stripped, priority, 0)
        )
        self._conn.commit()
        return cursor.lastrowid

    def get(self, todo_id: int) -> dict | None:
        cursor = self._conn.execute(
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
            query = "SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC"
            params = ()
        else:
            query = "SELECT id, title, priority, done FROM todos WHERE done = ? ORDER BY priority ASC, id ASC"
            params = (1 if done else 0,)
        
        cursor = self._conn.execute(query, params)
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
        cursor = self._conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?",
            (todo_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete(self, todo_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self, done: bool | None = None) -> int:
        if done is None:
            query = "SELECT COUNT(*) FROM todos"
            params = ()
        else:
            query = "SELECT COUNT(*) FROM todos WHERE done = ?"
            params = (1 if done else 0,)
        
        cursor = self._conn.execute(query, params)
        return cursor.fetchone()[0]

    def close(self) -> None:
        self._conn.close()
