"""MiMo transport over the host's limiter, execution budget and invocation ledger."""
from __future__ import annotations
import asyncio
import json
from time import perf_counter
from .qa_latency import current_timing
from contextlib import asynccontextmanager
from uuid import uuid4
import httpx
from .common import AppError, digest, dumps, require, utc_now
from .rag_api import api_permit_held
from .execution_budget import budget_scope, current_budget


class MimoProvider:
    def __init__(self, config, platform=None, transport=None):
        self.config, self.platform, self.transport = config, platform, transport
        self._shared_client = None

    @asynccontextmanager
    async def invocation(self, messages, scope, *, capability='text', model=None, max_output_tokens=None):
        if capability == 'text' and any(isinstance(m.get('content'), list) and any(isinstance(p, dict) and p.get('type') == 'image_url' for p in m['content']) for m in messages):
            capability = 'image'
        require(bool(self.config.api_key), 'AI_UNAVAILABLE')
        output_limit = max_output_tokens if max_output_tokens is not None else self.config.max_output_tokens
        require(type(output_limit) is int and 0 < output_limit <= self.config.max_output_tokens, 'AI_OUTPUT_BUDGET_EXCEEDED')
        with budget_scope(self.config) as budget:
            request_id, release = None, None
            timing, model_started = current_timing.get(), None
            state = {'usage': None, 'complete': False, 'usable': False, 'finishReason': None, 'outputLimit': output_limit}
            if self.platform:
                if api_permit_held(self.platform):
                    release = (lambda: None)
                else:
                    # Queue instead of failing instantly; timeout <= 0 keeps the
                    # legacy fail-fast API_BUSY contract for existing callers.
                    release = await self.platform.resources.acquire_wait('api', getattr(self.config, 'api_queue_timeout', 0.0))
                require(release is not None, 'API_BUSY')
            try:
                state['reservedCost'] = budget.model(messages, output_limit, capability=capability, model=model or self.config.model)
                if self.platform:
                    request_id = str(uuid4())
                    self.platform.db.execute('INSERT INTO invocations(id,user_id,course_id,status,provider,request_hash,at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                        (request_id, scope.user_id, scope.course_id, 'pending', 'mimo', digest(messages), utc_now(), utc_now()))
                    from .invocation_context import attach_invocation
                    attach_invocation(self.platform, scope, request_id, capability=capability, model=model or self.config.model,
                                      base_url=self.config.base_url, key=self.config.api_key)
                if timing:
                    model_started = perf_counter()
                    timing.model_calls += 1
                yield state
            except Exception as error:
                # Class names only: exception messages can contain provider URLs,
                # headers or request data. Keep uncertain dispatches unknown.
                state['errorType'] = type(error).__name__
                raise
            finally:
                if timing:
                    if model_started is not None:
                        timing.model_ms += (perf_counter()-model_started)*1000
                    # Exactly one usage accrual per dispatched call, including
                    # failures and budget-unknown outcomes (None is ignored).
                    timing.note_usage(state.get('usage'))
                try:
                    if request_id:
                        status = 'succeeded' if state['usable'] else 'failed' if state['complete'] else 'unknown'
                        self.platform.db.execute('UPDATE invocations SET status=?,updated_at=?,usage_json=?,billing_status=? WHERE id=?',
                            (status, utc_now(), dumps(state['usage']) if state['usage'] else None, 'unknown' if status == 'unknown' else 'not_reported', request_id))
                        key = 'invocation-context:'+request_id
                        row = self.platform.db.one('SELECT value FROM meta WHERE key=?', (key,))
                        if row:
                            context = json.loads(row['value'])
                            context.update(finishReason=state['finishReason'], usable=state['usable'], outputTokenLimit=output_limit,
                                budget={'modelCalls': budget.models, 'toolCalls': budget.tools, 'reservedOutputTokens': budget.output,
                                        'reservedCny': str(budget.money), 'monetaryLimitEnabled': bool(budget.money_limit)})
                            if state.get('errorType'):
                                context['errorType'] = state['errorType']
                            self.platform.db.execute('UPDATE meta SET value=? WHERE key=?', (dumps(context), key))
                finally:
                    if release:
                        release()

    def new_client(self, timeout):
        return httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=self.transport,
                                 limits=httpx.Limits(max_connections=self.config.api_slots,
                                                    max_keepalive_connections=self.config.api_slots, keepalive_expiry=60),
                                 headers={'Authorization': 'Bearer '+self.config.api_key, 'Content-Type': 'application/json'})

    async def probe_connectivity(self):
        """Non-inference origin GET with no credentials or user content.

        A 404 on the origin is normal; this only proves transport connectivity,
        not authentication, generation quality, billing or API availability.
        """
        from urllib.parse import urlsplit
        parsed = urlsplit(self.config.base_url)
        require(parsed.scheme in ('http', 'https') and parsed.netloc and not parsed.username
                and not parsed.password, 'AI_INVALID_BASE_URL')
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False, transport=self.transport) as client:
                response = await client.get(parsed.scheme+'://'+parsed.netloc+'/')
                return {'connected': True, 'httpStatus': response.status_code, 'inference': False}
        except httpx.HTTPError as error:
            raise AppError('AI_CONNECTION_FAILED') from error

    @asynccontextmanager
    async def connection_pool(self):
        """One pool per host lifetime/event loop; standalone calls still close themselves."""
        require(self._shared_client is None, 'AI_CLIENT_ALREADY_OPEN')
        async with self.new_client(60) as client:
            self._shared_client = client
            try:
                yield self
            finally:
                self._shared_client = None

    @asynccontextmanager
    async def client(self, timeout, *, fresh=False):
        if self._shared_client is not None and not fresh:
            yield self._shared_client
        else:
            async with self.new_client(timeout) as client:
                yield client

    @staticmethod
    def check_finish(reason):
        require(reason != 'length', 'AI_TRUNCATED')
        require(reason != 'tool_calls' and reason != 'function_call', 'AI_UNEXPECTED_TOOL_CALL')
        require(reason is None or reason == 'stop', 'AI_INVALID_RESPONSE')

    @staticmethod
    def choice(payload):
        require(isinstance(payload, dict) and not payload.get('error'), 'AI_INVALID_RESPONSE')
        choices = payload.get('choices') or [{}]
        require(isinstance(choices, list) and isinstance(choices[0], dict), 'AI_INVALID_RESPONSE')
        return choices[0]

    async def generate(self, messages, *, scope=None, temperature=.2, timeout=25, max_output_tokens=None, response_format=None, thinking=None):
        require(response_format is None or response_format == {'type': 'json_object'}, 'AI_INVALID_RESPONSE_FORMAT')
        require(thinking is None or thinking in ({'type': 'enabled'}, {'type': 'disabled'}), 'AI_INVALID_THINKING_MODE')
        async with self.invocation(messages, scope, max_output_tokens=max_output_tokens) as state:
            timeout = min(timeout, current_budget.get().remaining())
            async with asyncio.timeout(timeout), self.client(timeout) as client:
                async with client.stream('POST', self.config.base_url.rstrip('/')+'/chat/completions', timeout=timeout,
                    json={'model': self.config.model, 'temperature': temperature, 'messages': messages,
                          'max_completion_tokens': state['outputLimit'],
                          **({'response_format': response_format} if response_format else {}),
                          **({'thinking': thinking} if thinking else {})}) as response:
                    require(response.is_success, 'AI_UNAVAILABLE')
                    buffer = bytearray()
                    async for part in response.aiter_bytes():
                        buffer.extend(part)
                        require(len(buffer) <= 2097152, 'AI_INVALID_RESPONSE')
                    state['complete'] = True
                    data = json.loads(buffer)
                    choice = self.choice(data)
                    state.update(usage=data.get('usage'), finishReason=choice.get('finish_reason'))
                    current_budget.get().observe(state['usage'], state['reservedCost'], state['outputLimit'])
                    self.check_finish(state['finishReason'])
                    message = choice.get('message')
                    require(isinstance(message, dict), 'AI_INVALID_RESPONSE')
                    require(not message.get('tool_calls') and not message.get('function_call'), 'AI_UNEXPECTED_TOOL_CALL')
                    content = message.get('content')
                    require(isinstance(content, str), 'AI_INVALID_RESPONSE')
                    current_budget.get().remaining()
                    state['usable'] = True
                    return {'content': content, 'model': self.config.model, 'usage': state['usage'], 'finishReason': state['finishReason']}

    async def stream(self, messages, *, scope=None, timeout=60, max_output_tokens=None, response_format=None, thinking=None, fresh_connection=False):
        require(response_format is None or response_format == {'type': 'json_object'}, 'AI_INVALID_RESPONSE_FORMAT')
        require(thinking is None or thinking in ({'type': 'enabled'}, {'type': 'disabled'}), 'AI_INVALID_THINKING_MODE')
        async with self.invocation(messages, scope, max_output_tokens=max_output_tokens) as state:
            timeout = min(timeout, current_budget.get().remaining())
            async with asyncio.timeout(timeout), self.client(timeout, fresh=fresh_connection) as client:
                async with client.stream('POST', self.config.base_url.rstrip('/')+'/chat/completions', timeout=timeout,
                    json={'model': self.config.model, 'temperature': .2, 'messages': messages, 'stream': True,
                          'max_completion_tokens': state['outputLimit'], 'stream_options': {'include_usage': True},
                          **({'response_format': response_format} if response_format else {}),
                          **({'thinking': thinking} if thinking else {})}) as response:
                    require(response.is_success, 'AI_UNAVAILABLE')
                    data_lines, size, ended, done_received = [], 0, False, False

                    def events(frame):
                        nonlocal ended
                        if frame == '[DONE]':
                            ended = state['complete'] = True
                            return []
                        try:
                            payload = json.loads(frame)
                        except ValueError as error:
                            raise AppError('AI_INVALID_RESPONSE') from error
                        choice = self.choice(payload)
                        if payload.get('usage'):
                            state['usage'] = payload['usage']
                        reason = choice.get('finish_reason')
                        if reason is not None:
                            state.update(finishReason=reason, complete=True)
                        if payload.get('usage'):
                            state['reservedCost'] = current_budget.get().observe(state['usage'], state['reservedCost'], state['outputLimit'])
                        if reason is not None:
                            self.check_finish(reason)
                            ended = True
                        delta = choice.get('delta') or {}
                        timing = current_timing.get()
                        if timing and timing.first_token is None and isinstance(delta, dict) and (delta.get('content') or delta.get('reasoning_content')):
                            timing.first_token = timing.elapsed()
                        require(isinstance(delta, dict), 'AI_INVALID_RESPONSE')
                        require(not delta.get('tool_calls') and not delta.get('function_call'), 'AI_UNEXPECTED_TOOL_CALL')
                        return [{'type': kind, 'text': delta[key], 'model': self.config.model}
                                for key, kind in (('reasoning_content', 'reasoning'), ('content', 'content'))
                                if isinstance(delta.get(key), str) and delta[key]]

                    # httpx handles split UTF-8 and CR/LF boundaries; keep multiline data.
                    async for line in response.aiter_lines():
                        size += len(line.encode('utf-8'))
                        require(size <= 2097152, 'AI_INVALID_RESPONSE')
                        if done_received:
                            continue
                        if line.startswith('data:'):
                            data_lines.append(line[5:].removeprefix(' '))
                        elif not line and data_lines:
                            frame = '\n'.join(data_lines)
                            data_lines.clear()
                            for event in events(frame):
                                yield event
                            if frame == '[DONE]':
                                # Consume the HTTP body terminator so the pooled
                                # connection is reusable; ignore post-DONE frames.
                                done_received = True
                    if data_lines:
                        for event in events('\n'.join(data_lines)):
                            yield event
                    require(ended, 'AI_INCOMPLETE')
                    current_budget.get().observe(state['usage'], state['reservedCost'], state['outputLimit'])
                    current_budget.get().remaining()
                    state['usable'] = True
