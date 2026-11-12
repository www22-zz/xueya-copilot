"""Optional fast mode: exact citations are still enforced, prose review is skipped."""
import json

import httpx
from fastapi.testclient import TestClient

from backend.xueya.app import create_app
from backend.xueya.common import dumps
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider

SOURCE = {'id': 'fast-mode-source', 'documentId': 'fast-mode-doc', 'title': '队列', 'location': '第1页',
          'version': '1', 'quote': '队列遵循先进先出。队尾入队，队首出队。', 'keywords': ['队列']}
PROSE = '队列是先进先出的结构：新元素从队尾进入，从队首离开。'


def answer(claims=None):
    return {'answer': PROSE, 'sources': [SOURCE['id']],
            'claims': claims or [{'text': '队列遵循先进先出。', 'kind': 'excerpt',
                                  'evidence': [{'sourceId': SOURCE['id'], 'quote': '队列遵循先进先出。'}]}]}


def host(tmp_path, *, review_status='supported', claim=None):
    calls = []

    def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        if '证据核对员' in body['messages'][0]['content']:
            batch = json.loads(body['messages'][-1]['content'])['claims']
            verdicts = {'verdicts': [{'index': row['index'], 'status': review_status} for row in batch]}
            return httpx.Response(200, json={'choices': [{'message': {'content': dumps(verdicts)}, 'finish_reason': 'stop'}]})
        content = dumps(answer([claim] if claim else None))
        return httpx.Response(200, text='data: '+dumps({'choices': [{'delta': {'content': content}, 'finish_reason': 'stop'}]})
                              + '\n\ndata: [DONE]\n\n', headers={'Content-Type': 'text/event-stream'})

    config = Config(data_dir=tmp_path / 'data', api_key='offline-only')
    app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)), start_jobs=False)
    return app, calls


def ask(app, *, fast_mode):
    with TestClient(app, base_url='http://127.0.0.1') as client:
        platform = app.state.platform
        platform.repo.put(platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        response = client.post('/api/agent/stream', json={
            'question': '队列是什么？', 'sources': [SOURCE], 'documentIds': [SOURCE['documentId']],
            **({'fastMode': True} if fast_mode else {})})
        assert response.status_code == 200
        events = [json.loads(frame[6:]) for frame in response.text.split('\n\n') if frame.startswith('data: ')]
        return events[-1]


def test_fast_mode_publishes_claims_supported_prose_without_prose_review(tmp_path):
    app, calls = host(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        platform = app.state.platform
        platform.repo.put(platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        response = client.post('/api/agent/stream', json={'question': '队列是什么？', 'sources': [SOURCE],
                                                          'documentIds': [SOURCE['documentId']], 'fastMode': True})
        done = [json.loads(frame[6:]) for frame in response.text.split('\n\n') if frame.startswith('data: ')][-1]
    assert done['verification'] == 'claims-supported-prose' and done['proseReview'] == 'skipped'
    assert PROSE in done['answer']
    assert done['timings']['modelCalls'] == 1  # excerpt claims need no review call
    assert [body for body in calls if not body.get('stream')] == []


def test_strict_mode_still_reviews_the_narrative_prose(tmp_path):
    app, calls = host(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        platform = app.state.platform
        platform.repo.put(platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        response = client.post('/api/agent/stream', json={'question': '队列是什么？', 'sources': [SOURCE],
                                                          'documentIds': [SOURCE['documentId']]})
        done = [json.loads(frame[6:]) for frame in response.text.split('\n\n') if frame.startswith('data: ')][-1]
    assert done['verification'] == 'reviewed-narrative' and 'proseReview' not in done
    assert PROSE in done['answer']
    assert len([body for body in calls if not body.get('stream')]) == 1


def test_fast_mode_never_publishes_prose_when_claims_are_unsupported(tmp_path):
    claim = {'text': '队列是先进先出的结构。', 'kind': 'paraphrase',
             'evidence': [{'sourceId': SOURCE['id'], 'quote': SOURCE['quote']}]}
    app, calls = host(tmp_path, review_status='unsupported', claim=claim)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        platform = app.state.platform
        platform.repo.put(platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        response = client.post('/api/agent/stream', json={'question': '队列是什么？', 'sources': [SOURCE],
                                                          'documentIds': [SOURCE['documentId']], 'fastMode': True})
        done = [json.loads(frame[6:]) for frame in response.text.split('\n\n') if frame.startswith('data: ')][-1]
    assert done['answerStatus'] == 'unavailable'
    assert PROSE not in done['answer']
    assert len([body for body in calls if not body.get('stream')]) == 1  # claim was reviewed


def test_deep_think_is_opt_in_and_default_answers_disable_reasoning(tmp_path):
    app, calls = host(tmp_path / 'deep')
    with TestClient(app, base_url='http://127.0.0.1') as client:
        platform = app.state.platform
        platform.repo.put(platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        client.post('/api/agent/stream', json={'question': '队列是什么？', 'sources': [SOURCE],
                                               'documentIds': [SOURCE['documentId']]})
        client.post('/api/agent/stream', json={'question': '队列是什么？', 'sources': [SOURCE],
                                               'documentIds': [SOURCE['documentId']], 'deepThink': True})
    generation = [body for body in calls if body.get('stream')]
    assert generation[0]['thinking'] == {'type': 'disabled'}
    assert 'thinking' not in generation[1]


def test_fast_mode_still_rejects_forged_citations(tmp_path):
    claim = {'text': '队列永远后进先出。', 'kind': 'paraphrase',
             'evidence': [{'sourceId': SOURCE['id'], 'quote': '伪造原文'}]}
    app, calls = host(tmp_path, claim=claim)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        platform = app.state.platform
        platform.repo.put(platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        response = client.post('/api/agent/stream', json={'question': '队列是什么？', 'sources': [SOURCE],
                                                          'documentIds': [SOURCE['documentId']], 'fastMode': True})
        done = [json.loads(frame[6:]) for frame in response.text.split('\n\n') if frame.startswith('data: ')][-1]
    assert done['answerStatus'] == 'unavailable'
    assert PROSE not in done['answer'] and '伪造原文' not in response.text
    assert [body for body in calls if not body.get('stream')] == []
