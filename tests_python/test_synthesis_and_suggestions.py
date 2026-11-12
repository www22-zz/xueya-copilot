"""Synthesized answers, generic follow-up questions, and LLM-predicted follow-ups."""
import json
from types import SimpleNamespace

import pytest

from backend.agent.answer_policy import finalize_answer
from backend.xueya.agent import Agent

SOURCE = {'id': 'syn-source', 'documentId': 'syn-doc', 'title': '队列', 'location': '第1页',
          'version': '1', 'quote': '队列遵循先进先出。队尾入队，队首出队。', 'keywords': ['队列']}
PROSE = '队列是一种先进先出的结构：元素从队尾进入，从队首离开，因此先来的元素先得到处理。'


class Provider:
    def __init__(self, content='{}'):
        self.content = content
        self.calls = []
        self.config = SimpleNamespace(model='controlled', max_output_tokens=4096,
                                      answer_repair_enabled=False, answer_repair_tokens=1024,
                                      answer_thinking_disabled=False)

    async def generate(self, messages, **options):
        self.calls.append((messages, options))
        return {'content': self.content, 'model': 'controlled', 'usage': {}}

    async def stream(self, messages, **options):
        yield {'type': 'content', 'text': self.content, 'model': 'controlled'}


class Review:
    def __init__(self):
        self.provider = Provider()
        self.scope = None

    async def prepare(self, claims, signal=None):
        return None

    async def __call__(self, claim, signal=None):
        return {'supported': True, 'method': 'fixture'}


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def test_answer_carries_three_llm_predicted_followups():
    content = {'answer': PROSE, 'sources': [SOURCE['id']],
               'claims': [{'text': '队列遵循先进先出。', 'kind': 'excerpt',
                           'evidence': [{'sourceId': SOURCE['id'], 'quoteId': 'q0'}]}],
               'suggestedQuestions': ['LR 和 RL 双旋怎么区分？', 'AVL 删除结点怎么调整？', '红黑树和 AVL 有什么区别？', '太短', 'LR 和 RL 双旋怎么区分？']}
    import asyncio
    result = asyncio.run(finalize_answer(dumps(content), [SOURCE], 'controlled', review=Review(),
                                         question='队列是什么？', narrative=True, prose_review=False))
    assert result['answer'].startswith(PROSE)
    assert result['suggestedQuestions'] == ['LR 和 RL 双旋怎么区分？', 'AVL 删除结点怎么调整？',
                                            '红黑树和 AVL 有什么区别？']
    assert result['verification'] == 'claims-supported-prose' and result['proseReview'] == 'skipped'


def test_suggested_questions_are_bounded_and_validated():
    provider = Provider(content=dumps({'questions': [' 如何判断 LR 型失衡？ ',
                                                     'x', '如何在代码里实现 AVL 旋转？',
                                                     '红黑树与 AVL 树的核心区别是什么？',
                                                     '红黑树与 AVL 树的核心区别是什么？']}))
    agent = Agent(provider)
    import asyncio
    result = asyncio.run(agent.suggestions({'question': 'AVL 怎么旋转？', 'answer': '先判断失衡类型。'}))
    assert result['ok'] is True
    assert result['questions'] == ['如何判断 LR 型失衡？', '如何在代码里实现 AVL 旋转？',
                                   '红黑树与 AVL 树的核心区别是什么？']
    assert provider.calls[0][1]['response_format'] == {'type': 'json_object'}
    assert provider.calls[0][1]['thinking'] == {'type': 'disabled'}


def test_suggestions_endpoint_rejects_empty_answer():
    import asyncio
    from backend.xueya.common import AppError
    agent = Agent(Provider())
    with pytest.raises(AppError):
        asyncio.run(agent.suggestions({'question': 'AVL 怎么旋转？', 'answer': ' '}))


def test_suggestions_http_route_returns_llm_questions(tmp_path):
    import httpx
    from fastapi.testclient import TestClient
    from backend.xueya.app import create_app
    from backend.xueya.config import Config
    from backend.xueya.provider import MimoProvider

    calls = []

    def upstream(request):
        calls.append(json.loads(request.content))
        content = dumps({'questions': ['LR 为什么必须双旋？', '删除结点时如何判断旋转？',
                                      '红黑树和 AVL 树的区别是什么？']})
        return httpx.Response(200, json={'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]})

    config = Config(data_dir=tmp_path / 'data', api_key='fixture-only')
    app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)), start_jobs=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        response = client.post('/api/agent/suggestions', json={'question': 'AVL 怎么旋转？',
                                                               'answer': '先判断失衡类型再旋转。'})
        value = response.json()
    assert value['ok'] is True and value['questions'] == ['LR 为什么必须双旋？', '删除结点时如何判断旋转？',
                                                          '红黑树和 AVL 树的区别是什么？']
    assert calls and calls[0]['response_format'] == {'type': 'json_object'}
    assert calls[0]['thinking'] == {'type': 'disabled'}
