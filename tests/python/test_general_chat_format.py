"""Default host general-chat regressions; all upstream calls stay offline."""
import asyncio
import json

import httpx
import pytest

from backend.xueya.agent import Agent
from backend.xueya.common import AppError
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider


@pytest.mark.parametrize('path', ['/api/agent', '/api/agent/stream'])
@pytest.mark.parametrize('content,reason,expected', [
    ('今天是星期五。', 'stop', '今天是星期五。'),
    ('雷军是小米的创始人。', 'stop', '雷军是小米的创始人。'),
    ('引用："正文"\n路径 C:\\notes，emoji：😀', 'stop', '引用："正文"\n路径 C:\\notes，emoji：😀'),
    ('```json\n{"answer":42}\n```', 'stop', '```json\n{"answer":42}\n```'),
    ('   ', 'stop', '模型没有返回回答正文'),
    ('半段回答', 'length', '回答不完整'),
])
def test_general_chat_format_on_default_http_and_sse(client, path, content, reason, expected):
    calls = []

    def upstream(request):
        calls.append(json.loads(request.content))
        frame = {'choices': [{'delta': {'content': content}, 'finish_reason': reason}]}
        return httpx.Response(200, text='data: '+json.dumps(frame)+'\n\ndata: [DONE]\n\n')

    provider = MimoProvider(Config(api_key='test-only'), client.platform, httpx.MockTransport(upstream))
    client.app.state.agent = Agent(provider, client.platform)
    response = client.post(path, json={'question': '今天星期几'})
    assert response.status_code == 200
    if path.endswith('/stream'):
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        result = events[-1]
        assert result['type'] == 'done'
        if reason != 'stop' or not content.strip():
            assert events[-2]['status'] == 'degraded'
            assert expected in events[-2]['label']
        else:
            wrapped = ''.join(e['text'] for e in events if e['type'] == 'content')
            assert json.loads(wrapped)['answer'] == content
    else:
        result = response.json()
    assert expected in result['answer']
    assert 'API 配置' not in result['answer']
    assert result['sources'] == [] and result['ok'] is True
    assert result['engine'] == ('general-chat' if reason == 'stop' and content.strip() else 'general-chat-unavailable')
    assert len(calls) == 1  # Never retry a charged request to repair its format.
    assert 'response_format' not in calls[0]
    assert calls[0]['thinking'] == {'type': 'disabled'}
    assert '用自然连贯的中文段落回答' in calls[0]['messages'][0]['content']
    assert calls[0]['stream'] is True
    assert client.platform.resources.stats()['active']['api'] == 0


@pytest.mark.parametrize('failure,expected', [
    ('missing-key', '尚未配置通用问答 API 密钥'),
    ('network', '服务暂时不可用'),
    ('http', '服务暂时不可用'),
    ('incomplete', '回答不完整'),
])
def test_general_chat_failure_messages_do_not_blame_configuration(client, failure, expected):
    calls = []

    def upstream(request):
        calls.append(True)
        if failure == 'network':
            raise httpx.ConnectError('private-upstream-details')
        if failure == 'incomplete':
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')
        return httpx.Response(401, text='private-upstream-details')

    provider = MimoProvider(Config(api_key='' if failure == 'missing-key' else 'test-only'),
                            client.platform, httpx.MockTransport(upstream))
    client.app.state.agent = Agent(provider, client.platform)
    result = client.post('/api/agent', json={'question': '今天星期几'}).json()
    assert expected in result['answer']
    assert result['engine'] == 'general-chat-unavailable'
    assert 'private-upstream-details' not in json.dumps(result)
    assert 'API 配置' not in result['answer']
    assert len(calls) == (0 if failure == 'missing-key' else 1)
    assert client.platform.resources.stats()['active']['api'] == 0


def test_stream_validates_format_before_dispatch():
    def upstream(request):
        pytest.fail('Invalid format must be rejected before calling the provider')

    provider = MimoProvider(Config(api_key='test-only'), transport=httpx.MockTransport(upstream))

    async def run():
        with pytest.raises(AppError, match='AI_INVALID_RESPONSE_FORMAT'):
            _ = [event async for event in provider.stream([], response_format={'type': 'unsupported'})]

    asyncio.run(run())


