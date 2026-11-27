"""The event log: everything noteworthy that happens, saved to SQLite.

The paper and the stats page read from here. They never read the
simulation's internals, so the writing side can change freely.

importance: 1 = routine, 3 = worth a paragraph, 5 = front page
"""
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    day INTEGER NOT NULL,
    type TEXT NOT NULL,
    region TEXT,
    importance INTEGER NOT NULL,
    people TEXT NOT NULL,
    data TEXT NOT NULL,
    summary TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_day ON events(day);
CREATE TABLE IF NOT EXISTS weekly_stats (
    week_end_day INTEGER PRIMARY KEY,
    data TEXT NOT NULL
);
"""


class EventLog:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self.pending = []

    def add(self, day, type_, summary, region=None, importance=1, people=(), **data):
        self.pending.append((day, type_, region, importance,
                             json.dumps(list(people)), json.dumps(data), summary))

    def weekly(self, day, data):
        self.flush()
        self.db.execute("INSERT OR REPLACE INTO weekly_stats VALUES (?, ?)",
                        (day, json.dumps(data)))
        self.db.commit()

    def flush(self):
        if self.pending:
            self.db.executemany(
                "INSERT INTO events(day,type,region,importance,people,data,summary) "
                "VALUES (?,?,?,?,?,?,?)", self.pending)
            self.db.commit()
            self.pending = []

    def between(self, start_day, end_day, min_importance=1):
        self.flush()
        cur = self.db.execute(
            "SELECT day,type,region,importance,people,data,summary FROM events "
            "WHERE day BETWEEN ? AND ? AND importance >= ? ORDER BY day, id",
            (start_day, end_day, min_importance))
        return [dict(day=r[0], type=r[1], region=r[2], importance=r[3],
                     people=json.loads(r[4]), data=json.loads(r[5]), summary=r[6])
                for r in cur]

    def recent_weeks(self, n=2):
        self.flush()
        cur = self.db.execute("SELECT data FROM weekly_stats ORDER BY week_end_day DESC LIMIT ?", (n,))
        return [json.loads(r[0]) for r in cur]

    def close(self):
        self.flush()
        self.db.close()
