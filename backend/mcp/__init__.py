"""Python MCP tools and an explicit, allowlisted gateway."""
import asyncio
import re
import time
import jsonschema
from ..core import require, resolve, check_cancel, clone, Cancellation, DomainError


class ToolGateway:
    def __init__(self, timeout_ms=10000, *, max_duration_ms=60000, max_argument_bytes=65536, max_result_bytes=131072, max_concurrent=4, max_calls=64, max_cost_units=64, allowed_tools=None, on_trace=None):
        self.timeout = timeout_ms/1000
        self.adapters, self.definitions, self.handlers = {}, {}, {}
        self.deadline = time.monotonic()+max_duration_ms/1000
        self.argument_bytes, self.result_bytes, self.maximum = max_argument_bytes, max_result_bytes, max_concurrent
        self.max_calls, self.max_cost, self.allowed, self.on_trace = max_calls, max_cost_units, allowed_tools, on_trace
        self.calls, self.cost, self.active, self.peak, self.total = 0, 0, 0, 0, 0
        self.costs, self.validators = {}, {}

    def register_tool(self, definition, handler):
        require(isinstance(definition, dict) and isinstance(definition.get('name'), str) and re.fullmatch('[-a-zA-Z0-9_]{1,150}', definition['name']) and callable(handler), 'INVALID_TOOL')
        name = definition['name']
        require(name not in self.definitions, 'DUPLICATE_TOOL')
        schema = definition.get('inputSchema', {'type': 'object'})
        jsonschema.Draft202012Validator.check_schema(schema)
        self.validators[name] = jsonschema.Draft202012Validator(schema)
        self.costs[name] = definition.get('costUnits', 1)
        self.definitions[name] = clone({'name': name, 'description': definition.get('description', ''), 'inputSchema': schema, **({'annotations': definition['annotations']} if 'annotations' in definition else {}), '_meta': {'version': definition.get('version', '1.0.0'), 'risk': definition.get('risk', 'read')}})
        self.handlers[name] = handler

    async def register_server(self, name, adapter, risks=None, default_risk='unknown'):
        require(isinstance(name, str) and re.fullmatch('[a-zA-Z0-9_-]+', name) and callable(getattr(adapter, 'list_tools', None)) and callable(getattr(adapter, 'call_tool', None)), 'INVALID_MCP_ADAPTER')
        definitions = await adapter.list_tools()
        require(isinstance(definitions, list) and all(isinstance(t, dict) and isinstance(t.get('name'), str) and t['name'] for t in definitions), 'INVALID_MCP_ADAPTER')
        prepared = {}
        for tool in definitions:
            key = name+'__'+tool['name']
            require(re.fullmatch('[-a-zA-Z0-9_]{1,150}', key), 'INVALID_TOOL')
            require(key not in self.definitions and key not in prepared, 'DUPLICATE_TOOL')
            jsonschema.Draft202012Validator.check_schema(tool.get('inputSchema', {'type': 'object'}))
            prepared[key] = {**tool, 'name': key, 'risk': (risks or {}).get(tool['name'], default_risk)}
        self.adapters[name] = adapter
        for original, definition in zip(definitions, prepared.values()):
            async def handler(args, signal=None, tool_name=original['name']):
                return await adapter.call_tool(tool_name, args, signal=signal)
            self.register_tool(definition, handler)

    register = register_server

    async def list_tools(self):
        return clone([value for name, value in self.definitions.items() if self.allowed is None or name in self.allowed])

    def stats(self):
        return {'active': self.active, 'peak': self.peak, 'total': self.total, 'max': self.maximum, 'calls': self.calls, 'costUnits': self.cost}

    async def call_tool(self, name, args=None, signal=None):
        check_cancel(signal)
        require(name in self.definitions, 'TOOL_NOT_FOUND')
        require(self.allowed is None or name in self.allowed, 'TOOL_FORBIDDEN')
        args = {} if args is None else args
        require(isinstance(args, dict) and self.validators[name].is_valid(args), 'INVALID_TOOL_ARGUMENTS')
        from ..core import dumps
        require(len(dumps(args).encode()) <= self.argument_bytes, 'TOOL_ARGUMENTS_TOO_LARGE')
        require(time.monotonic() < self.deadline and self.calls < self.max_calls and self.cost+self.costs[name] <= self.max_cost, 'TOOL_BUDGET_EXCEEDED')
        require(self.active < self.maximum, 'MCP_BUSY')
        self.active += 1
        self.calls += 1
        self.cost += self.costs[name]
        self.total += 1
        self.peak = max(self.peak, self.active)
        controller = Cancellation()
        async def work():
            controller.check()
            return await resolve(self.handlers[name](clone(args), signal=controller))
        task = asyncio.create_task(work())
        def release(future):
            self.active -= 1
            if not future.cancelled():
                future.exception()  # Consume late failure after a timeout; the caller already has its outcome.
        task.add_done_callback(release)
        waiter = asyncio.create_task(signal.event.wait()) if signal else None
        started, status = time.monotonic(), 'completed'
        try:
            done, _ = await asyncio.wait([task, *([waiter] if waiter else [])], timeout=min(self.timeout, max(.001, self.deadline-time.monotonic())), return_when=asyncio.FIRST_COMPLETED)
            check_cancel(signal)
            require(task in done, 'TOOL_TIMEOUT')
            result = task.result()
            require(isinstance(result, dict) and isinstance(result.get('content'), list) and len(result['content']) <= 16 and all(b.get('type') == 'text' and isinstance(b.get('text'), str) for b in result['content']), 'INVALID_TOOL_RESULT')
            require(len(dumps(result).encode()) <= self.result_bytes, 'TOOL_RESULT_TOO_LARGE')
            return result
        except (Exception, asyncio.CancelledError) as error:
            status = getattr(error, 'code', 'TOOL_ABORTED' if isinstance(error, asyncio.CancelledError) else 'TOOL_FAILED')
            raise
        finally:
            controller.cancel()
            for pending in (task, waiter):
                if pending and not pending.done():
                    pending.cancel()
            if self.on_trace:
                try:
                    self.on_trace({'tool': name, 'status': status, 'durationMs': round((time.monotonic()-started)*1000), 'calls': self.calls, 'costUnits': self.cost})
                except Exception:
                    pass
