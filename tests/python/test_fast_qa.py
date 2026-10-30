"""Offline causal checks: one model call, early verified output, current evidence."""
import asyncio
from contextlib import aclosing
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.xueya.agent import Agent
from backend.xueya.app import create_app
from backend.xueya.common import dumps
from backend.xueya.config import Config
from backend.xueya.fast_qa import ClaimStream, ordinary_question
from backend.xueya.provider import MimoProvider
from backend.xueya.qa_latency import current_timing

SOURCE = {'id': 'fast-source', 'documentId': 'fast-doc', 'title': '队列', 'location': '第1页',
          'quote': '队列遵循先进先出。队尾入队，队首出队。', 'keywords': ['队列']}
CLAIM = {'text': '队列遵循先进先出。', 'evidence': [{'sourceId': SOURCE['id'], 'quote': '队列遵循先进先出。'}]}


@pytest.mark.parametrize('question,mode,intent,expected', [
    ('队列是什么？', 'ask', 'ask', True), ('栈和队列有什么区别？', 'ask', 'ask', True),
    ('为什么呢？', 'ask', 'ask', True), ('对比所有章节并生成复习计划', 'ask', 'plan', False),
    ('帮我学习队列这一章', 'ask', 'ask', False), ('跨文档综合分析队列', 'ask', 'ask', False),
    ('证明算法的正确性', 'ask', 'ask', False), ('队列', 'summarize', 'summarize', False),
    ('请出题', 'quiz', 'quiz', False), ('先解释队列然后给出学习安排', 'ask', 'ask', False),
])
def test_conservative_routing(question, mode, intent, expected):
    assert ordinary_question({'question': question, 'mode': mode}, intent) is expected


async def test_claim_parser_ignores_strings_and_never_publishes_unchecked_text():
    parser = ClaimStream()
    forged = {'text': '编造结论', 'evidence': [{'sourceId': SOURCE['id'], 'quote': '队列遵循先进先出。'}]}
    content = dumps({'answer': '含有转义的假字段 "claims":[{}]', 'claims': [CLAIM, forged], 'sources': [SOURCE['id']]})
    texts = []
    for char in content:
        for claim in parser.feed(char):
            text = await parser.checked_text(claim, [SOURCE])
            if text:
                texts.append(text)
    assert texts == ['队列遵循先进先出。 [1]']


class DelayedResponse(httpx.AsyncByteStream):
    def __init__(self, release, claim=CLAIM, before_tail=None):
        self.release, self.claim, self.before_tail = release, claim, before_tail
        self.started = asyncio.Event()
        self.finished = False
        self.closed = False

    async def __aiter__(self):
        prefix = '{"claims":['+dumps(self.claim)
        yield ('data: '+dumps({'choices': [{'delta': {'content': prefix}}]})+'\n\n').encode()
        self.started.set()
        await self.release.wait()
        if self.before_tail:
            self.before_tail()
        self.finished = True
        tail = '],"answer":"'+self.claim['text']+'","sources":["'+SOURCE['id']+'"]}'
        yield ('data: '+dumps({'choices': [{'delta': {'content': tail}, 'finish_reason': 'stop'}]})+'\n\ndata: [DONE]\n\n').encode()

    async def aclose(self):
        self.closed = True


def model(platform, response):
    captured = []
    async def upstream(request):
        body = json.loads(request.content)
        captured.append(body)
        assert body['stream'] is True, 'ordinary Q&A must not call the planner'
        return httpx.Response(200, stream=response, headers={'Content-Type': 'text/event-stream'})
    provider = MimoProvider(Config(api_key='offline-only'), platform, transport=httpx.MockTransport(upstream))
    return Agent(provider, platform), captured


