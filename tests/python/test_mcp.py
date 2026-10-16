import asyncio
import json
import threading
import sys
from types import SimpleNamespace
import httpx
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from backend.xueya.common import AppError, Scope, dumps
from backend.xueya.gateway import ToolGateway
from backend.xueya.mcp_core import Registry, create_server, open_session, platform_registry, obj, PAGE, lookup_reference, CONNECTIONS, STDIO_CONNECTIONS
from backend.xueya.mcp_http import create_mcp_http_app, connect_http, HTTP_CONNECTIONS
from conftest import live_server


def test_real_scoped_sdk_pagination_scope_override_and_missing_ports(platform):
    p = platform
    for key in ("a", "b"):
        p.repo.put(p.scope(), "note", key, {"title": key}, 0)

    async def run():
        async with open_session(platform_registry(p, p.scope())) as session:
            assert "confirm_action" not in session.definitions and "get_prerequisites" not in session.definitions
            page = await session.call("list_notes", {"limit": 1})
            assert page["items"][0]["id"] == "a" and page["nextCursor"]
            assert (await session.call("list_notes", {"cursor": page["nextCursor"]}))["items"][0]["id"] == "b"
            with pytest.raises(AppError, match="INVALID_TOOL_ARGUMENTS"):
                await session.call("list_notes", {"courseId": "other"})
            with pytest.raises(AppError, match="TOOL_NOT_FOUND"):
                await session.call("unavailable")
        assert CONNECTIONS.active == 0
    asyncio.run(run())


def test_session_confirm_in_fresh_connection_and_atomic_idempotency(platform):
    p = platform

    async def run():
        async with open_session(platform_registry(p, p.scope())) as session:
            preview = await session.call("prepare_action", {"kind": "note", "entityId": "sdk-note", "expectedVersion": 0, "after": {"title": "SDK", "content": "saved once"}})
        assert CONNECTIONS.active == 0
        p.authority.confirm(p.scope(), preview)
        async with open_session(platform_registry(p, p.scope())) as session:
            results = await asyncio.gather(*(session.call("apply_action", {"actionId": preview["actionId"]}) for _ in range(2)))
            assert results[0] == results[1]
        assert p.db.one("SELECT count(*) n FROM audits")["n"] == 1
    asyncio.run(run())


@pytest.mark.parametrize("bad", [{"items": [1, 2], "nextCursor": None}, {"items": [], "nextCursor": "x"*301}, {"items": [], "nextCursor": "same"}])
def test_business_page_validation_rejects_invalid_results(bad):
    registry = Registry()
    registry.add("list_notes", PAGE, lambda _: bad)
    with pytest.raises(AppError, match="INVALID_BUSINESS_PAGE"):
        asyncio.run(registry.call("list_notes", {"limit": 1, "cursor": "same"}))


def test_business_scope_and_result_byte_bounds():
    registry = Registry()
    registry.bound_scope = Scope(user_id="u", course_id="c")
    registry.add("mismatch", obj(), lambda _: {"scope": {"userId": "u", "courseId": "other"}})
    registry.add("huge", obj(), lambda _: {"text": "x"*140000})
    for name, code in (("mismatch", "RESULT_SCOPE_MISMATCH"), ("huge", "TOOL_RESULT_TOO_LARGE")):
        with pytest.raises(AppError, match=code):
            asyncio.run(registry.call(name, {}))


