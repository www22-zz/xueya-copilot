"""Promote real, already computed vectors without issuing another model request.

The source file, provider identity, quote hashes, dimensions and every required
cache key must match before mutation. The normal index job runs with networking
disabled, so a missing cache entry cannot become an unnoticed billable request.
"""
import hashlib
import json

import httpx

from backend.xueya.common import digest, require
from backend.xueya.rag_api import ApiSettings
from backend.xueya.rag_moark import QwenEmbeddingProvider
from backend.xueya.rag_search import normalize
from scripts.import_prepared_pdf import finish


async def promote(p, rag, scope, document_id, cache, provenance, *, expected_identity):
    raw = cache.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == provenance.get('cacheSha256'), 'VECTOR_CACHE_HASH_MISMATCH')
    value = json.loads(raw)
    doc = rag.document(scope, document_id, active=True)
    identity = value.get('identity')
    require(value.get('schema') == 'validated-vector-cache-v1' and value.get('materialSha256') == doc['fileHash']
            and provenance.get('materialSha256') == doc['fileHash'], 'VECTOR_MATERIAL_HASH_MISMATCH')
    require(identity == expected_identity and identity.get('model') == 'Qwen3-VL-Embedding-2B'
            and identity.get('dimension') == 2048, 'VECTOR_IDENTITY_MISMATCH')
    rows = value.get('rows')
    require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), 'INVALID_VECTOR_CACHE')
    by_id = {row.get('id'): row for row in rows}
    require(len(by_id) == len(rows), 'INVALID_VECTOR_CACHE')
    sources = rag.sources(scope, document_ids=[document_id])
    require(bool(sources) and value.get('sourceCount') == len(sources), 'VECTOR_SOURCE_COUNT_MISMATCH')
    needed = {}
    for source in sources:
        require(rag.validate(scope, source), 'INVALID_CITATION')
        key = rag._cache_id(identity, source['quote'])
        row = by_id.get(key)
        require(row and row.get('identity') == identity and row.get('textHash') == digest(source['quote']), 'VECTOR_CACHE_INCOMPLETE')
        normalized = normalize(row.get('values'), identity['dimension'])
        require(max(abs(a-b) for a, b in zip(normalized, row['values'])) < 1e-6, 'VECTOR_NOT_NORMALIZED')
        needed[key] = {k: row[k] for k in ('identity', 'textHash', 'values')}
    require(set(needed) == set(by_id), 'VECTOR_CACHE_HAS_UNRELATED_TEXT')

    def no_network(request):
        raise AssertionError('A validated cache promotion must never make a network request')

    rag.embedding = QwenEmbeddingProvider(p, ApiSettings(key='offline-cache-promotion', model=identity['model'],
        base_url=identity['provider'], revision=identity['revision'], dimension=identity['dimension']),
        transport=httpx.MockTransport(no_network), name='moark-qwen-embedding')
    require(rag.embedding.identity == identity, 'VECTOR_IDENTITY_MISMATCH')
    with p.db.transaction():
        require(rag.document(scope, document_id)['version'] == doc['version'], 'VERSION_CONFLICT')
        for key, row in needed.items():
            previous = p.repo.read(scope, 'vector', key, include_deleted=True)
            p.repo.put(scope, 'vector', key, row, previous['version'] if previous else 0)
    before = p.db.one('SELECT count(*) n FROM invocations')['n']
    job = rag.submit(scope, 'rag-index', document_id, 'validated-cache-'+doc['fileHash'], expected_version=doc['version'])
    p.jobs.stopped = False
    done = await finish(p, job)
    require(done['result']['computed'] == 0 and done['result']['cached'] == len(needed), 'CACHE_PROMOTION_NOT_OFFLINE')
    require(p.db.one('SELECT count(*) n FROM invocations')['n'] == before, 'CACHE_PROMOTION_NOT_OFFLINE')
    return {'documentId': document_id, 'identity': identity, 'sourceCount': len(sources), 'cachedVectors': len(needed),
            'newModelRequests': 0, 'result': done['result']}
