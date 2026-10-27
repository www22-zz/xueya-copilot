"""Previewed, atomic replacement of PPT sources by a usable PDF in the same course."""
import time
from .common import digest, identifier, require, utc_now


class KnowledgeReplacement:
    def __init__(self, platform, rag):
        self.p, self.rag = platform, rag

    def ready(self, scope, document_id):
        doc = self.rag.document(scope, document_id, active=True)
        require(doc['kind'] == 'pdf', 'REPLACEMENT_PDF_REQUIRED')
        parsed = self.rag.artifact(scope, doc)
        require(bool(doc.get('chunks')) and not parsed['empty'] and not any(p['needsOcr'] for p in parsed['pages']),
                'REPLACEMENT_NOT_READY')
        # Revalidate published evidence, including current hashes/versions.
        require(bool(self.rag.sources(scope, document_ids=[doc['id']])), 'REPLACEMENT_NOT_READY')
        return doc

    @staticmethod
    def snapshot(doc):
        return {key: doc[key] for key in ('id', 'name', 'version', 'fileHash', 'contentRevision')}

    def preview(self, scope, value):
        target = self.ready(scope, identifier(value.get('targetDocumentId')))
        ids = value.get('oldDocumentIds')
        require(isinstance(ids, list) and 0 < len(ids) <= 100 and all(isinstance(i, str) for i in ids)
                and len(ids) == len(set(ids)) and target['id'] not in ids, 'INVALID_REPLACEMENT')
        previous = [self.rag.document(scope, identifier(i), active=True) for i in sorted(ids)]
        require(all(doc['kind'] == 'pptx' for doc in previous), 'REPLACEMENT_PPTX_REQUIRED')
        payload = {'target': self.snapshot(target), 'previous': [self.snapshot(doc) for doc in previous]}
        key = 'kb-replacement-'+digest(payload, canonical=True)[:40]
        row = self.p.repo.read(scope, 'artifact', key)
        if not row:
            self.p.repo.put(scope, 'artifact', key, {'kind': 'knowledge-replacement-preview', **payload,
                            'createdAt': utc_now(), 'expiresAt': time.time()+3600}, 0)
            row = self.p.repo.read(scope, 'artifact', key)
        return {'previewId': key, **row['value'], 'retainedForRecovery': True}

    def apply(self, scope, value):
        require(value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
        key = identifier(value.get('previewId'))
        with self.p.db.transaction():
            row = self.p.repo.read(scope, 'artifact', key)
            require(row and row['value'].get('kind') == 'knowledge-replacement-preview', 'REPLACEMENT_PREVIEW_NOT_FOUND')
            preview = row['value']
            if preview.get('result'):
                return preview['result']
            require(preview['expiresAt'] >= time.time(), 'REPLACEMENT_PREVIEW_EXPIRED')
            target = self.ready(scope, preview['target']['id'])
            require(self.snapshot(target) == preview['target'], 'VERSION_CONFLICT')
            # Check every old version before retiring any source; outer transaction
            # also rolls all removals back if a later conflict occurs.
            for expected in preview['previous']:
                current = self.rag.document(scope, expected['id'], active=True)
                require(self.snapshot(current) == expected, 'VERSION_CONFLICT')
            for expected in preview['previous']:
                self.rag.remove(scope, expected['id'], expected['version'])
            result = {'targetDocumentId': target['id'], 'removedDocumentIds': [d['id'] for d in preview['previous']],
                      'retainedForRecovery': True}
            self.p.repo.put(scope, 'artifact', key, {**preview, 'result': result}, row['version'])
            return result