def test_stream_keeps_default_thinking_for_other_tasks():
    calls = []

    def upstream(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"answer"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')

    provider = MimoProvider(Config(api_key='test-only'), transport=httpx.MockTransport(upstream))

    async def run():
        events = [event async for event in provider.stream([{'role': 'user', 'content': '学习任务'}])]
        assert events[0]['text'] == 'answer'

    asyncio.run(run())
    assert len(calls) == 1 and 'thinking' not in calls[0]


def test_stream_rejects_invalid_thinking_before_dispatch():
    def upstream(request):
        pytest.fail('Invalid thinking mode must be rejected before dispatch')

    provider = MimoProvider(Config(api_key='test-only'), transport=httpx.MockTransport(upstream))

    async def run():
        with pytest.raises(AppError, match='AI_INVALID_THINKING_MODE'):
            _ = [event async for event in provider.stream([], thinking={'type': 'unknown'})]

    asyncio.run(run())


@pytest.mark.parametrize('path', ['/api/agent', '/api/agent/stream'])
@pytest.mark.parametrize('with_history', [False, True])
def test_real_multiturn_prose_is_not_discarded_for_lacking_json(client, path, with_history):
    history = [
        {'role': 'user', 'content': '今天星期几'},
        {'role': 'assistant', 'content': '通用问答服务暂时不可用，请检查 API 配置后重试。'},
        {'role': 'user', 'content': '今天星期几'},
        {'role': 'assistant', 'content': '今天是 2026年10月23日，星期五。'},
        {'role': 'user', 'content': '马斯克是谁'},
        {'role': 'assistant', 'content': '埃隆·马斯克是一位企业家，创办了 SpaceX，并参与特斯拉等公司。'},
        {'role': 'user', 'content': '今天星期几'},
        {'role': 'assistant', 'content': '今天是 2026年10月23日，星期五。'},
    ] if with_history else []
    answer = '雷军，出生于1969年12月，于1991年7月取得武汉大学计算机科学学士学位。雷军是小米集团的创始人。\n他也是中国知名的科技创业者。'
    calls = []

    def upstream(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert 'response_format' not in payload
        assert '直接输出回答正文' in payload['messages'][0]['content']
        assert payload['messages'][1:-1] == history
        frames = [{'choices': [{'delta': {'content': answer[i:i+7]}}]} for i in range(0, len(answer), 7)]
        frames.append({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
        return httpx.Response(200, text=''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n')

    provider = MimoProvider(Config(api_key='test-only'), client.platform, httpx.MockTransport(upstream))
    client.app.state.agent = Agent(provider, client.platform)
    response = client.post(path, json={'question': '雷军是谁', 'history': history})
    assert response.status_code == 200
    if path.endswith('/stream'):
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        result = events[-1]
        assert json.loads(''.join(e['text'] for e in events if e['type'] == 'content')) == {'answer': answer}
        assert len([e for e in events if e['type'] == 'content']) > 2
        assert not any(e.get('status') == 'degraded' or e['type'] == 'error' for e in events)
    else:
        result = response.json()
    assert result['engine'] == 'general-chat' and result['answer'] == answer
    assert result['sources'] == [] and len(calls) == 1


@pytest.mark.parametrize('hint,history,question,previous,expect_general', [
    ('general', '```json\n{"name":"张三","age":25}\n```', '把代码块里的 name 改成“小明”，age 改成 20。', [], True),
    (None, '```json\n{"name":"张三","age":25}\n```', '把代码块里的 name 改成“小明”，age 改成 20。', [], True),
    ('general', '名字叫张三。', '把这个名字改成小明。', [], True),
    ('general', '```json\n{"name":"张三"}\n```', '根据讲义把代码块里的 name 改成小明。', [], False),
    ('general', '```json\n{"name":"张三"}\n```', '把代码块里的 name 改成小明。', ['code-course'], False),
    ('general', '', '把代码块里的 name 改成小明。', [], False),
])
def test_general_edit_followup_does_not_enter_course_planning(monkeypatch, hint, history, question, previous, expect_general):
    from types import SimpleNamespace

    class Model:
        config = SimpleNamespace(model='controlled', api_key='offline-only', agent_planning_enabled=True)
        calls = 0

        async def stream(self, messages, **options):
            self.calls += 1
            assert options.get('thinking') in (None, {'type': 'disabled'})
            yield {'type': 'content', 'text': '```json\n{"name":"小明","age":20}\n```', 'model': 'controlled'}

    planning = []

    async def planner(*args):
        planning.append(True)
        yield {'type': 'done', 'engine': 'course-guard', 'answer': 'course path', 'sources': []}

    monkeypatch.setattr('backend.xueya.learning_integration.stream_readonly_agent', planner)
    source = {'id': 'code-course', 'title': '代码块', 'quote': '课程中的代码块和字段修改规则。', 'keywords': ['代码块', '名字']}
    value = {'question': question, 'context': {'library': [source], 'previousSourceIds': previous},
             'history': [{'role': 'assistant', 'content': history}] if history else []}
    if hint:
        value['previousAnswerKind'] = hint
    model = Model()

    async def run():
        return [e async for e in Agent(model).workflow(value)]

    events = asyncio.run(run())
    assert events[-1]['engine'] == ('general-chat' if expect_general else 'course-guard')
    assert model.calls == int(expect_general)
    assert bool(planning) is not expect_general
