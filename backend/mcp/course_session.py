import asyncio
import json
import sys
from contextlib import asynccontextmanager, AsyncExitStack
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ..core import require, check_cancel


class CourseSession:
    def __init__(self, client, context, timeout):
        self.client, self.context, self.timeout = client, context, timeout

    async def list_tools(self):
        return [{'name': t.name, 'description': t.description} for t in (await self.client.list_tools()).tools]

    async def call(self, name, args=None):
        require(name in ('search_materials', 'read_source', 'analyze_progress', 'build_review_plan'), 'MCP_TOOL_NOT_FOUND')
        actual = dict(args or {})
        if name in ('search_materials', 'read_source'):
            actual['sources'] = self.context['library']
        else:
            actual.update({k: self.context[k] for k in ('questions', 'records', 'baseDate')})
            if name == 'build_review_plan':
                actual.update({k: self.context[k] for k in ('examDate', 'minutes')})
        async with asyncio.timeout(self.timeout):
            result = await self.client.call_tool(name, actual)
        require(not result.is_error, 'MCP_TOOL_FAILED')
        structured = result.structured_content
        if structured:
            return structured
        return json.loads(next(c.text for c in result.content if c.type == 'text'))


@asynccontextmanager
async def open_course_session(context, timeout_ms=5000):
    params = StdioServerParameters(command=sys.executable, args=['-m', 'backend.mcp.course_server'], cwd=str(Path(__file__).resolve().parents[2]))
    from mcp import Client
    async with Client(params, read_timeout_seconds=timeout_ms/1000) as client:
        yield CourseSession(client, context, timeout_ms/1000)
