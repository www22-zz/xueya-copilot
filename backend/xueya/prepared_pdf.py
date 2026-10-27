"""Adopt already prepared OCR text; this module never runs OCR or calls a model.

Local CLI only. Originals, revision publication and cancellation use the host's
existing FileStore, repository and leased CPU queue.
"""
import json
from .common import digest, identifier, require
from .rag_parse import assemble, MAX_TEXT


class PreparedPdf:
    def __init__(self, rag):
        self.rag, self.p = rag, rag.p
        self.p.jobs.register('rag-prepared-pdf', self.run)

    def parsed(self, scope, doc, value):
        require(doc['kind'] == 'pdf' and isinstance(value, dict), 'PREPARED_PDF_REQUIRED')
        require(value.get('schema') == 'prepared-pdf-ocr-v1' and value.get('sourceFileHash') == doc['fileHash'], 'PREPARED_PDF_HASH_MISMATCH')
        pages = value.get('pages')
        original = self.rag.artifact(scope, doc)['pages']
        require(isinstance(pages, list) and len(pages) == len(original), 'PREPARED_PDF_PAGE_MISMATCH')
        engine = value.get('engine')
        require(isinstance(engine, str) and 0 < len(engine) <= 120, 'INVALID_PREPARED_OCR')
        output = []
        total = 0
        for row, before in zip(pages, original):
            require(isinstance(row, dict) and type(row.get('page')) is int and row['page'] == before['number'], 'PREPARED_PDF_PAGE_MISMATCH')
            text = row.get('text')
            require(isinstance(text, str) and '\x00' not in text, 'INVALID_PREPARED_OCR')
            blank = row.get('reviewedBlank') is True
            require(bool(text.strip()) != blank, 'PREPARED_PDF_UNRESOLVED_PAGE')
            total += len(text) + 1
            require(total <= MAX_TEXT, 'PARSED_TEXT_TOO_LARGE')
            output.append({'number': row['page'], 'text': text, 'method': 'prepared-ocr', 'needsOcr': False,
                           'hasImages': before.get('hasImages', True), 'width': before.get('width'), 'height': before.get('height'),
                           'ocrPreparation': {'engine': engine, 'reviewedBlank': blank,
                                              'textIndependentlyReviewed': False, 'formulaAndCodeNeedReview': True}})
        parsed = assemble(output, 'pdf', doc['fileHash'])
        parsed['preparation'] = {'engine': engine, 'sourceFileHash': doc['fileHash'],
                                 'notice': 'OCR整理文本；公式、代码和图表请核对原PDF，不等同逐字人工校订。'}
        return parsed

    def submit(self, scope, document_id, value, key):
        identifier(key)
        self.p.repo.require_course(scope)
        request_hash = digest(value, canonical=True)
        prior = self.p.db.one("SELECT id,input FROM jobs WHERE user_id=? AND course_id=? AND type='rag-prepared-pdf' AND idempotency_key=?", (scope.user_id, scope.course_id, key))
        if prior:
            previous = json.loads(prior['input'])
            require(previous['documentId'] == document_id and previous['requestHash'] == request_hash, 'IDEMPOTENCY_CONFLICT')
            return self.p.jobs.get(prior['id'], scope.user_id)
        doc = self.rag.document(scope, document_id, active=True)
        self.parsed(scope, doc, value)  # Validate everything before storing or enqueueing.
        bundle = self.p.files.put(json.dumps(value, ensure_ascii=False).encode())
        return self.p.jobs.submit(scope.user_id, {'type': 'rag-prepared-pdf', 'courseId': scope.course_id,
            'resource': 'cpu', 'maxAttempts': 1, 'idempotencyKey': key,
            'input': {'documentId': doc['id'], 'expectedVersion': doc['version'], 'bundleHash': bundle['hash'],
                      'requestHash': request_hash, 'jobKey': key}})

    async def run(self, scope, args, *, progress, checkpoint, commit):
        require(isinstance(args, dict) and set(args) == {'documentId', 'expectedVersion', 'bundleHash', 'requestHash', 'jobKey'}, 'INVALID_JOB')
        row = self.p.db.one("SELECT status,resource FROM jobs WHERE user_id=? AND course_id=? AND type='rag-prepared-pdf' AND idempotency_key=?", (scope.user_id, scope.course_id, args['jobKey']))
        require(row and row['status'] == 'running' and row['resource'] == 'cpu', 'NOT_SENT')
        doc = self.rag.document(scope, args['documentId'], active=True)
        require(doc['version'] == args['expectedVersion'], 'VERSION_CONFLICT')
        value = json.loads(self.p.files.read(args['bundleHash']))
        require(digest(value, canonical=True) == args['requestHash'], 'PREPARED_PDF_HASH_MISMATCH')
        parsed = self.parsed(scope, doc, value)
        progress({'percent': 60, 'label': '核对原件hash与逐页文字'})
        checkpoint({'documentId': doc['id'], 'bundleHash': args['bundleHash']})
        return commit(lambda: self.rag._publish(scope, doc, parsed))
