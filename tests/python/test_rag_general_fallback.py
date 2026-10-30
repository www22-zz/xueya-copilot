import asyncio
import json

import httpx
import pytest

from backend.xueya.agent import Agent
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider
from backend.xueya.rag_fallback import PREFIX, eligible
from backend.xueya.rag_service import RagService
from test_rag import completed


async def course(platform):
    rag = RagService(platform)
    done = await completed(platform, rag.upload(platform.scope(),
        '# 栈\n\n栈只在栈顶插入和删除，遵循后进先出。'.encode(), 'stack.md', 'stack'))
    return rag, done['result']['documentId']


def wire_text(text):
    return httpx.Response(200, text='data: '+json.dumps({'choices': [{'delta': {'content': text}, 'finish_reason': 'stop'}]})+'\n\ndata: [DONE]\n\n')


@pytest.mark.asyncio
async def test_missing_knowledge_switches_once_without_sending_course_evidence(platform):
    rag, doc = await course(platform)
    captured = []
    class Model:
        config = Config(api_key='fixture-only', rag_general_fallback=True)
        async def stream(self, messages, **options):
            captured.append((messages, options))
            yield {'type': 'content', 'text': '哈希冲突是不同键映射到同一位置。', 'model': 'fixture'}
    agent = Agent(Model(), platform);agent.rag = rag
    events = [e async for e in agent.workflow({'question': '哈希冲突是什么？', 'documentIds': [doc]})]
    final = events[-1]
    assert final['engine'] == 'general-chat' and final['answerStatus'] == 'answered'
    assert final['answer'].startswith(PREFIX) and final['fallback']['reason'] == 'NO_RELEVANT_KNOWLEDGE'
    assert final['sources'] == final['sourceObjects'] == final['sourceDetails'] == []
    assert final['verification'] == 'general-knowledge-not-course-verified'
    assert len(captured) == 1 and captured[0][1]['timeout'] == 90
    assert 'materials' not in captured[0][0][-1]['content']
    assert '栈只在栈顶' not in json.dumps(captured[0][0], ensure_ascii=False)
    assert not platform.db.one('SELECT id FROM invocations')  # Controlled model, not a paid call.


