"""Explanations require real citations plus a separate, bounded semantic verdict."""
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.common import dumps
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider
from scripts.readonly_agent_fixture import planner_response

SOURCE = {'id': 'explain-source', 'title': '队列', 'location': '第2页',
          'quote': '队列遵循先进先出。入队只能在队尾进行，出队只能在队首进行。', 'keywords': ['队列']}
TEXT = '可以把队列理解为按到达顺序处理的队伍：先进入的先离开，新元素接在队尾，从队首取出元素。'
INFERENCE = '假设甲先入队、乙随后入队，那么正常出队时甲会先于乙离开。'


def claim(text=TEXT, kind='paraphrase', quote=None, source_id=None):
    return {'text': text, 'kind': kind, 'evidence': [{'sourceId': source_id or SOURCE['id'], 'quote': quote or SOURCE['quote']}]}


def host(tmp_path, claims, verdict='supported', *, options=None, on_review=None, complex_task=False):
    calls = []
    answer = {'answer': '不能绕过claims发布的正文', 'claims': claims, 'sources': [SOURCE['id']], 'knowledgePoints': []}
    def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        if '证据核对员' in body['messages'][0]['content']:
            if on_review:
                on_review(app)
            if isinstance(verdict, httpx.Response):
                return verdict
            batch = json.loads(body['messages'][-1]['content'])['claims']
            content = {'verdicts': [{'index': c['index'], 'status': verdict if isinstance(verdict, str) else verdict[c['index']]} for c in batch]} if isinstance(verdict, (str, list)) else verdict
            return httpx.Response(200, json={'choices': [{'message': {'content': dumps(content)}, 'finish_reason': 'stop'}]})
        planned = planner_response(body) if complex_task else None
        if planned is not None:
            value = planned.json()
            decision = json.loads(value['choices'][0]['message']['content'])
            if decision['action']['type'] == 'finish':
                decision['action']['answer'] = answer
                value['choices'][0]['message']['content'] = dumps(decision)
            return httpx.Response(200, json=value)
        content = dumps(answer)
        if body.get('stream'):
            return httpx.Response(200, text='data: '+dumps({'choices': [{'delta': {'content': content}, 'finish_reason': 'stop'}]})+'\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json={'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]})
    config = Config(data_dir=tmp_path, api_key='offline-only', **(options or {}))
    app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)), start_jobs=False)
    return app, calls


def ask(app, path='/api/agent/stream', question='队列是什么？'):
    with TestClient(app, base_url='http://127.0.0.1') as client:
        p = app.state.platform
        p.repo.put(p.scope(), 'source', SOURCE['id'], SOURCE, 0)
        response = client.post(path, json={'question': question, 'sources': [SOURCE]})
        assert response.status_code == 200
        if path.endswith('/stream'):
            events = [json.loads(f[6:]) for f in response.text.split('\n\n') if f.startswith('data: ')]
            result = events[-1]
            assert result['type'] == 'done'
            return result, events
        return response.json(), []


@pytest.mark.parametrize('path', ['/api/ai', '/api/ai/stream', '/api/agent', '/api/agent/stream'])
def test_supported_explanation_is_not_replaced_by_a_quote(tmp_path, path):
    app, calls = host(tmp_path, [claim(), claim(INFERENCE, 'inference')])
    result, events = ask(app, path)
    assert TEXT in result['answer'] and INFERENCE in result['answer']
    assert '基于资料的推理：' in result['answer']
    assert result['verification'] == 'reviewed-claims'
    assert result['sources'] == [SOURCE['id']]
    assert '不能绕过claims' not in result['answer']
    assert len(calls) == 2
    review = json.loads(calls[-1]['messages'][-1]['content'])['claims']
    assert len(review) == 2 and review[0]['evidence'][0]['quote'] == SOURCE['quote']
    assert calls[-1]['response_format'] == {'type': 'json_object'}
    if events:
        text = ''.join(e.get('text', '') for e in events if e['type'] == 'content')
        assert TEXT in text


@pytest.mark.parametrize('verdict', ['unsupported', 'uncertain', {'verdicts': []},
    {'verdicts': [{'index': True, 'status': 'supported'}]}, {'verdicts': [{'index': 0, 'status': True}]},
    httpx.Response(503), {'answer': '自报审核通过'}])
def test_valid_reference_alone_does_not_authorize_a_paraphrase(tmp_path, verdict):
    app, calls = host(tmp_path, [claim('队列永远是后进入的元素先离开。')], verdict)
    result, events = ask(app)
    assert '永远是后进入' not in dumps(events)
    assert result['engine'] == 'local-workflow' and result['verification'] == 'not-generated' and result['answerStatus'] == 'unavailable'
    assert len(calls) == 2  # No review or generation retries.


