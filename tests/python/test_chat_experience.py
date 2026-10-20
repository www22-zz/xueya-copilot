import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider


@pytest.mark.parametrize('already_running', [True, False])
def test_launcher_opens_globe_in_both_start_paths(tmp_path, monkeypatch, already_running):
    from scripts import launch
    python = tmp_path/'.venv/Scripts/python.exe'
    python.parent.mkdir(parents=True)
    python.touch()
    lock = tmp_path/'requirements.lock'
    lock.write_bytes(b'')
    (tmp_path/'.venv/xueya-launch-dependencies.txt').write_text(hashlib.sha256(b'').hexdigest())
    directory = tmp_path/'data'
    directory.mkdir()
    identity = {'port': 43210, 'instanceId': 'controlled'}
    monkeypatch.setattr(launch, 'ROOT', tmp_path)
    monkeypatch.setattr(launch.sys, 'executable', str(python))
    monkeypatch.setattr(launch.os, 'chdir', lambda path: None)
    monkeypatch.setattr(launch.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    import backend.xueya.config as config
    monkeypatch.setattr(config, 'load_config', lambda: SimpleNamespace(data_dir=directory))
    monkeypatch.setattr(launch, 'ready', lambda *a: True)
    opened = []
    monkeypatch.setattr(launch.webbrowser, 'open', opened.append)
    if already_running:
        (directory/'server.json').write_text(json.dumps(identity))
    else:
        def spawn(*a, **k):
            (directory/'server.json').write_text(json.dumps(identity))
            return SimpleNamespace(poll=lambda: None)
        monkeypatch.setattr(launch.subprocess, 'Popen', spawn)
    launch.main()
    assert opened == ['http://127.0.0.1:43210/#home']


@pytest.mark.parametrize('with_materials', [False, True, 'unrelated'])
def test_image_question_uses_scoped_media_and_existing_invocation_ledger(tmp_path, with_materials):
    captured = []
    def upstream(request):
        value = json.loads(request.content)
        captured.append(value)
        result = json.dumps({'answer': '图中是三角形。', 'sources': ['s1'] if with_materials is True else []}, ensure_ascii=False)
        stream = 'data: '+json.dumps({'choices': [{'delta': {'content': result}}]})+'\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=stream, headers={'Content-Type': 'text/event-stream'})
    config = Config(data_dir=tmp_path/'data', api_key='controlled-image-test', base_url='https://controlled.invalid/v1')
    app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)))
    with TestClient(app, base_url='http://127.0.0.1') as client:
        headers = {'X-Xueya-Token': client.get('/api/platform/bootstrap').json()['token']}
        if with_materials:
            source = {'id': 's1', 'title': '三角形', 'quote': '三角形有三条边。', 'keywords': ['三角形']} if with_materials is True else {'id': 's1', 'title': '植物', 'quote': '叶绿体参与光合作用。', 'keywords': ['叶绿体']}
            app.state.platform.repo.put(app.state.platform.scope('course-default'), 'source', 's1', source, 0)
        media = client.post('/api/learning/media/upload?name=figure.png', content=b'controlled-image', headers={**headers, 'Content-Type': 'image/png'}).json()['result']
        payload = {'question': '三角形的定义是什么？看图解释。', 'media': [{'id': media['id'], 'version': 1}]}
        response = client.post('/api/learning/chat/respond', json=payload, headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()['result']
        assert '三角形' in result['answer'] and result['sources'] == (['s1'] if with_materials is True else [])
        assert result['verification'] == ('course-citations-only' if with_materials is True else 'image-not-course-verified')
        assert result['online']
        parts = captured[0]['messages'][-1]['content']
        assert any(p['type'] == 'image_url' and p['image_url']['url'].startswith('data:image/png;base64,') for p in parts)
        calls = app.state.platform.db.all('SELECT * FROM invocations')
        assert len(calls) == 1 and calls[0]['status'] == 'succeeded'
        context = app.state.platform.db.one('SELECT value FROM meta WHERE key=?', ('invocation-context:'+calls[0]['id'],))
        assert json.loads(context['value'])['capability'] == 'image'
        app.state.platform.repo.ensure_course(app.state.platform.user_id, {'id': 'other', 'name': 'Other'})
        assert client.post('/api/learning/chat/respond?courseId=other', json=payload, headers=headers).status_code == 404
        assert len(captured) == 1
        assert client.post('/api/learning/chat/respond', json=payload).status_code == 403


def test_unconfigured_image_chat_does_not_call_model(client):
    response = client.post('/api/learning/chat/respond', headers=client.platform_headers, json={'question': 'test', 'media': [{'id': 'missing', 'version': 1}]})
    assert response.status_code == 503 or response.json()['error'] == 'IMAGE_MODEL_NOT_CONFIGURED'
    assert not client.platform.db.all('SELECT * FROM invocations')
