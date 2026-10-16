"""Official MCP Streamable HTTP transport with host-owned identity and endpoint policy."""
from __future__ import annotations
import inspect
import json
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from .common import AppError, Scope, require
from .mcp_core import Limiter, Session, create_server, platform_registry

HTTP_CONNECTIONS = Limiter(4)


def create_mcp_http_app(platform, *, authenticate, allowed_hosts, allowed_origins=(), reference=False):
    require(callable(authenticate) and bool(allowed_hosts), "MCP_AUTH_REQUIRED")

    def resolve(ctx):
        require(ctx.request is not None, "AUTH_REQUIRED")
        identity = ctx.request.state.mcp_scope
        return platform_registry(platform, identity, reference=reference)

    server = create_server(resolve_registry=resolve)
    # SDK 2.3's SSE path monitors disconnects and cancels the actual handler.
    # Its forced-JSON path waits for the handler without that monitor.
    sdk_app = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=False, max_request_body_size=262144, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    limiter, rates = Limiter(8), {}

    class HostPolicy:
        def __init__(self):
            # Uvicorn/TestClient must run the SDK lifespan exactly once.
            self.router = sdk_app.router

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                return await sdk_app(scope, receive, send)
            request = Request(scope, receive)

            async def fail(text, status):
                await PlainTextResponse(text, status_code=status)(scope, receive, send)
            host, origin = request.headers.get("host"), request.headers.get("origin")
            if host not in allowed_hosts or origin and origin not in allowed_origins:
                return await fail("Forbidden", 403)
            if request.url.path != "/mcp" or request.url.query:
                return await fail("Not found", 404)
            try:
                identity = authenticate(request)
                if inspect.isawaitable(identity):
                    identity = await identity
                identity = Scope.model_validate(identity)
                platform.repo.require_course(identity)
            except Exception:
                return await fail("Unauthorized", 401)
            if request.method != "POST":
                return await fail("Method not allowed", 405)
            now = time.monotonic()
            for key in list(rates):
                if rates[key][1] <= now:
                    del rates[key]
            key = (identity.user_id, identity.course_id)
            if key not in rates:
                if len(rates) >= 1000:
                    return await fail("Busy", 429)
                rates[key] = [0, now+60]
            rates[key][0] += 1
            if rates[key][0] > 120:
                return await fail("Rate limited", 429)
            try:
                release = limiter.acquire()
            except AppError:
                return await fail("Busy", 429)
            try:
                if request.method == "POST":
                    data = bytearray()
                    async for part in request.stream():
                        data.extend(part)
                        if len(data) > 262144:
                            return await fail("Too large", 413)
                    try:
                        json.loads(data)
                    except (ValueError, UnicodeError):
                        return await fail("Invalid JSON", 400)
                    sent = False

                    async def replay():
                        nonlocal sent
                        if not sent:
                            sent = True
                            return {"type": "http.request", "body": bytes(data), "more_body": False}
                        return await receive()
                    receive_body = replay
                else:
                    receive_body = receive
                scope.setdefault("state", {})["mcp_scope"] = identity
                await sdk_app(scope, receive_body, send)
            finally:
                release()
    return HostPolicy()


class BoundedStream(httpx2.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            require(size <= 524288, "MCP_RESPONSE_TOO_LARGE")
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class EndpointTransport(httpx2.AsyncBaseTransport):
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.delegate = httpx2.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        require(str(request.url) == self.endpoint, "MCP_URL_FORBIDDEN")
        response = await self.delegate.handle_async_request(request)
        require(not response.is_redirect, "MCP_REDIRECT_FORBIDDEN")
        response.stream = BoundedStream(response.stream)
        return response

    async def aclose(self):
        await self.delegate.aclose()


class HttpTransport:
    def __init__(self, endpoint, token, timeout):
        self.endpoint, self.token, self.timeout = endpoint, token, timeout

    async def __aenter__(self):
        self.http = httpx2.AsyncClient(transport=EndpointTransport(self.endpoint), timeout=self.timeout, follow_redirects=False, headers={"Authorization": "Bearer "+self.token} if self.token else {})
        await self.http.__aenter__()
        self.connector = streamable_http_client(self.endpoint, http_client=self.http, max_sse_event_size=524288)
        try:
            return await self.connector.__aenter__()
        except BaseException:
            await self.http.aclose()
            raise

    async def __aexit__(self, *args):
        try:
            return await self.connector.__aexit__(*args)
        finally:
            await self.http.aclose()


@asynccontextmanager
async def connect_http(url, *, allowed_origins, token="", allow_localhost=False, protocol="2026-07-28", timeout=5):
    endpoint = urlsplit(url)
    origin = f"{endpoint.scheme}://{endpoint.netloc}"
    require(not endpoint.username and not endpoint.password and not endpoint.query and not endpoint.fragment and origin in allowed_origins and (endpoint.scheme == "https" or allow_localhost and endpoint.scheme == "http" and endpoint.hostname in ("127.0.0.1", "::1")), "MCP_URL_FORBIDDEN")
    require(protocol in ("2026-07-28", "legacy"), "MCP_PROTOCOL_FORBIDDEN")
    release, session = HTTP_CONNECTIONS.acquire(), None
    try:
        import asyncio
        async with asyncio.timeout(60):
            async with Client(HttpTransport(url, token, timeout), mode="legacy" if protocol == "legacy" else "auto", read_timeout_seconds=timeout) as client:
                require(protocol == "legacy" or client.protocol_version == protocol, "MCP_PROTOCOL_FORBIDDEN")
                session = Session(client, timeout=timeout)
                await session.list_tools()
                try:
                    yield session
                finally:
                    await session.close()
    finally:
        release()
