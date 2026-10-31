"""G2 library operations over B's lifecycle and the existing platform stores."""
import asyncio
import hashlib
import json
import math
import re
import secrets
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import Response
from .common import require, utc_now, identifier, digest
from .library_fetch import fetch_snapshot


class Library:
    def __init__(self, app):
        self.app, self.p, self.rag = app, app.state.platform, app.state.rag
        self.p.jobs.register('library-web-import', self.web_import)

    def profile(self, scope):
        row = self.p.repo.read(scope, 'artifact', 'library-profile')
        return {'version': row['version'] if row else 0, **(row['value'] if row else {})}

    def annotate(self, scope, job, metadata):
        doc = self.rag.document(scope, json.loads(self.p.db.one('SELECT input FROM jobs WHERE id=?', (job['id'],))['input'])['documentId'])
        self.p.repo.put(scope, 'document', doc['id'], {**doc, **metadata}, doc['version'])
        # The leased parse validates document revision; update its not-yet-started input.
        row = self.p.db.one('SELECT input,status FROM jobs WHERE id=?', (job['id'],))
        require(row['status'] == 'queued', 'IMPORT_ALREADY_RUNNING')
        value = json.loads(row['input'])
        value['expectedVersion'] = doc['version']+1
        self.p.db.execute('UPDATE jobs SET input=? WHERE id=?', (json.dumps(value, ensure_ascii=False), job['id']))
        return job

    def text_import(self, scope, value, origin=None):
        text, title = value.get('text'), value.get('title')
        require(isinstance(text, str) and text.strip() and len(text.encode()) <= 1_048_576, 'INVALID_IMPORT_TEXT')
        require(isinstance(title, str) and title.strip() and len(title) <= 160, 'INVALID_IMPORT_TITLE')
        chapter = value.get('chapter', '')
        require(isinstance(chapter, str) and len(chapter) <= 200, 'INVALID_CHAPTER')
        key = identifier(value.get('idempotencyKey'))
        signature = digest({'text': text, 'title': title, 'chapter': chapter, 'origin': origin,
                            'previousDocumentId': value.get('previousDocumentId')})
        prior = self.p.db.one("SELECT id FROM jobs WHERE user_id=? AND course_id=? AND type='rag-parse' AND idempotency_key=?", (scope.user_id, scope.course_id, key))
        if prior:
            job = self.p.jobs.get(prior['id'], scope.user_id)
            payload = json.loads(self.p.db.one('SELECT input FROM jobs WHERE id=?', (job['id'],))['input'])
            doc = self.rag.document(scope, payload['documentId'])
            require(doc.get('importSignature') == signature, 'IDEMPOTENCY_CONFLICT')
            return job
        with self.p.db.transaction():
            job = self.rag.upload(scope, text.encode(), title.strip()+'.md', key, previous_document_id=value.get('previousDocumentId'))
            return self.annotate(scope, job, {'chapter': chapter, 'origin': origin or {'type': 'pasted-text', 'capturedAt': utc_now()}, 'importSignature': signature})

    async def web_import(self, scope, args, **callbacks):
        callbacks['progress']({'percent': 10, 'label': '读取公开网页快照'})
        async with asyncio.timeout(22):
            snapshot = await asyncio.to_thread(fetch_snapshot, args['url'])
        origin = {'type': 'web-snapshot', 'originalUrl': snapshot['originalUrl'], 'finalUrl': snapshot['finalUrl'],
                  'capturedAt': utc_now(), 'contentHash': hashlib.sha256(snapshot['text'].encode()).hexdigest()}
        value = {**args, 'title': args.get('title') or snapshot['title'], 'text': snapshot['text'], 'idempotencyKey': 'web-text-'+args['idempotencyKey']}
        def save():
            job = self.text_import(scope, value, origin)
            return {'parseJobId': job['id'], 'documentId': json.loads(self.p.db.one('SELECT input FROM jobs WHERE id=?', (job['id'],))['input'])['documentId']}
        return callbacks['commit'](save)

    def organize(self, scope, value):
        with self.p.db.transaction():
            doc = self.rag.document(scope, value.get('documentId'))
            require(doc['version'] == value.get('version'), 'VERSION_CONFLICT')
            action = value.get('action')
            require(action in ('chapter', 'archive', 'restore', 'detach'), 'INVALID_LIBRARY_ACTION')
            if action in ('chapter', 'detach'):
                chapter = '' if action == 'detach' else value.get('chapter')
                require(isinstance(chapter, str) and len(chapter) <= 200, 'INVALID_CHAPTER')
                updated = {**doc, 'chapter': chapter}
            else:
                updated = {**doc, 'archived': action == 'archive'}
            saved = self.p.repo.put(scope, 'document', doc['id'], updated, doc['version'])
            return {**updated, 'version': saved['version']}