@pytest.mark.parametrize('bad', [claim(quote='伪造引文'), claim(source_id='forged')])
def test_forged_citation_is_rejected_before_review(tmp_path, bad):
    app, calls = host(tmp_path, [bad])
    result, events = ask(app)
    assert result['verification'] == 'not-generated' and result['answerStatus'] == 'unavailable'
    assert len(calls) == 1
    assert TEXT not in dumps(events)


def test_keep_supported_explanation_and_omit_an_unsupported_claim(tmp_path):
    app, calls = host(tmp_path, [claim(), claim('队列可以保证所有问题最快得到解决。')], ['supported', 'unsupported'])
    result, events = ask(app)
    assert TEXT in result['answer'] and '所有问题最快' not in dumps(events)
    assert result['omittedClaims'] == 1 and '已省略' in result['answer']
    assert result['verification'] == 'reviewed-claims' and len(calls) == 2


def test_review_cannot_bypass_shared_model_budget(tmp_path):
    app, calls = host(tmp_path, [claim()], options={'run_model_calls': 1})
    result, _ = ask(app)
    assert result['engine'] == 'local-workflow' and len(calls) == 1


def test_source_changed_during_review_is_not_published(tmp_path):
    def update(app):
        p = app.state.platform
        p.repo.put(p.scope(), 'source', SOURCE['id'], {**SOURCE, 'location': '修订页码'}, 1)
    app, calls = host(tmp_path, [claim()], on_review=update)
    result, events = ask(app)
    assert result['sources'] == [] and '资料已更新' in result['answer']
    assert TEXT not in dumps(events) and len(calls) == 2


def test_complex_agent_uses_the_same_review_and_keeps_planning(tmp_path):
    app, calls = host(tmp_path, [claim()], complex_task=True)
    result, _ = ask(app, question='跨章节综合分析队列')
    assert result['agent']['decisionCount'] >= 3
    assert result['verification'] == 'reviewed-claims'
    assert TEXT in result['answer'] and result['sources'] == [SOURCE['id']]
    assert len(calls) == result['agent']['decisionCount']+1


@pytest.mark.parametrize('verdicts', [
    {'verdicts': [{'index': 0, 'status': 'supported'}, {'index': 0, 'status': 'supported'}]},
    {'verdicts': [{'index': 0, 'status': 'supported'}]},
    {'verdicts': [{'index': 0, 'status': 'supported'}, {'index': 9, 'status': 'supported'}]},
])
def test_incomplete_or_duplicated_review_does_not_partially_authorize_content(tmp_path, verdicts):
    app, calls = host(tmp_path, [claim(), claim(INFERENCE, 'inference')], verdicts)
    result, events = ask(app)
    assert TEXT not in dumps(events) and INFERENCE not in dumps(events)
    assert result['verification'] == 'not-generated' and result['answerStatus'] == 'unavailable' and len(calls) == 2


def test_excerpt_prefix_and_reviewed_explanation_form_one_valid_stream(tmp_path):
    app, _ = host(tmp_path, [claim(SOURCE['quote']), claim()])
    result, events = ask(app)
    streamed = json.loads(''.join(e.get('text', '') for e in events if e['type'] == 'content'))
    assert streamed['answer'] == result['answer']
    assert streamed['sources'] == result['sources'] == [SOURCE['id']]
    assert TEXT in result['answer'] and result['verification'] == 'reviewed-claims'


async def test_cancel_during_review_releases_slot_without_publishing_paraphrase(platform):
    import asyncio
    from backend.xueya.agent import Agent
    entered = asyncio.Event()
    class Blocked(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            entered.set()
            await asyncio.Event().wait()
            yield b'never'
        async def aclose(self):
            self.closed = True
    blocked = Blocked()
    calls, published = [], []
    async def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 2:
            return httpx.Response(200, stream=blocked)
        content = dumps({'answer': TEXT, 'claims': [claim()], 'sources': [SOURCE['id']]})
        return httpx.Response(200, text='data: '+dumps({'choices': [{'delta': {'content': content}, 'finish_reason': 'stop'}]})+'\n\ndata: [DONE]\n\n')
    config = Config(api_key='offline-only')
    provider = MimoProvider(config, platform, transport=httpx.MockTransport(upstream))
    platform.repo.put(platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
    async def collect():
        async for event in Agent(provider, platform).workflow({'question': '队列是什么？', 'sources': [SOURCE]}):
            if event['type'] == 'content':
                published.append(event)
    task = asyncio.create_task(collect())
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert blocked.closed and not published and len(calls) == 2
    assert platform.resources.stats()['active']['api'] == 0
    assert platform.db.one("SELECT count(*) AS n FROM invocations WHERE status='unknown'")['n'] == 1
