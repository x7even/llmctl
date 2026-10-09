import sqlite3


class TodoRepo:
    def __init__(self, path=":memory:"):
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS todos ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
            "priority INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0)"
        )
        self._db.commit()

    @staticmethod
    def _row(r):
        return {"id": r[0], "title": r[1], "priority": r[2], "done": bool(r[3])}

    def add(self, title, priority=3):
        title = title.strip()
        if not title:
            raise ValueError("empty title")
        if not isinstance(priority, int) or isinstance(priority, bool) or not 1 <= priority <= 5:
            raise ValueError("priority must be 1..5")
        cur = self._db.execute("INSERT INTO todos (title, priority) VALUES (?, ?)", (title, priority))
        self._db.commit()
        return cur.lastrowid

    def get(self, todo_id):
        r = self._db.execute("SELECT id, title, priority, done FROM todos WHERE id = ?", (todo_id,)).fetchone()
        return self._row(r) if r else None

    def list(self, done=None):
        sql = "SELECT id, title, priority, done FROM todos"
        args = ()
        if done is not None:
            sql += " WHERE done = ?"
            args = (1 if done else 0,)
        sql += " ORDER BY priority, id"
        return [self._row(r) for r in self._db.execute(sql, args)]

    def mark_done(self, todo_id):
        cur = self._db.execute("UPDATE todos SET done = 1 WHERE id = ?", (todo_id,))
        self._db.commit()
        return cur.rowcount > 0

    def delete(self, todo_id):
        cur = self._db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self._db.commit()
        return cur.rowcount > 0

    def count(self, done=None):
        if done is None:
            return self._db.execute("SELECT COUNT(*) FROM todos").fetchone()[0]
        return self._db.execute("SELECT COUNT(*) FROM todos WHERE done = ?", (1 if done else 0,)).fetchone()[0]

    def close(self):
        self._db.commit()
        self._db.close()