def test_official_sdk_cancellation_reaches_business_handler_and_releases_permit():
    async def run():
        registry, started, stopped = Registry(), asyncio.Event(), asyncio.Event()

        async def slow(args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        registry.add("slow", obj(), slow)
        async with open_session(registry) as session:
            task = asyncio.create_task(session.call("slow"))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(stopped.wait(), 1)
        assert CONNECTIONS.active == 0
    asyncio.run(run())


def test_stdio_crash_and_cancel_release_owned_connection():
    async def run():
        async with open_session(stdio=True) as session:
            assert len(session.definitions) == 4
            with pytest.raises(AppError, match="INVALID_TOOL_ARGUMENTS"):
                await session.call("read_source", {"sourceId": "missing", "sources": "wrong"})
        assert STDIO_CONNECTIONS.active == 0
        with pytest.raises(Exception):
            async with open_session(stdio_params=StdioServerParameters(command=sys.executable, args=["-c", "import os;os._exit(7)"]), timeout=.5):
                pytest.fail("crashed server connected")
        assert STDIO_CONNECTIONS.active == 0
        task = asyncio.create_task(open_and_wait())
        await asyncio.sleep(.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert STDIO_CONNECTIONS.active == 0

    async def open_and_wait():
        async with open_session(stdio=True):
            await asyncio.Event().wait()
    asyncio.run(run())


def test_sdk_connection_lifetime_closes_idle_session():
    async def run():
        with pytest.raises(TimeoutError):
            async with open_session(Registry(), max_duration=.05):
                await asyncio.sleep(1)
        assert CONNECTIONS.active == 0
    asyncio.run(run())


def test_gateway_schema_metadata_namespacing_and_atomic_discovery():
    async def run():
        async def call(name, args):
            return {"content": [{"type": "text", "text": name+":"+args["term"]}]}

        async def definitions():
            return [{"name": "lookup", "inputSchema": {"type": "object", "required": ["term"], "properties": {"term": {"type": "string"}}}, "annotations": {"readOnlyHint": True}}]
        gateway = ToolGateway()
        await gateway.register_server("course", SimpleNamespace(list_tools=definitions, call_tool=call))
        metadata = await gateway.list_tools()
        metadata[0]["inputSchema"]["required"].append("mutated")
        assert (await gateway.list_tools())[0]["inputSchema"]["required"] == ["term"]
        assert (await gateway.list_tools())[0]["_meta"]["risk"] == "unknown"
        assert "lookup:树" in (await gateway.call_tool("course__lookup", {"term": "树"}))["content"][0]["text"]
        with pytest.raises(AppError, match="INVALID_TOOL_ARGUMENTS"):
            await gateway.call_tool("course__lookup", [])
        async def duplicate():
            return [{"name": "same"}, {"name": "same"}]
        with pytest.raises(AppError, match="DUPLICATE_TOOL"):
            await gateway.register_server("broken", SimpleNamespace(list_tools=duplicate, call_tool=call))
        assert len(await gateway.list_tools()) == 1
    asyncio.run(run())


def test_gateway_timeout_keeps_noncooperative_permit_until_completion():
    async def run():
        gateway = ToolGateway(timeout=.02, max_concurrent=1)
        finish = asyncio.Event()

        async def ignores_cancellation(args):
            while not finish.is_set():
                try:
                    await finish.wait()
                except asyncio.CancelledError:
                    continue
            return {"content": []}
        gateway.register({"name": "slow"}, ignores_cancellation)
        with pytest.raises(AppError, match="TOOL_TIMEOUT"):
            await gateway.call_tool("slow")
        assert gateway.limiter.active == 1
        with pytest.raises(AppError, match="MCP_BUSY"):
            await gateway.call_tool("slow")
        finish.set()
        await asyncio.sleep(.01)
        assert gateway.limiter.active == 0
    asyncio.run(run())


def test_gateway_allowlist_budget_and_size_limits():
    async def run():
        gateway = ToolGateway(max_calls=1, allowed_tools=["good"])
        async def good(a):
            return {"content": []}
        gateway.register({"name": "good"}, good)
        gateway.register({"name": "forbidden"}, good)
        with pytest.raises(AppError, match="TOOL_FORBIDDEN"):
            await gateway.call_tool("forbidden")
        with pytest.raises(AppError, match="TOOL_ARGUMENTS_TOO_LARGE"):
            await gateway.call_tool("good", {"data": "x"*65536})
        await gateway.call_tool("good")
        with pytest.raises(AppError, match="TOOL_BUDGET_EXCEEDED"):
            await gateway.call_tool("good")
    asyncio.run(run())


@pytest.mark.parametrize("protocol", ["2026-07-28", "legacy"])
def test_real_http_official_sdk_authentication_scopes_and_protocols(platform, protocol):
    p = platform
    allowed = ["127.0.0.1"]
    identity = p.scope()
    app = create_mcp_http_app(p, authenticate=lambda req: identity if req.headers.get("authorization") == "Bearer test-token" else None, allowed_hosts=allowed)
    with live_server(app) as base:
        allowed.append(base.removeprefix("http://"))

        async def run():
            async with connect_http(base+"/mcp", allowed_origins=[base], token="test-token", allow_localhost=True, protocol=protocol) as session:
                assert "list_notes" in session.definitions
                assert (await session.call("list_notes", {"limit": 1}))["items"] == []
            assert HTTP_CONNECTIONS.active == 0
        asyncio.run(run())
        with httpx.Client() as client:
            assert client.get(base+"/mcp").status_code == 401
            assert client.get(base+"/mcp", headers={"Authorization": "Bearer test-token", "Origin": "https://evil.example"}).status_code == 403
            assert client.get(base+"/other", headers={"Authorization": "Bearer test-token"}).status_code == 404
            assert client.post(base+"/mcp", headers={"Authorization": "Bearer test-token"}, content=b"x"*262145).status_code == 413
            assert client.get(base+"/mcp", headers={"Authorization": "Bearer test-token", "Accept": "text/event-stream"}).status_code == 405


def test_remote_http_endpoint_must_be_host_approved():
    async def run():
        for url in ("http://169.254.169.254/mcp", "https://approved.example/mcp?x=1", "https://user:secret@approved.example/mcp"):
            with pytest.raises(AppError, match="MCP_URL_FORBIDDEN"):
                async with connect_http(url, allowed_origins=["https://approved.example"]):
                    pytest.fail("unsafe endpoint accepted")
    asyncio.run(run())


def test_modern_http_cancellation_reaches_server_business(platform, monkeypatch):
    started, aborted = threading.Event(), threading.Event()
    registry = Registry()

    async def slow(args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            aborted.set()
    registry.add("slow", obj(), slow)
    monkeypatch.setattr("backend.xueya.mcp_http.platform_registry", lambda *a, **k: registry)
    allowed = ["127.0.0.1"]
    app = create_mcp_http_app(platform, authenticate=lambda req: platform.scope(), allowed_hosts=allowed)
    with live_server(app) as base:
        allowed.append(base.removeprefix("http://"))

        async def run():
            async with connect_http(base+"/mcp", allowed_origins=[base], allow_localhost=True) as session:
                task = asyncio.create_task(session.call("slow"))
                assert await asyncio.to_thread(started.wait, 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert await asyncio.to_thread(aborted.wait, 2)
        asyncio.run(run())


def test_reference_connector_opt_in_doi_only_and_bounded(platform, monkeypatch):
    import backend.xueya.mcp_core as module
    real_client, observed = httpx.AsyncClient, []

    async def response(request):
        observed.append(str(request.url))
        return httpx.Response(200, json={"message": {"DOI": "10.1038/nphys1170", "title": ["Public metadata"], "publisher": "Publisher", "published": {"date-parts": [[2009]]}}})
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **k: real_client(transport=httpx.MockTransport(response), **k))
    assert "lookup_reference" not in platform_registry(platform, platform.scope()).tools

    async def run():
        async with open_session(platform_registry(platform, platform.scope(), reference=True)) as session:
            result = await session.call("lookup_reference", {"doi": "10.1038/nphys1170"})
            assert result["courseEvidence"] is False and result["year"] == 2009
            with pytest.raises(AppError, match="INVALID_TOOL_ARGUMENTS"):
                await session.call("lookup_reference", {"doi": "https://evil.example"})
        assert observed == ["https://api.crossref.org/works/10.1038%2Fnphys1170"]
    asyncio.run(run())
