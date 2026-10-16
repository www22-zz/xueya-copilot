"""SQLite v3 compatibility, atomic migrations and nested synchronous transactions."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from .common import require

SCHEMA_VERSION = 3


class Database:
    def __init__(self, filename):
        if str(filename) != ":memory:":
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.connection = sqlite3.connect(filename, isolation_level=None, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        try:
            version = self.one("PRAGMA user_version")["user_version"]
            require(version <= SCHEMA_VERSION, "DATABASE_NEWER_THAN_APP")
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA busy_timeout=5000")
            for n in range(version + 1, SCHEMA_VERSION + 1):
                sql = (Path(__file__).parent / "sql" / f"{n:03}.sql").read_text(encoding="utf-8")
                self.connection.executescript(f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version={n};\nCOMMIT;")
        except BaseException:
            if self.connection.in_transaction:
                self.connection.rollback()
            self.close()
            raise
        self._savepoint = 0

    def execute(self, sql, params=()):
        with self.lock:
            return self.connection.execute(sql, params)

    def one(self, sql, params=()):
        with self.lock:
            row = self.connection.execute(sql, params).fetchone()
            return dict(row) if row is not None else None

    def all(self, sql, params=()):
        with self.lock:
            return [dict(row) for row in self.connection.execute(sql, params).fetchall()]

    @contextmanager
    def transaction(self):
        # No await in this block: one connection and one thread owns the transaction.
        with self.lock:
            nested = self.connection.in_transaction
            self._savepoint += 1
            name = f"tx_{self._savepoint}"
            self.connection.execute(f"SAVEPOINT {name}" if nested else "BEGIN IMMEDIATE")
            try:
                yield
                self.connection.execute(f"RELEASE {name}" if nested else "COMMIT")
            except BaseException:
                self.connection.execute(f"ROLLBACK TO {name}" if nested else "ROLLBACK")
                if nested:
                    self.connection.execute(f"RELEASE {name}")
                raise

    def close(self):
        with self.lock:
            self.connection.close()
