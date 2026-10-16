"""FastAPI assembly preserving browser HTTP/SSE contracts and static allowlists."""
import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, Response
from .config import load_config
from .contracts import LIMITS, normalize_chat_request
from .core import DomainError, Cancellation, dumps
from .rag import RagService
from .providers import MimoProvider
from .mcp import ToolGateway
from .agent.agent import Agent
from .agent.learning_workflow import LearningWorkflow

PUBLIC_SHARED = {'/shared/learning.js', '/shared/contracts/index.js', '/shared/fixtures/course.js', '/shared/rag/index.js', '/shared/agent/local-answer.js', '/shared/agent/sse.js', '/shared/agent/context.js', '/shared/agent/tasks.js'}


def create_app(config=None, rag=None, tools=None, model=None, learning_handler=None, platform=None):
    config = config or load_config()
    rag, tools = rag or RagService(), tools or ToolGateway()
    model = model or MimoProvider(config['ai'])
    if platform is None and config.get('platform', {}).get('enabled'):
        from .platform import Platform
        options = config['platform']
        platform = Platform(options['dataDir'], rag, options.get('userId', 'local-user'), options.get('apiSlots', 2))
    if platform:
        from .platform.api_provider import TrackedProvider
        from .platform.workflow import StoredWorkflow
        managed = TrackedProvider(platform, model, platform.scope('course-default'))
    else:
        managed = model
    agent = Agent(rag, managed, tools)
    fallback = LearningWorkflow(managed, tool_timeout_ms=config.get('agent', {}).get('toolTimeoutMs', 5000))
    workflow = StoredWorkflow(platform, model, rag, fallback) if platform else fallback
    @asynccontextmanager
    async def lifespan(app):
        if platform:
            platform.jobs.start()
        try:
            yield
        finally:
            if platform:
                await platform.close()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.model, app.state.workflow = model, workflow
    app.state.platform = platform
    if platform:
        from .platform.http import PlatformHandler
        app.include_router(PlatformHandler(platform).router)
    if learning_handler:
        app.include_router(learning_handler.router)

    @app.middleware('http')
    async def same_origin(request, call_next):
        if request.url.path.startswith('/api/') and request.headers.get('origin') and request.headers['origin'] != 'http://'+request.headers.get('host', ''):
            return JSONResponse({'ok': False, 'error': 'ORIGIN_FORBIDDEN'}, status_code=403)
        return await call_next(request)

    async def body(request, limit=LIMITS['requestBytes'], binary=False):
        result = bytearray()
        async for chunk in request.stream():
            result.extend(chunk)
            if len(result) > limit:
                raise DomainError('FILE_TOO_LARGE' if binary else 'REQUEST_TOO_LARGE', status=413)
        if binary:
            return bytes(result)
        try:
            return json.loads(result)
        except (ValueError, UnicodeError):
            raise DomainError('INVALID_JSON', status=400) from None

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({'ok': False, 'error': error.code}, status_code=error.details.get('status', 400))

    @app.get('/api/health')
    async def health():
        return {'ok': True, 'engine': 'xiaomi-mimo' if config['ai'].get('apiKey') else 'local-fallback', 'model': config['ai'].get('model'), 'runtime': 'python',
                **({'instanceId': app.state.instance_id} if getattr(app.state, 'instance_id', None) else {}),
                **({'platform': {'schemaVersion': '1.0', 'storage': 'sqlite', 'inference': 'external-api-only', 'resources': platform.resources.stats()}} if platform else {})}

    @app.post('/api/{kind}')
    async def json_endpoint(kind: str, request: Request):
        if kind == 'parse':
            document_kind = request.query_params.get('type')
            if document_kind not in ('pdf', 'docx'):
                return JSONResponse({'ok': False, 'error': 'UNSUPPORTED_DOCUMENT_TYPE'}, status_code=400)
            data = await body(request, LIMITS['fileBytes'], True)
            try:
                return await rag.parse_document(data, document_kind)
            except DomainError:
                return {'ok': False, 'error': 'PARSE_FAILED'}
        if kind not in ('ai', 'agent', 'topics', 'questions'):
            return JSONResponse({'ok': False, 'error': 'ROUTE_NOT_FOUND'}, status_code=404)
        value = await body(request)
        if kind in ('ai', 'agent'):
            normalize_chat_request(value)
        if not isinstance(value, dict):
            raise DomainError('INVALID_REQUEST')
        signal = Cancellation()
        async def disconnected():
            while True:
                if await request.is_disconnected():
                    signal.cancel()
                    return
                await asyncio.sleep(.1)
        worker = asyncio.create_task((workflow if kind == 'agent' else agent).run(value, signal) if kind in ('ai', 'agent') else getattr(agent, kind)(value, signal))
        watcher = asyncio.create_task(disconnected())
        try:
            done, _ = await asyncio.wait([worker, watcher], return_when=asyncio.FIRST_COMPLETED)
            if watcher in done:
                worker.cancel()
                raise asyncio.CancelledError()
            return worker.result()
        except DomainError as error:
            code = error.code if error.code in ('NO_SOURCES', 'EMPTY_QUESTION', 'AI_TIMEOUT', 'AI_EMPTY') else 'AI_UNAVAILABLE'
            return {'ok': False, 'error': code, 'engine': 'local-fallback'}
        finally:
            watcher.cancel()

    @app.post('/api/{kind}/stream')
    async def stream_endpoint(kind: str, request: Request):
        if kind not in ('ai', 'agent'):
            return JSONResponse({'ok': False, 'error': 'ROUTE_NOT_FOUND'}, status_code=404)
        value = await body(request)
        normalize_chat_request(value)
        signal = Cancellation()
        async def stream():
            try:
                async for event in (workflow if kind == 'agent' else agent).stream(value, signal):
                    if await request.is_disconnected():
                        signal.cancel()
                        return
                    yield 'data: '+dumps(event)+'\n\n'
            except DomainError as error:
                yield 'data: '+dumps({'type': 'error', 'error': error.code if error.code in ('NO_SOURCES', 'EMPTY_QUESTION', 'AI_INVALID_RESPONSE', 'AI_TIMEOUT') else 'AI_UNAVAILABLE'})+'\n\n'
            except asyncio.CancelledError:
                signal.cancel()
                raise
            finally:
                signal.cancel()
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    @app.api_route('/{requested:path}', methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
    async def static(requested: str, request: Request):
        if request.method not in ('GET', 'HEAD'):
            return JSONResponse({'error': 'Method not allowed'}, status_code=405)
        requested = '/'+unquote(requested) if requested else '/index.html'
        shared = requested in PUBLIC_SHARED
        allowed = shared or requested == '/index.html' or bool(re.fullmatch(r'/(?:css/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+\.css|js/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+\.js|assets/[a-zA-Z0-9_-]+\.(svg|png|jpg|woff2))', requested))
        if not allowed:
            return Response('Not found', status_code=404)
        root = Path(config['root']) if shared else Path(config['root'])/'frontend'
        file = (root/requested.lstrip('/')).resolve()
        if not file.is_relative_to(root.resolve()) or not file.is_file():
            return Response('Not found', status_code=404)
        headers = {'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff'}
        if request.method == 'HEAD':
            return Response(headers={**headers, 'Content-Length': str(file.stat().st_size)})
        return FileResponse(file, headers=headers)
    return app
