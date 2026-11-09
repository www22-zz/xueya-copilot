"""Request/job ownership without mutating the shared platform's legacy identity."""
from contextvars import ContextVar
from contextlib import contextmanager
import hashlib
import json

from fastapi import Request

owner_context = ContextVar('xueya_scope_owner', default=None)


def account_owner(record):
    # Persisted on rename; existing shared local-user data is never auto-assigned.
    return record.get('dataOwner') or 'account-' + hashlib.sha256(record['username'].encode()).hexdigest()[:40]


@contextmanager
def bind_owner(owner):
    token = owner_context.set(owner)
    try:
        yield
    finally:
        owner_context.reset(token)


class AccountBoundaryMiddleware:
    """Bind trusted identity for the complete response, including streaming tasks.

    Projection lives at the HTTP boundary so old routers and job/entity exports
    cannot accidentally bypass the platform-source policy. Internal evidence is
    left intact for version validation and model auditing.
    """
    def __init__(self, app, host):
        self.app, self.host = app, host

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/api/'):
            return await self.app(scope, receive, send)
        account = getattr(self.host.state, 'account', None)
        record = account.current(Request(scope)) if account and account.authorized(Request(scope)) else None
        owner = account_owner(record) if record else None
        expected = Request(scope).headers.get('x-xueya-owner')
        if expected and owner != expected:
            from fastapi.responses import JSONResponse
            return await JSONResponse({'ok': False, 'error': 'ACCOUNT_CHANGED'}, status_code=409)(scope, receive, send)
        platform = getattr(self.host.state, 'platform', None)
        if owner and not platform.repo.courses(owner):
            platform.repo.ensure_course(owner, {'id': 'course-default', 'name': '个人参考资料'})
        content_type, pending, project = '', b'', None
        async def projected_send(message):
            nonlocal content_type, pending, project
            if message['type'] == 'http.response.start':
                content_type = dict(message['headers']).get(b'content-type', b'').decode()
                if 'application/json' in content_type or 'text/event-stream' in content_type:
                    message = {**message, 'headers': [(k, v) for k, v in message['headers'] if k.lower() != b'content-length']}
            elif message['type'] == 'http.response.body' and platform:
                from .rag_scope_adapter import public_api_projector
                # Resolve at send time: uploads/revisions may have happened since
                # request start. The projector includes every authorized course.
                if project is None:
                    project = public_api_projector(platform)
                if 'application/json' in content_type:
                    pending += message.get('body', b'')
                    if message.get('more_body'):
                        return
                    message = {**message, 'body': json.dumps(project(json.loads(pending)), ensure_ascii=False).encode()}
                elif 'text/event-stream' in content_type:
                    pending += message.get('body', b'')
                    frames = []
                    while b'\n\n' in pending:
                        frame, pending = pending.split(b'\n\n', 1)
                        lines = []
                        for line in frame.split(b'\n'):
                            if line.startswith(b'data: '):
                                value = project(json.loads(line[6:]))
                                if project.has_protected_sources:
                                    # Protected evidence can span multiple content
                                    # frames. Publish prose only with the verified
                                    # completion; never leak split raw JSON/quotes.
                                    if value.get('type') in ('content', 'reasoning'):
                                        continue
                                    if value.get('type') == 'done' and isinstance(value.get('answer'), str):
                                        content = {'type': 'content', 'text': json.dumps({'answer': value['answer'], 'sources': value.get('sources', [])}, ensure_ascii=False), 'model': value.get('model')}
                                        lines.append(b'data: ' + json.dumps(content, ensure_ascii=False).encode() + b'\n\n')
                                line = b'data: ' + json.dumps(value, ensure_ascii=False).encode()
                            lines.append(line)
                        frames.append(b'\n'.join(lines) + b'\n\n')
                    # Incomplete frames cannot be published as successful output.
                    message = {**message, 'body': b''.join(frames)}
            await send(message)
        with bind_owner(owner):
            await self.app(scope, receive, projected_send)
