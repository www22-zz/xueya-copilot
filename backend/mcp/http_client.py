from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import urlsplit
import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from ..core import require


@asynccontextmanager
async def connect_http(url, allowed_origins, token=None, timeout_ms=5000, allow_localhost=False, transport=None):
    endpoint = urlsplit(url)
    origin = endpoint.scheme+'://'+endpoint.netloc
    require(not endpoint.username and not endpoint.password and not endpoint.fragment and not endpoint.query and origin in allowed_origins and (endpoint.scheme == 'https' or allow_localhost and endpoint.scheme == 'http' and endpoint.hostname in ('127.0.0.1', '::1')), 'MCP_URL_FORBIDDEN')
    class BoundedStream(httpx.AsyncByteStream):
        def __init__(self, original):
            self.original = original
        async def __aiter__(self):
            total = 0
            async for chunk in self.original:
                total += len(chunk)
                require(total <= 524288, 'MCP_RESPONSE_TOO_LARGE')
                yield chunk
        async def aclose(self):
            await self.original.aclose()
    class Transport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.inner = transport or httpx.AsyncHTTPTransport(retries=0)
        async def handle_async_request(self, request):
            require(str(request.url) == url, 'MCP_URL_FORBIDDEN')
            response = await self.inner.handle_async_request(request)
            response.stream = BoundedStream(response.stream)
            return response
        async def aclose(self):
            await self.inner.aclose()
    async with httpx.AsyncClient(transport=Transport(), headers={'Authorization': 'Bearer '+token} if token else {}, timeout=timeout_ms/1000, follow_redirects=False) as http:
        class TransportContext:
            async def __aenter__(self):
                self.context = streamable_http_client(url, http_client=http)
                return await self.context.__aenter__()
            async def __aexit__(self, *args):
                return await self.context.__aexit__(*args)
        async with Client(TransportContext(), read_timeout_seconds=timeout_ms/1000) as client:
            yield client
