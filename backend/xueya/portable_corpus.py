"""Add the approved seven-file vector bundle to each local account without external calls."""
import asyncio
import gzip
import hashlib
import io
import json
import logging
import time

from .common import Scope, digest, require
from .rag_search import normalize

MARKER = 'portable-dsa-md-v1'
LIMIT = 96 * 1024 * 1024
log = logging.getLogger(__name__)


def load_corpus(root):
    directory = root/'资料库'
    manifest = json.loads((directory/'portable/manifest.json').read_text('utf-8'))
    require(manifest.get('schema') == MARKER and manifest.get('vectorFile') == 'vectors.json.gz', 'INVALID_CORPUS_BUNDLE')
    identity = manifest['identity']
    require(identity.get('model') == 'Qwen3-VL-Embedding-8B' and identity.get('dimension') == 4096
            and identity.get('adapter') == 'moark-qwen-text-v2', 'CORPUS_MODEL_MISMATCH')
    require(len(manifest['documents']) == 7, 'INVALID_CORPUS_DOCUMENTS')
    contents = {}
    for item in manifest['documents']:
        name = item['file']
        require(isinstance(name, str) and '/' not in name and '\\' not in name and name.endswith('.md'), 'INVALID_CORPUS_PATH')
        raw = (directory/name).read_bytes()
        require(len(raw) <= 1_048_576 and hashlib.sha256(raw).hexdigest() == item['sha256'], 'CORPUS_MATERIAL_CHANGED')
        require(name not in contents, 'DUPLICATE_CORPUS_FILE')
        contents[name] = raw
    path = directory/'portable/vectors.json.gz'
    require(path.stat().st_size <= LIMIT, 'CORPUS_CACHE_TOO_LARGE')
    packed = path.read_bytes()
    require(hashlib.sha256(packed).hexdigest() == manifest['compressedSha256'], 'CORPUS_CACHE_CHANGED')
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
        raw = stream.read(LIMIT+1)
    require(len(raw) <= LIMIT and len(raw) == manifest['uncompressedBytes']
            and hashlib.sha256(raw).hexdigest() == manifest['cacheSha256'], 'CORPUS_CACHE_CHANGED')
    cache = json.loads(raw)
    require(cache.get('schema') == MARKER and cache.get('identity') == identity
            and cache.get('documents') == manifest['documents'], 'CORPUS_IDENTITY_MISMATCH')
    rows = {r['id']: r for r in cache['vectors']}
    require(len(rows) == len(cache['vectors']) == manifest['vectorCount'], 'CORPUS_DUPLICATE_VECTORS')
    require(set(rows) == {key for d in manifest['documents'] for key in d['vectorIds']}, 'CORPUS_UNRELATED_VECTORS')
    for row in rows.values():
        require(set(row) == {'id', 'textHash', 'values'}, 'INVALID_CORPUS_VECTOR')
        values = normalize(row['values'], identity['dimension'])
        require(max(abs(a-b) for a,b in zip(values,row['values'])) < 1e-6, 'CORPUS_VECTOR_NOT_NORMALIZED')
    return manifest, contents, rows


