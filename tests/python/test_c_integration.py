"""Cross-branch regressions: main host + B originals + C durable learning."""
import asyncio
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.learning_integration import LearningRepository
from backend.core import DomainError
import pytest


def upload(client):
    headers = {"X-Xueya-Token": client.get('/api/platform/bootstrap').json()['token']}
    result = client.post('/api/platform/rag/upload?name=chapter.md', content='# Trees\nA tree consists of nodes and edges.'.encode(), headers={**headers, 'Idempotency-Key': 'c-integration-upload'})
    assert result.status_code == 200, result.text
    job = result.json()['job']
    async def finish():
        p = client.app.state.platform
        p.jobs.stopped = False
        for _ in range(300):
            await p.jobs.tick()
            current = p.jobs.get(job['id'], p.user_id)
            if current['status'] in ('succeeded', 'failed', 'unknown', 'cancelled'):
                assert current['status'] == 'succeeded', current
                return current['result']['documentId']
            await asyncio.sleep(.02)
        raise AssertionError('parse timeout')
    return headers, client.portal.call(finish)


def test_b_to_c_preview_adoption_review_and_restart(tmp_path):
    config = Config(data_dir=tmp_path/'data')
    with TestClient(create_app(config, start_jobs=False), base_url='http://127.0.0.1') as client:
        headers, doc = upload(client)
        selection = {'documentIds': [doc]}
        assert client.post('/api/learning/answers', json={'question': 'nodes', 'selection': selection}).status_code == 403
        def post(path, value):
            response = client.post('/api/learning/'+path, json=value, headers=headers)
            assert response.status_code == 200, response.text
            return response.json()['result']
        answer = post('answers', {'question': 'nodes', 'selection': selection})
        assert answer['verification'] == 'verbatim-only'
        preview = post('package/preview', {'id': 'package', 'selection': selection})
        assert preview['draft']['content']['summary']['coverage']['sourceCount'] > 0
        adopted = post('draft/adopt', {'draftId': preview['draftId'], 'operationId': 'adopt-package', 'confirmed': True})
        assert adopted['revision'] == 1
        assert post('draft/adopt', {'draftId': preview['draftId'], 'operationId': 'adopt-package', 'confirmed': True}) == adopted
        sources = client.portal.call(client.app.state.learning.sources, {'courseId': 'course-default', 'selection': selection})
        card = post('card/preview', {'id': 'card', 'selection': selection, 'prompt': 'What is a tree?', 'answer': 'Nodes and edges', 'evidence': [{'sourceId': sources[0]['id'], 'quote': sources[0]['quote']}]})
        post('draft/adopt', {'draftId': card['draftId'], 'operationId': 'adopt-card', 'confirmed': True})
        rated = post('reviews/rate', {'id': 'card', 'rating': 3, 'expectedRevision': 1, 'operationId': 'rate-card'})
        assert rated['revision'] == 2
        snapshot = answer['evidenceVersion']
        assert client.portal.call(client.app.state.learning.verify_snapshot, 'course-default', snapshot)
        current = client.app.state.rag.document(client.app.state.platform.scope(), doc)
        client.app.state.rag.remove(client.app.state.platform.scope(), doc, current['version'])
        assert not client.portal.call(client.app.state.learning.verify_snapshot, 'course-default', snapshot)
    with TestClient(create_app(config, start_jobs=False), base_url='http://127.0.0.1') as client:
        stored = client.portal.call(client.app.state.learning.repo.get, 'course-default', 'card')
        assert stored['revision'] == 2
        assert stored['content']['schedule']['algorithm'].startswith('py-fsrs-')


def test_c_repository_receipts_cas_and_b_namespace(platform):
    async def exercise():
        repo = LearningRepository(platform)
        p = platform
        p.repo.put(p.scope(), 'artifact', 'same-id', {'documentId': 'b-document'}, 0)
        value = {'courseId': 'course-default', 'id': 'same-id', 'operationId': 'first', 'requestHash': 'hash', 'expectedRevision': 0,
                 'value': {'courseId': 'course-default', 'id': 'same-id', 'kind': 'note', 'revision': 1, 'content': {'text': 'first'}}}
        first = await repo.commit(value)
        await repo.commit({**value, 'operationId': 'second', 'expectedRevision': 1, 'value': {**value['value'], 'revision': 2}})
        assert await repo.commit(value) == first
        with pytest.raises(DomainError, match='IDEMPOTENCY_CONFLICT'):
            await repo.commit({**value, 'requestHash': 'changed'})
        with pytest.raises(DomainError, match='ARTIFACT_CONFLICT'):
            await repo.commit({**value, 'operationId': 'third'})
        assert p.repo.read(p.scope(), 'artifact', 'same-id')['value'] == {'documentId': 'b-document'}
        assert repo.all('course-default')[0]['revision'] == 2
    asyncio.run(exercise())


def test_c_chapter_queue_requires_confirmation_and_rejects_stale_preview(tmp_path):
    with TestClient(create_app(Config(data_dir=tmp_path/'data'), start_jobs=False), base_url='http://127.0.0.1') as client:
        headers, doc = upload(client)
        data = {'id': 'chapter-run', 'artifactId': 'chapter-package', 'selection': {'documentIds': [doc]}}
        response = client.post('/api/learning/chapter', json=data, headers=headers)
        assert response.status_code == 202, response.text
        async def finish():
            p = client.app.state.platform
            for _ in range(300):
                await p.jobs.tick()
                jobs = [j for j in p.jobs.list(p.user_id) if j['type'] == 'learning-chapter']
                if all(j['status'] == 'succeeded' for j in jobs):
                    return
                assert all(j['status'] not in ('failed', 'unknown') for j in jobs), jobs
                await asyncio.sleep(.02)
            raise AssertionError('chapter timeout')
        client.portal.call(finish)
        run = client.get('/api/learning/runs/chapter-run', headers=headers).json()['result']
        assert run['status'] == 'awaiting_confirmation'
        assert client.portal.call(client.app.state.learning.repo.get, 'course-default', 'chapter-package') is None
        resumed = client.post('/api/learning/runs/resume', json={'id': run['id'], 'revision': run['revision'], 'confirmation': True}, headers=headers)
        assert resumed.status_code == 202, resumed.text
        client.portal.call(finish)
        assert client.get('/api/learning/runs/chapter-run', headers=headers).json()['result']['status'] == 'completed'
        preview = client.post('/api/learning/package/preview', json={'id': 'stale', 'selection': {'documentIds': [doc]}}, headers=headers).json()['result']
        p, rag = client.app.state.platform, client.app.state.rag
        current = rag.document(p.scope(), doc)
        rag.remove(p.scope(), doc, current['version'])
        result = client.post('/api/learning/draft/adopt', json={'draftId': preview['draftId'], 'operationId': 'stale-adoption', 'confirmed': True}, headers=headers)
        assert result.status_code == 409 and result.json()['error'] == 'STALE_EVIDENCE'
