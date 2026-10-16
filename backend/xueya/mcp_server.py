"""Standalone Python MCP stdio endpoint (stdout is reserved for protocol frames)."""
import asyncio
from mcp.server.stdio import stdio_server
from .mcp_core import course_registry, create_server, open_session


async def serve():
    server = create_server(course_registry())
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


async def check():
    async with open_session(stdio=True) as session:
        from .learning import SOURCES
        result = await session.call("search_materials", {"query": "二叉树", "sources": [{k: s[k] for k in ("id", "title", "location", "quote", "keywords", "sample") if k in s} for s in SOURCES]})
        print("MCP stdio: official Python SDK; tools=", len(session.definitions), "; matched=", len(result["sources"]))


if __name__ == "__main__":
    import sys
    asyncio.run(check() if "--check" in sys.argv else serve())
