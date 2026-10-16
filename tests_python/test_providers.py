import asyncio
import base64
import json
import httpx
import pytest
from backend.core import DomainError, Cancellation, dumps
from backend.providers import MimoProvider, MimoSpeech
from backend.providers.router import ModelRouter


def provider(handler, **options):
    return MimoProvider({'apiKey': 'test-only', 'model': 'mimo-v2.6-flash', **options}, transport=httpx.MockTransport(handler))


async def test_provider_parameters_usage_and_no_paid_retry():
    observed = []
    def upstream(request):
        observed.append(json.loads(request.content))
        assert request.headers['authorization'] == 'Bearer test-only'
        return httpx.Response(200, json={'model': 'mimo-v2.6-flash', 'choices': [{'message': {'content': '{"answer":5}'}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 4}})
    model = provider(upstream, maxRequests=1)
    result = await model.generate({'messages': [{'role': 'user', 'content': '3+2'}], 'responseFormat': {'type': 'json_object'}})
    assert result['usage']['prompt_tokens'] == 10
    assert observed[0]['max_completion_tokens'] == 4096 and observed[0]['response_format']['type'] == 'json_object'
    with pytest.raises(DomainError, match='AI_BUDGET_EXCEEDED'):
        await model.generate({'messages': [{'role': 'user', 'content': 'retry'}]})
    assert len(observed) == 1


@pytest.mark.parametrize('status,code', [(401, 'AI_UNAVAILABLE'), (403, 'AI_UNAVAILABLE'), (429, 'AI_RATE_LIMITED'), (500, 'AI_UNAVAILABLE')])
async def test_provider_status_is_sanitized_and_not_retried(status, code):
    calls = []
    def upstream(request):
        calls.append(True)
        return httpx.Response(status, json={'error': {'message': 'secret-upstream-detail'}})
    with pytest.raises(DomainError, match=code) as caught:
        await provider(upstream).generate({'messages': [{'role': 'user', 'content': 'hi'}]})
    assert 'secret-upstream-detail' not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize('finish,code', [('length', 'AI_TRUNCATED'), ('content_filter', 'AI_INVALID_RESPONSE')])
async def test_truncated_response_is_not_success(finish, code):
    model = provider(lambda request: httpx.Response(200, json={'choices': [{'message': {'content': '{}'}, 'finish_reason': finish}]}))
    with pytest.raises(DomainError, match=code):
        await model.generate({'messages': [{'role': 'user', 'content': 'hi'}]})


async def test_streaming_utf8_usage_tools_and_missing_completion():
    data = [{'choices': [{'delta': {'reasoning_content': '核对'}}]}, {'choices': [{'delta': {'content': '{"answer":"你好"}'}}]}, {'choices': [{'delta': {}, 'finish_reason': 'stop'}], 'usage': {'total_tokens': 12}}]
    raw = ''.join('data: '+dumps(row)+'\r\n\r\n' for row in data)+'data: [DONE]\n\n'
    model = provider(lambda request: httpx.Response(200, text=raw))
    events = [e async for e in model.stream({'messages': [{'role': 'user', 'content': 'hi'}]})]
    assert any(e.get('text') == '{"answer":"你好"}' for e in events)
    assert model.usage()[0]['status'] == 'completed' and model.usage()[0]['usage']['total_tokens'] == 12
    model = provider(lambda request: httpx.Response(200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'))
    with pytest.raises(DomainError, match='AI_INCOMPLETE'):
        _ = [e async for e in model.stream({'messages': [{'role': 'user', 'content': 'hi'}]})]


async def test_cancellation_and_capability_checks_before_dispatch():
    def never(request):
        pytest.fail('No transport call expected')
    model = provider(never, model='mimo-v2.5-pro')
    signal = Cancellation()
    signal.cancel()
    with pytest.raises(asyncio.CancelledError):
        await model.generate({'signal': signal, 'messages': [{'role': 'user', 'content': 'hi'}]})
    with pytest.raises(DomainError, match='AI_UNSUPPORTED_CAPABILITY'):
        await model.generate({'messages': [{'role': 'user', 'content': [{'type': 'image_url'}]}]})


async def test_sse_accepts_complete_final_frame_without_trailing_blank_line():
    raw = 'data: {"choices":[{"delta":{"content":"你好"},"finish_reason":"stop"}]}'
    model = provider(lambda request: httpx.Response(200, text=raw))
    events = [e async for e in model.stream({'messages': [{'role': 'user', 'content': 'hi'}]})]
    assert events[0]['text'] == '你好'
    assert model.usage()[0]['status'] == 'completed'


async def test_speech_uses_different_models_and_real_audio_fields():
    observed = []
    wav = b'RIFF'+b'\x00'*4+b'WAVE'
    def upstream(request):
        body = json.loads(request.content)
        observed.append(body)
        if body['model'] == 'mimo-v2.5-tts':
            return httpx.Response(200, json={'choices': [{'message': {'audio': {'data': base64.b64encode(wav).decode()}}, 'finish_reason': 'stop'}]})
        return httpx.Response(200, json={'choices': [{'message': {'content': '三加二等于五'}, 'finish_reason': 'stop'}]})
    speech = MimoSpeech({'apiKey': 'test'}, httpx.MockTransport(upstream))
    audio = await speech.synthesize({'text': '三加二等于五'})
    text = await speech.transcribe({'audio': 'data:audio/wav;base64,'+audio['data']})
    assert '三加二' in text['text']
    assert observed[0]['messages'][0]['role'] == 'assistant'
    assert observed[1]['messages'][0]['content'][0]['type'] == 'input_audio'


async def test_router_does_not_escalate_or_double_settle():
    calls = []
    class Model:
        def capabilities(self):
            return {'model': 'controlled'}
        async def generate(self, request):
            calls.append(request)
            return {'content': '{}', 'usage': {'total_tokens': 2}}
    class Cache:
        def __init__(self):
            self.rows = {}
        async def get(self, c, k):
            return self.rows.get((c, k))
        async def put(self, c, k, v):
            self.rows[c, k] = v
    class Ledger:
        def __init__(self):
            self.settlements = []
        async def reserve(self, value):
            return 'reservation'
        async def settle(self, key, value):
            self.settlements.append(value)
    ledger = Ledger()
    router = ModelRouter({'only': Model()}, {'default': 'only'}, Cache(), ledger)
    value = {'courseId': 'c', 'task': 'answer', 'evidenceVersion': '1', 'promptVersion': '1', 'messages': []}
    assert (await router.generate(value))['execution'] == 'live'
    assert (await router.generate(value))['execution'] == 'cache'
    assert len(calls) == len(ledger.settlements) == 1
