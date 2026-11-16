"""Course knowledge-base facade; B owns parsing/search, G2 owns reading/lifecycle."""
import hashlib
import json
import re
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import APIRouter, Request

from .common import digest, identifier, require
from .jobs import TERMINAL
from .document_limits import document_limit
from .document_catalog import is_demo_placeholder


def infer_chapter(name):
    """Use only explicit chapter/week labels in filenames; never infer syllabus facts."""
    match = re.search(r'第\s*([0-9]+(?:\.[0-9]+)?|[一二三四五六七八九十]+)\s*章', name)
    if match:
        return '第' + match[1] + '章'
    match = re.search(r'week\s*(\d+)', name, re.I)
    return '第' + match[1] + '周' if match else ''


def filename_chapter(name):
    return name.rsplit('.', 1)[0].strip() or name


def document_chapter(doc):
    return (doc.get('chapter') or '').strip() or filename_chapter(doc['name'])


class KnowledgeBase:
    def __init__(self, app):
        self.p, self.rag, self.library = app.state.platform, app.state.rag, app.state.library
        from .visual_review import VisualReview
        self.visual = VisualReview(self.p, self.rag)
        from .knowledge_replacement import KnowledgeReplacement
        self.replacement = KnowledgeReplacement(self.p, self.rag)
        self.demo = None

    def create(self, value):
        name, description = value.get('name'), value.get('description', '')
        require(isinstance(name, str) and 0 < len(name.strip()) <= 60, 'INVALID_KNOWLEDGE_NAME')
        require(isinstance(description, str) and len(description) <= 4000, 'INVALID_DESCRIPTION')
        key = identifier(value.get('idempotencyKey'))
        course_id = 'kb-' + digest(key)[:32]
        content = {'kind': 'knowledge-base-profile', 'name': name.strip(), 'description': description}
        with self.p.db.transaction():
            existing = next((c for c in self.p.repo.courses(self.p.scope_user_id) if c['id'] == course_id), None)
            if existing:
                require(not existing['archived'], 'COURSE_ARCHIVED')
                old = self.p.repo.read(self.p.scope(course_id), 'artifact', 'knowledge-base-profile')
                require(old and old['value'] == content, 'IDEMPOTENCY_CONFLICT')
                return existing
            self.p.repo.ensure_course(self.p.scope_user_id, {'id': course_id, 'name': name.strip()})
            self.p.repo.put(self.p.scope(course_id), 'artifact', 'knowledge-base-profile', content, 0)
        return next(c for c in self.p.repo.courses(self.p.scope_user_id) if c['id'] == course_id)

    def upload(self, scope, buffer, name, chapter, key, *, review=False):
        require(isinstance(name, str) and not name.startswith('~$'), 'TEMPORARY_FILE_FORBIDDEN')
        require(not any(c in name for c in ('/', '\\', '\x00')), 'INVALID_FILE_NAME')
        require(isinstance(chapter, str) and len(chapter) <= 200, 'INVALID_CHAPTER')
        default_chapter = not chapter.strip()
        chapter = chapter.strip() or filename_chapter(name)
        signature = digest({'name': name, 'chapter': chapter, 'bytes': hashlib.sha256(buffer).hexdigest(), **({'review': True} if review else {})})
        legacy_signature = digest({'name': name, 'chapter': infer_chapter(name), 'bytes': hashlib.sha256(buffer).hexdigest(), **({'review': True} if review else {})}) if default_chapter else None
        key = identifier(key)
        with self.p.db.transaction():
            receipt_id = 'knowledge-import-' + digest(key)[:40]
            prior = self.p.repo.read(scope, 'artifact', receipt_id, include_deleted=True)
            require(not prior or prior['value']['signature'] in (signature, legacy_signature), 'IDEMPOTENCY_CONFLICT')
            # Same file+name+chapter is one import, even across browser and CLI keys.
            job_key = 'knowledge-file-'+signature
            if legacy_signature:
                legacy_job = self.p.db.one("SELECT input FROM jobs WHERE user_id=? AND course_id=? AND type='rag-parse' AND idempotency_key=?", (scope.user_id, scope.course_id, 'knowledge-file-'+legacy_signature))
                if legacy_job and self.p.repo.read(scope, 'document', json.loads(legacy_job['input'])['documentId']):
                    signature = legacy_signature
                    job_key = 'knowledge-file-'+signature
            while old_job := self.p.db.one("SELECT input FROM jobs WHERE user_id=? AND course_id=? AND type='rag-parse' AND idempotency_key=?", (scope.user_id, scope.course_id, job_key)):
                old_document = json.loads(old_job['input'])['documentId']
                if self.p.repo.read(scope, 'document', old_document):
                    break
                job_key = 'knowledge-file-'+digest({'signature': signature, 'afterDeleted': old_document})
            job = self.rag.upload(scope, buffer, name, job_key)
            payload = json.loads(self.p.db.one('SELECT input FROM jobs WHERE id=?', (job['id'],))['input'])
            doc = self.rag.document(scope, payload['documentId'])
            if 'knowledgeImportSignature' in doc:
                require(doc['knowledgeImportSignature'] in (signature, legacy_signature), 'IDEMPOTENCY_CONFLICT')
            else:
                self.library.annotate(scope, job, {'chapter': chapter, 'knowledgeImportSignature': signature,
                                                 'origin': {'type': 'local-file', 'fileName': name},
                                                 **({'knowledgeReview': {'confirmedRevision': None}} if review else {})})
            if not prior or prior['value']['documentId'] != doc['id']:
                self.p.repo.put(scope, 'artifact', receipt_id, {'kind': 'knowledge-import-receipt', 'signature': signature, 'documentId': doc['id']}, prior['version'] if prior else 0)
            return {'job': job, 'documentId': doc['id']}

    def capabilities(self):
        return {'lexical': True, 'embedding': bool(self.rag.embedding),
                'ocr': bool(self.rag.ocr), 'rerank': bool(self.rag.rerank), 'externalVerified': False,
                'embeddingModel': self.rag.embedding.settings.model if self.rag.embedding else None,
                'ocrModel': self.rag.ocr.settings.model if self.rag.ocr else None,
                'embeddingInput': ['text'], 'ocrBatchLimit': 20 if self.rag.ocr and self.rag.ocr.name == 'moark-mineru-ocr' else 64}

    def catalog(self, scope):
        # Latest task per document, including retries/reparses and external index jobs.
        latest = {}
        for row in self.p.db.all("SELECT id,input FROM jobs WHERE user_id=? AND course_id=? AND type IN ('rag-parse','rag-index','rag-ocr','rag-visual-apply','rag-prepared-pdf') ORDER BY created_at DESC, rowid DESC", (scope.user_id, scope.course_id)):
            document_id = json.loads(row['input']).get('documentId')
            if not document_id:
                preview = self.p.repo.read(scope, 'artifact', json.loads(row['input']).get('previewId', ''))
                document_id = preview['value'].get('documentId') if preview else None
            if document_id not in latest:
                j = self.p.jobs.get(row['id'], scope.user_id)
                latest[document_id] = {k: j[k] for k in ('id', 'type', 'status', 'progress', 'error', 'updatedAt')}
        documents = []
        for doc in self.p.repo.all(scope, 'document'):
            if doc.get('superseded') or is_demo_placeholder(doc):
                continue
            original_available = False
            if doc.get('fileHash'):
                original_available = self.p.files.path(doc['fileHash']).is_file()
            quality_summary = doc.get('quality') or {}
            pages = quality_summary.get('pages', [])
            review = {'totalPages': len(pages), 'pendingPages': [p['number'] for p in pages if p.get('needsOcr')],
                      'transcribedPages': [p['number'] for p in pages if p.get('visualReview', {}).get('kind') == 'transcription'],
                      'blankPages': [p['number'] for p in pages if p.get('visualReview', {}).get('kind') == 'blank']}
            image_reviews = [r for p in pages for r in p.get('imageReviews', [])]
            review.update(supplementedPages=[p['number'] for p in pages if any(r['kind'] in ('transcription', 'diagram') for r in p.get('imageReviews', []))],
                          reviewedImages=len(image_reviews),
                          partialImages=sum(bool(r.get('partial')) for r in image_reviews),
                          unreadableImages=sum(r['kind'] == 'unreadable' for r in image_reviews))
            documents.append({**{k: doc.get(k) for k in ('id', 'name', 'chapter', 'version', 'contentRevision', 'kind', 'size', 'status', 'indexStatus', 'archived', 'quality')},
                              'chapter': document_chapter(doc), 'originalAvailable': original_available,
                              'review': review, 'ocrPreparation': doc.get('ocrPreparation'), 'pageSelection': doc.get('pageSelection'),
                              'knowledgeReview': doc.get('knowledgeReview'), 'reviewReady': self.rag.reviewed(doc),
                              'sourceCount': len(doc.get('chunks', [])) if original_available else 0, 'task': latest.get(doc['id']),
                              'vectorReady': bool(self.rag.embedding and doc.get('embeddingIdentity') == self.rag.embedding.identity and doc.get('indexStatus') == 'ready')})
        active = [d for d in documents if not d['archived']]
        return {'documents': sorted(documents, key=lambda d: (d.get('chapter') or '', d['name'])),
                'summary': {'documents': len(active), 'sources': sum(d['sourceCount'] for d in active),
                            'processing': sum(bool(d['task'] and d['task']['status'] not in TERMINAL) for d in active),
                            'needsReview': sum(bool(d.get('quality', {}) and d['quality'].get('warnings')) for d in active),
                            'missingOriginals': sum(not d['originalAvailable'] for d in active)},
                'capabilities': self.capabilities(),
                **({'demoImport': self.demo.status()} if self.demo and self.demo.config.auto_import_demo
                   and scope.course_id == 'course-default' and self.demo.status() else {})}

    def task(self, scope, value):
        task_id = identifier(value.get('id'))
        job = self.p.jobs.get(task_id, scope.user_id)
        require(job and job['courseId'] == scope.course_id and job['type'] in ('rag-parse', 'rag-index', 'rag-ocr', 'rag-visual-apply'), 'JOB_NOT_FOUND')
        require(value.get('action') in ('cancel', 'retry'), 'INVALID_JOB_ACTION')
        if value['action'] == 'cancel':
            return self.p.jobs.cancel(task_id, scope.user_id)
        require(job['type'] in ('rag-parse', 'rag-visual-apply') and job['resource'] == 'cpu', 'PAID_RETRY_FORBIDDEN')
        if job['type'] == 'rag-visual-apply':
            payload = json.loads(self.p.db.one('SELECT input FROM jobs WHERE id=?', (task_id,))['input'])
            preview = self.p.repo.read(scope, 'artifact', payload.get('previewId', ''))
            require(preview and preview['value']['expiresAt'] >= time.time(), 'VISUAL_PREVIEW_EXPIRED')
            self.visual.current(scope, preview['value'])
        # B's version check also rejects obsolete retries after a source changed.
        return self.p.jobs.retry(task_id, scope.user_id)


