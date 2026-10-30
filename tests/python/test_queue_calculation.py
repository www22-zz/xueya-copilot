"""Independent local checks for the narrowly supported textbook conventions."""
import pytest
from backend.xueya.queue_calculation import answer
from backend.xueya.agent import Agent
from backend.xueya.config import Config
from backend.xueya.rag_service import RagService
from scripts.eval_stack_queue import chapter_sources


RULES = [
    {'id': 'full', 'quote': '可以浪费一个数组元素空间。队满的条件是：(rear + 1) % QueueSize == front。'},
    {'id': 'enqueue', 'quote': 'rear = (rear + 1) % QueueSize;'},
    {'id': 'dequeue', 'quote': 'if (rear == front) throw "下溢"; front = (front + 1) % QueueSize;'},
    {'id': 'head', 'quote': '队头指针指向链队列的头结点。'},
    {'id': 'last', 'quote': 'if (p->next == nullptr) rear = front; delete p;'},
]


def test_all_small_ring_states_against_a_traversal_oracle():
    for size in range(2, 16):
        for front in range(size):
            for rear in range(size):
                result = answer(f'循环队列数组长度为{size}，front={front}，rear={rear}，有多少元素，最多存几个？', RULES)
                assert result is not None
                positions, cursor = [], (front+1) % size
                while cursor != (rear+1) % size:
                    positions.append(cursor);cursor = (cursor+1) % size
                values = result['calculation']
                assert values['count'] == len(positions)
                assert values['full'] == (len(positions) == size-1)
                assert 0 <= values['count'] <= values['capacity'] == size-1


def test_mixed_operations_use_the_actual_values_and_wrap_at_the_boundary():
    question = '数组长度为5的循环队列初始front=rear=4，入队A、B、C，出队一次，入队D、E。给出最后的front、rear和队列内容，判断是否队满。'
    result = answer(question, RULES)
    value = result['calculation']
    assert (value['front'], value['rear'], value['items'], value['full']) == (0, 4, ['B','C','D','E'], True)
    assert [s['item'] for s in value['steps'] if s['operation'] == 'dequeue'] == ['A']
    assert 'B、C、D、E' in result['answer']


@pytest.mark.parametrize('question,rules', [
    ('循环队列数组长度为1，front=0，rear=0，有多少元素？', RULES),
    ('循环队列数组长度为5，front=5，rear=1，有多少元素？', RULES),
    ('循环队列数组长度为5，front=1，rear=0，已满吗？', []),
    ('循环队列数组长度为5，front=1，rear=0，有多少元素？', RULES[:1]),
    ('循环队列采用计数器，不保留空位，数组长度为5，front=1，rear=0，已满吗？', RULES),
    ('循环队列数组长度为5，初始front=rear=4，入队A并删除它。', RULES),
    ('循环队列数组长度为3，初始front=rear=2，出队一次。', RULES),
    ('不带头结点链队列删掉最后一个元素后rear指向哪里？', RULES),
    ('循环队列数组长度为5，front=1，rear=0，队列内容是什么？', RULES),
    ('循环队列数组长度为5，front=1，rear=0，请编写完整实现。', RULES),
    ('带头结点链队列删除最后一个元素后rear指向哪里，为什么？', RULES),
    ('循环队列数组长度为5，front=1，rear=3，入队A后有多少元素？', RULES),
    ('循环队列数组长度为5，front=1，rear=3，出队一次后有多少元素？', RULES),
    ('循环队列数组长度为5，front=1，rear=3，清空后有多少元素？', RULES),
])
def test_missing_proof_other_conventions_and_unknown_operations_do_not_get_guessed(question, rules):
    assert answer(question, rules) is None


