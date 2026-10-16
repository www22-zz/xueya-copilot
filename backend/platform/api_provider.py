import asyncio
import uuid
from ..core import require, dumps, fingerprint, now_iso


class TrackedProvider:
    def __init__(self, platform, model, scope):
        self.platform, self.model, self.scope = platform, model, scope

    def capabilities(self):
        return self.model.capabilities() if hasattr(self.model, 'capabilities') else {}

    def _start(self, request):
        release = self.platform.resources.acquire('api')
        require(release, 'API_BUSY')
        key, at = str(uuid.uuid4()), now_iso()
        try:
            self.platform.db.execute('INSERT INTO invocations(id,user_id,course_id,status,provider,request_hash,at,updated_at) VALUES(?,?,?,?,?,?,?,?)', (key, self.scope['userId'], self.scope['courseId'], 'pending', 'mimo', fingerprint(request['messages']), at, at))
        except BaseException:
            release()
            raise
        return key, release

    def _finish(self, execution, status, usage=None):
        key, release = execution
        try:
            self.platform.db.execute('UPDATE invocations SET status=?,updated_at=?,usage_json=?,billing_status=? WHERE id=?', (status, now_iso(), dumps(usage) if usage else None, 'unknown' if status == 'unknown' else 'not_reported', key))
        finally:
            release()

    async def generate(self, request):
        execution = self._start(request)
        try:
            result = await self.model.generate(request)
        except BaseException:
            self._finish(execution, 'unknown')
            raise
        self._finish(execution, 'succeeded', result.get('usage'))
        return result

    async def stream(self, request):
        execution, complete, usage = self._start(request), False, None
        try:
            if callable(getattr(self.model, 'stream', None)):
                async for event in self.model.stream(request):
                    if event['type'] == 'usage':
                        usage = event['usage']
                    yield event
            else:
                result = await self.model.generate(request)
                usage = result.get('usage')
                yield {'type': 'content', 'text': result['content'], 'model': result.get('model')}
            complete = True
        finally:
            self._finish(execution, 'succeeded' if complete else 'unknown', usage)
