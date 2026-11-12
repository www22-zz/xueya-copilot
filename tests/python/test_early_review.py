"""Early claim review can stop a doomed generation before it finishes."""
import asyncio
import json

import httpx
import pytest

from backend.xueya.agent import Agent
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider
from backend.xueya.common import dumps

SOURCE = {'id': 'early-source', 'documentId': 'early-doc', 'title': '队列', 'location': '第1页',
          'version': '1', 'quote': '队列遵循先进先出。队尾入队，队首出队。', 'keywords': ['队列']}
CLAIM = {'text': '队列是一种先进先出的结构。', 'kind': 'paraphrase',
         'evidence': [{'sourceId': SOURCE['id'], 'quote': '队列遵循先进先出。'}]}


class Generation(httpx.AsyncByteStream):
    def __init__(self):
        self.closed = False

    async def __aiter__(self):
        prefix = '{"claims":['+dumps(CLAIM)+'],'
        yield ('data: '+dumps({'choices': [{'delta': {'content': prefix}}]})+'\n\n').encode()
        try:
            for _ in range(400):
                await asyncio.sleep(.01)
                if self.closed:
                    return
                yield ('data: '+dumps({'choices': [{'delta': {'content': ' '}}]})+'\n\n').encode()
        finally:
            pass

    async def aclose(self):
        self.closed = True


def transport(captured, generation, *, repair=False):
    async def respond(request):
        body = json.loads(request.content)
        captured.append(body)
        system = body['messages'][0]['content']
        if '证据核对员' in system:
            verdicts = {'verdicts': [{'index': 0, 'status': 'unsupported'}]}
            return httpx.Response(200, json={'choices': [{'message': {'content': dumps(verdicts)}, 'finish_reason': 'stop'}]})
        if '保守修复器' in system:
            data = {'answerable': True, 'quotes': [{'sourceId': 'cite1', 'quoteId': 's1'}]}
            return httpx.Response(200, json={'choices': [{'message': {'content': dumps(data)}, 'finish_reason': 'stop'}]})
        return httpx.Response(200, stream=generation, headers={'Content-Type': 'text/event-stream'})
    return respond


def workflow_request():
    return {'question': '队列是什么？', 'sources': [{**SOURCE}], 'documentIds': [SOURCE['documentId']]}


async def run(tmp_path, *, repair):
    platform = None
    from backend.xueya.platform import Platform
    platform = Platform(tmp_path / 'data')
    try:
        platform.repo.put(platform.scope(), 'source', SOURCE['id'], SOURCE, 0)
        config = Config(api_key='offline-only', early_review=True, early_review_failfast=True,
                        answer_repair_enabled=repair, draft_streaming=False, review_shard_min_claims=4,
                        answer_thinking_disabled=True)
        generation = Generation()
        captured = []
        agent = Agent(MimoProvider(config, platform, httpx.MockTransport(transport(captured, generation, repair=repair))), platform)
        events = []
        async with asyncio.timeout(10):
            async for event in agent.workflow(workflow_request()):
                events.append(event)
        return events, captured, generation, platform
    finally:
        await platform.close()


@pytest.mark.asyncio
async def test_failfast_stops_generation_and_falls_back_without_repair(tmp_path):
    events, captured, generation, _ = await run(tmp_path, repair=False)
    assert any('证据核对员' in body['messages'][0]['content'] for body in captured)
    assert any(body.get('stream') for body in captured)
    assert generation.closed
    done = events[-1]
    assert done['type'] == 'done' and done['answerStatus'] == 'unavailable'
    assert done['reason'] == 'CLAIMS_NEED_REVIEW'
    assert '保守修复器' not in ''.join(body['messages'][0]['content'] for body in captured)


@pytest.mark.asyncio
async def test_failfast_repairs_from_excerpts_instead_of_finishing_generation(tmp_path):
    events, captured, generation, _ = await run(tmp_path, repair=True)
    assert generation.closed
    done = events[-1]
    assert done['type'] == 'done'
    assert done['verification'] == 'repaired-excerpts'
    assert done['answer'] == '队列遵循先进先出。 [1]'
    assert any('保守修复器' in body['messages'][0]['content'] for body in captured)
