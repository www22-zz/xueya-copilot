import httpx
import pytest
from backend.app import create_app
from backend.agent.http_handler import LearningHandler
from backend.agent.learning_service import LearningService
from backend.config import ROOT


async def client_for(repository, course):
    service = LearningService(repository, clock=lambda: '2026-10-15T01:00:00Z')
    class Previews:
        def __init__(self):
            self.rows = {}
        async def put(self, c, k, v):
            self.rows[c, k] = v
        async def get(self, c, k):
            return self.rows.get((c, k))
    async def context(request):
        return {'courseId': 'course', 'userId': 'learner', 'loadStudyContext': lambda: course}
    handler = LearningHandler(service, context, lambda selection: course['sources'], lambda selection: [q for q in course['questions'] if q['id'] in selection['ids']], Previews())
    app = create_app({'root': ROOT, 'ai': {}}, learning_handler=handler)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


async def test_learning_routes_require_scope_preview_adoption_and_preserve_grades(repository, course):
    async with await client_for(repository, course) as client:
        denied = await client.post('/api/learning/study/session', json={'courseId': 'other'})
        assert denied.status_code == 403
        session = (await client.post('/api/learning/study/session', json={'events': [], 'cards': []})).json()
        assert session['ok'] and session['result']['estimates']
        preview = (await client.post('/api/learning/quiz/preview', json={'id': 'quiz', 'questionIds': ['new-node'], 'count': 1})).json()['result']
        assert not await repository.get('course', 'quiz')
        adopt = {'draftId': preview['draftId'], 'operationId': 'adopt', 'confirmed': True}
        assert (await client.post('/api/learning/draft/adopt', json={**adopt, 'content': {'changed': True}})).status_code == 409
        assert (await client.post('/api/learning/draft/adopt', json=adopt)).json()['ok']
        public = (await client.get('/api/learning/quiz/quiz')).json()['result']
        assert 'answer' not in public['questions'][0]
        attempt = (await client.post('/api/learning/attempts', json={'id': 'attempt', 'quizId': 'quiz', 'quizRevision': 1, 'responses': [{'questionId': 'new-node', 'answer': 1}]})).json()['result']
        assert attempt['content']['events'][0]['grade']['score'] == 0
        assert (await client.post('/api/learning/chapter', json={'id': 'run', 'artifactId': 'p'})).status_code == 503
        assert (await client.get('/api/learning/attempts')).status_code == 405
        assert (await client.post('/api/learning/unknown', json={})).status_code == 404
