"""Offline adversarial checks for the production host's P0 boundaries."""
import asyncio
from contextlib import aclosing
from dataclasses import replace
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from backend.agent.answer_policy import finalize_answer
from backend.xueya.agent import Agent, LEARNING_READ_TOOLS
from backend.xueya.app import create_app
from backend.xueya.common import AppError, dumps
from backend.xueya.config import Config
from backend.xueya.execution_budget import BudgetMiddleware, budget_scope, current_budget
from backend.xueya.gateway import ToolGateway
from backend.xueya.mcp_core import Registry, open_session, obj
from backend.xueya.provider import MimoProvider
from backend.xueya.rag_api import EmbeddingProvider, ApiSettings
from backend.xueya.rag_api import borrowed_api_permit

SOURCE = {'id': 'p0-source', 'title': '队列', 'quote': '队列遵循先进先出。', 'keywords': ['队列']}
FORGED = '没有任何证据的收费操作结论'


def controlled(answer, *, finish='stop', stream_finish=True, tool_calls=None):
    captured = []
    def upstream(request):
        body = json.loads(request.content)
        captured.append(body)
        if body.get('stream'):
            choice = {'delta': {'content': dumps(answer)}}
            frames = ['data: '+dumps({'choices': [choice]})+'\n\n']
            if stream_finish:
                frames.append('data: '+dumps({'choices': [{'delta': {}, 'finish_reason': finish}],
                    'usage': {'total_tokens': 10}})+'\n\n')
                frames.append('data: [DONE]\n\n')
            return httpx.Response(200, text=''.join(frames), headers={'Content-Type': 'text/event-stream'})
        message = {'content': dumps(answer)}
        if tool_calls:
            message['tool_calls'] = tool_calls
        return httpx.Response(200, json={'choices': [{'message': message, 'finish_reason': finish}],
            'usage': {'total_tokens': 10}})
    return httpx.MockTransport(upstream), captured


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('claims', [None, [], [None], [{'text': FORGED, 'evidence': [None]}],
    [{'text': FORGED, 'evidence': [{'sourceId': SOURCE['id'], 'quote': SOURCE['quote']}]}]])
def test_valid_source_id_cannot_publish_unsupported_text(tmp_path, stream, claims):
    answer = {'answer': FORGED, 'sources': [SOURCE['id']], 'knowledgePoints': [FORGED]}
    if claims is not None:
        answer['claims'] = claims
    transport, requests = controlled(answer)
    config = Config(data_dir=tmp_path, platform_enabled=False, api_key='offline-only')
    app = create_app(config, provider=MimoProvider(config, transport=transport))
    with TestClient(app, base_url='http://127.0.0.1') as client:
        response = client.post('/api/ai'+('/stream' if stream else ''), json={'question': '队列', 'sources': [SOURCE]})
        assert response.status_code == 200
        if stream:
            events = [json.loads(frame[6:]) for frame in response.text.split('\n\n') if frame.startswith('data: ')]
            result = events[-1]
            assert result['type'] == 'done'
            # Even provisional streamed content must not leak the unsupported answer.
            assert FORGED not in response.text
            assert any(e['type'] == 'workflow' for e in events)
        else:
            result = response.json()
        assert FORGED not in result['answer']
        assert SOURCE['quote'] in result['answer'] and result['verification'] == 'verbatim-only'
        assert result['knowledgePoints'] == []
        assert len(requests) == 1 and requests[0]['max_completion_tokens'] == 4096


async def test_checked_claims_rebuild_body_and_reject_fabricated_quote():
    claim = {'text': SOURCE['quote'], 'evidence': [{'sourceId': SOURCE['id'], 'quote': SOURCE['quote']}]}
    good = await finalize_answer(dumps({'answer': FORGED, 'sources': [SOURCE['id']], 'claims': [claim],
        'knowledgePoints': {'unexpected': True}}), [SOURCE], 'offline')
    assert FORGED not in good['answer'] and good['verification'] == 'verbatim-only'
    claim['evidence'][0]['quote'] = '伪造原文'
    bad = await finalize_answer(dumps({'answer': FORGED, 'sources': [SOURCE['id']], 'claims': [claim]}), [SOURCE], 'offline')
    assert bad['reason'] == 'INVALID_CLAIM_EVIDENCE' and '伪造原文' not in bad['answer']


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('finish,code', [('length', 'AI_TRUNCATED'), ('tool_calls', 'AI_UNEXPECTED_TOOL_CALL'),
                                      ('content_filter', 'AI_INVALID_RESPONSE')])
