import asyncio
from backend.agent.tasks import normalize_context
from backend.mcp.course_session import open_course_session


async def main():
    context = normalize_context({'library': ['source-1']})
    async with open_course_session(context, timeout_ms=15000) as session:
        tools = await session.list_tools()
        assert len(tools) == 4
        result = await session.call('search_materials', {'query': '二叉搜索树'})
        assert result['sources']
        print('Python MCP passed: 4 real stdio tools discovered and source retrieval succeeded.')


if __name__ == '__main__':
    asyncio.run(main())
