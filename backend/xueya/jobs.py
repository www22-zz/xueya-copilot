"""Durable leased queue. Ambiguous paid API results are never replayed automatically."""
from __future__ import annotations
import asyncio
import json
import time
from functools import wraps
from uuid import uuid4
from .common import AppError, Scope, dumps, identifier, require, utc_now
from .execution_budget import budget_scope


def budgeted_job(method):
    @wraps(method)
    async def execute(self, *args, **kwargs):
        with budget_scope(getattr(self, 'budget_config', None), fresh=True):
            return await method(self, *args, **kwargs)
    return execute

TERMINAL = frozenset(("succeeded", "failed", "cancelled", "unknown"))


class JobQueue:
    def __init__(self, repository, resources, lease_ms=15000, timeout=90):
        self.repo, self.db, self.resources = repository, repository.db, resources
        self.owner, self.handlers, self.active = str(uuid4()), {}, {}
        self.lease_ms, self.timeout, self.runner = lease_ms, timeout, None
        self.stopped = True

    @staticmethod
    def now():
        return int(time.time()*1000)

    def event(self, job_id, value):
        self.db.execute("INSERT INTO job_events(job_id,event,at) VALUES(?,?,?)", (job_id, dumps(value), utc_now()))

    def get(self, job_id, user_id):
        r = self.db.one("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user_id))
        if not r:
            return None
        return {"id": r["id"], "courseId": r["course_id"], "type": r["type"], "status": r["status"], "progress": json.loads(r["progress"]), "checkpoint": json.loads(r["checkpoint"]), "result": json.loads(r["result"]) if r["result"] else None, "error": r["error"], "attempts": r["attempts"], "resource": r["resource"], "leaseUntil": r["lease_until"], "createdAt": r["created_at"], "updatedAt": r["updated_at"]}

    def list(self, user_id):
        return [self.get(r["id"], user_id) for r in self.db.all("SELECT id FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 100", (user_id,))]

    def register(self, name, handler):
        require(name not in self.handlers and callable(handler), "INVALID_JOB_HANDLER")
        self.handlers[name] = handler

    def submit(self, user_id, args):
        require(isinstance(args, dict) and not set(args)-{"type", "courseId", "input", "resource", "idempotencyKey", "maxAttempts"}, "INVALID_JOB")
        job_type, course_id, key = args.get("type"), identifier(args.get("courseId")), identifier(args.get("idempotencyKey"))
        self.repo.require_course(Scope(user_id=user_id, course_id=course_id))
        require(job_type in self.handlers, "JOB_TYPE_UNAVAILABLE")
        resource, attempts = args.get("resource", "cpu"), args.get("maxAttempts", 3)
        require(resource in ("cpu", "api"), "RESOURCE_UNSUPPORTED")
        require(type(attempts) is int and 1 <= attempts <= 5, "INVALID_JOB")
        payload = dumps(args.get("input", {}))
        require(len(payload.encode()) <= 131072, "JOB_INPUT_TOO_LARGE")
        with self.db.transaction():
            prior = self.db.one("SELECT * FROM jobs WHERE user_id=? AND course_id=? AND type=? AND idempotency_key=?", (user_id, course_id, job_type, key))
            if prior:
                require(prior["input"] == payload and prior["resource"] == resource, "IDEMPOTENCY_CONFLICT")
                return self.get(prior["id"], user_id)
            job_id, at = str(uuid4()), utc_now()
            self.db.execute("INSERT INTO jobs(id,user_id,course_id,type,input,resource,status,max_attempts,idempotency_key,available_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, user_id, course_id, job_type, payload, resource, "queued", attempts, key, self.now(), at, at))
            self.event(job_id, {"status": "queued"})
            return self.get(job_id, user_id)

    def recover(self):
        with self.db.transaction():
            rows = self.db.all("SELECT * FROM jobs WHERE status IN ('running','cancelling') AND lease_until<=?", (self.now(),))
            for r in rows:
                status = "unknown" if r["resource"] == "api" else "cancelled" if r["status"] == "cancelling" else "failed" if r["attempts"] >= r["max_attempts"] else "queued"
                self.db.execute("UPDATE jobs SET status=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?", (status, utc_now(), r["id"]))
                self.event(r["id"], {"status": status, "recovered": True})
            return len(rows)

    def update(self, job_id, field, value):
        require(field in ("progress", "checkpoint"), "INVALID_JOB_FIELD")
        payload = dumps(value)
        require(len(payload.encode()) <= 65536, "JOB_UPDATE_TOO_LARGE")
        with self.db.transaction():
            changed = self.db.execute(f"UPDATE jobs SET {field}=?,updated_at=? WHERE id=? AND lease_owner=? AND status='running' AND lease_until>?", (payload, utc_now(), job_id, self.owner, self.now())).rowcount
            require(changed == 1, "JOB_LEASE_LOST")
            self.event(job_id, {field: value})

    def commit(self, job_id, fn):
        with self.db.transaction():
            row = self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
            require(row is not None and row["lease_owner"] == self.owner and row["status"] == "running" and row["lease_until"] > self.now(), "JOB_LEASE_LOST")
            require(not asyncio.current_task().cancelling(), "JOB_CANCELLED")
            return fn()

    async def _heartbeat(self, job_id, execution):
        while True:
            await asyncio.sleep(max(.05, self.lease_ms/3000))
            changed = self.db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND lease_owner=? AND status='running'", (self.now()+self.lease_ms, job_id, self.owner)).rowcount
            if not changed:
                execution.cancel()
                return

    @budgeted_job
    async def _execute(self, row, release):
        job_id = row["id"]
        from .invocation_context import active_job
        job_context = active_job.set({'id': job_id, 'userId': row['user_id'], 'courseId': row['course_id']})
        heartbeat = asyncio.create_task(self._heartbeat(job_id, asyncio.current_task()))
        try:
            scope = Scope(user_id=row["user_id"], course_id=row["course_id"])
            self.repo.require_course(scope)
            async with asyncio.timeout(self.timeout):
                result = await self.handlers[row["type"]](scope, json.loads(row["input"]), progress=lambda v: self.update(job_id, "progress", v), checkpoint=lambda v: self.update(job_id, "checkpoint", v), commit=lambda fn: self.commit(job_id, fn))
            require(len(dumps(result).encode()) <= 131072, "JOB_RESULT_TOO_LARGE")

            def finish():
                self.db.execute("UPDATE jobs SET status='succeeded',result=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?", (dumps(result), utc_now(), job_id))
                self.event(job_id, {"status": "succeeded", "result": result})
            self.commit(job_id, finish)
        except (Exception, asyncio.CancelledError) as error:
            current = self.get(job_id, row["user_id"])
            unknown = row["resource"] == "api" and getattr(error, "code", None) != "NOT_SENT"
            cancelled = isinstance(error, asyncio.CancelledError) or self.stopped or current and current["status"] == "cancelling"
            status = "unknown" if unknown else "cancelled" if cancelled else "queued" if row["attempts"] < row["max_attempts"] else "failed"
            code = error.code if isinstance(error, AppError) else "JOB_TIMEOUT" if isinstance(error, TimeoutError) else "JOB_CANCELLED" if cancelled else "JOB_FAILED"
            with self.db.transaction():
                changed = self.db.execute("UPDATE jobs SET status=?,error=?,available_at=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=? AND lease_owner=?", (status, code, self.now()+min(30000, 250*2**row["attempts"]), utc_now(), job_id, self.owner)).rowcount
                if changed:
                    self.event(job_id, {"status": status, "error": code})
        finally:
            heartbeat.cancel()
            try:
                await asyncio.gather(heartbeat, return_exceptions=True)
            finally:
                # stop() may cancel again while a cancelled job is draining its heartbeat.
                self.active.pop(job_id, None)
                active_job.reset(job_context)
                release()

    async def tick(self):
        if self.stopped:
            return
        self.recover()
        for row in self.db.all("SELECT * FROM jobs WHERE status='queued' AND available_at<=? ORDER BY created_at LIMIT 50", (self.now(),)):
            if row["type"] not in self.handlers or row["id"] in self.active:
                continue
            release = self.resources.acquire(row["resource"])
            if not release:
                continue
            with self.db.transaction():
                changed = self.db.execute("UPDATE jobs SET status='running',attempts=attempts+1,lease_owner=?,lease_until=?,updated_at=? WHERE id=? AND status='queued'", (self.owner, self.now()+self.lease_ms, utc_now(), row["id"])).rowcount
                if not changed:
                    release()
                    continue
                row["attempts"] += 1
                self.event(row["id"], {"status": "running", "attempt": row["attempts"]})
            self.active[row["id"]] = asyncio.create_task(self._execute(row, release))

    def events(self, job_id, user_id, after=0):
        require(self.get(job_id, user_id) is not None, "JOB_NOT_FOUND")
        require(type(after) is int and after >= 0, "INVALID_CURSOR")
        return [{"seq": r["seq"], "at": r["at"], **json.loads(r["event"])} for r in self.db.all("SELECT seq,event,at FROM job_events WHERE job_id=? AND seq>? ORDER BY seq LIMIT 100", (job_id, after))]

    def cancel(self, job_id, user_id):
        row = self.get(job_id, user_id)
        require(row is not None, "JOB_NOT_FOUND")
        if row["status"] in TERMINAL:
            return row
        task = self.active.get(job_id)
        # Another process may own the lease. Leave cancelling for its heartbeat/recovery.
        state = "cancelled" if row["status"] == "queued" else "cancelling"
        with self.db.transaction():
            self.db.execute("UPDATE jobs SET status=?,updated_at=? WHERE id=? AND user_id=?", (state, utc_now(), job_id, user_id))
            self.event(job_id, {"status": state})
        if task:
            task.cancel()
        return self.get(job_id, user_id)

    def retry(self, job_id, user_id):
        row = self.get(job_id, user_id)
        require(row is not None and row["status"] in ("failed", "cancelled"), "JOB_NOT_RETRYABLE")
        with self.db.transaction():
            self.db.execute("UPDATE jobs SET status='queued',attempts=0,error=NULL,available_at=?,updated_at=? WHERE id=? AND user_id=?", (self.now(), utc_now(), job_id, user_id))
            self.event(job_id, {"status": "queued", "manualRetry": True})
        return self.get(job_id, user_id)

    async def _poll(self):
        while not self.stopped:
            await self.tick()
            await asyncio.sleep(.1)

    def start(self):
        if self.runner is None:
            self.stopped = False
            self.runner = asyncio.create_task(self._poll())

    async def stop(self):
        self.stopped = True
        if self.runner:
            self.runner.cancel()
            await asyncio.gather(self.runner, return_exceptions=True)
            self.runner = None
        tasks = list(self.active.values())
        for task in tasks:
            task.cancel()
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=5)
            require(not pending, "WORKERS_NOT_STOPPED")
