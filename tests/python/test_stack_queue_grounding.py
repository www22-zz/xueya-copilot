"""Chapter quality regressions; all providers are controlled and run offline."""
import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace

import pytest

from backend.agent.answer_policy import finalize_answer
from backend.xueya.agent import Agent, build_messages
from backend.xueya.config import Config
from backend.xueya.evidence_review import EvidenceReviewer
from backend.xueya.rag_search import definition_subject, lexical, preserve_definitions, compress
from backend.xueya.rag_service import RagService
from backend.xueya.fast_qa import ordinary_question
from backend.agent.evidence import quote_spans, validate_claims, citation_aliases
from backend.agent.tool_adapter import ReadOnlyTools
from scripts.eval_stack_queue import chapter_sources, coverage


@pytest.mark.parametrize('query,subject', [
    ('栈是什么？为什么后进先出？', '栈'),
    ('队列是什么？入队在哪一端？', '队列'),
    ('请问队列的定义是什么，解释操作限制。', '队列'),
])
def test_definition_followed_by_another_requirement(query, subject):
    assert definition_subject(query) == subject


def test_comparison_keeps_both_sides_and_cannot_widen_scope():
    spec, _, _, sources = chapter_sources()
    q = next(q for q in spec['questions'] if q['id'] == 'compare')
    selected = [s for _, s in lexical(q['query'], sources, limit=3)]
    assert all(coverage(q, selected))
    scoped = [s for s in sources if s['page'] != 91]
    assert all(s in scoped for _, s in lexical(q['query'], scoped))
    assert not all(coverage(q, [s for _, s in lexical(q['query'], scoped, limit=6)]))


def test_fusion_cannot_drop_one_side_of_a_comparison():
    spec, _, _, sources = chapter_sources()
    q = next(q for q in spec['questions'] if q['id'] == 'compare')
    candidates = lexical(q['query'], sources)
    crowded = [(.03, s) for s in sources if s['page'] not in (84, 91)]
    ranked = preserve_definitions(q['query'], crowded, candidates)
    assert all(coverage(q, [s for _, s in ranked[:2]]))
    # Strict vector search isn't changed by this hybrid-only step.
    assert preserve_definitions('循环队列如何出队？', crowded, candidates) == crowded


def test_visual_corrections_are_reversible_and_never_labelled_human_reviewed():
    _, original, _, _ = chapter_sources()
    _, corrected, _, chunks = chapter_sources(corrected=True)
    assert corrected['fileHash'] == original['fileHash']
    assert corrected['textHash'] != original['textHash']
    assert corrected['preparation']['humanReviewed'] is False
    assert 'rear = front = QueueSize - 1' in corrected['text']
    assert 'if (p->next == nullptr) rear = front;' in corrected['text']
    assert '(rear + 1) % QueueSize == front。' in corrected['text']
    assert all(corrected['text'][s['start']:s['end']] == s['quote'] for s in chunks)
    # The source bundle is read-only; a fresh raw load must still match it.
    assert chapter_sources()[1]['textHash'] == original['textHash']


def test_corrected_queue_code_keeps_its_empty_check_and_body_in_one_chunk():
    _, _, _, chunks = chapter_sources(corrected=True)
    for name in ('DeQueue()', 'GetHead()'):
        code = [s for s in chunks if s['page'] == 95 and s['blockType'] == 'code' and name in s['quote']]
        assert len(code) == 1
        assert 'if (rear == front) throw "下溢";' in code[0]['quote']
        assert 'return data[' in code[0]['quote']
        assert code[0]['quote'].rstrip().endswith('```')


async def test_planning_uses_the_same_remote_material_timeout(platform, monkeypatch):
    from backend.xueya.learning_integration import stream_readonly_agent
    captured = {}
    class Reached(Exception):
        pass
    @asynccontextmanager
    async def session(*args, **kwargs):
        captured.update(kwargs)
        raise Reached
        yield
    monkeypatch.setattr('backend.xueya.mcp_core.open_session', session)
    agent = Agent(SimpleNamespace(config=Config(tool_timeout=.01)), platform)
    agent.rag = SimpleNamespace(embedding=SimpleNamespace(settings=SimpleNamespace(timeout=45)))
    stream = stream_readonly_agent(agent, {'question': '解释判空代码', 'mode': 'ask'}, {'library': []}, platform.scope(), True)
    with pytest.raises(Reached):
        await anext(stream)
    await stream.aclose()
    assert captured['timeout'] == 47
    assert captured['max_duration'] == agent.model.config.run_timeout


