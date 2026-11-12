import json
import pytest
from backend.agent.answer_policy import finalize_answer
from backend.xueya.agent import Agent
from backend.xueya.config import Config
from backend.xueya.rag_service import RagService
from test_rag import completed

SOURCE = {'id': 's1', 'quote': 'A stack is last in, first out. Peek reads without removal; pop removes the top.'}
PROSE = 'Imagine putting plates on a pile. The last plate placed is the first removed.\n\nLooking at the top plate leaves it there, whereas taking it off changes the pile.'

class Reviewer:
    def __init__(self, reject_prose=False):
        self.calls = []
        self.reject_prose = reject_prose
    async def prepare(self, claims, signal=None):
        self.calls.append(claims)
    async def __call__(self, claim, signal=None):
        return {'supported': not (self.reject_prose and claim['text'] == PROSE)}

def payload(answer=PROSE):
    return {'answer': answer, 'sources': ['s1'], 'claims': [
        {'text': SOURCE['quote'], 'kind': 'excerpt', 'evidence': [{'sourceId': 's1', 'quoteId': 'q0'}]}]}

@pytest.mark.asyncio
async def test_reviewed_prose_is_delivered_instead_of_claim_list():
    review = Reviewer()
    result = await finalize_answer(json.dumps(payload()), [SOURCE], 'fixture', review=review, narrative=True)
    assert result['answer'] == PROSE + ' [1]'
    assert result['verification'] == 'reviewed-narrative'
    assert len(review.calls) == 1 and review.calls[0][-1]['text'] == PROSE

@pytest.mark.asyncio
async def test_valid_claims_do_not_authorize_unverified_prose():
    result = await finalize_answer(json.dumps(payload()), [SOURCE], 'fixture', review=Reviewer(True), narrative=True)
    # The unverified prose is never published and is not replaced by a
    # mechanical excerpt list; the caller falls back to a natural answer.
    assert result['answerStatus'] == 'unavailable'
    assert result['verification'] == 'not-generated'
    assert PROSE not in result['answer']

@pytest.mark.asyncio
async def test_code_subscripts_survive_narrative_review():
    prose = 'Read arr[1].\n```cpp\nreturn arr[1];\n```'
    result = await finalize_answer(json.dumps(payload(prose)), [SOURCE], 'fixture', review=Reviewer(), narrative=True)
    assert result['answer'] == prose + ' [1]'

@pytest.mark.asyncio
async def test_document_question_sends_mimo_prose_to_sse(platform):
    rag = RagService(platform)
    job = await completed(platform, rag.upload(platform.scope(), '# Stack\n\n栈遵循后进先出，取栈顶只读取而不删除，出栈会删除栈顶。'.encode(), 'stack.md', 'narrative'))
    source = next(s for s in rag.sources(platform.scope()) if s['blockType'] == 'paragraph')
    calls = []
    class Model:
        config = Config(api_key='fixture-only', rag_general_fallback=True)
        async def stream(self, messages, **kwargs):
            calls.append(messages)
            value = payload()
            value['sources'] = [source['id']]
            value['claims'][0] = {'text': source['quote'], 'evidence': [{'sourceId': source['id'], 'quoteId': 'q0'}]}
            yield {'type': 'content', 'text': json.dumps(value)}
        async def generate(self, messages, **kwargs):
            body = json.loads(messages[-1]['content'])
            return {'content': json.dumps({'verdicts': [{'index': i, 'status': 'supported'} for i in range(len(body['claims']))]})}
    agent = Agent(Model(), platform); agent.rag = rag
    events = [e async for e in agent.workflow({'question': '解释栈的顺序和取栈顶与出栈的区别', 'documentIds': [job['result']['documentId']]})]
    final = events[-1]
    assert final['answer'] == PROSE + ' [1]'
    assert json.loads(''.join(e['text'] for e in events if e['type'] == 'content'))['answer'] == final['answer']
    assert final['sources'] == [source['id']]
    assert 'claims只是后台证据核对笔记' in calls[0][0]['content']