async def test_provider_rejects_unusable_completion_and_keeps_usage(platform, stream, finish, code):
    transport, captured = controlled({'answer': FORGED}, finish=finish)
    provider = MimoProvider(Config(api_key='offline-only'), platform, transport)
    with pytest.raises(AppError, match=code):
        if stream:
            async for _ in provider.stream([], scope=platform.scope()):
                pass
        else:
            await provider.generate([], scope=platform.scope())
    row = platform.db.one('SELECT * FROM invocations')
    assert row['status'] == 'failed' and json.loads(row['usage_json'])['total_tokens'] == 10
    context = json.loads(platform.db.one('SELECT value FROM meta WHERE key=?', ('invocation-context:'+row['id'],))['value'])
    assert context['finishReason'] == finish and context['usable'] is False
    assert len(captured) == 1 and platform.resources.active['api'] == 0


async def test_eof_without_completion_is_unknown_and_not_retried(platform):
    transport, captured = controlled({'answer': FORGED}, stream_finish=False)
    provider = MimoProvider(Config(api_key='offline-only'), platform, transport)
    with pytest.raises(AppError, match='AI_INCOMPLETE'):
        async for _ in provider.stream([], scope=platform.scope()):
            pass
    assert len(captured) == 1
    assert platform.db.one('SELECT status FROM invocations')['status'] == 'unknown'


async def test_unexpected_tool_payload_is_never_executed():
    transport, captured = controlled({'answer': 'ignored'}, tool_calls=[{'function': {'name': 'apply_action', 'arguments': '{}'}}])
    with pytest.raises(AppError, match='AI_UNEXPECTED_TOOL_CALL'):
        await MimoProvider(Config(api_key='offline-only'), transport=transport).generate([])
    assert len(captured) == 1


@pytest.mark.parametrize('changes,code', [({'run_model_calls': 1}, 'AI_MODEL_BUDGET_EXCEEDED'),
    ({'run_output_tokens': 4096}, 'AI_OUTPUT_BUDGET_EXCEEDED')])
async def test_parallel_children_cannot_overspend_shared_reservations(changes, code):
    config = replace(Config(api_key='offline-only'), **changes)
    transport, captured = controlled({'answer': 'ok'})
    provider = MimoProvider(config, transport=transport)
    with budget_scope(config) as budget:
        results = await asyncio.gather(provider.generate([]), provider.generate([]), return_exceptions=True)
        assert sum(isinstance(r, dict) for r in results) == 1
        assert any(isinstance(r, AppError) and r.code == code for r in results)
        assert budget.models == 1 and budget.output == 4096
    assert len(captured) == 1 and current_budget.get() is None


@pytest.mark.parametrize('changes,code', [({'run_budget_cny': '1'}, 'AI_PRICING_REQUIRED'),
    ({'run_budget_cny': '.000001', 'input_cny_per_million': '1', 'output_cny_per_million': '1'}, 'AI_COST_BUDGET_EXCEEDED'),
    ({'run_output_tokens': 1}, 'AI_OUTPUT_BUDGET_EXCEEDED')])
async def test_budget_denial_precedes_transport_and_releases_api_slot(platform, changes, code):
    config = replace(Config(api_key='offline-only'), **changes)
    transport, captured = controlled({'answer': 'ok'})
    with budget_scope(config), pytest.raises(AppError, match=code):
        await MimoProvider(config, platform, transport).generate([], scope=platform.scope())
    assert captured == [] and not platform.db.all('SELECT id FROM invocations')
    assert platform.resources.active['api'] == 0


