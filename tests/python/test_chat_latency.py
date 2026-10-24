"""Keep chat fast without bypassing evidence checks or leaking connections."""
import asyncio
import json
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
import httpx
import pytest

from backend.xueya.agent import Agent
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.common import AppError
from backend.xueya.learning import SOURCES
from backend.xueya.provider import MimoProvider
from conftest import live_server


@pytest.mark.parametrize('disconnect', [asyncio.CancelledError, OSError])
async def test_stream_disconnect_closes_real_mcp_in_the_stream_task(disconnect):
    from backend.xueya.agent import normalize_context
    from backend.xueya.app import ClosingStreamingResponse
    from backend.xueya.mcp_core import CONNECTIONS, open_session

    before = CONNECTIONS.active
    owner = asyncio.current_task()
    closed = []

    async def events():
        try:
            async with open_session(context=normalize_context({'library': SOURCES})) as session:
                await session.call('search_materials', {'query': '队列', 'limit': 1})
                yield b'data: pending\n\n'
        finally:
            closed.append(asyncio.current_task())

    async def disconnected_send(message):
        if message['type'] == 'http.response.body':
            raise disconnect()

    response = ClosingStreamingResponse(events())
    with pytest.raises(disconnect):
        await response.stream_response(disconnected_send)
    assert closed == [owner]
    assert CONNECTIONS.active == before


async def test_closing_general_followup_immediately_releases_provider(platform):
    closed = []

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            await asyncio.Event().wait()

        async def aclose(self):
            closed.append(True)

    config = Config(api_key='offline-only')
    provider = MimoProvider(config, platform, httpx.MockTransport(lambda request: httpx.Response(200, stream=Body())))
    events = Agent(provider, platform).workflow({'question': '把代码块里的 name 改成小明',
        'previousAnswerKind': 'general', 'history': [{'role': 'assistant', 'content': '```json\n{"name":"张三"}\n```'}]})
    try:
        async for event in events:
            if event['type'] == 'content':
                break
    finally:
        await events.aclose()
    assert closed == [True]
    assert platform.resources.stats()['active']['api'] == 0


@pytest.mark.parametrize('question,grounded', [('今天星期几', False), ('二叉搜索树的查找复杂度', True)])
def test_browser_library_uses_scoped_mcp_without_starting_process(monkeypatch, question, grounded):
    def no_subprocess(*args, **kwargs):
        pytest.fail('Chat must not cold-start a stdio server')

    monkeypatch.setattr('backend.xueya.mcp_core.StdioServerParameters', no_subprocess)

    class Model:
        config = SimpleNamespace(model='controlled')

        async def stream(self, messages, **options):
            assert options.get('thinking') == {'type': 'disabled'}
            if '本次为通用问答' in messages[0]['content']:
                yield {'type': 'content', 'text': '星期五。', 'model': 'controlled'}
                return
            else:
                materials = json.loads(messages[-1]['content'])['materials']
                answer = {'answer': materials[0]['quote'], 'sources': [materials[0]['id']]}
            yield {'type': 'content', 'text': json.dumps(answer), 'model': 'controlled'}

    async def run():
        return [e async for e in Agent(Model()).workflow({'question': question, 'context': {'library': SOURCES}})]

    events = asyncio.run(run())
    assert not any(e.get('status') == 'degraded' for e in events)
    assert any(e.get('stage') == 'retrieve' for e in events)
    assert bool(events[-1]['sources']) is grounded
    assert events[-1]['engine'] == ('xiaomi-mimo' if grounded else 'general-chat')


def test_host_reuses_real_upstream_connection_and_closes_pool(tmp_path):
    upstream = FastAPI()
    peers = []

    @upstream.post('/chat/completions')
    async def completion(request: Request):
        peers.append(request.client.port)
        return StreamingResponse(iter(['data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n',
                                       'data: [DONE]\n\n']), media_type='text/event-stream')

    with live_server(upstream) as base:
        config = Config(data_dir=tmp_path, base_url=base, api_key='offline-only')
        provider = MimoProvider(config)
        with TestClient(create_app(config, provider=provider), base_url='http://127.0.0.1') as client:
            shared = provider._shared_client
            assert shared is not None and not shared.is_closed
            for _ in range(2):
                assert client.post('/api/agent', json={'question': '今天星期几'}).json()['answer'] == 'ok'
                assert provider._shared_client is shared and not shared.is_closed
        assert shared.is_closed and provider._shared_client is None
    assert len(peers) == 2 and peers[0] == peers[1]


def test_pooled_calls_keep_individual_timeout_and_survive_failed_response():
    requests = []

    def upstream(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503)
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n')

    provider = MimoProvider(Config(api_key='offline-only'), transport=httpx.MockTransport(upstream))

    async def run():
        async with provider.connection_pool():
            with pytest.raises(AppError, match='AI_UNAVAILABLE'):
                _ = [e async for e in provider.stream([], timeout=2)]
            result = [e async for e in provider.stream([], timeout=7)]
            assert result[0]['text'] == 'ok'
            assert not provider._shared_client.is_closed
        assert provider._shared_client is None

    asyncio.run(run())
    assert requests[0].extensions['timeout']['read'] == 2
    assert requests[1].extensions['timeout']['read'] == 7


def test_pooled_cancelled_stream_releases_permit_and_allows_next_request(platform):
    async def run():
        ready = asyncio.Event()
        closed = asyncio.Event()
        calls = []

        class Blocked(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
                ready.set()
                await asyncio.Event().wait()

            async def aclose(self):
                closed.set()

        def upstream(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(200, stream=Blocked())
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n')

        provider = MimoProvider(Config(api_key='offline-only'), platform, httpx.MockTransport(upstream))

        async def consume():
            return [e async for e in provider.stream([], scope=platform.scope())]

        async with provider.connection_pool():
            task = asyncio.create_task(consume())
            await asyncio.wait_for(ready.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert closed.is_set()
            assert platform.resources.stats()['active']['api'] == 0
            assert (await consume())[0]['text'] == 'ok'
        assert len(calls) == 2

    asyncio.run(run())


def test_pooled_stream_consumes_body_but_ignores_content_after_done():
    class Tail(httpx.AsyncByteStream):
        drained = False

        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
            yield b'data: {"choices":[{"delta":{"content":"untrusted-tail"}}]}\n\n'
            self.drained = True

    tail = Tail()
    provider = MimoProvider(Config(api_key='offline-only'), transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=tail)))

    async def run():
        async with provider.connection_pool():
            events = [e async for e in provider.stream([])]
            assert tail.drained
            assert [e['text'] for e in events] == ['ok']

    asyncio.run(run())