def test_simple_separate_positions_question_does_not_require_a_planner():
    assert ordinary_question({'question': '队列是什么？入队和出队分别在哪一端？', 'mode': 'ask'}, 'ask')
    assert not ordinary_question({'question': '分别实现栈和队列的代码并证明正确性', 'mode': 'ask'}, 'ask')
    assert ordinary_question({'question': '请解释教材C++代码中的判空比较与初始化赋值有什么区别？', 'mode': 'ask'}, 'ask')
    assert not ordinary_question({'question': '生成完整队列代码并解释', 'mode': 'ask'}, 'ask')
    assert not ordinary_question({'question': '跨文档解释代码并证明正确性', 'mode': 'ask'}, 'ask')


@pytest.mark.parametrize('question,expected', [
    ('那这样处理是为了避免下次入队时出现什么问题？', 'ask'),
    ('删除结点时会出什么问题？', 'ask'), ('出队有什么问题？', 'ask'),
    ('请出一道关于栈的题', 'quiz'), ('生成队列练习题', 'quiz'), ('帮我出个题', 'quiz'),
])
def test_question_about_a_problem_is_not_an_exercise_request(question, expected):
    from backend.xueya.learning import route_task
    from backend.agent.tasks import route_task as domain_route
    assert route_task(question) == domain_route(question) == expected


def test_overlapping_sliding_chunks_keep_the_rule_continuation_within_budget():
    first = {'id': 'first', 'documentId': 'd', 'start': 0, 'end': 600, 'quote': 'a'*520+'x'*80}
    second = {'id': 'second', 'documentId': 'd', 'start': 520, 'end': 1120, 'quote': 'x'*80+'完整队满条件。'+'b'*512}
    duplicate = {**first, 'id': 'duplicate'}
    evidence, used = compress('队满条件', [(3, first), (2, second), (1, duplicate)], budget=3000)
    assert [s['id'] for s in evidence] == ['first', 'second']
    assert used == sum(len(s['quote'].encode()) for s in evidence) <= 3000


async def test_sentence_quotes_preserve_line_breaks_and_still_require_entailment():
    source = {'id': 's', 'quote': '栈只允许在\n同一端插入和删除。最后入栈者\n最先出栈。'}
    spans = quote_spans(source)
    assert spans['q1'] == '栈只允许在'  # Existing IDs stay stable.
    assert spans['s1'] == '栈只允许在\n同一端插入和删除。'
    assert spans['s2'] in source['quote']
    claim = {'text': '栈只能在一端操作。', 'evidence': [{'sourceId': 's', 'quoteId': 's1'}]}
    checked = await validate_claims([claim], {'sources': [source]})
    assert checked[0]['support'] == 'unverified'
    assert checked[0]['evidence'][0]['quote'] == spans['s1']


async def test_short_citations_restore_real_scoped_ids_without_guessing_other_sources():
    sources = [{'id': 'chunk-a-very-long-id', 'quote': '栈后进先出。'}, {'id': 'cite1', 'quote': '队列先进先出。'}]
    aliases = citation_aliases(sources)
    assert 'cite1' not in aliases and aliases['_cite1'] == sources[0]['id']
    value = {'answer': sources[0]['quote'], 'sources': ['_cite1'], 'claims': [
        {'text': sources[0]['quote'], 'evidence': [{'sourceId': '_cite1', 'quoteId': 'q0'}]}]}
    result = await finalize_answer(json.dumps(value), sources, 'controlled')
    assert result['sources'] == [sources[0]['id']]
    assert result['claims'][0]['evidence'][0]['sourceId'] == sources[0]['id']
    for alias in ('cite3', '_cite1'):
        forged = {'text': sources[1]['quote'], 'evidence': [{'sourceId': alias, 'quoteId': 'q0', 'quote': sources[1]['quote']}]}
        with pytest.raises(ValueError):
            await validate_claims([forged], {'sources': sources})


