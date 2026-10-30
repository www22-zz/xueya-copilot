import hashlib
import json

import pytest

from backend.xueya.common import AppError, digest
from backend.xueya.rag_api import ApiSettings
from backend.xueya.rag_moark import QwenEmbeddingProvider
from backend.xueya.rag_service import RagService
from scripts.import_validated_vector_cache import promote
from test_rag import completed


@pytest.mark.asyncio
async def test_cache_requires_exact_source_identity_and_promotes_without_network(platform, tmp_path):
    rag = RagService(platform)
    scope = platform.scope()
    done = await completed(platform, rag.upload(scope, '# 规则\n\n栈遵循后进先出。'.encode(), 'rules.md', 'rules'))
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
    assert not platform.db.one('SELECT id FROM invocations')