@pytest.mark.asyncio
async def test_connection_failure_switches_to_source_free_request_on_fresh_client(platform):
    import httpx
    from backend.xueya.provider import MimoProvider
    from test_rag_general_fallback import course, wire_text
    rag, doc = await course(platform)
    requests = []
    def upstream(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            raise httpx.RemoteProtocolError('controlled disconnect')
        return wire_text('A stack is last in, first out.')
    class Provider(MimoProvider):
        clients = 0
        def new_client(self, timeout):
            self.clients += 1
            return super().new_client(timeout)
    provider = Provider(Config(api_key='fixture-only', rag_general_fallback=True), platform, httpx.MockTransport(upstream))
    agent = Agent(provider, platform); agent.rag = rag
    async with provider.connection_pool():
        final = [e async for e in agent.workflow({'question': '解释栈的操作顺序', 'documentIds': [doc]})][-1]
    assert len(requests) == 2 and provider.clients == 2
    assert final['engine'] == 'general-chat' and final['sources'] == []
    assert requests[0]['messages'] != requests[1]['messages']

@pytest.mark.asyncio
async def test_inline_citations_remain_inline_without_duplicate_trailer():
    prose = 'The top plate leaves first. [1]\n\nLooking at it does not remove it. [1]'
    result = await finalize_answer(json.dumps(payload(prose)), [SOURCE], 'fixture', review=Reviewer(), narrative=True)
    assert result['answer'] == prose

@pytest.mark.asyncio
async def test_prose_cannot_smuggle_unknown_citation():
    from backend.core import DomainError
    with pytest.raises(DomainError):
        await finalize_answer(json.dumps(payload('Unsupported source [99]')), [SOURCE], 'fixture', review=Reviewer(), narrative=True)

@pytest.mark.asyncio
async def test_numeric_course_answer_is_integrated_by_mimo_before_publication(platform):
    from scripts.eval_stack_queue import chapter_sources
    _, parsed, doc, _ = chapter_sources(corrected=True)
    rag = RagService(platform)
    platform.repo.put(platform.scope(), 'document', doc['id'], {**doc, 'contentRevision': 0, 'kind': 'pdf',
        'fileHash': parsed['fileHash'], 'chunks': [], 'originalAvailable': False}, 0)
    with platform.db.transaction():
        rag._publish(platform.scope(), rag.document(platform.scope(), doc['id']), parsed)
    calls = []
    prose = '当前有4个元素，最多能存7个。这里采用保留一个空位的约定，front指向队头前一个位置，rear指向队尾。\n\n把题设代入元素个数公式，得到(2-6+8)%8=4；数组虽然长8，仍须留一个空位区分队空与队满，所以容量为8-1=7。'
    class Model:
        config = Config(api_key='fixture-only')
        async def stream(self, messages, **kwargs):
            calls.append(messages)
            materials = json.loads(messages[-1]['content'])['materials']
            refs = [{'sourceId': m['id'], 'quoteId': 'q0'} for m in materials]
            value = {'answer': prose, 'sources': [m['id'] for m in materials], 'claims': [
                {'text': prose, 'kind': 'inference', 'evidence': refs}]}
            yield {'type': 'content', 'text': json.dumps(value)}
        async def generate(self, messages, **kwargs):
            batch = json.loads(messages[-1]['content'])['claims']
            return {'content': json.dumps({'verdicts': [{'index': i, 'status': 'supported'} for i in range(len(batch))]})}
    agent = Agent(Model(), platform); agent.rag = rag
    final = [e async for e in agent.workflow({'question': '循环队列数组长度为8，front=6，rear=2，有多少元素，最多存几个？', 'documentIds': [doc['id']]})][-1]
    assert len(calls) == 1
    assert '独立核算' in calls[0][0]['content']
    assert final['answer'].startswith(prose)
    assert final['engine'] == 'xiaomi-mimo' and final['verification'] == 'reviewed-narrative'