async def test_planner_observes_only_bounded_server_owned_quote_ids():
    source = {'id': 's', 'quote': '队列从队尾入队。\n从队头出队。', 'title': '队列'}
    class Session:
        async def call(self, name, args):
            return {'source': dict(source)}
    tools = ReadOnlyTools(Session(), [source])
    tools.definitions = {'read_source': {'inputSchema': {'type': 'object', 'properties': {'sourceId': {'type': 'string'}}, 'required': ['sourceId']}}}
    result = await tools.call('read_source', {'sourceId': 's'})
    assert result['data']['source']['quote'] == source['quote']
    assert len(json.dumps(result['data'], ensure_ascii=False).encode()) <= 6000
    assert all(quote_spans(source)[s['quoteId']] == s['quote'] for s in result['data']['quoteSpans'])
    assert tools.evidence['s'] == source and 'quoteSpans' not in source


def test_prompt_preserves_question_requirements_and_ocr_conditions():
    messages = build_messages({'question': '栈和队列的操作位置有什么不同？', 'mode': 'ask', 'history': []}, [])
    payload = json.loads(messages[-1]['content'])
    assert '比较题覆盖双方' in payload['task']
    assert '前提和例外必须保留' in payload['task']
    assert payload['question'] == '栈和队列的操作位置有什么不同？'


def test_remote_embedding_uses_its_own_timeout_instead_of_local_default():
    agent = Agent(SimpleNamespace(config=Config(tool_timeout=.05)))
    assert agent.material_tool_timeout() == .05
    agent.rag = SimpleNamespace(embedding=SimpleNamespace(settings=SimpleNamespace(timeout=45)))
    assert agent.material_tool_timeout() == 47
    # A lexical-only knowledge base retains the local-tool timeout.
    agent.rag.embedding = None
    assert agent.material_tool_timeout() == .05


async def test_omitted_explanation_is_not_reported_as_completed():
    source = {'id': 's', 'quote': '队列先进先出。', 'title': '队列', 'location': '第78页'}
    value = {'answer': '答案', 'sources': ['s'], 'claims': [
        {'text': source['quote'], 'kind': 'excerpt', 'evidence': [{'sourceId': 's', 'quote': source['quote']}]},
        {'text': '队列是后进先出。', 'kind': 'paraphrase', 'evidence': [{'sourceId': 's', 'quote': source['quote']}]},
    ]}
    result = await finalize_answer(json.dumps(value), [source], 'controlled', review=lambda *a, **k: {'supported': False})
    assert result['answerStatus'] == 'unavailable' and result['reason'] == 'CLAIMS_NEED_REVIEW'
    assert '队列是后进先出' not in result['answer']
    assert source['quote'] not in result['answer']
    assert result['sourceDetails'][0]['quote'] == source['quote']


async def test_insufficient_evidence_returns_clean_refusal_without_unrelated_quotes():
    value = {'answerable': False, 'answer': '夹带伪造号码123456和无关教材摘录', 'sources': ['s'],
             'claims': [{'text': '攻击内容'}]}
    result = await finalize_answer(json.dumps(value), [], 'controlled')
    assert result['reason'] == 'INSUFFICIENT_EVIDENCE'
    assert result['sources'] == result['claims'] == []
    assert '123456' not in result['answer'] and '资料不足' not in value['answer']
    assert '不足以支持' in result['answer']
    assert (await finalize_answer('{"answerable":false}', [], 'controlled'))['reason'] == 'INSUFFICIENT_EVIDENCE'