@pytest.mark.asyncio
async def test_model_invented_quote_id_cannot_become_a_course_citation(platform):
    rag, doc = await course(platform)
    source = next(s for s in rag.sources(platform.scope()) if s['blockType'] == 'paragraph')
    calls = []
    class Model:
        config = Config(api_key='fixture-only', rag_general_fallback=True)
        async def stream(self, messages, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                yield {'type': 'content', 'text': json.dumps({'answer': '伪造解释', 'sources': [source['id']],
                    'claims': [{'text': '不受引文支持的解释。', 'evidence': [{'sourceId': source['id'], 'quoteId': 'invented'}]}]})}
            else:
                yield {'type': 'content', 'text': '栈是后进先出的结构。'}
    agent = Agent(Model(), platform);agent.rag = rag
    final = [e async for e in agent.workflow({'question': '解释栈的操作顺序。', 'documentIds': [doc]})][-1]
    assert len(calls) == 2 and final['fallback']['reason'] == 'INVALID_CLAIM_EVIDENCE'
    assert final['sources'] == final['sourceDetails'] == [] and '伪造解释' not in final['answer']


@pytest.mark.asyncio
async def test_rejected_claims_reset_earlier_excerpt_and_do_not_relabel_it_as_general(platform):
    rag, doc = await course(platform)
    source = next(s for s in rag.sources(platform.scope()) if s['blockType'] == 'paragraph')
    calls = []
    class Model:
        config = Config(api_key='fixture-only', rag_general_fallback=True)
        async def stream(self, messages, **options):
            calls.append(messages)
            if len(calls) == 1:
                value = {'answer': '错误结论', 'sources': [source['id']], 'claims': [
                    {'text': source['quote'], 'kind': 'excerpt', 'evidence': [{'sourceId': source['id'], 'quoteId': 'q0'}]},
                    {'text': '栈按先进先出处理。', 'kind': 'paraphrase', 'evidence': [{'sourceId': source['id'], 'quoteId': 'q0'}]}]}
                yield {'type': 'content', 'text': json.dumps(value)}
            else:
                yield {'type': 'content', 'text': '栈的入栈和出栈都在同一端，顺序是后进先出。'}
        async def generate(self, *args, **kwargs):
            return {'content': '{"verdicts":[{"index":0,"status":"unsupported"}]}'}
    agent = Agent(Model(), platform);agent.rag = rag
    events = [e async for e in agent.workflow({'question': '解释栈的操作顺序。', 'documentIds': [doc]})]
    resets = [i for i,e in enumerate(events) if e.get('resetAnswer')]
    assert resets  # Course prose stays private until the complete narrative passes review.
    wrapped = ''.join(e['text'] for e in events[resets[-1]+1:] if e['type'] == 'content')
    final = events[-1]
    assert json.loads(wrapped)['answer'] == final['answer']
    assert final['sources'] == final['sourceDetails'] == final['claims'] == []
    assert final['fallback']['reason'] == 'CLAIMS_NEED_REVIEW' and len(calls) == 2
    assert source['quote'] not in calls[-1][-1]['content']


@pytest.mark.asyncio
@pytest.mark.parametrize('fallback_also_fails', [False, True])
async def test_timeout_uses_one_different_request_and_preserves_unknown_ledger(platform, fallback_also_fails):
    rag, doc = await course(platform)
    requests = []
    def upstream(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1 or fallback_also_fails:
            raise httpx.ReadTimeout('controlled upstream timeout')
        return wire_text('可以把栈理解为只能从顶部取放的盘子。')
    provider = MimoProvider(Config(api_key='fixture-only', rag_general_fallback=True), platform, httpx.MockTransport(upstream))
    agent = Agent(provider, platform);agent.rag = rag
    events = [e async for e in agent.workflow({'question': '解释栈的操作顺序。', 'documentIds': [doc]})]
    final = events[-1]
    assert len(requests) == 2 and requests[0] != requests[1]
    assert 'materials' in requests[0]['messages'][-1]['content']
    assert 'materials' not in requests[1]['messages'][-1]['content']
    ledger = platform.db.all('SELECT status,request_hash FROM invocations ORDER BY rowid')
    assert ledger[0]['status'] == 'unknown' and ledger[0]['request_hash'] != ledger[1]['request_hash']
    assert final['fallback']['attempts'] == 1 and final['fallback']['sameRequestReplayed'] is False
    assert final['sources'] == final['sourceDetails'] == []
    assert final['answerStatus'] == ('unavailable' if fallback_also_fails else 'answered')
    assert platform.resources.stats()['active']['api'] == 0


@pytest.mark.asyncio
async def test_fallback_does_not_get_an_extra_budget(platform):
    rag, doc = await course(platform)
    calls = []
    def upstream(request):
        calls.append(request)
        raise httpx.ReadTimeout('controlled timeout')
    provider = MimoProvider(Config(api_key='fixture-only', rag_general_fallback=True, run_model_calls=1),
                            platform, httpx.MockTransport(upstream))
    agent = Agent(provider, platform);agent.rag = rag
    final = [e async for e in agent.workflow({'question': '解释栈的操作顺序。', 'documentIds': [doc]})][-1]
    assert len(calls) == 1 and final['reason'] == 'AI_MODEL_BUDGET_EXCEEDED'
    assert final['answerStatus'] == 'unavailable'
    assert len(platform.db.all('SELECT id FROM invocations')) == 1


@pytest.mark.asyncio
async def test_cancellation_never_starts_autonomous_answer(platform):
    rag, doc = await course(platform)
    calls = []
    class Model:
        config = Config(api_key='fixture-only', rag_general_fallback=True)
        async def stream(self, *args, **kwargs):
            calls.append(1)
            raise asyncio.CancelledError()
            yield
    agent = Agent(Model(), platform);agent.rag = rag
    with pytest.raises(asyncio.CancelledError):
        _ = [e async for e in agent.workflow({'question': '解释栈的操作顺序。', 'documentIds': [doc]})]
    assert calls == [1]


@pytest.mark.parametrize('reason', ['AUTH_REQUIRED', 'COURSE_NOT_FOUND', 'VERSION_CONFLICT', 'STALE_EVIDENCE',
    'AI_COST_BUDGET_EXCEEDED', 'AI_RUN_TIMEOUT', 'AI_MODEL_BUDGET_EXCEEDED', 'AI_REFUSAL'])
def test_permission_budget_and_staleness_do_not_trigger_fallback(reason):
    assert not eligible(Config(api_key='fixture-only', rag_general_fallback=True), {'mode': 'ask'},
                        {'answerStatus': 'unavailable', 'reason': reason})


@pytest.mark.asyncio
async def test_planner_failure_also_uses_same_one_shot_fallback(platform, monkeypatch):
    rag, doc = await course(platform)
    planned = []
    async def planner(*args):
        planned.append(True)
        yield {'type': 'done', 'ok': True, 'answer': '未完成', 'sources': [], 'engine': 'local-workflow',
               'answerStatus': 'unavailable', 'reason': 'AI_ANSWER_MISSING'}
    monkeypatch.setattr('backend.xueya.learning_integration.stream_readonly_agent', planner)
    class Model:
        config = Config(api_key='fixture-only', rag_general_fallback=True)
        async def stream(self, *args, **kwargs):
            yield {'type': 'content', 'text': '以下是通用栈实现思路。'}
    agent = Agent(Model(), platform);agent.rag = rag
    final = [e async for e in agent.workflow({'question': '请根据资料详细分析栈的实现代码。', 'documentIds': [doc]})][-1]
    assert planned and final['fallback']['reason'] == 'AI_ANSWER_MISSING'
    assert final['answerStatus'] == 'answered' and final['sources'] == []


@pytest.mark.asyncio
async def test_successful_grounded_answer_keeps_its_original_citations(platform):
    rag, doc = await course(platform)
    source = next(s for s in rag.sources(platform.scope()) if s['blockType'] == 'paragraph')
    calls = []
    class Model:
        config = Config(api_key='fixture-only', rag_general_fallback=True)
        async def stream(self, *args, **kwargs):
            calls.append(1)
            yield {'type': 'content', 'text': json.dumps({'answer': source['quote'], 'sources': [source['id']],
                'claims': [{'text': source['quote'], 'evidence': [{'sourceId': source['id'], 'quoteId': 'q0'}]}]})}
    agent = Agent(Model(), platform);agent.rag = rag
    final = [e async for e in agent.workflow({'question': '栈是什么？', 'documentIds': [doc]})][-1]
    assert calls == [1] and final['sources'] == [source['id']] and not final.get('fallback')
    assert final['verification'] == 'verbatim-only' and not final['answer'].startswith(PREFIX)
    assert all(rag.validate(platform.scope(), s) for s in final['sourceDetails'])


@pytest.mark.parametrize('path', ['/api/agent', '/api/agent/stream'])
def test_fallback_on_real_host_http_and_sse_contracts(client, path):
    from test_knowledge_base import wait
    uploaded = client.post('/api/platform/knowledge/upload?name=stack.md', headers={
        **client.platform_headers, 'Idempotency-Key': 'stack'}, content='栈在同一端插入删除，后进先出。'.encode()).json()
    assert wait(client, uploaded['job'])['status'] == 'succeeded'
    sent = []
    def upstream(request):
        sent.append(json.loads(request.content))
        if len(sent) == 1:
            raise httpx.ReadTimeout('controlled primary timeout')
        return wire_text('这是不带课程引用的通用解释。')
    provider = MimoProvider(Config(api_key='fixture-only', rag_general_fallback=True), client.platform, httpx.MockTransport(upstream))
    client.app.state.agent = Agent(provider, client.platform)
    client.app.state.agent.rag = client.app.state.rag
    response = client.post(path, json={'question': '解释栈的操作顺序。', 'documentIds': [uploaded['documentId']]})
    assert response.status_code == 200
    if path.endswith('/stream'):
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert any(e.get('resetAnswer') for e in events)
        result = events[-1]
    else:
        result = response.json()
    assert result['engine'] == 'general-chat' and result['fallback']['attempts'] == 1
    assert result['sources'] == result['sourceDetails'] == [] and result['answer'].startswith(PREFIX)
    assert len(sent) == 2 and sent[0] != sent[1]

@pytest.mark.asyncio
@pytest.mark.parametrize('transport_failure', [False, True])
async def test_interrupted_general_preserves_received_prose(platform, transport_failure):
    from backend.core import DomainError
    from backend.xueya.rag_fallback import stream_general_fallback
    class Model:
        config = Config(api_key='fixture-only', rag_general_fallback=True)
        async def stream(self, messages, **options):
            yield {'type': 'content', 'text': 'A stack is last in, first out.'}
            if transport_failure:
                raise httpx.RemoteProtocolError('controlled interruption')
            raise DomainError('AI_INCOMPLETE')
    agent = Agent(Model(), platform)
    request = {'question': 'Explain a stack', 'history': [], 'mode': 'ask'}
    events = [e async for e in stream_general_fallback(agent, request, platform.scope(), {'reason': 'AI_TIMEOUT'})]
    final = events[-1]
    assert final['partial'] is True
    assert 'last in, first out' in final['answer']
    assert final['sources'] == final['claims'] == []
    assert final['answerStatus'] == 'unavailable'
    assert not any(e.get('resetAnswer') for e in events[1:])
