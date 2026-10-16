"""Explicitly configured, scope-bound MCP Streamable HTTP endpoint."""
from contextlib import asynccontextmanager
import secrets
import time
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount
from starlette.requests import Request
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from ..core import require
from .platform_server import create_platform_server


def create_platform_http_app(platform, scope, token, allowed_hosts, allowed_origins=(), path='/mcp'):
    require(token and allowed_hosts, 'MCP_AUTH_REQUIRED')
    server = create_platform_server(platform, scope)
    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True, max_request_body_size=262144,
        security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=list(allowed_hosts), allowed_origins=list(allowed_origins)))
    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield
    class Endpoint:
        def __init__(self):
            self.active, self.calls, self.reset = 0, 0, time.monotonic()+60
        async def __call__(self, scope, receive, send):
            request = Request(scope, receive=receive)
            if request.headers.get('host') not in allowed_hosts or request.headers.get('origin') and request.headers['origin'] not in allowed_origins:
                return await Response('Forbidden', 403)(scope, receive, send)
            if request.url.path.rstrip('/') != path or request.url.query:
                return await Response('Not found', 404)(scope, receive, send)
            if not secrets.compare_digest(request.headers.get('authorization', ''), 'Bearer '+token):
                return await Response('Unauthorized', 401, headers={'WWW-Authenticate': 'Bearer'})(scope, receive, send)
            if time.monotonic() >= self.reset:
                self.calls, self.reset = 0, time.monotonic()+60
            if self.active >= 8 or self.calls >= 120:
                return await Response('Busy', 429)(scope, receive, send)
            self.active += 1
            self.calls += 1
            try:
                await manager.asgi_app(scope, receive, send)
            finally:
                self.active -= 1
    return Starlette(routes=[Mount(path, app=Endpoint())], lifespan=lifespan)
