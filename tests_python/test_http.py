import json
from pathlib import Path
import httpx
import pytest
from backend.app import create_app
from backend.core import dumps


class ControlledModel:
    def __init__(self):
        self.calls = []

    async def generate(self, request):
        self.calls.append(request)
        user = request['messages'][-1]['content']
        if '通用问答' in request['messages'][0]['content']:
            return {'model': 'controlled', 'content': dumps({'answer': '可以固定起床时间，逐步调整作息。', 'sources': ['forged']})}
        parsed = json.loads(user)
        source = parsed['materials'][0]
        if '知识点整理助手' in request['messages'][0]['content']:
            return {'model': 'controlled', 'content': dumps([{'name': '节点', 'sourceId': source['id']}, {'name': '伪造', 'sourceId': 'forged'}])}
        if '出题助手' in request['messages'][0]['content']:
            return {'model': 'controlled', 'content': dumps([{'prompt': '节点是什么？', 'options': ['组成部分', '无关'], 'answer': 0, 'sourceId': source['id']}])}
        return {'model': 'controlled', 'content': dumps({'answer': source['quote'], 'sources': [source['id'], 'forged']})}

    async def stream(self, request):
        result = await self.generate(request)
        for i in range(0, len(result['content']), 7):
            yield {'type': 'content', 'text': result['content'][i:i+7], 'model': 'controlled'}


@pytest.fixture
def application():
    root = Path(__file__).resolve().parent.parent
    return create_app({'root': root, 'ai': {'apiKey': 'test-only', 'model': 'controlled'}}, model=ControlledModel())


@pytest.mark.parametrize('path', ['/.env', '/.git/config', '/backend/server.py', '/backend/config.py', '/requirements.txt', '/README.md', '/docs/api-contracts.md', '/%2e%2e/.env', '/shared/private.js'])
async def test_private_files_are_never_served(application, path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
        assert (await client.get(path)).status_code == 404


@pytest.mark.parametrize('path', ['/', '/css/styles.css', '/js/app.js', '/shared/learning.js', '/shared/agent/tasks.js', '/assets/mark.svg'])
async def test_frontend_assets(application, path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
        assert (await client.get(path)).status_code == 200


async def test_chat_json_stream_general_and_grounded(application, course):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
        health = (await client.get('/api/health')).json()
        assert health['runtime'] == 'python'
        greeting = (await client.post('/api/agent', json={'question': '你好'})).json()
        assert '你好' in greeting['answer'] and not application.state.model.calls
        general = (await client.post('/api/agent', json={'question': '怎样早睡？', 'sources': []})).json()
        assert general['engine'] == 'general-chat' and general['sources'] == []
        assert (await client.post('/api/ai', json={'question': '根据资料回答', 'sources': []})).json()['error'] == 'NO_SOURCES'
        result = (await client.post('/api/ai', json={'question': '节点是什么', 'sources': course['sources']})).json()
        assert result['sources'] == ['s'] and result['verification'] == 'verbatim-only'
        response = await client.post('/api/ai/stream', json={'question': '节点是什么', 'sources': course['sources']})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert events[-1]['type'] == 'done' and events[-1]['sources'] == ['s']
        response = await client.post('/api/agent/stream', json={'question': '有什么日常建议？'})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert events[-1]['engine'] == 'general-chat'


async def test_request_errors_practice_and_limits(application, course):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
        assert (await client.post('/api/ai', content='{')).status_code == 400
        assert (await client.post('/api/ai/stream', json={'question': ''})).status_code == 400
        assert (await client.post('/api/ai', content=b'x'*524289)).status_code == 413
        assert (await client.put('/hello')).status_code == 405
        topics = (await client.post('/api/topics', json={'sources': course['sources']})).json()
        assert topics['ok'] and len(topics['topics']) == 1
        questions = (await client.post('/api/questions', json={'sources': course['sources']})).json()
        assert questions['ok'] and questions['questions'][0]['answer'] == 0
        assert (await client.post('/api/parse?type=exe', content=b'anything')).status_code == 400


async def test_pdf_docx_parse_and_empty_documents(application):
    import io
    from docx import Document
    from pypdf import PdfWriter
    document, stream = Document(), io.BytesIO()
    document.add_paragraph('Python 迁移：节点是树的组成部分。')
    document.save(stream)
    pdf, binary = PdfWriter(), io.BytesIO()
    pdf.add_blank_page(width=100, height=100)
    pdf.write(binary)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
        result = (await client.post('/api/parse?type=docx', content=stream.getvalue())).json()
        assert '节点是树的组成部分' in result['text']
        result = (await client.post('/api/parse?type=pdf', content=binary.getvalue())).json()
        assert result['ok'] and result['empty']
        assert not (await client.post('/api/parse?type=pdf', content=b'bad-pdf')).json()['ok']