def install_library(app):
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(host):
        async with previous(host):
            host.state.library = Library(host)
            yield
    app.router.lifespan_context = lifespan
    router = APIRouter(prefix='/api/platform/library')

    @router.api_route('/{operation}', methods=['GET', 'POST'])
    async def route(operation: str, request: Request):
        require(secrets.compare_digest(request.headers.get('x-xueya-token', ''), app.state.token), 'AUTH_REQUIRED')
        from .app import json_body, success
        value = await json_body(request, 1_100_000) if request.method == 'POST' else {}
        q, library, p = request.query_params, app.state.library, app.state.platform
        scope = p.scope(value.get('courseId') or q.get('courseId') or 'course-default')
        p.repo.require_course(scope, archived=True)
        post = request.method == 'POST'
        if operation == 'catalog' and not post:
            rows = [d for d in p.repo.all(scope, 'document') if not d.get('superseded')]
            media = [{'id': r['content']['id'], 'revision': r['revision'], 'durationMs': r['content'].get('durationMs') or (r['content']['endMs']-r['content'].get('startMs', 0) if 'endMs' in r['content'] else None), **{k: r['content'][k] for k in ('kind', 'mime', 'name') if k in r['content']}} for r in app.state.learning.repo.all(scope.course_id) if r.get('kind') == 'media']
            links = [r for r in p.repo.all(scope, 'artifact') if r.get('kind') == 'library-media-link']
            return success(documents=rows, profile=library.profile(scope), media=media, links=links, courses=p.repo.courses(p.scope_user_id))
        if operation == 'profile' and post:
            allowed = ('description', 'goals', 'prerequisites', 'examScope')
            profile = {k: value.get(k, '') for k in allowed}
            require(all(isinstance(v, str) and len(v) <= 4000 for v in profile.values()), 'INVALID_COURSE_PROFILE')
            chapters = value.get('chapters', [])
            require(isinstance(chapters, list) and len(chapters) <= 100 and all(isinstance(c, str) and 0 < len(c) <= 200 for c in chapters), 'INVALID_CHAPTERS')
            profile['chapters'] = list(dict.fromkeys(chapters))
            require(type(value.get('version')) is int, 'INVALID_VERSION')
            return success(profile=p.repo.put(scope, 'artifact', 'library-profile', profile, value['version']))
        if operation == 'text' and post:
            return success(job=library.text_import(scope, value))
        if operation == 'url' and post:
            require(value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
            require(isinstance(value.get('url'), str) and len(value['url']) <= 2048, 'INVALID_PUBLIC_URL')
            return success(job=p.jobs.submit(p.scope_user_id, {'type': 'library-web-import', 'courseId': scope.course_id, 'resource': 'cpu', 'maxAttempts': 1,
                'idempotencyKey': identifier(value.get('idempotencyKey')), 'input': {k: value[k] for k in ('url', 'title', 'chapter', 'previousDocumentId', 'idempotencyKey') if k in value}}))
        if operation == 'organize' and post:
            require(value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
            return success(document=library.organize(scope, value))
        if operation == 'reuse' and post:
            require(value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
            doc = library.rag.document(scope, value.get('documentId'), active=True)
            require(doc['version'] == value.get('version'), 'VERSION_CONFLICT')
            target = p.scope(value.get('targetCourseId'))
            require(target.course_id != scope.course_id, 'TARGET_COURSE_REQUIRED')
            p.repo.require_course(target)
            key = identifier(value.get('idempotencyKey'))
            chapter = value.get('chapter', '')
            require(isinstance(chapter, str) and len(chapter) <= 200, 'INVALID_CHAPTER')
            with p.db.transaction():
                job = library.rag.upload(target, p.files.read(doc['fileHash']), doc['name'], key)
                payload = json.loads(p.db.one('SELECT input FROM jobs WHERE id=?', (job['id'],))['input'])
                copied = library.rag.document(target, payload['documentId'])
                if not copied.get('reusedFrom'):
                    library.annotate(target, job, {'reusedFrom': {'courseId': scope.course_id, 'documentId': doc['id'], 'version': doc['version']}, 'chapter': value.get('chapter', ''), 'origin': doc.get('origin')})
                else:
                    require(copied['reusedFrom'] == {'courseId': scope.course_id, 'documentId': doc['id'], 'version': doc['version']} and copied.get('chapter', '') == chapter, 'IDEMPOTENCY_CONFLICT')
            return success(job=job)
        if operation == 'read' and not post:
            doc = library.rag.document(scope, q.get('documentId'))
            versions = p.db.all("SELECT version,data,at FROM revisions WHERE user_id=? AND course_id=? AND kind='document' AND id=? ORDER BY version DESC LIMIT 100", (scope.user_id, scope.course_id, doc['id']))
            requested = q.get('version')
            if requested:
                row = next((r for r in versions if str(r['version']) == requested), None)
                require(row, 'DOCUMENT_VERSION_NOT_FOUND')
                doc = {**json.loads(row['data']), 'version': row['version']}
            artifact = p.repo.read(scope, 'artifact', doc.get('activeArtifact', ''), include_deleted=True) if doc.get('activeArtifact') else None
            return success(document=doc, artifact=artifact['value'] if artifact else None,
                versions=[{'version': r['version'], 'at': r['at']} for r in versions], historical=bool(requested or doc.get('superseded') or doc.get('archived')))
        if operation == 'media-link' and post:
            require(value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
            doc = library.rag.document(scope, value.get('documentId'), active=True)
            require(doc['version'] == value.get('documentVersion'), 'VERSION_CONFLICT')
            media = await app.state.learning.repo.get(scope.course_id, 'media:'+str(value.get('mediaId')))
            require(media and media['kind'] == 'media' and media['revision'] == value.get('mediaVersion'), 'MEDIA_NOT_FOUND')
            location = value.get('location', {})
            require(isinstance(location, dict) and not set(location)-{'page', 'startMs', 'endMs'}, 'INVALID_MEDIA_LOCATION')
            if 'page' in location:
                artifact = library.rag.artifact(scope, doc)
                require(type(location['page']) is int and location['page'] in {b.get('page') for b in artifact['blocks']}, 'INVALID_PAGE')
            if 'startMs' in location or 'endMs' in location:
                start, end, duration = location.get('startMs'), location.get('endMs'), media['content'].get('durationMs', media['content'].get('endMs', 0)-media['content'].get('startMs', 0))
                require(all(type(v) in (int, float) and math.isfinite(v) for v in (start, end, duration)) and 0 <= start < end <= duration, 'INVALID_MEDIA_LOCATION')
            key = 'library-link-'+identifier(value.get('idempotencyKey'))
            link = {'kind': 'library-media-link', 'documentId': doc['id'], 'documentVersion': doc['version'], 'documentContentRevision': doc.get('contentRevision'), 'mediaId': value['mediaId'],
                    'mediaVersion': media['revision'], 'location': location, 'confirmedByUser': True}
            old = p.repo.read(scope, 'artifact', key)
            require(not old or old['value'] == link, 'IDEMPOTENCY_CONFLICT')
            if not old:
                p.repo.put(scope, 'artifact', key, link, 0)
            return success(link=link)
        if operation == 'media-original' and not post:
            media = await app.state.learning.repo.get(scope.course_id, 'media:'+str(q.get('id')))
            require(media and media['kind'] == 'media' and str(media['revision']) == q.get('version'), 'MEDIA_NOT_FOUND')
            content = p.files.read(media['content']['fileHash'])
            headers = {'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store'}
            span, status = request.headers.get('range'), 200
            if span:
                match = re.fullmatch(r'bytes=(\d+)-(\d*)', span)
                require(match, 'INVALID_MEDIA_RANGE')
                start, end = int(match[1]), int(match[2]) if match[2] else len(content)-1
                require(0 <= start <= end < len(content), 'INVALID_MEDIA_RANGE')
                headers['Content-Range'] = f'bytes {start}-{end}/{len(content)}'
                content, status = content[start:end+1], 206
            return Response(content, media_type=media['content']['mime'], headers=headers, status_code=status)
        require(False, 'NOT_FOUND')

    count = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[count:]
    del app.router.routes[count:]
    app.router.routes[0:0] = added