def seed(platform):
    platform.repo.put(platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
    return {'question': '队列是什么？', 'sources': [SOURCE], 'documentIds': [SOURCE['documentId']]}


async def test_complete_narrative_waits_for_model_and_uses_one_call(platform):
    request = seed(platform)
    release = asyncio.Event()
    response = DelayedResponse(release)
    agent, captured = model(platform, response)
    events = []
    async def consume():
        async with aclosing(agent.workflow(request)) as stream:
            async for event in stream:
                events.append(event)
    async with asyncio.timeout(5):
        task = asyncio.create_task(consume())
        await response.started.wait()
        assert not response.finished
        assert not any(e['type'] == 'content' for e in events)
        release.set()
        await task
    result = events[-1]
    assert result['type'] == 'done' and result['sources'] == [SOURCE['id']]
    assert result['answer'] == CLAIM['text']+' [1]'
    assert len(captured) == result['timings']['modelCalls'] == 1
    assert captured[0]['thinking'] == {'type': 'disabled'}
    timing = result['timings']
    assert timing['route'] == 'fast-qa'
    assert 0 <= timing['firstModelTokenMs'] <= timing['firstContentMs'] <= timing['totalMs']
    assert timing['phasesMs']['retrieve'] >= 0 and timing['phasesMs']['read'] >= 0
    assert timing['phasesMs']['validate'] >= 0 and timing['modelMs'] > 0
    saved = platform.repo.all(platform.scope(), 'run')[0]['result']
    assert saved['timings']['route'] == 'fast-qa'
    assert response.closed and current_timing.get() is None


async def test_invalid_claim_never_streams_and_no_paid_retry(platform):
    request = seed(platform)
    release = asyncio.Event()
    release.set()
    claim = {'text': '无来源的错误结论', 'evidence': [{'sourceId': 'forged', 'quote': '伪造原文'}]}
    response = DelayedResponse(release, claim)
    agent, captured = model(platform, response)
    events = [event async for event in agent.workflow(request)]
    assert '无来源的错误结论' not in dumps(events)
    assert '伪造原文' not in ''.join(e.get('text', '') for e in events)
    assert len(captured) == 1
    assert events[-1]['engine'] == 'local-workflow'


async def test_source_revision_change_stops_final_publication(platform):
    request = seed(platform)
    release = asyncio.Event()
    release.set()
    def change():
        platform.repo.put(platform.scope(), 'source', SOURCE['id'], {**SOURCE, 'location': '更正页码'}, 1)
    response = DelayedResponse(release, before_tail=change)
    agent, _ = model(platform, response)
    events = []
    async with asyncio.timeout(5):
        async for event in agent.workflow(request):
            events.append(event)
            if event['type'] == 'content':
                release.set()
    assert events[-1]['sources'] == []
    assert '资料已更新' in events[-1]['answer']


async def test_cancel_before_narrative_closes_transport_and_records_interruption(platform):
    request = seed(platform)
    response = DelayedResponse(asyncio.Event())
    agent, _ = model(platform, response)
    async def consume():
        async with aclosing(agent.workflow(request)) as stream:
            async for event in stream:
                assert event['type'] != 'content'
    async with asyncio.timeout(5):
        task = asyncio.create_task(consume())
        await response.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert response.closed
    run = platform.repo.all(platform.scope(), 'run')[0]
    assert run['status'] == 'cancelled' and run['timings']['route'] == 'fast-qa'
    assert platform.db.one('SELECT status FROM invocations')['status'] == 'unknown'


def test_http_sse_keeps_contract_and_server_owns_the_evidence(tmp_path):
    async def upstream(request):
        body = json.loads(request.content)
        source = json.loads(body['messages'][-1]['content'])['materials'][0]
        assert source['quote'] == SOURCE['quote']
        content = dumps({'claims': [CLAIM], 'answer': CLAIM['text'], 'sources': [SOURCE['id']]})
        return httpx.Response(200, text='data: '+dumps({'choices': [{'delta': {'content': content}, 'finish_reason': 'stop'}]})+'\n\ndata: [DONE]\n\n')
    config = Config(data_dir=tmp_path, api_key='offline-only')
    app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)), start_jobs=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        app.state.platform.repo.put(app.state.platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        response = client.post('/api/agent/stream', json={'question': '队列是什么？', 'sources': [{**SOURCE, 'quote': '客户端伪造内容'}], 'documentIds': [SOURCE['documentId']]})
        events = [json.loads(frame[6:]) for frame in response.text.split('\n\n') if frame.startswith('data: ')]
        assert response.headers['content-type'].startswith('text/event-stream')
        assert events[-1]['type'] == 'done' and events[-1]['timings']['modelCalls'] == 1
        assert '客户端伪造内容' not in response.text
