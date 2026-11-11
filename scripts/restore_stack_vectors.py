"""Restore validated existing vectors into the active account, with no network."""
import argparse
import asyncio
import json
from pathlib import Path
from backend.xueya.account_scope import bind_owner
from backend.xueya.backup import create_backup
from backend.xueya.common import require
from backend.xueya.config import ROOT, load_config
from backend.xueya.platform import Platform
from backend.xueya.rag_http import configured_service
from backend.xueya.server import pid_alive
from scripts.import_validated_vector_cache import promote


async def run(args):
    config = load_config()
    lock = config.data_dir/'server.json'
    require(not lock.exists() or not pid_alive(json.loads(lock.read_text('utf-8'))['pid']), 'STOP_HOST_BEFORE_RESTORE')
    backup = create_backup(config.data_dir, args.backup)
    p = Platform(config.data_dir, recover=False, preserve_legacy_data=True)
    try:
        require(not p.db.one("SELECT id FROM jobs WHERE status IN ('queued','running','cancelling')"), 'ACTIVE_JOBS')
        require(not p.db.one("SELECT id FROM invocations WHERE status='pending'"), 'ACTIVE_INVOCATIONS')
        rag = configured_service(p, config.root)
        require(rag.embedding is not None, 'EMBEDDING_NOT_CONFIGURED')
        expected = rag.embedding.identity
        with bind_owner(args.owner):
            scope = p.scope(args.course_id)
            docs = [d for d in rag.repo.all(scope, 'document') if not d.get('archived') and not d.get('superseded')]
            require(len(docs) == 1 and docs[0]['name'] == '栈与队列知识库.md', 'UNEXPECTED_KNOWLEDGE_SCOPE')
            directory = ROOT/'test-results/stack-queue-md'
            provenance = json.loads((directory/'vector-provenance.json').read_text('utf-8'))
            result = await promote(p, rag, scope, docs[0]['id'], directory/'vectors.json', provenance, expected_identity=expected)
            current = rag.document(scope, docs[0]['id'])
            require(current['indexStatus'] == 'ready' and current['embeddingIdentity'] == expected, 'INDEX_NOT_READY')
            return {**result, 'backup': backup, 'indexReady': True, 'previousUnknownJobsRetained': True}
    finally:
        await p.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--course-id', required=True)
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    output = ROOT/'test-results/stack-only/vector-restore.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('sourceCount','cachedVectors','newModelRequests','indexReady')}))


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