@pytest.mark.parametrize('question,expected', [
    ('循环队列数组长度为5，front=1、rear=0，保留一个空位。现在是否已满，还能入队吗？', 'circular-queue'),
    ('按教材循环队列的约定，数组长度为8，front=6、rear=2，现在有多少个元素？最多能存多少个？', 'circular-queue'),
    ('数组长度为5的循环队列初始front=rear=4，入队A、B、C，出队一次，入队D、E。给出最后的front、rear和队列内容，判断是否队满。', 'circular-queue'),
    ('我认为保留一个空位的循环队列，长度为N的数组最多仍能存N个元素。这个理解对吗？', 'symbolic-capacity'),
    ('带头结点链队列删完最后一个元素后，rear应指向哪里？只用一句话回答。', 'last-linked-node'),
])
@pytest.mark.parametrize('revision', [1, 4])
async def test_actual_chapter_evidence_can_answer_without_a_model_or_embedding(platform, question, expected, revision):
    _, parsed, doc, _ = chapter_sources(corrected=True)
    rag = RagService(platform)
    platform.repo.put(platform.scope(), 'document', doc['id'], {**doc, 'contentRevision': 0, 'kind': 'pdf',
        'fileHash': parsed['fileHash'], 'chunks': [], 'originalAvailable': False}, 0)
    for _ in range(revision):
        with platform.db.transaction():
            rag._publish(platform.scope(), rag.document(platform.scope(), doc['id']), parsed)
    class NoExternalModel:
        config = Config()
        async def stream(self, *args, **kwargs):
            raise AssertionError('A supported local calculation must not call a model')
            yield
    agent = Agent(NoExternalModel(), platform);agent.rag = rag
    result = [event async for event in agent.workflow({'question': question, 'documentIds': [doc['id']]})][-1]
    assert result.get('verification') == 'calculated-from-cited-rules', result
    assert result['calculation']['kind'] == expected
    assert result['timings']['modelCalls'] == 0
    assert result['sourceDetails'] and all(s['documentId'] == doc['id'] for s in result['sourceDetails'])


async def test_calculation_does_not_read_beyond_a_narrow_source_selection(platform):
    _, parsed, doc, _ = chapter_sources(corrected=True)
    rag = RagService(platform)
    platform.repo.put(platform.scope(), 'document', doc['id'], {**doc, 'contentRevision': 0, 'kind': 'pdf',
        'fileHash': parsed['fileHash'], 'chunks': [], 'originalAvailable': False}, 0)
    with platform.db.transaction():
        rag._publish(platform.scope(), rag.document(platform.scope(), doc['id']), parsed)
    only = next(s for s in rag.sources(platform.scope()) if '(rear + 1) % QueueSize == front' in s['quote'])
    class Refusal:
        config = Config()
        async def stream(self, *args, **kwargs):
            yield {'type': 'content', 'text': '{"answerable":false}'}
    agent = Agent(Refusal(), platform);agent.rag = rag
    result = [event async for event in agent.workflow({'question': '循环队列数组长度为8，front=6，rear=2，有多少元素？',
        'sources': [only]})][-1]
    assert result.get('verification') != 'calculated-from-cited-rules'


async def test_host_only_rule_sources_are_not_forwarded_to_the_planner(platform, monkeypatch):
    _, parsed, doc, _ = chapter_sources(corrected=True)
    rag = RagService(platform)
    platform.repo.put(platform.scope(), 'document', doc['id'], {**doc, 'contentRevision': 0, 'kind': 'pdf',
        'fileHash': parsed['fileHash'], 'chunks': [], 'originalAvailable': False}, 0)
    with platform.db.transaction():
        rag._publish(platform.scope(), rag.document(platform.scope(), doc['id']), parsed)
    captured = []
    async def planner(agent, request, context, scope, stored):
        captured.append((dict(request), context))
        yield {'type': 'done', 'ok': True, 'answer': '受控结果', 'sources': [], 'engine': 'local-workflow', 'model': 'controlled'}
    monkeypatch.setattr('backend.xueya.learning_integration.stream_readonly_agent', planner)
    class Model:
        config = Config(api_key='offline-only')
    agent = Agent(Model(), platform);agent.rag = rag
    _ = [event async for event in agent.workflow({'question': '跨文档解释循环队列并证明算法正确性', 'documentIds': [doc['id']]})]
    assert captured and '_calculationSources' not in captured[0][0]
    assert len(captured[0][1]['library']) <= 48
