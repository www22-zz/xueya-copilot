import asyncio
import json
import time

from fastapi.testclient import TestClient
import pytest

from backend.xueya.app import create_app
from backend.xueya.config import Config, load_config
from backend.xueya.demo_import import DemoImport, MARKER
from backend.xueya.platform import Platform
from test_course_bundle import make_bundle


def setup_config(tmp_path, **options):
    root = tmp_path/'repo'
    directory = root/'materials/data-structures-algorithms'
    directory.parent.mkdir(parents=True)
    make_bundle(directory)
    return Config(root=root, data_dir=tmp_path/'data', auto_import_demo=True, **options), directory


def catalog(client):
    token = client.get('/api/platform/bootstrap').json()['token']
    return client.get('/api/platform/knowledge/catalog?courseId=course-default', headers={'X-Xueya-Token': token}).json()


def finished(client):
    for _ in range(300):
        value = catalog(client)
        state = value.get('demoImport')
        if state and state['status'] in ('completed', 'failed'):
            return value
        time.sleep(.03)
    raise AssertionError('demo preparation did not finish')


def test_empty_workspace_prepares_offline_and_restart_creates_no_more_jobs(tmp_path):
    config, _ = setup_config(tmp_path)
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        assert client.get('/api/health').status_code == 200
        result = finished(client)
        assert result['demoImport']['status'] == 'completed'
        assert result['demoImport']['completed'] == result['demoImport']['total'] == 1
        assert result['summary']['documents'] == 1 and result['summary']['sources'] == 3
        p = client.app.state.platform
        jobs = p.db.one('SELECT COUNT(*) n FROM jobs')['n']
        revisions = p.db.one('SELECT COUNT(*) n FROM revisions')['n']
        assert not p.db.all('SELECT * FROM invocations')
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        assert catalog(client)['demoImport']['status'] == 'completed'
        p = client.app.state.platform
        assert p.db.one('SELECT COUNT(*) n FROM jobs')['n'] == jobs
        assert p.db.one('SELECT COUNT(*) n FROM revisions')['n'] == revisions


@pytest.mark.parametrize('history', ['private', 'archived', 'deleted'])
def test_existing_document_history_is_not_seeded(tmp_path, history):
    config, _ = setup_config(tmp_path)
    platform = Platform(config.data_dir)
    platform.repo.put(platform.scope(), 'document', 'private', {'name': '私人资料.md', 'chunks': [], 'archived': history == 'archived'}, 0, deleted=history == 'deleted')
    platform.repo.put(platform.scope(), 'note', 'note', {'text': '我的笔记'}, 0)
    asyncio.run(platform.close())
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        assert 'demoImport' not in catalog(client)
        p = client.app.state.platform
        assert not p.db.one('SELECT 1 FROM jobs')
        assert p.repo.read(p.scope(), 'note', 'note')['value']['text'] == '我的笔记'
        assert p.repo.read(p.scope(), 'document', 'private', include_deleted=True)['version'] == 1


def test_stop_and_resume_reuses_original_upload(tmp_path, monkeypatch):
    config, _ = setup_config(tmp_path)
    original = DemoImport.wait

    async def hold(self, job):
        await asyncio.sleep(100)

    monkeypatch.setattr(DemoImport, 'wait', hold)
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        for _ in range(100):
            value = catalog(client)
            if value['documents']:
                document_id = value['documents'][0]['id']
                break
            time.sleep(.03)
        else:
            raise AssertionError('original upload was not submitted')
    monkeypatch.setattr(DemoImport, 'wait', original)
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        result = finished(client)
        assert result['demoImport']['status'] == 'completed'
        assert result['summary']['documents'] == 1 and result['summary']['sources'] == 3
        assert result['documents'][0]['id'] == document_id
        assert not client.app.state.platform.db.all('SELECT * FROM invocations')


def test_corrupt_bundle_stops_before_upload_and_explicit_retry_can_repair(tmp_path):
    config, bundle = setup_config(tmp_path)
    original = bundle/'lecture.pptx'
    raw = original.read_bytes()
    original.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        result = finished(client)
        assert result['demoImport']['status'] == 'failed'
        assert result['demoImport']['error'] == 'BUNDLE_ORIGINAL_HASH_MISMATCH'
        assert result['summary']['documents'] == 0
        token = client.get('/api/platform/bootstrap').json()['token']
        headers = {'X-Xueya-Token': token}
        assert client.post('/api/platform/knowledge/demo-retry', headers=headers, json={}).status_code == 400
        original.write_bytes(raw)
        assert client.post('/api/platform/knowledge/demo-retry', headers=headers, json={'confirmed': True}).status_code == 200
        assert finished(client)['demoImport']['status'] == 'completed'


def test_missing_materials_is_visible_and_disabled_mode_writes_nothing(tmp_path):
    config = Config(root=tmp_path/'missing', data_dir=tmp_path/'data', auto_import_demo=True)
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        result = finished(client)
        assert result['demoImport']['status'] == 'failed'
        assert result['demoImport']['error'] == 'DEMO_IMPORT_MATERIALS_UNAVAILABLE'
        assert result['summary']['documents'] == 0
    config = Config(root=tmp_path/'missing', data_dir=tmp_path/'disabled', auto_import_demo=False)
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        assert 'demoImport' not in catalog(client)
        p = client.app.state.platform
        assert p.repo.read(p.scope(), 'artifact', MARKER) is None
        assert not p.db.one('SELECT 1 FROM jobs')


def test_server_config_defaults_on_and_environment_can_opt_out(tmp_path, monkeypatch):
    monkeypatch.setattr('backend.xueya.config.ROOT', tmp_path)
    monkeypatch.delenv('XUEYA_AUTO_IMPORT_DEMO', raising=False)
    assert load_config().auto_import_demo is True
    monkeypatch.setenv('XUEYA_AUTO_IMPORT_DEMO', '0')
    assert load_config().auto_import_demo is False
