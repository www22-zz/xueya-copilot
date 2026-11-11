"""Install the distributable teaching material/cache on a fresh local account.

No credentials, private database, external call or new document embeddings are
part of installation. Uses the existing repository, FileStore and CPU parser.
"""
import asyncio
import gzip
import hashlib
import io
import json
import logging

from .common import Scope, digest, require
from .rag_search import normalize

log = logging.getLogger(__name__)
MARKER = 'portable-stack-queue-v1'
MAX_CACHE = 16*1024*1024


def load_bundle(root):
    directory = root/'materials/stack-queue'
    manifest = json.loads((directory/'portable/manifest.json').read_text('utf-8'))
    require(manifest.get('schema') == MARKER and manifest.get('vectorFile') == 'vectors.json.gz', 'INVALID_PORTABLE_BUNDLE')
    material = directory/'栈与队列知识库.md'
    content = material.read_bytes()
    require(hashlib.sha256(content).hexdigest() == manifest['materialSha256'], 'PORTABLE_MATERIAL_CHANGED')
    path = directory/'portable/vectors.json.gz'
    require(path.stat().st_size <= MAX_CACHE, 'PORTABLE_CACHE_TOO_LARGE')
    packed = path.read_bytes()
    require(hashlib.sha256(packed).hexdigest() == manifest['compressedSha256'], 'PORTABLE_CACHE_CHANGED')
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
        raw = stream.read(MAX_CACHE+1)
    require(len(raw) <= MAX_CACHE and len(raw) == manifest['uncompressedBytes']
            and hashlib.sha256(raw).hexdigest() == manifest['cacheSha256'], 'PORTABLE_CACHE_CHANGED')
    cache = json.loads(raw)
    require(cache.get('schema') == 'validated-vector-cache-v1' and cache['materialSha256'] == manifest['materialSha256']
            and cache['identity'] == manifest['identity'] and cache['sourceCount'] == manifest['sourceCount'], 'PORTABLE_CACHE_IDENTITY_MISMATCH')
    identity = cache['identity']
    require(identity.get('model') == 'Qwen3-VL-Embedding-2B' and identity.get('dimension') == 2048
            and identity.get('adapter') == 'moark-qwen-text-v2', 'PORTABLE_MODEL_MISMATCH')
    return content, manifest, cache


class PortableKnowledge:
    def __init__(self, knowledge, config):
        self.kb, self.p, self.config = knowledge, knowledge.p, config
        self.locks = {}
        self.loaded = None

    async def ensure(self, owner):
        if not self.config.auto_import_stack:
            return None
        async with self.locks.setdefault(owner, asyncio.Lock()):
            scope = Scope(user_id=owner, course_id='course-default')
            self.p.repo.require_course(scope)
            prior = self.p.repo.read(scope, 'artifact', MARKER)
            if prior:
                return prior['value']
            # Even archived/deleted history must not be silently repopulated.
            existing = self.p.repo.all(scope, 'document')
            matching = [d for d in existing if d.get('fileHash') == '7a36da9a2a222b39d22c13a720f587f7f2d21073dbfbcccc9b2769c222d0652a'
                        and not any(d.get(k) for k in ('archived', 'deleted', 'superseded'))]
            history = self.p.db.one("SELECT id FROM entities WHERE user_id=? AND course_id=? AND kind='document' LIMIT 1", (owner, scope.course_id))
            if history and not matching:
                return {'status': 'skipped-existing-history'}
            if matching:
                jobs = self.p.db.all("SELECT input FROM jobs WHERE user_id=? AND course_id=? AND type='rag-index' AND status IN ('queued','running','cancelling')", (owner, scope.course_id))
                if any(json.loads(j['input']).get('documentId') == matching[0]['id'] for j in jobs):
                    return {'status': 'deferred-active-index'}
            try:
                if self.loaded is None:
                    self.loaded = await asyncio.to_thread(load_bundle, self.config.root)
                content, manifest, cache = self.loaded
                if matching:
                    doc = matching[0]
                else:
                    uploaded = self.kb.upload(scope, content, '栈与队列知识库.md', '栈与队列', 'portable-'+manifest['materialSha256'])
                    for _ in range(3000):
                        await self.p.jobs.tick()
                        state = self.p.jobs.get(uploaded['job']['id'], owner)
                        if state['status'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
                            require(state['status'] == 'succeeded', 'PORTABLE_PARSE_FAILED')
                            break
                        await asyncio.sleep(.02)
                    else:
                        raise RuntimeError('PORTABLE_PARSE_TIMEOUT')
                    doc = self.kb.rag.document(scope, uploaded['documentId'])
                result = self.publish(scope, doc, manifest, cache)
                return result
            except Exception as error:
                code = getattr(error, 'code', 'PORTABLE_IMPORT_FAILED')
                log.warning('Portable knowledge installation stopped: %s', code)
                result = {'status': 'failed', 'error': code}
                self.p.repo.put(scope, 'artifact', MARKER, result, 0)
                return result

    def publish(self, scope, doc, manifest, cache):
        rag = self.kb.rag
        sources = rag.sources(scope, document_ids=[doc['id']])
        identity = cache['identity']
        require(doc['fileHash'] == manifest['materialSha256'] and len(sources) == cache['sourceCount'], 'PORTABLE_SOURCE_MISMATCH')
        rows = {r['id']: r for r in cache['rows']}
        require(len(rows) == len(cache['rows']), 'PORTABLE_DUPLICATE_VECTORS')
        needed = {}
        for source in sources:
            require(rag.validate(scope, source), 'INVALID_CITATION')
            key = rag._cache_id(identity, source['quote'])
            row = rows.get(key)
            require(row and row.get('identity') == identity and row.get('textHash') == digest(source['quote']), 'PORTABLE_TEXT_MISMATCH')
            values = normalize(row['values'], identity['dimension'])
            require(max(abs(a-b) for a,b in zip(values,row['values'])) < 1e-6, 'PORTABLE_VECTOR_NOT_NORMALIZED')
            needed[key] = {k: row[k] for k in ('identity','textHash','values')}
        require(set(needed) == set(rows), 'PORTABLE_UNRELATED_VECTORS')
        result = {'status': 'completed', 'documentId': doc['id'], 'sources': len(sources), 'cachedVectors': len(needed),
                  'model': identity['model'], 'newModelRequests': 0}
        with self.p.db.transaction():
            current = rag.document(scope, doc['id'], active=True)
            require(current['version'] == doc['version'], 'VERSION_CONFLICT')
            for key, row in needed.items():
                old = self.p.repo.read(scope, 'vector', key, include_deleted=True)
                if not old or old['deleted'] or old['value'] != row:
                    self.p.repo.put(scope, 'vector', key, row, old['version'] if old else 0)
            if current.get('embeddingIdentity') != identity or current.get('indexStatus') != 'ready':
                self.p.repo.put(scope, 'document', doc['id'], {**current, 'embeddingIdentity': identity, 'indexStatus': 'ready'}, current['version'])
            name = '栈与队列知识库'
            profile_id = 'source-bound-knowledge-base'
            old = self.p.repo.read(scope, 'artifact', profile_id)
            profile = {'kind': profile_id, 'name': name, 'documentId': doc['id'], 'fileHash': doc['fileHash']}
            if not old or old['value'] != profile:
                self.p.repo.put(scope, 'artifact', profile_id, profile, old['version'] if old else 0)
            self.p.repo.ensure_course(scope.user_id, {'id': scope.course_id, 'name': name})
            self.p.repo.put(scope, 'artifact', MARKER, result, 0)
        return result