class PortableCorpus:
    def __init__(self, knowledge, config):
        self.kb, self.p, self.config = knowledge, knowledge.p, config
        self.loaded, self.locks = None, {}

    async def ensure(self, owner):
        if not self.config.auto_import_corpus or not (self.config.root/'资料库/portable/manifest.json').is_file():
            return None
        async with self.locks.setdefault(owner, asyncio.Lock()):
            scope = Scope(user_id=owner, course_id='course-default')
            self.p.repo.require_course(scope)
            # The top-level receipt also avoids repeated large bundle reads.
            receipt = self.p.repo.read(scope, 'artifact', MARKER)
            if receipt:
                return receipt['value']
            try:
                if self.loaded is None:
                    self.loaded = await asyncio.to_thread(load_corpus, self.config.root)
                manifest, contents, rows = self.loaded
                installed, skipped = [], []
                for item in manifest['documents']:
                    prior = self.p.db.all("SELECT data,deleted FROM entities WHERE user_id=? AND course_id=? AND kind='document'", (owner,scope.course_id))
                    same = [(json.loads(d['data']), d['deleted']) for d in prior if json.loads(d['data']).get('fileHash') == item['sha256']]
                    if same and not any(not deleted and not any(d.get(k) for k in ('archived','deleted','superseded')) for d,deleted in same):
                        skipped.append(item['file']); continue
                    active = next((d for d in self.p.repo.all(scope, 'document') if d.get('fileHash') == item['sha256']
                                   and not any(d.get(k) for k in ('archived','deleted','superseded'))), None)
                    if active is None:
                        # Gate automatic teaching/quiz hooks until the bundled
                        # parser output and vectors have been validated together.
                        result = self.kb.upload(scope, contents[item['file']], item['file'], item['chapter'],
                                                MARKER+'-'+item['sha256'], review=True)
                        deadline = time.monotonic()+180
                        while time.monotonic() < deadline:
                            await self.p.jobs.tick()
                            state = self.p.jobs.get(result['job']['id'], owner)
                            if state['status'] in ('succeeded','failed','cancelled','unknown'):
                                require(state['status'] == 'succeeded', 'CORPUS_PARSE_FAILED'); break
                            await asyncio.sleep(.02)
                        else:
                            raise RuntimeError('CORPUS_PARSE_TIMEOUT')
                        active = self.kb.rag.document(scope, result['documentId'])
                    jobs = self.p.db.all("SELECT input FROM jobs WHERE user_id=? AND type='rag-index' AND status IN ('queued','running','cancelling')", (owner,))
                    if any(json.loads(j['input']).get('documentId') == active['id'] for j in jobs):
                        return {'status': 'deferred-active-index', 'newModelRequests': 0}
                    self.publish(scope, active, item, manifest['identity'], rows)
                    installed.append(active['id'])
                result = {'status': 'completed', 'documentIds': installed, 'skippedFiles': skipped,
                          'sources': sum(d['sourceCount'] for d in manifest['documents'] if d['file'] not in skipped),
                          'packageSources': manifest['sourceCount'], 'model': manifest['identity']['model'], 'newModelRequests': 0}
                self.p.repo.put(scope, 'artifact', MARKER, result, 0)
                return result
            except Exception as error:
                code = getattr(error, 'code', 'CORPUS_IMPORT_FAILED')
                log.warning('Portable corpus installation stopped: %s', code)
                result = {'status': 'failed', 'error': code, 'newModelRequests': 0}
                self.p.repo.put(scope, 'artifact', MARKER, result, 0)
                return result

    def publish(self, scope, doc, item, identity, rows):
        rag = self.kb.rag
        with self.p.db.transaction():
            current = rag.document(scope, doc['id'], active=True)
            require(current['version'] == doc['version'] and current['fileHash'] == item['sha256'], 'CORPUS_DOCUMENT_CHANGED')
            review = current.get('knowledgeReview')
            if review and review.get('confirmedRevision') is None:
                current = {**current, 'knowledgeReview': {'confirmedRevision': current['contentRevision'], 'confirmedBy': MARKER}}
                saved = self.p.repo.put(scope, 'document', current['id'], current, current['version'])
                current['version'] = saved['version']
            sources = rag.sources(scope, document_ids=[doc['id']])
            require(len(sources) == item['sourceCount'], 'CORPUS_SOURCE_MISMATCH')
            needed = set()
            for source in sources:
                require(rag.validate(scope, source), 'INVALID_CITATION')
                key = rag._cache_id(identity, source['quote'])
                require(key in rows and rows[key]['textHash'] == digest(source['quote']), 'CORPUS_TEXT_MISMATCH')
                needed.add(key)
            require(needed == set(item['vectorIds']), 'CORPUS_VECTOR_MISMATCH')
            for key in needed:
                row = {**{k: rows[key][k] for k in ('textHash','values')}, 'identity': identity}
                old = self.p.repo.read(scope, 'vector', key, include_deleted=True)
                if not old or old['deleted'] or old['value'] != row:
                    self.p.repo.put(scope, 'vector', key, row, old['version'] if old else 0)
            if current.get('embeddingIdentity') != identity or current.get('indexStatus') != 'ready':
                self.p.repo.put(scope, 'document', current['id'], {**current, 'embeddingIdentity': identity, 'indexStatus': 'ready'}, current['version'])
