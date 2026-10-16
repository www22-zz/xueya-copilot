import asyncio
import json
import re
import secrets
from urllib.parse import quote
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from ..core import require, DomainError, dumps
from ..mcp.platform_server import open_platform_session
from .repository import valid_id


class PlatformHandler:
    def __init__(self, platform):
        self.platform, self.token = platform, secrets.token_hex(32)
        self.router = APIRouter(prefix='/api/platform')
        self.router.add_api_route('/{path:path}', self.handle, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])

    async def handle(self, path: str, request: Request):
        platform, repository = self.platform, self.platform.repository
        user, query = platform.user_id, request.query_params
        try:
            host = request.headers.get('host', '')
            require(re.fullmatch(r'(127\.0\.0\.1|localhost|\[::1\])(:\d+)?', host), 'ORIGIN_FORBIDDEN')
            require(not request.headers.get('origin') or request.headers['origin'] == 'http://'+host, 'ORIGIN_FORBIDDEN')
            if path == 'bootstrap' and request.method == 'GET':
                return {'ok': True, 'token': self.token, 'schemaVersion': '1.0', 'workspace': repository.get_workspace(user), 'courses': repository.courses(user), 'jobs': platform.jobs.list(user), 'resources': platform.resources.stats()}
            require(secrets.compare_digest(request.headers.get('x-xueya-token', ''), self.token), 'AUTH_REQUIRED')
            value = {}
            if request.method in ('POST', 'PUT'):
                binary = path in ('documents/upload', 'documents/import-original')
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    require(len(body) <= (10485760 if binary else 25000000), 'REQUEST_TOO_LARGE')
                if binary:
                    value = {'buffer': bytes(body)}
                else:
                    try:
                        value = json.loads(body)
                    except ValueError:
                        require(False, 'INVALID_JSON')
                    require(isinstance(value, dict), 'INVALID_REQUEST')
            def scope():
                return platform.scope(value.get('courseId', query.get('courseId', 'course-default')))
            result = {}
            if path == 'workspace':
                if request.method == 'GET':
                    result = {'workspace': repository.get_workspace(user)}
                elif request.method == 'PUT':
                    result = {'workspace': repository.save_workspace(user, value['workspace'], value.get('expectedVersion', 0))}
                else:
                    raise DomainError('METHOD_NOT_ALLOWED')
            elif path == 'migration/preview':
                result = {'preview': platform.migration.preview(user, value)}
            elif path == 'migration/apply':
                result = platform.migration.apply(user, value)
            elif path == 'migration/backup':
                result = {'backup': platform.migration.backup(user, query.get('id'))}
            elif path == 'courses':
                require(valid_id(value.get('id')) and isinstance(value.get('name'), str) and 0 < len(value['name']) <= 100, 'INVALID_COURSE')
                repository.ensure_course(user, value)
                result = {'courses': repository.courses(user)}
            elif path == 'documents/upload':
                require(valid_id(request.headers.get('idempotency-key')), 'INVALID_IDEMPOTENCY_KEY')
                result = {'job': platform.upload(scope(), query.get('name', ''), value['buffer'], request.headers['idempotency-key'], query.get('previousDocumentId'))}
            elif path == 'documents/import-original':
                document = platform.document(scope(), query.get('documentId'))
                file = platform.files.put(value['buffer'])
                require(not document.get('fileHash') or document['fileHash'] == file['hash'], 'ORIGINAL_CONFLICT')
                saved = repository.put(scope(), 'document', document['id'], {**document, 'fileHash': file['hash'], 'size': file['size'], 'originalAvailable': True}, document['version'])
                result = {'document': {**saved['value'], 'version': saved['version']}}
            elif path == 'documents':
                result = {'documents': repository.all(scope(), 'document')}
            elif path == 'documents/original':
                document = platform.document(scope(), query.get('documentId'))
                return Response(platform.files.read(document.get('fileHash')), media_type='application/octet-stream', headers={'Content-Disposition': "attachment; filename*=UTF-8''"+quote(document['name']), 'X-Content-Type-Options': 'nosniff'})
            elif path == 'documents/update':
                document = platform.document(scope(), value['documentId'])
                require(isinstance(value.get('changes'), dict) and isinstance(value['changes'].get('name'), str) and value['changes']['name'].strip(), 'INVALID_DOCUMENT')
                saved = repository.put(scope(), 'document', document['id'], {**document, 'name': value['changes']['name'][:200], 'tags': [str(x) for x in value['changes'].get('tags', document.get('tags', []))][:30]}, value['version'])
                result = {'document': {**saved['value'], 'version': saved['version']}}
            elif path == 'documents/remove':
                with platform.db.transaction():
                    document = platform.document(scope(), value['documentId'])
                    repository.put(scope(), 'document', document['id'], document, value['version'], True)
                    for source in repository.all(scope(), 'source'):
                        if source.get('documentId') == document['id']:
                            repository.put(scope(), 'source', source['id'], source, deleted=True)
                result = {'removed': True, 'retainedForRecovery': True}
            elif path == 'jobs':
                result = {'jobs': platform.jobs.list(user)} if request.method == 'GET' else {'job': platform.jobs.submit(user, value)}
            elif path == 'jobs/status':
                job = platform.jobs.get(query.get('id'), user)
                require(job, 'JOB_NOT_FOUND')
                result = {'job': job}
            elif path in ('jobs/cancel', 'jobs/retry'):
                result = {'job': getattr(platform.jobs, path.split('/')[1])(value['id'], user)}
            elif path == 'jobs/events':
                key, after = query.get('id'), int(request.headers.get('last-event-id', query.get('after', '0')))
                platform.jobs.events(key, user, after)
                async def stream():
                    nonlocal after
                    while not await request.is_disconnected():
                        for event in platform.jobs.events(key, user, after):
                            after = event['seq']
                            yield f'id: {after}\ndata: '+dumps(event)+'\n\n'
                        if platform.jobs.get(key, user)['status'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
                            return
                        await asyncio.sleep(.3)
                return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store'})
            elif path in ('tools', 'tools/call'):
                async with open_platform_session(platform, scope()) as session:
                    result = {'tools': await session.list_tools()} if path == 'tools' else {'data': await session.call(value['name'], value.get('arguments', {}))}
            elif path == 'actions/confirm':
                result = platform.authority.confirm(scope(), value)
            elif path == 'actions/cancel':
                result = platform.authority.cancel(scope(), value['actionId'])
            elif path == 'entities':
                result = repository.page(scope(), query.get('kind'), query.get('cursor'), int(query.get('limit') or 20))
            elif path == 'audit':
                result = {'audits': [json.loads(row['data']) for row in platform.db.all('SELECT data FROM audits WHERE user_id=? AND course_id=? ORDER BY at DESC LIMIT 100', (user, scope()['courseId']))]}
            elif path == 'invocations':
                result = {'invocations': [{'id': r['id'], 'courseId': r['course_id'], 'status': r['status'], 'provider': r['provider'], 'at': r['at'], 'usage': json.loads(r['usage_json']) if r['usage_json'] else None, 'billingStatus': r['billing_status']} for r in platform.db.all('SELECT * FROM invocations WHERE user_id=? AND course_id=? ORDER BY at DESC LIMIT 100', (user, scope()['courseId']))]}
            else:
                raise DomainError('NOT_FOUND')
            return {'ok': True, **result}
        except Exception as error:
            def known(err):
                if isinstance(err, DomainError):
                    return err.code
                for child in getattr(err, 'exceptions', []):
                    code = known(child)
                    if code:
                        return code
            code = known(error) or ('INVALID_REQUEST' if isinstance(error, (KeyError, TypeError, ValueError)) else 'PLATFORM_ERROR')
            status = 403 if re.search('AUTH|ORIGIN', code) else 409 if 'CONFLICT' in code else 404 if 'NOT_FOUND' in code else 413 if 'TOO_LARGE' in code else 405 if code == 'METHOD_NOT_ALLOWED' else 400
            return JSONResponse({'ok': False, 'error': code}, status_code=status)
