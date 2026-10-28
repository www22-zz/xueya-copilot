"""Controlled checks for MCP search and host-tracked chat speech. No paid requests."""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.xueya.agent import Agent
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider


def speech_app(tmp_path, handler, **options):
    config = Config(data_dir=tmp_path, api_key='controlled-only', api_slots=1, **options)
    provider = MimoProvider(config, transport=httpx.MockTransport(handler))
    return create_app(config, provider=provider)


def authorized(client):
    client.headers['X-Xueya-Token'] = client.get('/api/platform/bootstrap').json()['token']


def test_chat_tts_requires_token_and_uses_main_invocation_ledger(tmp_path):
    requests = []
    encoded = base64.b64encode(b'RIFF-controlled-audio').decode()

    def upstream(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload['model'] == 'mimo-v2.5-tts'
        assert payload['audio']['voice'] == 'mimo_default'
        assert len(payload['messages'][0]['content']) <= 1000
        return httpx.Response(200, json={'choices': [{'message': {'audio': {'data': encoded}}, 'finish_reason': 'stop'}],
                                         'usage': {'prompt_tokens': 10, 'completion_tokens': 20}})

    app = speech_app(tmp_path, upstream)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.post('/api/tts', json={'text': '正文'}).status_code == 403
        authorized(client)
        assert client.post('/api/tts', json={'text': '正文', 'voice': 'unknown'}).status_code == 400
        answer = client.post('/api/tts', json={'text': '**正文** [1]\n' + '一' * 1100}).json()
        assert answer['audio'] == 'data:audio/wav;base64,' + encoded
        assert answer['ok'] is True and len(requests) == 1
        assert '**' not in requests[0]['messages'][0]['content']
        rows = app.state.platform.db.all('SELECT status,course_id,usage_json FROM invocations')
        assert len(rows) == 1 and rows[0]['status'] == 'succeeded'
        assert rows[0]['course_id'] == 'course-default'
        assert json.loads(rows[0]['usage_json'])['completion_tokens'] == 20


def test_chat_tts_respects_shared_api_permit_and_unpriced_monetary_budget(tmp_path):
    calls = []
    app = speech_app(tmp_path / 'slots', lambda request: calls.append(request))
    with TestClient(app, base_url='http://127.0.0.1') as client:
        authorized(client)
        release = app.state.platform.resources.acquire('api')
        try:
            result = client.post('/api/tts', json={'text': '正文'}).json()
            assert result['ok'] is False and result['error'] == 'API_BUSY'
            assert not calls
        finally:
            release()
    app = speech_app(tmp_path / 'budget', lambda request: calls.append(request), run_budget_cny='1',
                     input_cny_per_million='1', output_cny_per_million='2')
    with TestClient(app, base_url='http://127.0.0.1') as client:
        authorized(client)
        result = client.post('/api/tts', json={'text': '正文'}).json()
        assert result['error'] == 'AI_PRICING_REQUIRED'
        assert not calls


def test_chat_tts_timeout_is_unknown_without_retry_or_error_leak(tmp_path):
    calls = []

    def unavailable(request):
        calls.append(request)
        raise httpx.ReadTimeout('private-upstream-detail')

    app = speech_app(tmp_path, unavailable)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        authorized(client)
        response = client.post('/api/tts', json={'text': '正文'})
        assert response.json()['ok'] is False and 'private-upstream-detail' not in response.text
        assert len(calls) == 1
        assert app.state.platform.db.one('SELECT status FROM invocations')['status'] == 'unknown'


@pytest.mark.parametrize('fails', [False, True])
async def test_web_search_uses_mcp_once_without_direct_paid_replay(monkeypatch, fails):
    calls = []
    web = {'id': 'web-controlled', 'title': '受控网页', 'quote': '工具返回的资料。',
           'location': 'https://example.com', 'url': 'https://example.com', 'isWeb': True}

    async def search(query, limit=5):
        calls.append((query, limit))
        if fails:
            raise TimeoutError('request outcome unknown')
        return {'sources': [web], 'warnings': []}

    monkeypatch.setattr('backend.xueya.web_search.search_tavily', search)

    class Model:
        config = Config(api_key='controlled-only', agent_planning_enabled=False)

        async def stream(self, messages, **options):
            yield {'type': 'content', 'text': '工具返回的资料。 [1]'}

    events = [event async for event in Agent(Model()).workflow({'question': '搜索近期学习资料', 'webSearch': True})]
    result = events[-1]
    assert len(calls) == 1
    assert result['toolCalls'][0]['tool'] == 'search_web'
    assert result['toolCalls'][0]['status'] == ('failed' if fails else 'completed')
    if not fails:
        assert result['sources'] == [web['id']]


def test_session_rename_and_branch_names_survive_persist_and_reload():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser state checks')
    source = r'''
const assert=require('node:assert/strict');
const L=require('./shared/learning.js');
const {createStore}=require('./frontend/js/state/workspace-store.js');
const values=new Map();const storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
let seq=0;const create=()=>createStore({storage,learning:L,id:()=>String(++seq)});
const store=create();store.state.messages.push({role:'user',text:'原始问题'},{role:'ai',text:'原始回答'});store.persist();
const original=store.state.sessionId;store.renameSession(original,'手动标题');store.persist();
assert.equal(store.state.sessions.find(s=>s.id===original).title,'手动标题');
const branch=store.branchSession(1);assert.match(branch.title,/分支/);store.persist();
const loaded=create();assert.equal(loaded.state.sessions.find(s=>s.id===original).title,'手动标题');
assert.match(loaded.state.sessions.find(s=>s.id===branch.id).title,/分支/);
loaded.togglePinSession(branch.id);assert.equal(loaded.state.sessions.find(s=>s.id===branch.id).pinned,true);
loaded.toggleArchiveSession(branch.id);assert.notEqual(loaded.state.sessionId,branch.id);
loaded.deleteSession(branch.id);assert.equal(loaded.state.sessions.some(s=>s.id===branch.id),false);
assert.equal(loaded.state.messages.length,2);
'''
    result = subprocess.run([node, '-e', source], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
