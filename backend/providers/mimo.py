"""Async MiMo transport. No automatic retries or implicit paid escalation."""
import asyncio
import time
import httpx
from ..core import DomainError, require, finite, now_iso, clone, check_cancel

MODELS = {
    'mimo-v2.6-flash': {'image': True, 'json': True, 'tools': True},
    'mimo-v2.6-pro': {'image': True, 'json': True, 'tools': True},
    'mimo-v2.6-pro-ultraspeed': {'image': True, 'json': True, 'tools': True},
    'mimo-v2.5': {'image': True, 'json': True, 'tools': True},
    'mimo-v2.5-pro': {'image': False, 'json': True, 'tools': True},
    'mimo-v2.5-asr': {'audioInput': True}, 'mimo-v2.5-tts': {'audioOutput': True}}


async def sse_frames(response, signal=None):
    data, size = [], 0
    async for line in response.aiter_lines():
        check_cancel(signal)
        require(len(line) <= 200000, 'AI_INVALID_RESPONSE')
        if line.startswith('data:'):
            part = line[5:]
            if part.startswith(' '):
                part = part[1:]
            size += len(part)
            require(size <= 200000, 'AI_INVALID_RESPONSE')
            data.append(part)
        elif not line and data:
            yield '\n'.join(data)
            data, size = [], 0
    if data:
        yield '\n'.join(data)