def install_knowledge_base(app):
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(host):
        async with previous(host):
            host.state.knowledge = KnowledgeBase(host)
            from .portable_knowledge import PortableKnowledge
            host.state.portable_knowledge = PortableKnowledge(host.state.knowledge, host.state.config)
            from .portable_corpus import PortableCorpus
            host.state.portable_corpus = PortableCorpus(host.state.knowledge, host.state.config)
            from .practice_generation import PracticeGeneration
            host.state.practice_generation = PracticeGeneration(host)
            def analysis_catalog(account):
                from .practice_catalog import exam_bank
                return host.state.practice_generation.catalog(account, history=True)['questions'] + exam_bank()['questions']
            host.state.practice_analysis.generated_catalog = analysis_catalog
            from .demo_import import DemoImport
            demo = DemoImport(host.state.knowledge, host.state.config)
            host.state.knowledge.demo = demo
            try:
                demo.start()
                yield
            finally:
                await demo.close()
    app.router.lifespan_context = lifespan
    router = APIRouter(prefix='/api/platform/knowledge')

    @router.api_route('/{operation}', methods=['GET', 'POST'])
    async def route(operation: str, request: Request):
        from .app import body, connected_work, json_body, success
        require(secrets.compare_digest(request.headers.get('x-xueya-token', ''), app.state.token), 'AUTH_REQUIRED')
        kb, q, post = app.state.knowledge, request.query_params, request.method == 'POST'
        if operation == 'upload' and post:
            scope = kb.p.scope(q.get('courseId', 'course-default'))
            review = q.get('review') == '1'
            uploaded = kb.upload(scope, await body(request, document_limit(q.get('name'))), q.get('name'), q.get('chapter', ''), request.headers.get('idempotency-key'), review=review)
            account = (app.state.account.current(request) or {}).get('username') or 'local'
            generated = None if review else app.state.practice_generation.watch(account, scope, uploaded['documentId'])
            return success(**uploaded, practiceGeneration=generated)
        value = await json_body(request) if post else {}
        if operation == 'bases' and not post:
            return success(bases=[c for c in kb.p.repo.courses(kb.p.scope_user_id) if not c['archived']])
        if operation == 'create' and post:
            return success(base=kb.create(value))
        scope = kb.p.scope(value.get('courseId') or q.get('courseId') or 'course-default')
        if operation == 'index-plan' and not post:
            return success(plan=kb.rag.index_plan(scope, q.get('documentId')))
        if operation == 'remove' and post:
            require(value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
            require(type(value.get('version')) is int and value['version'] > 0, 'INVALID_VERSION')
            return success(**kb.rag.remove(scope, value.get('documentId'), value['version']))
        if operation == 'review-confirm' and post:
            require(value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
            require(type(value.get('version')) is int, 'INVALID_VERSION')
            return success(**kb.rag.confirm_review(scope, value.get('documentId'), value['version']))
        if operation == 'replacement-preview' and post:
            return success(preview=kb.replacement.preview(scope, value))
        if operation == 'replacement-apply' and post:
            return success(replacement=kb.replacement.apply(scope, value))
        if operation == 'demo-retry' and post:
            require(scope.course_id == 'course-default' and value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
            require(kb.demo and kb.demo.config.auto_import_demo, 'DEMO_IMPORT_DISABLED')
            return success(demoImport=kb.demo.start(retry=True))
        if operation == 'visual-pack' and not post:
            return success(pack=kb.visual.pack(scope, q.get('documentId')))
        if operation == 'visual-preview' and post:
            return success(preview=kb.visual.preview(scope, value))
        if operation == 'visual-apply' and post:
            return success(job=kb.visual.submit(scope, value))
        if operation == 'catalog' and not post:
            account = (app.state.account.current(request) or {}).get('username') or 'local'
            return success(**kb.catalog(scope), practiceGenerations=app.state.practice_generation.catalog(account, scope.course_id)['generations'] if app.state.practice_generation.legacy_enabled else [])
        if operation == 'search' and post:
            mode = value.get('mode', 'lexical')
            require(mode in ('lexical', 'vector', 'hybrid', 'rerank'), 'INVALID_SEARCH_MODE')
            require(mode == 'lexical' or value.get('confirmedExternal') is True, 'EXTERNAL_CONFIRMATION_REQUIRED')
            ids = value.get('documentIds')
            chapter = value.get('chapter', '')
            require(isinstance(chapter, str) and len(chapter) <= 200, 'INVALID_CHAPTER')
            if chapter:
                chapter_ids = {d['id'] for d in kb.p.repo.all(scope, 'document') if document_chapter(d) == chapter and not d.get('archived') and not d.get('superseded')}
                require(ids is None or isinstance(ids, list) and all(isinstance(i, str) for i in ids), 'INVALID_DOCUMENT_IDS')
                ids = sorted(chapter_ids if ids is None else chapter_ids.intersection(ids))
            return success(evidence=await connected_work(request, kb.rag.search(scope, value.get('query'), document_ids=ids,
                           mode=mode, budget=8000, limit=8)))
        if operation == 'process' and post:
            action = value.get('action')
            require(action in ('parse', 'index', 'ocr'), 'INVALID_PROCESS_ACTION')
            require(action == 'parse' or value.get('confirmedExternal') is True, 'EXTERNAL_CONFIRMATION_REQUIRED')
            require(type(value.get('version')) is int and value['version'] > 0, 'INVALID_VERSION')
            if action == 'ocr':
                doc = kb.rag.document(scope, value.get('documentId'), active=True)
                require(doc['kind'] == 'pdf', 'OCR_PDF_REQUIRED')
                pages = kb.rag.artifact(scope, doc)['pages']
                chosen = value.get('pages')
                require(chosen is None or isinstance(chosen, list) and 0 < len(chosen) <= kb.capabilities()['ocrBatchLimit'], 'OCR_PAGE_LIMIT')
                require(chosen is not None or 0 < sum(bool(p.get('needsOcr')) for p in pages) <= 64, 'OCR_PAGE_LIMIT')
            return success(job=kb.rag.submit(scope, 'rag-'+action, value.get('documentId'), value.get('idempotencyKey'), expected_version=value['version'], pages=value.get('pages')))
        if operation == 'task' and post:
            return success(job=kb.task(scope, value))
        require(False, 'NOT_FOUND')

    count = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[count:]
    del app.router.routes[count:]
    app.router.routes[0:0] = added
    return app
