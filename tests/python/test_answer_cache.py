"""Evidence-versioned answer cache: repeat questions skip generation, stale data does not."""
import json

import httpx
from fastapi.testclient import TestClient

from backend.xueya.app import create_app
from backend.xueya.common import dumps
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider

SOURCE = {'id': 'cache-source', 'documentId': 'cache-doc', 'title': '队列', 'location': '第1页',
          'version': '1', 'quote': '队列遵循先进先出。队尾入队，队首出队。', 'keywords': ['队列']}
ANSWER = {'claims': [{'text': '队列遵循先进先出。', 'kind': 'excerpt',
                      'evidence': [{'sourceId': SOURCE['id'], 'quote': '队列遵循先进先出。'}]}],
          'answer': '队列遵循先进先出。', 'sources': [SOURCE['id']]}


def upstream(captured):
    async def respond(request):
        body = json.loads(request.content)
        captured.append(body)
        if '证据核对员' in body['messages'][0]['content']:
            verdicts = {'verdicts': [{'index': 0, 'status': 'supported'}]}
            return httpx.Response(200, text='data: '+dumps({'choices': [{'delta': {'content': dumps(verdicts)},
                                                                          'finish_reason': 'stop'}]})+'\n\ndata: [DONE]\n\n')
        content = dumps(ANSWER)
        return httpx.Response(200, text='data: '+dumps({'choices': [{'delta': {'content': content},
                                                                      'finish_reason': 'stop'}]})+'\n\ndata: [DONE]\n\n')
    return respond


def events(response):
    return [json.loads(frame[6:]) for frame in response.text.split('\n\n') if frame.startswith('data: ')]


def ask(client, *, history=None):
    response = client.post('/api/agent/stream', json={'question': '队列是什么？',
                                                      'sources': [{**SOURCE, 'quote': '队列遵循先进先出。队尾入队，队首出队。'}],
                                                      'documentIds': [SOURCE['documentId']],
                                                      **({'history': history} if history else {})})
    assert response.status_code == 200
    return events(response)[-1]


def host(tmp_path, **options):
    captured = []
    config = Config(data_dir=tmp_path / 'data', api_key='offline-only', **options)
    app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream(captured))), start_jobs=False)
    return app, captured


def test_repeated_question_is_served_from_the_evidence_versioned_cache(tmp_path):
    app, captured = host(tmp_path, answer_cache_ttl=3600)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        app.state.platform.repo.put(app.state.platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        first = ask(client)
        assert first.get('answerStatus') != 'unavailable' and first['sources'] == [SOURCE['id']]
        assert not first.get('cacheHit')
        generation_calls = len([body for body in captured if '证据核对员' not in body['messages'][0]['content']])
        assert generation_calls == 1
        second = ask(client)
        assert second.get('cacheHit') is True
        assert second['answer'] == first['answer'] and second['sources'] == first['sources']
        generation_calls = len([body for body in captured if '证据核对员' not in body['messages'][0]['content']])
        assert generation_calls == 1  # no new generation request


def test_source_revision_change_invalidates_the_cache(tmp_path):
    app, captured = host(tmp_path, answer_cache_ttl=3600)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        platform = app.state.platform
        platform.repo.put(platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        ask(client)
        assert ask(client).get('cacheHit') is True
        platform.repo.put(platform.scope(), 'source', SOURCE['id'],
                          {**SOURCE, 'quote': '队列遵循先进先出。队尾入队，队首出队。修订版'}, 1)
        assert not ask(client).get('cacheHit')


def test_conversation_history_participates_in_the_cache_key(tmp_path):
    app, captured = host(tmp_path, answer_cache_ttl=3600)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        app.state.platform.repo.put(app.state.platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        history = [{'role': 'user', 'content': '之前问过队列'}]
        assert not ask(client, history=history).get('cacheHit')
        # The same history replays the cached turn; a different history must not.
        assert ask(client, history=history).get('cacheHit') is True
        assert not ask(client, history=[{'role': 'user', 'content': '别的话题'}]).get('cacheHit')


def test_cache_ttl_zero_disables_storage(tmp_path):
    app, captured = host(tmp_path, answer_cache_ttl=0)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        app.state.platform.repo.put(app.state.platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        ask(client)
        assert not ask(client).get('cacheHit')
