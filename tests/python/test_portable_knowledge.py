import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.common import Scope
from backend.xueya.portable_knowledge import load_bundle, MARKER
from backend.xueya.rag_api import ApiSettings
from backend.xueya.rag_moark import QwenEmbeddingProvider
from tests.python.test_private_library_boundary import login

ROOT = Path(__file__).resolve().parents[2]


def prepare_root(tmp_path):
    root = tmp_path/'repo'
    shutil.copytree(ROOT/'materials/stack-queue', root/'materials/stack-queue')
    return root


def test_distributable_bundle_is_bound_to_exact_material_and_model():
    content, manifest, cache = load_bundle(ROOT)
    assert hashlib.sha256(content).hexdigest() == manifest['materialSha256']
    assert len(cache['rows']) == cache['sourceCount'] == 178
    assert cache['identity']['dimension'] == 2048
    # Teaching vectors carry content hashes and values, never account scope/keys.
    assert all(set(r) == {'id','identity','textHash','values'} for r in cache['rows'])


def test_fresh_clone_accounts_get_cache_without_model_calls_and_restart_is_idempotent(tmp_path):
    root = prepare_root(tmp_path)
    config = Config(root=root, data_dir=tmp_path/'fresh-data', auto_import_stack=True, preserve_legacy_data=True)
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        headers = login(client, 'alice', True)  # No developer DB, password or .env.
        boot = client.get('/api/platform/bootstrap').json()
        assert boot['portableKnowledge']['status'] == 'completed'
        assert boot['portableKnowledge']['newModelRequests'] == 0
        p = client.app.state.platform
        owner = next(r['user_id'] for r in p.db.all("SELECT user_id FROM courses WHERE user_id LIKE 'account-%'"))
        scope = Scope(user_id=owner, course_id='course-default')
        docs = p.repo.all(scope, 'document')
        assert len(docs) == 1 and docs[0]['indexStatus'] == 'ready'
        assert len(p.repo.all(scope, 'vector')) == 178
        assert p.repo.courses(owner)[0]['name'] == '栈与队列知识库'
        # A matching provider can consume imported vectors with a single query
        # embedding. The controlled fixture does not claim real model accuracy.
        import httpx, asyncio
        identity = docs[0]['embeddingIdentity']; calls = []
        vector = p.repo.all(scope, 'vector')[0]['values']
        def upstream(request):
            payload = json.loads(request.content); calls.append(payload)
            return httpx.Response(200, json={'model': identity['model'], 'data': [{'index':0,'embedding':vector}]})
        rag = client.app.state.rag
        rag.embedding = QwenEmbeddingProvider(p, ApiSettings(key='test-only', model=identity['model'], base_url=identity['provider'], dimension=2048), transport=httpx.MockTransport(upstream))
        result = asyncio.run(rag.search(scope, '循环队列', mode='vector'))
        assert result['sources'] and not result['warnings']
        assert len(calls) == 1 and len(calls[0]['input']) == 1
        before = len(p.repo.all(scope, 'vector'))
        login(client, 'bobby', True)
        assert client.get('/api/platform/bootstrap').json()['portableKnowledge']['sources'] == 178
        assert len(p.repo.all(scope, 'vector')) == before
        # Ignore the controlled query above; import never issued an embedding call.
        assert p.db.one('SELECT count(*) AS n FROM invocations')['n'] == 1
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        login(client, 'alice')
        p = client.app.state.platform
        before = p.db.one('SELECT count(*) AS n FROM revisions')['n']
        assert client.get('/api/platform/bootstrap').json()['portableKnowledge']['status'] == 'completed'
        assert p.db.one('SELECT count(*) AS n FROM revisions')['n'] == before


@pytest.mark.parametrize('broken', ['material', 'vectors'])
def test_changed_material_fails_without_publishing_document(tmp_path, broken):
    root = prepare_root(tmp_path)
    if broken == 'material':
        (root/'materials/stack-queue/栈与队列知识库.md').write_text('changed text', encoding='utf-8')
    else:
        (root/'materials/stack-queue/portable/vectors.json.gz').write_bytes(b'broken')
    config = Config(root=root, data_dir=tmp_path/'bad-data', auto_import_stack=True)
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        reply = client.get('/api/platform/bootstrap').json()
        assert reply['portableKnowledge'] == {'status':'failed','error':'PORTABLE_MATERIAL_CHANGED' if broken == 'material' else 'PORTABLE_CACHE_CHANGED'}
        assert client.app.state.platform.repo.all(client.app.state.platform.scope(), 'document') == []
        assert not client.app.state.platform.db.one('SELECT id FROM invocations')


def test_archived_material_is_not_automatically_restored_on_restart(tmp_path):
    config = Config(root=prepare_root(tmp_path), data_dir=tmp_path/'data', auto_import_stack=True)
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        client.get('/api/platform/bootstrap')
        p = client.app.state.platform; scope = p.scope()
        doc = p.repo.all(scope, 'document')[0]
        client.app.state.library.organize(scope, {'documentId':doc['id'],'version':doc['version'],'action':'archive'})
    with TestClient(create_app(config), base_url='http://127.0.0.1') as client:
        client.get('/api/platform/bootstrap')
        p = client.app.state.platform
        assert len(p.repo.all(p.scope(), 'document')) == 1
        assert p.repo.all(p.scope(), 'document')[0]['archived']