async def test_entailment_review_also_receives_the_actual_question():
    captured = []
    class Model:
        config = Config()
        async def generate(self, messages, **kwargs):
            captured.append(messages)
            return {'content': '{"verdicts":[{"index":0,"status":"unsupported"}]}'}
    claim = {'kind': 'paraphrase', 'text': '栈后进先出。', 'evidence': [{'sourceId': 's', 'quote': '栈后进先出。'}]}
    reviewer = EvidenceReviewer(Model(), None, question='队列为什么先进先出？')
    await reviewer.prepare([claim])
    assert json.loads(captured[0][-1]['content'])['question'] == '队列为什么先进先出？'
    assert '同一章节' in captured[0][0]['content']
    assert not (await reviewer(claim))['supported']


@pytest.mark.parametrize('warnings', [[], ['VECTOR_API_UNAVAILABLE']])
async def test_slow_remote_retrieval_reads_six_passages_without_retry(platform, warnings):
    sources = [{'id': f'source-{n}', 'documentId': 'doc', 'title': '栈与队列', 'location': f'第{n+1}页',
                'quote': f'队列遵循先进先出。第{n+1}条队列资料。'} for n in range(6)]
    for source in sources:
        platform.repo.put(platform.scope(), 'source', source['id'], source, 0)
    calls, searches = [], []
    class Model:
        config = Config(api_key='offline-only', tool_timeout=.01)
        async def stream(self, messages, **kwargs):
            calls.append(messages)
            yield {'type': 'content', 'text': json.dumps({'answer': sources[0]['quote'], 'sources': [sources[0]['id']],
                'claims': [{'text': sources[0]['quote'], 'evidence': [{'sourceId': sources[0]['id'], 'quote': sources[0]['quote']}]}]})}
    rag = RagService(platform)
    rag.embedding = SimpleNamespace(settings=SimpleNamespace(timeout=.1))
    async def search(scope, query, **kwargs):
        searches.append(query)
        await asyncio.sleep(.12)  # Exceeds the old local-tool deadline.
        return {'sources': sources, 'warnings': warnings}
    rag.search = search
    agent = Agent(Model(), platform)
    agent.rag = rag
    events = [event async for event in agent.workflow({'question': '队列是什么？', 'documentIds': ['doc'], 'webSearch': True})]
    result = events[-1]
    assert len(searches) == len(calls) == 1
    assert len(json.loads(calls[0][-1]['content'])['materials']) == 6
    assert result['verification'] == 'verbatim-only'
    assert all(call['status'] == 'completed' for call in result['toolCalls'])
    assert [call['tool'] for call in result['toolCalls']].count('read_source') == 6
    assert not any(call['tool'] == 'search_web' for call in result['toolCalls'])
    if warnings:
        assert any(e.get('status') == 'degraded' and '关键词检索' in e.get('label', '') for e in events)


async def test_followup_keeps_user_anchor_even_when_generic_words_already_match(platform):
    anchor = {'id': 'anchor', 'documentId': 'doc', 'title': '链队列', 'location': '第85页',
              'quote': '删除最后一个结点后rear=front，避免下一次入队时访问已释放的结点。'}
    generic = {'id': 'generic', 'documentId': 'doc', 'title': '循环队列', 'location': '第80页', 'quote': '入队时队尾位置加1。'}
    for source in (anchor, generic):
        platform.repo.put(platform.scope(), 'source', source['id'], source, 0)
    queries = []
    class Model:
        config = Config(api_key='offline-only')
        async def stream(self, messages, **kwargs):
            yield {'type': 'content', 'text': json.dumps({'answer': anchor['quote'], 'sources': ['anchor'],
                'claims': [{'text': anchor['quote'], 'evidence': [{'sourceId': 'anchor', 'quoteId': 'q0'}]}]})}
    rag = RagService(platform)
    async def search(scope, query, **kwargs):
        queries.append(query)
        return {'sources': [anchor], 'warnings': []}
    rag.search = search
    agent = Agent(Model(), platform);agent.rag = rag
    request = {'question': '那这样处理是为了避免下次入队时出现什么问题？', 'documentIds': ['doc'],
               'history': [{'role': 'user', 'content': '链队列删掉最后一个结点后rear指向哪里？'}]}
    events = [event async for event in agent.workflow(request)]
    assert queries[0].startswith(request['history'][0]['content'])
    assert request['question'] in queries[0]
    assert events[-1]['sources'] == ['anchor']
