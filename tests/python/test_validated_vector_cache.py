import hashlib
import json
import asyncio

import pytest

from backend.xueya.common import AppError, digest, Scope
from backend.xueya.rag_api import ApiSettings
from backend.xueya.rag_moark import QwenEmbeddingProvider
from backend.xueya.rag_service import RagService
from scripts.import_validated_vector_cache import promote


@pytest.mark.asyncio
@pytest.mark.parametrize('owner', ['local-user', 'account-cached-vectors'])
async def test_cache_requires_exact_source_identity_and_promotes_without_network(platform, tmp_path, owner):
    rag = RagService(platform)
    platform.repo.ensure_course(owner, {'id': 'course-default', 'name': '缓存恢复测试'})
    scope = Scope(user_id=owner, course_id='course-default')
    job = rag.upload(scope, '# 规则\n\n栈遵循后进先出。'.encode(), 'rules.md', 'rules')
    platform.jobs.stopped = False
    for _ in range(500):
        await platform.jobs.tick()
        done = platform.jobs.get(job['id'], owner)
        if done['status'] in ('succeeded', 'failed'):
            break
        await asyncio.sleep(.01)
    assert done['status'] == 'succeeded'
    doc_id = done['result']['documentId']
    doc = rag.document(scope, doc_id)
    identity = QwenEmbeddingProvider(platform, ApiSettings(model='Qwen3-VL-Embedding-2B', dimension=2048,
                                    base_url='https://api.moark.com/v1')).identity
    # Synthetic vectors are only a unit fixture, never a claimed real embedding.
    sources = rag.sources(scope, document_ids=[doc_id])
    rows = [{'id': rag._cache_id(identity, s['quote']), 'identity': identity,
             'textHash': digest(s['quote']), 'values': [1.0]+[0.0]*2047} for s in sources]
    bundle = {'schema': 'validated-vector-cache-v1', 'materialSha256': doc['fileHash'], 'identity': identity,
              'sourceCount': len(sources), 'rows': rows}
    path = tmp_path/'cache.json'
    path.write_text(json.dumps(bundle), encoding='utf-8')
    proof = {'materialSha256': doc['fileHash'], 'cacheSha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    with pytest.raises(AppError, match='VECTOR_CACHE_HASH_MISMATCH'):
        await promote(platform, rag, scope, doc_id, path, {**proof, 'cacheSha256': 'bad'}, expected_identity=identity)
    with pytest.raises(AppError, match='VECTOR_IDENTITY_MISMATCH'):
        await promote(platform, rag, scope, doc_id, path, proof, expected_identity={**identity, 'revision': 'wrong'})
    assert not platform.repo.all(scope, 'vector')
    platform.jobs.stopped = True  # A freshly opened CLI platform has no running worker.
    result = await promote(platform, rag, scope, doc_id, path, proof, expected_identity=identity)
    assert result['newModelRequests'] == result['result']['computed'] == 0
    assert result['cachedVectors'] == len(rows)
    current = rag.document(scope, doc_id)
    assert current['indexStatus'] == 'ready' and current['embeddingIdentity'] == identity
    plan = rag.index_plan(scope, doc_id)
    assert plan['cachedVectors'] == len(rows) and plan['missingVectors'] == 0
    assert not plan['requiresExternal']
    assert not platform.db.one('SELECT id FROM invocations')
    # Reparse invalidates the index binding but keeps matching content vectors.
    parsed = rag.submit(scope, 'rag-parse', doc_id, 'reparse', expected_version=current['version'])
    for _ in range(500):
        await platform.jobs.tick()
        done = platform.jobs.get(parsed['id'], owner)
        if done['status'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
            break
        await asyncio.sleep(.01)
    assert done['status'] == 'succeeded'
    assert rag.document(scope, doc_id)['indexStatus'] == 'not_indexed'
    restored = await promote(platform, rag, scope, doc_id, path, proof, expected_identity=identity)
    assert restored['newModelRequests'] == restored['result']['computed'] == 0
    assert rag.document(scope, doc_id)['indexStatus'] == 'ready'
