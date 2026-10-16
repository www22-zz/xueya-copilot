import sqlite3
from contextlib import contextmanager
from pathlib import Path
import threading
from ..core import require

MIGRATIONS = [
'''CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE courses(user_id TEXT NOT NULL,id TEXT NOT NULL,name TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(user_id,id));
CREATE TABLE entities(user_id TEXT NOT NULL,course_id TEXT NOT NULL,kind TEXT NOT NULL,id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(user_id,course_id,kind,id));
CREATE TABLE revisions(user_id TEXT NOT NULL,course_id TEXT NOT NULL,kind TEXT NOT NULL,id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,at TEXT NOT NULL,PRIMARY KEY(user_id,course_id,kind,id,version));
CREATE TABLE workspaces(user_id TEXT PRIMARY KEY,version INTEGER NOT NULL,data TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE imports(user_id TEXT NOT NULL,hash TEXT NOT NULL,backup TEXT NOT NULL,workspace_version INTEGER NOT NULL,at TEXT NOT NULL,PRIMARY KEY(user_id,hash));
CREATE TABLE audits(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,course_id TEXT NOT NULL,action_id TEXT NOT NULL UNIQUE,data TEXT NOT NULL,at TEXT NOT NULL);
CREATE TABLE receipts(user_id TEXT NOT NULL,course_id TEXT NOT NULL,action_id TEXT NOT NULL,receipt TEXT NOT NULL,PRIMARY KEY(user_id,course_id,action_id));
CREATE TABLE jobs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,course_id TEXT NOT NULL,type TEXT NOT NULL,input TEXT NOT NULL,resource TEXT NOT NULL,status TEXT NOT NULL,progress TEXT NOT NULL DEFAULT '{}',checkpoint TEXT NOT NULL DEFAULT '{}',result TEXT,error TEXT,attempts INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL,idempotency_key TEXT NOT NULL,lease_owner TEXT,lease_until INTEGER,available_at INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(user_id,course_id,type,idempotency_key));
CREATE INDEX jobs_queue ON jobs(status,available_at,created_at);
CREATE TABLE job_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL,event TEXT NOT NULL,at TEXT NOT NULL);
CREATE TABLE invocations(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,course_id TEXT NOT NULL,status TEXT NOT NULL,provider TEXT NOT NULL,request_hash TEXT NOT NULL,at TEXT NOT NULL,updated_at TEXT NOT NULL);''',
'''ALTER TABLE invocations ADD COLUMN usage_json TEXT;
ALTER TABLE invocations ADD COLUMN billing_status TEXT NOT NULL DEFAULT 'not_reported';''',
'''CREATE TABLE confirmations(id TEXT PRIMARY KEY,data TEXT NOT NULL);''']


class Database:
    def __init__(self, filename):
        if str(filename) != ':memory:':
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(filename), isolation_level=None, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock, self.sequence = threading.RLock(), 0
        self.connection.executescript('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;')
        version = self.one('PRAGMA user_version')['user_version']
        require(version <= len(MIGRATIONS), 'DATABASE_NEWER_THAN_APP')
        for index in range(version, len(MIGRATIONS)):
            try:
                self.connection.executescript('BEGIN IMMEDIATE;'+MIGRATIONS[index]+f'PRAGMA user_version={index+1};COMMIT;')
            except Exception:
                if self.connection.in_transaction:
                    self.connection.rollback()
                raise

    def execute(self, sql, args=()):
        with self.lock:
            return self.connection.execute(sql, args)

    def one(self, sql, args=()):
        return self.execute(sql, args).fetchone()

    def all(self, sql, args=()):
        return self.execute(sql, args).fetchall()

    @contextmanager
    def transaction(self):
        with self.lock:
            nested = self.connection.in_transaction
            self.sequence += 1
            name = 'tx_'+str(self.sequence)
            self.execute('SAVEPOINT '+name if nested else 'BEGIN IMMEDIATE')
            try:
                yield
                self.execute('RELEASE '+name if nested else 'COMMIT')
            except BaseException:
                self.execute('ROLLBACK TO '+name if nested else 'ROLLBACK')
                if nested:
                    self.execute('RELEASE '+name)
                raise

    def close(self):
        self.connection.close()
