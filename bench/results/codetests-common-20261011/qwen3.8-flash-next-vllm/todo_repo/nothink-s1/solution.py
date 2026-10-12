import sqlite3


class TodoRepo:
    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self) -> None:
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
        # Validate and strip title
        if not isinstance(title, str):
            raise ValueError("Title must be a string")
        stripped_title = title.strip()
        if not stripped_title:
            raise ValueError("Title cannot be empty or whitespace-only")

        # Validate priority
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("Priority must be an integer from 1 to 5")
        if priority < 1 or priority > 5:
            raise ValueError("Priority must be an integer from 1 to 5")

        cursor = self.conn.execute(
            "INSERT INTO todos (title, priority, done) VALUES (?, ?, ?)",
            (stripped_title, priority, 0),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get(self, todo_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT id, title, priority, done FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "priority": row["priority"],
            "done": bool(row["done"]),
        }

    def list(self, done: bool | None = None) -> list[dict]:
        if done is None:
            rows = self.conn.execute(
                "SELECT id, title, priority, done FROM todos ORDER BY priority ASC, id ASC"
            ).fetchall()
        else:
            done_val = 1 if done else 0
            rows = self.conn.execute(
                "SELECT id, title, priority, done FROM todos WHERE done = ? ORDER BY priority ASC, id ASC",
                (done_val,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "priority": row["priority"],
                "done": bool(row["done"]),
            }
            for row in rows
        ]

    def mark_done(self, todo_id: int) -> bool:
        # Check if the item exists
        row = self.conn.execute(
            "SELECT id FROM todos WHERE id = ?", (todo_id,)
        ).fetchone()
        if row is None:
            return False
        self.conn.execute(
            "UPDATE todos SET done = 1 WHERE id = ?", (todo_id,)
        )
        self.conn.commit()
        return True

    def delete(self, todo_id: int) -> bool:
        row = self.conn.execute(
            "SELECT id FROM todos WHERE id = ?", (todo_id,)
        ).fetchone()
        if row is None:
            return False
        self.conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self.conn.commit()
        return True

    def count(self, done: bool | None = None) -> int:
        if done is None:
            row = self.conn.execute("SELECT COUNT(*) FROM todos").fetchone()
        else:
            done_val = 1 if done else 0
            row = self.conn.execute(
                "SELECT COUNT(*) FROM todos WHERE done = ?", (done_val,)
            ).fetchone()
        return row[0]

    def close(self) -> None:
        self.conn.close()