async def test_unknown_call_keeps_reserved_cost_and_has_no_paid_retry(platform):
    captured = []
    def broken(request):
        captured.append(request)
        raise httpx.ReadError('offline ambiguity')
    config = Config(api_key='offline-only', run_budget_cny='.005', input_cny_per_million='1', output_cny_per_million='1')
    provider = MimoProvider(config, platform, httpx.MockTransport(broken))
    with budget_scope(config) as budget:
        with pytest.raises(httpx.ReadError):
            await provider.generate([], scope=platform.scope())
        reserved = budget.money
        with pytest.raises(AppError, match='AI_COST_BUDGET_EXCEEDED'):
            await provider.generate([], scope=platform.scope())
        assert budget.money == reserved
    assert len(captured) == 1 and platform.db.one('SELECT status FROM invocations')['status'] == 'unknown'


async def test_unpriced_rag_cannot_bypass_text_money_limit(platform):
    config = Config(run_budget_cny='1', input_cny_per_million='1', output_cny_per_million='1')
    captured = []
    embedding = EmbeddingProvider(platform, ApiSettings(key='offline', model='embedding'),
        transport=httpx.MockTransport(lambda request: captured.append(request)))
    with budget_scope(config), pytest.raises(AppError, match='AI_PRICING_REQUIRED'):
        await embedding.embed(platform.scope(), ['队列'])
    assert captured == [] and platform.resources.active['api'] == 0


async def test_model_readonly_session_and_tool_budget_preserve_host_write_authority():
    registry, calls = Registry(), []
    registry.add('read_source', obj({'sourceId': {'type': 'string'}}, ['sourceId']),
        lambda args: {'source': {'id': args['sourceId'], 'quote': 'real'}})
    registry.add('apply_action', obj(), lambda args: calls.append('write') or {})
    registry.allowed_tools = LEARNING_READ_TOOLS
    with pytest.raises(AppError, match='TOOL_FORBIDDEN'):
        await registry.call('apply_action', {})
    with budget_scope(Config(run_tool_calls=1)) as budget:
        async with open_session(registry, allowed_tools=LEARNING_READ_TOOLS) as session:
            assert {t['name'] for t in await session.list_tools()} == {'read_source'}
            with pytest.raises(AppError):
                await session.call('apply_action')
            with pytest.raises(AppError, match='INVALID_TOOL_ARGUMENTS'):
                await session.call('read_source', {'sourceId': 's', 'courseId': 'other'})
            assert budget.tools == 0
            await session.call('read_source', {'sourceId': 's'})
            with pytest.raises(AppError, match='AI_TOOL_BUDGET_EXCEEDED'):
                await session.call('read_source', {'sourceId': 's'})
    assert calls == []
    # The authenticated host can still use its existing separate confirmation path.
    registry.allowed_tools = None
    await registry.call('apply_action', {})
    assert calls == ['write']


async def test_http_budget_survives_stream_headers_and_isolated_between_requests():
    config = Config(api_key='offline-only', run_model_calls=1)
    transport, captured = controlled({'answer': 'ok'})
    provider = MimoProvider(config, transport=transport)
    app = FastAPI()
    app.add_middleware(BudgetMiddleware, config=config)
    @app.get('/api/probe')
    async def probe():
        async def chunks():
            await provider.generate([])
            yield 'first\n'
            try:
                await provider.generate([])
            except AppError as error:
                yield error.code
        return StreamingResponse(chunks())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
        responses = await asyncio.gather(client.get('/api/probe'), client.get('/api/probe'))
    assert all(r.text == 'first\nAI_MODEL_BUDGET_EXCEEDED' for r in responses)
    assert len(captured) == 2


@pytest.mark.parametrize('stream', [False, True])
async def test_source_revision_change_even_with_same_quote_blocks_publication(platform, stream):
    p, scope = platform, platform.scope()
    p.repo.put(scope, 'source', SOURCE['id'], SOURCE, 0)
    config = Config(api_key='offline-only')
    def upstream(request):
        row = p.repo.read(scope, 'source', SOURCE['id'])
        p.repo.put(scope, 'source', SOURCE['id'], {**row['value'], 'revisionNote': 'changed'}, row['version'])
        transport, _ = controlled({'answer': SOURCE['quote'], 'sources': [SOURCE['id']]})
        return transport.handle_request(request)
    agent = Agent(MimoProvider(config, p, httpx.MockTransport(upstream)), p)
    with pytest.raises(AppError, match='STALE_EVIDENCE'):
        async with aclosing(agent.direct({'question': '队列', 'sources': [SOURCE]}, stream=stream)) as events:
            async for event in events:
                assert event['type'] != 'done'


