import asyncio
import json
import shutil

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.xueya.app import create_app
from backend.xueya.config import Config, ROOT
from backend.xueya.portable_corpus import load_corpus
from backend.xueya.rag_api import ApiSettings
from backend.xueya.rag_moark import QwenEmbeddingProvider
from backend.xueya.common import Scope
from backend.xueya.account_scope import account_owner
from tests.python.test_private_library_boundary import login


def test_package_has_no_private_state_and_rejects_changed_material(tmp_path):
    manifest, contents, rows = load_corpus(ROOT)
    assert len(contents) == 7 and manifest['sourceCount'] == 518 and len(rows) == 500
    assert all(set(r) == {'id','textHash','values'} for r in rows.values())
    root = tmp_path/'clone'
    shutil.copytree(ROOT/'资料库', root/'资料库')
    path = root/'资料库'/manifest['documents'][0]['file']
    path.chmod(0o666)
    path.write_text('changed', encoding='utf-8')
    with pytest.raises(Exception, match='CORPUS_MATERIAL_CHANGED'):
        load_corpus(root)


def test_fresh_account_installs_existing_vectors_without_calls_and_preserves_history(tmp_path):
    root = tmp_path/'clone'
    shutil.copytree(ROOT/'资料库', root/'资料库')
    config = Config(root=root, data_dir=tmp_path/'data', auto_import_corpus=True,
                    preserve_legacy_data=True, api_key='controlled-no-generation')
    class NoModel:
        async def generate(self, *args, **kwargs):
            raise AssertionError('Bundle import must never call a model')
    with TestClient(create_app(config, provider=NoModel()), base_url='http://127.0.0.1') as client:
        login(client, 'alice', True)
        boot = client.get('/api/platform/bootstrap').json()
        assert boot['portableCorpus']['status'] == 'completed', boot
        assert boot['portableCorpus']['newModelRequests'] == 0
        p = client.app.state.platform
        scope = Scope(user_id=account_owner({'username':'alice'}), course_id='course-default')
        docs = p.repo.all(scope, 'document')
        assert len(docs) == 7 and all(d['indexStatus'] == 'ready' for d in docs)
        assert sum(len(d['chunks']) for d in docs) == 518
        assert len(p.repo.all(scope, 'vector')) == 500
        assert not p.db.one('SELECT id FROM invocations')
        assert not p.db.one("SELECT id FROM jobs WHERE resource='api'")
        # A real query path uses the installed cache: only one query embedding,
        # with a controlled provider here, never document embedding requests.
        rag = client.app.state.rag
        identity = docs[0]['embeddingIdentity']
        vector = p.repo.all(scope, 'vector')[0]['values']
        calls=[]
        def upstream(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={'model':identity['model'], 'data':[{'index':0,'embedding':vector}]})
        rag.embedding = QwenEmbeddingProvider(p, ApiSettings(key='test',model=identity['model'],
            base_url=identity['provider'],dimension=4096), transport=httpx.MockTransport(upstream))
        result = asyncio.run(rag.search(scope, '二叉树遍历', mode='vector'))
        assert result['sources'] and not result['warnings']
        assert len(calls) == 1 and len(calls[0]['input']) == 1
        doc=docs[0]
        client.app.state.library.organize(scope, {'documentId':doc['id'],'version':doc['version'],'action':'archive'})
        before=p.db.one('SELECT count(*) AS n FROM revisions')['n']
        client.get('/api/platform/bootstrap')
        assert p.db.one('SELECT count(*) AS n FROM revisions')['n'] == before
    with TestClient(create_app(config, provider=NoModel()), base_url='http://127.0.0.1') as client:
        login(client, 'alice')
        boot=client.get('/api/platform/bootstrap').json()
        p=client.app.state.platform
        assert len(p.repo.all(scope,'document')) == 7
        assert next(d for d in p.repo.all(scope,'document') if d['id']==doc['id'])['archived']
        assert len(boot['portableCorpus']['documentIds']) == 7
