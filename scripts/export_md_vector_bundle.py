"""Export only the seven approved MD files and their existing validated vectors. No API calls."""
import argparse
import asyncio
import gzip
import hashlib
import json
from pathlib import Path

from backend.xueya.common import Scope, digest, require
from backend.xueya.config import ROOT, load_config
from backend.xueya.platform import Platform
from backend.xueya.rag_service import RagService
from backend.xueya.rag_search import normalize

FILES = ('algorithm-design(1).md', 'graph(1).md', 'linear-list(1).md', 'search-hash(1).md',
         'sorting(1).md', 'string-array(1).md', 'tree-binary-tree(1).md')


async def export(owner):
    p = Platform(load_config().data_dir, recover=False, preserve_legacy_data=True)
    try:
        scope = Scope(user_id=owner, course_id='course-default')
        rag = RagService(p)
        documents, rows, identity = [], {}, None
        for name in FILES:
            raw = (ROOT/'资料库'/name).read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            docs = [d for d in p.repo.all(scope, 'document') if d.get('fileHash') == sha
                    and not any(d.get(k) for k in ('deleted', 'archived', 'superseded'))]
            require(len(docs) == 1 and docs[0].get('indexStatus') == 'ready', 'EXACT_READY_DOCUMENT_REQUIRED')
            doc = docs[0]
            current = doc.get('embeddingIdentity')
            require(current and current['model'] == 'Qwen3-VL-Embedding-8B' and current['dimension'] == 4096, 'WRONG_MODEL')
            require(identity is None or identity == current, 'MIXED_MODELS')
            identity = current
            ids = []
            sources = rag.sources(scope, document_ids=[doc['id']])
            require(bool(sources), 'NO_SOURCES')
            for source in sources:
                require(rag.validate(scope, source), 'INVALID_CITATION')
                key = rag._cache_id(identity, source['quote'])
                value = p.repo.read(scope, 'vector', key)['value']
                require(value['identity'] == identity and value['textHash'] == digest(source['quote']), 'INVALID_CACHE')
                normalized = normalize(value['values'], identity['dimension'])
                require(max(abs(a-b) for a,b in zip(normalized,value['values'])) < 1e-6, 'INVALID_VECTOR')
                rows[key] = {'id': key, 'textHash': value['textHash'], 'values': value['values']}
                ids.append(key)
            documents.append({'file': name, 'sha256': sha, 'chapter': doc['chapter'],
                              'sourceCount': len(sources), 'vectorIds': sorted(set(ids))})
        cache = {'schema': 'portable-dsa-md-v1', 'identity': identity, 'documents': documents,
                 'vectors': [rows[k] for k in sorted(rows)]}
        raw = json.dumps(cache, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        directory = ROOT/'资料库/portable'
        directory.mkdir(parents=True, exist_ok=True)
        (directory/'vectors.json.gz').write_bytes(packed)
        manifest = {'schema': cache['schema'], 'identity': identity, 'documents': documents,
                    'sourceCount': sum(d['sourceCount'] for d in documents), 'vectorCount': len(rows),
                    'uncompressedBytes': len(raw), 'cacheSha256': hashlib.sha256(raw).hexdigest(),
                    'compressedSha256': hashlib.sha256(packed).hexdigest(), 'vectorFile': 'vectors.json.gz'}
        (directory/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'documents': len(documents), 'sources': manifest['sourceCount'],
                          'vectors': len(rows), 'gzipBytes': len(packed), 'providerRequests': 0}))
    finally:
        await p.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True, help='Explicit local data owner whose approved files are exported')
    asyncio.run(export(parser.parse_args().owner))
