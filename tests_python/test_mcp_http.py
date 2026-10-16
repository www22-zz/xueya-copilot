import httpx
import pytest
from backend.platform import Platform
from backend.mcp.http_server import create_platform_http_app
from backend.mcp.http_client import connect_http
from backend.mcp.reference_tool import lookup_reference
from backend.core import DomainError


async def test_real_mcp_http_auth_discovery_and_scope(tmp_path):
    platform = Platform(tmp_path/'data')
    scope = platform.scope('course-default')
    app = create_platform_http_app(platform, scope, 'host-token', ['127.0.0.1:9999'])
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1:9999') as raw:
                assert (await raw.post('/mcp/', json={})).status_code == 401
                assert (await raw.post('/mcp/', headers={'Host': 'evil.example'}, json={})).status_code == 403
            async with connect_http('http://127.0.0.1:9999/mcp/', ['http://127.0.0.1:9999'], token='host-token', allow_localhost=True, transport=httpx.ASGITransport(app=app)) as client:
                tools = await client.list_tools()
                assert any(t.name == 'list_notes' for t in tools.tools)
                result = await client.call_tool('list_notes', {})
                assert result.structured_content['schemaVersion'] == '2.0'
                assert result.structured_content['data']['items'] == []
    finally:
        await platform.close()


async def test_http_client_rejects_untrusted_urls():
    for url in ['http://evil.example/mcp', 'https://user:secret@example.com/mcp', 'https://example.com/mcp?secret=x']:
        with pytest.raises(DomainError, match='MCP_URL_FORBIDDEN'):
            async with connect_http(url, ['https://example.com']):
                pass


async def test_optional_reference_only_sends_doi_and_is_not_course_evidence():
    observed = []
    def upstream(request):
        observed.append(request)
        return httpx.Response(200, json={'message': {'DOI': '10.1234/test', 'title': ['Public title'], 'publisher': 'Publisher'}})
    result = await lookup_reference('10.1234/test', enabled=True, transport=httpx.MockTransport(upstream))
    assert result['courseEvidence'] is False
    assert len(observed) == 1 and 'authorization' not in observed[0].headers
