import uuid
from ..core import require, now_iso
from ..agent.learning_workflow import LearningWorkflow
from ..agent.tasks import normalize_context
from ..mcp.platform_server import open_platform_session
from .api_provider import TrackedProvider


class StoredWorkflow:
    def __init__(self, platform, model, rag, fallback):
        self.platform, self.model, self.rag, self.fallback = platform, model, rag, fallback

    async def run(self, value, signal=None):
        async for event in self.stream(value, signal):
            if event['type'] == 'done':
                return {k: v for k, v in event.items() if k != 'type'}
        require(False, 'AGENT_INCOMPLETE')

    async def stream(self, value, signal=None):
        platform, repository = self.platform, self.platform.repository
        stored = repository.get_workspace(platform.user_id)
        if not stored:
            async for event in self.fallback.stream(value, signal):
                yield event
            return
        scope = platform.scope(value.get('courseId', stored['data']['activeId']))
        course = next((c for c in stored['data']['courses'] if c['id'] == scope['courseId']), None)
        require(course, 'COURSE_NOT_FOUND')
        candidates = repository.all(scope, 'source')
        supplied = (value.get('context') or {}).get('library', value.get('sources', []))
        ids = {s if isinstance(s, str) else s['id'] for s in supplied}
        sources = [s for s in candidates if s['id'] in ids] if ids else await self.rag.retrieve(value['question'], candidates)
        context = normalize_context({'library': sources, 'questions': repository.all(scope, 'question'), 'records': repository.all(scope, 'attempt'), 'examDate': course['data'].get('examDate'), 'minutes': course['data'].get('minutes'), 'previousSourceIds': (value.get('context') or {}).get('previousSourceIds', [])})
        def open_session(context, timeout_ms=5000):
            return open_platform_session(platform, scope, timeout_ms, context['library'])
        workflow = LearningWorkflow(TrackedProvider(platform, self.model, scope), open_session=open_session)
        key = 'run-'+str(uuid.uuid4())
        version = repository.put(scope, 'run', key, {'status': 'running', 'question': value['question'], 'startedAt': now_iso()}, 0)['version']
        complete = False
        try:
            async for event in workflow.stream({**value, 'context': context}, signal):
                if event['type'] == 'workflow':
                    repository.put(scope, 'checkpoint', key, {'stage': event['stage'], 'status': event['status'], 'at': now_iso()})
                if event['type'] == 'done':
                    repository.put(scope, 'run', key, {'status': 'succeeded', 'question': value['question'], 'result': event, 'finishedAt': now_iso()}, version)
                    complete = True
                yield {**event, 'runId': key}
        finally:
            if not complete:
                repository.put(scope, 'run', key, {'status': 'cancelled' if signal and signal.aborted else 'interrupted', 'question': value['question'], 'finishedAt': now_iso()}, version)