@pytest.mark.parametrize('changes', [{'run_model_calls': 0}, {'run_timeout': float('nan')},
    {'run_budget_cny': 'NaN'}, {'input_cny_per_million': '-1'}])
def test_invalid_host_budget_configuration_fails_closed(changes):
    with pytest.raises(AppError, match='AI_INVALID_BUDGET_CONFIG'):
        replace(Config(), **changes)


async def test_real_background_job_shares_one_budget_and_existing_api_permit(platform):
    config = Config(api_key='offline-only', run_model_calls=1)
    transport, captured = controlled({'answer': 'ok'})
    provider = MimoProvider(config, platform, transport)
    platform.jobs.budget_config = config
    async def handler(scope, value, **callbacks):
        with borrowed_api_permit(platform):
            await provider.generate([], scope=scope)
            await provider.generate([], scope=scope)
    platform.jobs.register('p0-probe', handler)
    job = platform.jobs.submit(platform.user_id, {'type': 'p0-probe', 'courseId': 'course-default',
        'resource': 'api', 'maxAttempts': 1, 'idempotencyKey': 'p0-budget'})
    platform.jobs.start()
    try:
        for _ in range(100):
            result = platform.jobs.get(job['id'], platform.user_id)
            if result['status'] in ('failed', 'unknown'):
                break
            await asyncio.sleep(.02)
        assert result['error'] == 'AI_MODEL_BUDGET_EXCEEDED'
        assert len(captured) == 1
        await asyncio.sleep(.15)
        assert len(captured) == 1 and result['attempts'] == 1
        row = platform.db.one('SELECT id FROM invocations')
        context = json.loads(platform.db.one('SELECT value FROM meta WHERE key=?', ('invocation-context:'+row['id'],))['value'])
        assert context['jobId'] == job['id']
    finally:
        await platform.jobs.stop()
    assert platform.resources.active['api'] == 0


@pytest.mark.parametrize('stream', [False, True])
async def test_provider_reported_output_overrun_is_unusable(platform, stream):
    def upstream(request):
        payload = {'choices': [{'message': {'content': 'ok'}, 'delta': {'content': 'ok'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 4097}}
        if stream:
            return httpx.Response(200, text='data: '+dumps(payload)+'\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json=payload)
    provider = MimoProvider(Config(api_key='offline-only'), platform, httpx.MockTransport(upstream))
    with pytest.raises(AppError, match='AI_OUTPUT_BUDGET_EXCEEDED'):
        if stream:
            async for _ in provider.stream([], scope=platform.scope()):
                pass
        else:
            await provider.generate([], scope=platform.scope())
    row = platform.db.one('SELECT * FROM invocations')
    assert row['status'] == 'failed' and json.loads(row['usage_json'])['completion_tokens'] == 4097
    assert platform.resources.active['api'] == 0


@pytest.mark.parametrize('kind', ['session', 'gateway'])
async def test_deadline_after_reserving_tool_slot_does_not_leak_it(kind):
    def expire_after_reservation(budget):
        checks = 0
        def remaining():
            nonlocal checks
            checks += 1
            if checks > 1:
                raise AppError('AI_RUN_TIMEOUT')
            return 1
        budget.remaining = remaining
    with budget_scope() as budget:
        if kind == 'session':
            registry = Registry()
            registry.add('safe', obj(), lambda _: {})
            async with open_session(registry) as session:
                expire_after_reservation(budget)
                with pytest.raises(AppError, match='AI_RUN_TIMEOUT'):
                    await session.call('safe')
                await session.close()
                assert session.limiter.active == 0
        else:
            gateway = ToolGateway()
            async def safe(args):
                return {'content': []}
            gateway.register({'name': 'safe', 'risk': 'read'}, safe)
            expire_after_reservation(budget)
            with pytest.raises(AppError, match='AI_RUN_TIMEOUT'):
                await gateway.call_tool('safe')
            await asyncio.gather(*list(gateway.pending), return_exceptions=True)
            assert gateway.limiter.active == 0