class MimoProvider:
    def __init__(self, config=None, *, transport=None):
        self.config = config or {}
        self.model = self.config.get('model', 'mimo-v2.6-flash')
        self.supported = {'text': True, 'stream': True, **MODELS.get(self.model, {}), **self.config.get('capabilities', {})}
        self.transport = transport
        self.records, self.times = [], []
        self.active = 0

    def capabilities(self):
        return {**self.supported, 'model': self.model, 'verification': 'documented-not-live-tested'}

    def usage(self):
        return clone(self.records)

    def _start(self, request, stream):
        check_cancel(request.get('signal'))
        require(self.config.get('apiKey'), 'AI_UNAVAILABLE')
        require(isinstance(request.get('messages'), list) and request['messages'], 'AI_INVALID_REQUEST')
        for key, capability in [('responseFormat', 'json'), ('tools', 'tools'), ('asrOptions', 'audioInput'), ('audio', 'audioOutput')]:
            require(not request.get(key) or self.supported.get(capability), 'AI_UNSUPPORTED_CAPABILITY')
        for message in request['messages']:
            if isinstance(message.get('content'), list):
                for part in message['content']:
                    if part.get('type') in ('image_url', 'input_audio'):
                        require(self.supported.get('image' if part['type'] == 'image_url' else 'audioInput'), 'AI_UNSUPPORTED_CAPABILITY')
        now = time.monotonic()
        self.times = [t for t in self.times if now-t < 60]
        require(self.active < self.config.get('maxConcurrent', 2) and len(self.times) < self.config.get('requestsPerMinute', 30), 'AI_RATE_LIMITED')
        require(len(self.records) < self.config.get('maxRequests', 100), 'AI_BUDGET_EXCEEDED')
        tokens = request.get('maxOutputTokens', self.config.get('maxOutputTokens', 4096))
        require(type(tokens) is int and 1 <= tokens <= self.config.get('maxOutputTokens', 4096), 'AI_OUTPUT_BUDGET')
        timeout = request.get('timeoutMs', 60000 if stream else self.config.get('timeoutMs', 25000))
        require(finite(timeout) and 1 <= timeout <= 300000, 'AI_INVALID_TIMEOUT')
        body = {'model': self.model, 'messages': request['messages'], 'temperature': request.get('temperature', .2), 'max_completion_tokens': tokens}
        for source, target in [('responseFormat', 'response_format'), ('tools', 'tools'), ('asrOptions', 'asr_options'), ('audio', 'audio')]:
            if request.get(source):
                body[target] = request[source]
        if self.config.get('thinking'):
            body['thinking'] = self.config['thinking']
        if stream:
            body.update(stream=True, stream_options={'include_usage': True})
        record = {'model': self.model, 'startedAt': now_iso(), 'stream': stream, 'status': 'running', 'usage': None, 'finishReason': None}
        self.records.append(record)
        self.times.append(now)
        self.active += 1
        return body, timeout/1000, record

    def _client(self, timeout):
        return httpx.AsyncClient(transport=self.transport, timeout=timeout, follow_redirects=False)

    def _request(self):
        return {'url': self.config.get('baseURL', 'https://api.xiaomimimo.com/v1').rstrip('/')+'/chat/completions',
                'headers': {'Authorization': 'Bearer '+self.config.get('apiKey', ''), 'Content-Type': 'application/json'}}

    @staticmethod
    def _status(response):
        if not response.is_success:
            raise DomainError('AI_RATE_LIMITED' if response.status_code == 429 else 'AI_UNAVAILABLE', status=response.status_code)

    @staticmethod
    def _finish(reason):
        require(reason != 'length', 'AI_TRUNCATED')
        require(not reason or reason in ('stop', 'tool_calls'), 'AI_INVALID_RESPONSE')

    async def generate(self, request):
        body, timeout, record = self._start(request, False)
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout), self._client(timeout) as client:
                response = await client.post(**self._request(), json=body)
                self._status(response)
                payload = response.json()
                check_cancel(request.get('signal'))
                choice = payload.get('choices', [{}])[0]
                message = choice.get('message', {})
                record.update(usage=payload.get('usage'), finishReason=choice.get('finish_reason'))
                self._finish(record['finishReason'])
                require(isinstance(message.get('content'), str) or isinstance(message.get('tool_calls'), list) or request.get('audio') and message.get('audio', {}).get('data'), 'AI_INVALID_RESPONSE')
                record['status'] = 'completed'
                return {'content': message.get('content') or '', 'model': payload.get('model', self.model), 'usage': record['usage'],
                        'finishReason': record['finishReason'], 'toolCalls': message.get('tool_calls', []),
                        'reasoningContent': message.get('reasoning_content'), 'audio': message.get('audio')}
        except (httpx.TimeoutException, TimeoutError):
            record['status'] = 'unknown'
            raise DomainError('AI_TIMEOUT', outcomeUnknown=True) from None
        except asyncio.CancelledError:
            record['status'] = 'cancelled'
            raise
        except DomainError:
            record['status'] = 'failed'
            raise
        except (httpx.HTTPError, ValueError, IndexError, TypeError):
            record['status'] = 'failed'
            raise DomainError('AI_UNAVAILABLE') from None
        finally:
            record['elapsedMs'] = round((time.monotonic()-started)*1000)
            self.active -= 1

    async def stream(self, request):
        import json
        body, timeout, record = self._start(request, True)
        started, ended = time.monotonic(), False
        try:
            async with asyncio.timeout(timeout), self._client(timeout) as client:
                async with client.stream('POST', **self._request(), json=body) as response:
                    self._status(response)
                    async for raw in sse_frames(response, request.get('signal')):
                        if raw == '[DONE]':
                            ended = True
                            break
                        payload = json.loads(raw)
                        require(not payload.get('error'), 'AI_UNAVAILABLE')
                        if payload.get('usage'):
                            record['usage'] = payload['usage']
                            yield {'type': 'usage', 'usage': payload['usage'], 'model': self.model}
                        choice = (payload.get('choices') or [{}])[0]
                        if choice.get('finish_reason'):
                            self._finish(choice['finish_reason'])
                            record['finishReason'], ended = choice['finish_reason'], True
                        delta = choice.get('delta') or {}
                        for field, kind in [('content', 'content'), ('reasoning_content', 'reasoning')]:
                            if isinstance(delta.get(field), str) and delta[field]:
                                yield {'type': kind, 'text': delta[field], 'model': self.model}
                        if delta.get('tool_calls'):
                            yield {'type': 'tool_calls', 'delta': delta['tool_calls'], 'model': self.model}
                    require(ended, 'AI_INCOMPLETE')
                    record['status'] = 'completed'
        except (httpx.TimeoutException, TimeoutError):
            record['status'] = 'unknown'
            raise DomainError('AI_TIMEOUT', outcomeUnknown=True) from None
        except asyncio.CancelledError:
            record['status'] = 'cancelled'
            raise
        except (httpx.HTTPError, ValueError) as error:
            record['status'] = 'failed'
            if isinstance(error, DomainError):
                raise
            raise DomainError('AI_INVALID_RESPONSE') from None
        finally:
            if record['status'] == 'running':
                record['status'] = 'cancelled'
            record['elapsedMs'] = round((time.monotonic()-started)*1000)
            self.active -= 1
