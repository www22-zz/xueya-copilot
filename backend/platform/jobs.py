import asyncio
import json
import time
import uuid
from ..core import require, dumps, now_iso, DomainError
from .repository import valid_id


class JobQueue:
    def __init__(self, repository, resources, lease_ms=15000, timeout_ms=90000, now=lambda: int(time.time()*1000)):
        self.repository, self.db, self.resources = repository, repository.db, resources
        self.lease, self.timeout, self.now = lease_ms, timeout_ms/1000, now
        self.owner, self.handlers, self.active, self.poller = str(uuid.uuid4()), {}, {}, None

    def event(self, key, value):
        self.db.execute('INSERT INTO job_events(job_id,event,at) VALUES(?,?,?)', (key, dumps(value), now_iso()))

    def register(self, kind, handler):
        require(kind not in self.handlers and callable(handler), 'INVALID_JOB_HANDLER')
        self.handlers[kind] = handler

    def get(self, key, user):
        row = self.db.one('SELECT * FROM jobs WHERE id=? AND user_id=?', (key, user))
        if not row:
            return None
        return {'id': row['id'], 'courseId': row['course_id'], 'type': row['type'], 'status': row['status'], 'progress': json.loads(row['progress']), 'checkpoint': json.loads(row['checkpoint']), 'result': json.loads(row['result']) if row['result'] else None,
                'error': row['error'], 'attempts': row['attempts'], 'resource': row['resource'], 'leaseUntil': row['lease_until'], 'createdAt': row['created_at'], 'updatedAt': row['updated_at']}

    def list(self, user):
        return [self.get(r['id'], user) for r in self.db.all('SELECT id FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 100', (user,))]

    def submit(self, user, value):
        require(isinstance(value, dict) and set(value) <= {'type', 'courseId', 'input', 'idempotencyKey', 'resource', 'maxAttempts'} and all(valid_id(value.get(k)) for k in ('type', 'courseId', 'idempotencyKey')), 'INVALID_JOB')
        self.repository.require_course({'userId': user, 'courseId': value['courseId']})
        require(value['type'] in self.handlers, 'JOB_TYPE_UNAVAILABLE')
        data, resource, maximum = dumps(value.get('input', {})), self.resources.choose(value.get('resource', 'cpu')), value.get('maxAttempts', 3)
        require(type(maximum) is int and 1 <= maximum <= 5 and len(data.encode()) <= 131072, 'JOB_INPUT_TOO_LARGE')
        with self.db.transaction():
            old = self.db.one('SELECT * FROM jobs WHERE user_id=? AND course_id=? AND type=? AND idempotency_key=?', (user, value['courseId'], value['type'], value['idempotencyKey']))
            if old:
                require(old['input'] == data and old['resource'] == resource, 'IDEMPOTENCY_CONFLICT')
                return self.get(old['id'], user)
            key, at = str(uuid.uuid4()), now_iso()
            self.db.execute('INSERT INTO jobs(id,user_id,course_id,type,input,resource,status,max_attempts,idempotency_key,available_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                            (key, user, value['courseId'], value['type'], data, resource, 'queued', maximum, value['idempotencyKey'], self.now(), at, at))
            self.event(key, {'status': 'queued'})
            return self.get(key, user)

    def recover(self):
        with self.db.transaction():
            rows = self.db.all("SELECT * FROM jobs WHERE status IN ('running','cancelling') AND lease_until<=?", (self.now(),))
            for row in rows:
                status = 'unknown' if row['resource'] == 'api' else 'cancelled' if row['status'] == 'cancelling' else 'failed' if row['attempts'] >= row['max_attempts'] else 'queued'
                self.db.execute('UPDATE jobs SET status=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?', (status, now_iso(), row['id']))
                self.event(row['id'], {'status': status, 'recovered': True})
            return len(rows)

    def _update(self, key, field, value):
        require(field in ('progress', 'checkpoint') and len(dumps(value).encode()) <= 65536, 'JOB_UPDATE_TOO_LARGE')
        changed = self.db.execute(f"UPDATE jobs SET {field}=?,updated_at=? WHERE id=? AND lease_owner=? AND status='running'", (dumps(value), now_iso(), key, self.owner))
        require(changed.rowcount, 'JOB_LEASE_LOST')
        self.event(key, {field: value})

    async def _execute(self, row, release):
        key = row['id']
        async def heartbeat():
            while True:
                await asyncio.sleep(max(.05, self.lease/3000))
                changed = self.db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND lease_owner=? AND status='running'", (self.now()+self.lease, key, self.owner))
                if not changed.rowcount:
                    active = self.active.get(key)
                    if active:
                        active.cancel()
                    return
        beat = asyncio.create_task(heartbeat())
        def commit(fn):
            with self.db.transaction():
                current = self.db.one('SELECT * FROM jobs WHERE id=?', (key,))
                require(current and current['lease_owner'] == self.owner and current['status'] == 'running' and current['lease_until'] > self.now(), 'JOB_LEASE_LOST')
                return fn()
        try:
            scope = {'userId': row['user_id'], 'courseId': row['course_id']}
            self.repository.require_course(scope)
            async with asyncio.timeout(self.timeout):
                result = await self.handlers[row['type']]({'scope': scope, 'input': json.loads(row['input']), 'jobId': key, 'checkpoint': json.loads(row['checkpoint'])},
                    progress=lambda v: self._update(key, 'progress', v), checkpoint=lambda v: self._update(key, 'checkpoint', v), commit=commit)
            require(len(dumps(result).encode()) <= 131072, 'JOB_RESULT_TOO_LARGE')
            def save():
                self.db.execute("UPDATE jobs SET status='succeeded',result=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?", (dumps(result), now_iso(), key))
                self.event(key, {'status': 'succeeded', 'result': result})
            commit(save)
        except (Exception, asyncio.CancelledError) as error:
            current = self.get(key, row['user_id'])
            if current and current['status'] not in ('succeeded', 'unknown'):
                unknown = row['resource'] == 'api' and getattr(error, 'code', '') != 'NOT_SENT'
                cancelled = isinstance(error, (asyncio.CancelledError, TimeoutError)) or current['status'] == 'cancelling'
                status = 'unknown' if unknown else 'cancelled' if cancelled else 'queued' if row['attempts'] < row['max_attempts'] else 'failed'
                code = getattr(error, 'code', 'JOB_FAILED')
                self.db.execute('UPDATE jobs SET status=?,error=?,available_at=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=? AND lease_owner=?', (status, code, self.now()+min(30000, 250*2**row['attempts']), now_iso(), key, self.owner))
                self.event(key, {'status': status, 'error': code})
        finally:
            beat.cancel()
            self.active.pop(key, None)
            release()

    async def tick(self):
        self.recover()
        for record in self.db.all("SELECT * FROM jobs WHERE status='queued' AND available_at<=? ORDER BY created_at LIMIT 50", (self.now(),)):
            row = dict(record)
            if row['type'] not in self.handlers or row['id'] in self.active:
                continue
            release = self.resources.acquire(row['resource'])
            if not release:
                continue
            claimed = self.db.execute("UPDATE jobs SET status='running',attempts=attempts+1,lease_owner=?,lease_until=?,updated_at=? WHERE id=? AND status='queued'", (self.owner, self.now()+self.lease, now_iso(), row['id']))
            if not claimed.rowcount:
                release()
                continue
            row['attempts'] += 1
            self.event(row['id'], {'status': 'running', 'attempt': row['attempts']})
            self.active[row['id']] = asyncio.create_task(self._execute(row, release))

    def cancel(self, key, user):
        row = self.get(key, user)
        require(row, 'JOB_NOT_FOUND')
        if row['status'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
            return row
        state = 'cancelling' if key in self.active else 'cancelled'
        self.db.execute('UPDATE jobs SET status=?,updated_at=? WHERE id=?', (state, now_iso(), key))
        if key in self.active:
            self.active[key].cancel()
        self.event(key, {'status': state})
        return self.get(key, user)

    def retry(self, key, user):
        row = self.get(key, user)
        require(row and row['status'] in ('failed', 'cancelled'), 'JOB_NOT_RETRYABLE')
        self.db.execute("UPDATE jobs SET status='queued',attempts=0,error=NULL,available_at=?,updated_at=? WHERE id=?", (self.now(), now_iso(), key))
        self.event(key, {'status': 'queued', 'manualRetry': True})
        return self.get(key, user)

    def events(self, key, user, after=0):
        require(self.get(key, user), 'JOB_NOT_FOUND')
        require(type(after) is int and after >= 0, 'INVALID_CURSOR')
        return [{'seq': r['seq'], 'at': r['at'], **json.loads(r['event'])} for r in self.db.all('SELECT seq,event,at FROM job_events WHERE job_id=? AND seq>? ORDER BY seq LIMIT 100', (key, after))]

    def start(self):
        async def poll():
            while True:
                await self.tick()
                await asyncio.sleep(.1)
        self.poller = asyncio.create_task(poll())

    async def stop(self):
        if self.poller:
            self.poller.cancel()
            await asyncio.gather(self.poller, return_exceptions=True)
        tasks = list(self.active.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)
