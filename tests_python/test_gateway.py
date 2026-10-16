import asyncio
import pytest
from backend.core import DomainError, Cancellation
from backend.mcp import ToolGateway


async def test_gateway_metadata_namespaces_and_atomic_duplicate_rejection():
    class Adapter:
        async def list_tools(self):
            return [{'name': 'read', 'description': 'Read', 'inputSchema': {'type': 'object'}, 'private': 'not public'}]
        async def call_tool(self, name, args, signal=None):
            return {'content': [{'type': 'text', 'text': name}]}
    gateway = ToolGateway()
    assert await gateway.list_tools() == []
    await gateway.register_server('course', Adapter())
    definitions = await gateway.list_tools()
    assert definitions[0]['name'] == 'course__read' and 'private' not in definitions[0]
    definitions[0]['description'] = 'mutated'
    assert (await gateway.list_tools())[0]['description'] == 'Read'
    assert (await gateway.call_tool('course__read', {}))['content'][0]['text'] == 'read'
    with pytest.raises(DomainError, match='DUPLICATE_TOOL'):
        await gateway.register_server('course', Adapter())
    assert len(await gateway.list_tools()) == 1
    with pytest.raises(DomainError, match='INVALID_TOOL_ARGUMENTS'):
        await gateway.call_tool('course__read', [])


async def test_gateway_timeout_and_cancel_do_not_wait_for_ignoring_handler():
    async def slow(args, signal=None):
        await asyncio.sleep(10)
        return {'content': []}
    gateway = ToolGateway(timeout_ms=10)
    gateway.register_tool({'name': 'slow'}, slow)
    with pytest.raises(DomainError, match='TOOL_TIMEOUT'):
        await gateway.call_tool('slow')
    gateway.timeout = 10
    signal = Cancellation()
    task = asyncio.create_task(gateway.call_tool('slow', {}, signal))
    await asyncio.sleep(.01)
    signal.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=.5)


async def test_gateway_rejects_invalid_results():
    gateway = ToolGateway()
    gateway.register_tool({'name': 'bad'}, lambda args, signal=None: {'notContent': []})
    with pytest.raises(DomainError, match='INVALID_TOOL_RESULT'):
        await gateway.call_tool('bad')


async def test_gateway_schema_budget_allowlist_and_host_owned_risk():
    trace = []
    gateway = ToolGateway(allowed_tools=['allowed'], max_calls=1, on_trace=trace.append)
    schema = {'type': 'object', 'properties': {'count': {'type': 'integer'}}, 'required': ['count'], 'additionalProperties': False}
    gateway.register_tool({'name': 'allowed', 'inputSchema': schema}, lambda args, signal=None: {'content': []})
    gateway.register_tool({'name': 'forbidden'}, lambda args, signal=None: {'content': []})
    assert len(await gateway.list_tools()) == 1
    with pytest.raises(DomainError, match='TOOL_FORBIDDEN'):
        await gateway.call_tool('forbidden')
    with pytest.raises(DomainError, match='INVALID_TOOL_ARGUMENTS'):
        await gateway.call_tool('allowed', {'count': 'wrong'})
    await gateway.call_tool('allowed', {'count': 1})
    with pytest.raises(DomainError, match='TOOL_BUDGET_EXCEEDED'):
        await gateway.call_tool('allowed', {'count': 1})
    assert len(trace) == 1 and gateway.stats()['calls'] == 1
    class Adapter:
        async def list_tools(self):
            return [{'name': 'write', 'risk': 'read', 'annotations': {'readOnlyHint': True}}]
        async def call_tool(self, name, args, signal=None):
            return {'content': []}
    scoped = ToolGateway()
    await scoped.register_server('remote', Adapter(), risks={'write': 'write'})
    assert (await scoped.list_tools())[0]['_meta']['risk'] == 'write'
