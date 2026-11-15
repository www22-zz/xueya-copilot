"""FastAPI HTTP assembly. Public wire contracts and frontend assets stay unchanged."""
from __future__ import annotations
import asyncio
import json
import re
import secrets
from contextlib import asynccontextmanager, aclosing, AsyncExitStack
from urllib.parse import quote
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import ValidationError
from .agent import Agent, normalize_request
from .common import AppError, dumps, identifier, require
from .config import Config, UI_BUILD, load_config
from .jobs import TERMINAL
from .mcp_core import open_session, platform_registry
from .parse_worker import parse_artifact
from .platform import Platform
from .provider import MimoProvider
from .execution_budget import BudgetMiddleware

PUBLIC_SHARED = frozenset("/shared/learning.js /shared/contracts/index.js /shared/fixtures/course.js /shared/rag/index.js /shared/agent/local-answer.js /shared/agent/sse.js /shared/agent/context.js /shared/agent/tasks.js".split())


class ClosingStreamingResponse(StreamingResponse):
    """Close task-scoped MCP generators before the HTTP stream task exits."""

    async def stream_response(self, send):
        try:
            await super().stream_response(send)
        finally:
            await self.body_iterator.aclose()


def success(**value):
    return {"ok": True, **value}


def error_response(code, status=None):
    if status is None:
        status = 403 if "AUTH" in code or "ORIGIN" in code else 409 if "CONFLICT" in code else 404 if "NOT_FOUND" in code else 413 if "TOO_LARGE" in code else 400
    return JSONResponse({"ok": False, "error": code}, status_code=status)


def ai_error_code(error, allowed=()):
    code = getattr(error, 'code', None)
    policy = {'AI_TRUNCATED', 'AI_INCOMPLETE', 'AI_UNEXPECTED_TOOL_CALL', 'AI_RUN_TIMEOUT',
              'AI_MODEL_BUDGET_EXCEEDED', 'AI_TOOL_BUDGET_EXCEEDED', 'AI_OUTPUT_BUDGET_EXCEEDED',
              'AI_COST_BUDGET_EXCEEDED', 'AI_PRICING_REQUIRED', 'STALE_EVIDENCE'}
    return code if code in policy or code in allowed else 'AI_TIMEOUT' if isinstance(error, TimeoutError) else 'AI_UNAVAILABLE'


async def body(request, limit=524288):
    buffer = bytearray()
    async for chunk in request.stream():
        buffer.extend(chunk)
        require(len(buffer) <= limit, "REQUEST_TOO_LARGE")
    return bytes(buffer)


async def json_body(request, limit=524288):
    try:
        value = json.loads(await body(request, limit))
    except (ValueError, UnicodeError) as error:
        raise AppError("INVALID_JSON") from error
    require(isinstance(value, dict), "INVALID_REQUEST")
    return value


async def connected_work(request, operation):
    """JSON routes also abort a provider/MCP operation when the browser disconnects."""
    async def disconnect():
        while True:
            message = await request.receive()
            if message["type"] == "http.disconnect":
                return
    work, monitor = asyncio.create_task(operation), asyncio.create_task(disconnect())
    try:
        done, _ = await asyncio.wait([work, monitor], return_when=asyncio.FIRST_COMPLETED)
        if work in done:
            return work.result()
        raise asyncio.CancelledError
    finally:
        monitor.cancel()
        if not work.done():
            work.cancel()
        await asyncio.gather(work, monitor, return_exceptions=True)


def create_app(config: Config | None = None, *, provider=None, start_jobs=True):
    config = config or load_config()

    @asynccontextmanager
    async def lifespan(app):
        platform = Platform(config.data_dir, config.api_slots, preserve_legacy_data=config.preserve_legacy_data) if config.platform_enabled else None
        app.state.platform = platform
        if platform:
            platform.jobs.budget_config = config
        from .account import LocalAccount
        app.state.account = LocalAccount(platform) if platform else None
        app.state.provider = provider or MimoProvider(config, platform)
        if isinstance(app.state.provider, MimoProvider):
            app.state.provider.platform = platform
        app.state.agent = Agent(app.state.provider, platform)
        app.state.token = secrets.token_hex(32)
        if platform:
            from .practice_analysis import PracticeAnalysis
            app.state.practice_analysis = PracticeAnalysis(platform, app.state.provider, config)
            from .analysis_schedule import AnalysisSchedule
            app.state.analysis_schedule=AnalysisSchedule(app.state.practice_analysis)
        if platform and start_jobs:
            platform.jobs.start()
            app.state.analysis_schedule.start()
        async with AsyncExitStack() as resources:
            try:
                if isinstance(app.state.provider, MimoProvider):
                    await resources.enter_async_context(app.state.provider.connection_pool())
                yield
            finally:
                if platform:
                    await app.state.analysis_schedule.stop()
                    await platform.close()
    app = FastAPI(title="学涯 Copilot API", version="2.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(BudgetMiddleware, config=config)
    app.state.config = config
    app.state.instance_id = None
    app.state.stop_token = None
    app.state.request_stop = None
    app.state.account = None
    from .account_scope import AccountBoundaryMiddleware
    app.add_middleware(AccountBoundaryMiddleware, host=app)

    @app.middleware("http")
    async def same_origin(request, call_next):
        if request.url.path.startswith("/api/"):
            host, origin = request.headers.get("host", ""), request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{host}":
                return error_response("ORIGIN_FORBIDDEN")
            if request.url.path.startswith("/api/platform/") and not re.fullmatch(r"(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?", host):
                return error_response("ORIGIN_FORBIDDEN")
        account = app.state.account
        if account and request.url.path.startswith('/api/') and request.url.path not in ('/api/health', '/api/account/status', '/api/account/login', '/api/account/register', '/api/platform/shutdown') and not account.authorized(request):
            return error_response('LOGIN_REQUIRED', 401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(AppError)
    async def app_error(request, error):
        return error_response(error.code)

    @app.exception_handler(ValidationError)
    async def validation_error(request, error):
        return error_response("INVALID_REQUEST", 400)

    @app.get("/api/health")
    async def health():
        platform = app.state.platform
        return success(engine="xiaomi-mimo" if config.api_key else "local-fallback", model=config.model,
                       uiBuild=UI_BUILD,
                       ragGeneralFallbackEnabled=config.rag_general_fallback,
                       **({"instanceId": app.state.instance_id} if app.state.instance_id else {}),
                       **({"platform": {"schemaVersion": "1.0", "storage": "sqlite", "inference": "external-api-only", "resources": platform.resources.stats()}} if platform else {}))

    @app.post("/api/platform/shutdown")
    async def shutdown(request: Request):
        require(app.state.stop_token is not None and secrets.compare_digest(request.headers.get("x-xueya-stop", ""), app.state.stop_token), "AUTH_REQUIRED")
        if app.state.request_stop:
            app.state.request_stop()
        return success()

    @app.post("/api/parse")
    async def parse(request: Request):
        kind = request.query_params.get("type", "pdf")
        require(kind in ("pdf", "docx"), "UNSUPPORTED_DOCUMENT_TYPE")
        buffer = await body(request, 10485760)
        platform = app.state.platform
        release = platform.resources.acquire("cpu") if platform else None
        if platform and release is None:
            return error_response("CPU_BUSY", 429)
        try:
            return await connected_work(request, parse_artifact(buffer, kind))
        except (AppError, TimeoutError):
            return {"ok": False, "error": "PARSE_FAILED"}
        finally:
            if release:
                release()

    @app.post("/api/tts")
    async def tts_endpoint(request: Request):
        require(bool(re.fullmatch(r'(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?', request.headers.get('host', ''))), 'ORIGIN_FORBIDDEN')
        require(secrets.compare_digest(request.headers.get('x-xueya-token', ''), app.state.token), 'AUTH_REQUIRED')
        value = await json_body(request, 32768)
        require(isinstance(value.get('text'), str), 'INVALID_SPEECH_REQUEST')
        text = value['text'].strip()
        voice = value.get('voice', 'mimo_default')
        require(voice in ('mimo_default', '冰糖', '茉莉', '苏打', '白桦', 'Mia', 'Chloe', 'Milo', 'Dean'), 'INVALID_SPEECH_REQUEST')
        course = value.get('courseId', 'course-default')
        require(isinstance(course, str), 'INVALID_COURSE')
        if not text:
            return JSONResponse({"ok": False, "error": "EMPTY_TEXT"}, status_code=400)

        plain = re.sub(r'```[\s\S]*?```', '（代码片段已省略）', text)
        plain = re.sub(r'`([^`]+)`', r'\1', plain)
        plain = re.sub(r'\[\d+\]', '', plain)
        plain = re.sub(r'[*#_~>|]', '', plain)
        plain = re.sub(r'https?://\S+', '网页链接', plain)
        plain = re.sub(r'\s+', ' ', plain).strip()
        if not plain:
            return JSONResponse({"ok": False, "error": "EMPTY_TEXT"}, status_code=400)

        if len(plain) > 1000:
            plain = plain[:990] + '…'

        host = getattr(app.state, 'learning', None)
        if not host or not app.state.config.api_key:
            return JSONResponse({"ok": False, "error": "TTS_NOT_CONFIGURED", "fallback": True})

        try:
            from .learning_ui_api import Speech
            speech = Speech(host, course)
            result = await connected_work(request, speech.synthesize({'text': plain, 'voice': voice}))
            return {
                "ok": True,
                "audio": f"data:{result['mime']};base64,{result['data']}",
                "model": result.get('model', 'mimo-v2.5-tts'),
            }
        except Exception as error:
            code = ai_error_code(error, ('TTS_NOT_CONFIGURED', 'INVALID_SPEECH_RESPONSE', 'COURSE_NOT_FOUND', 'API_BUSY'))
            return JSONResponse({"ok": False, "error": code, "fallback": True})

    @app.post("/api/{task:path}")
    async def api(request: Request, task: str):
        if task.startswith("platform/"):
            return await platform_route(request, "/"+task[len("platform/"):])
        require(task in ("ai", "ai/stream", "agent", "agent/stream", "topics", "questions", "suggestions", "agent/suggestions"), "NOT_FOUND")
        value = await json_body(request)
        agent = app.state.agent
        if task in ("suggestions", "agent/suggestions"):
            try:
                return await connected_work(request, agent.suggestions(value))
            except Exception as error:
                return {"ok": False, "error": ai_error_code(error, ('INVALID_REQUEST', 'EMPTY_QUESTION'))}
        if task in ("topics", "questions"):
            try:
                return await connected_work(request, agent.practice(task, value))
            except Exception as error:
                code = ai_error_code(error, ('NO_SOURCES', 'AI_EMPTY'))
                return {"ok": False, "error": code}
        normalize_request(value)
        iterator = agent.workflow(value) if task.startswith("agent") else agent.direct(value, stream=task.endswith("stream"))
        from .rag_scope_adapter import public_api_projector
        public = public_api_projector(app.state.platform, value.get('courseId') or 'course-default')
        if task.endswith("stream"):
            async def events():
                try:
                    async with aclosing(iterator):
                        async for event in iterator:
                            yield "data: "+dumps(public(event))+"\n\n"
                except Exception as error:
                    code = ai_error_code(error, ('NO_SOURCES', 'EMPTY_QUESTION', 'AI_INVALID_RESPONSE'))
                    yield "data: "+dumps({"type": "error", "error": code})+"\n\n"
            return ClosingStreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

        async def run():
            async with aclosing(iterator):
                async for event in iterator:
                    if event["type"] == "done":
                        return public({k: v for k, v in event.items() if k != "type"})
            raise AppError("AGENT_INCOMPLETE")
        try:
            return await connected_work(request, run())
        except Exception as error:
            code = ai_error_code(error, ('NO_SOURCES', 'EMPTY_QUESTION'))
            return {"ok": False, "error": code, "engine": "local-fallback"}

    async def platform_route(request, path):
        result = await internal_platform_route(request, path)
        if isinstance(result, dict):
            from .rag_scope_adapter import public_api_value
            return public_api_value(app.state.platform, result, request.query_params.get('courseId') or 'course-default')
        return result

    async def internal_platform_route(request, path):
        p = app.state.platform
        require(p is not None, "NOT_FOUND")
        repo, db, user_id, method = p.repo, p.db, p.scope_user_id, request.method
        if path == "/bootstrap" and method == "GET":
            portable = getattr(app.state, 'portable_knowledge', None)
            prepared = await portable.ensure(user_id) if portable else None
            corpus = getattr(app.state, 'portable_corpus', None)
            prepared_corpus = await corpus.ensure(user_id) if corpus else None
            return success(token=app.state.token, schemaVersion="1.0", workspace=repo.get_workspace(user_id), courses=repo.courses(user_id), jobs=p.jobs.list(user_id), resources=p.resources.stats(), **({'portableKnowledge': prepared} if prepared else {}), **({'portableCorpus': prepared_corpus} if prepared_corpus else {}))
        require(secrets.compare_digest(request.headers.get("x-xueya-token", ""), app.state.token), "AUTH_REQUIRED")
        binary = path in ("/documents/upload", "/documents/import-original")
        value = {}
        if method in ("PUT", "POST"):
            value = {"buffer": await body(request, 10485760)} if binary else await json_body(request, 25000000)
        query = request.query_params
        course_id = value.get("courseId") or query.get("courseId") or "course-default"
        scope = lambda: p.scope(course_id)
        if path == "/workspace":
            if method == "GET":
                return success(workspace=repo.get_workspace(user_id))
            if method == "PUT":
                return success(workspace=repo.save_workspace(user_id, value.get("workspace"), value.get("expectedVersion")))
        if path == "/migration/preview" and method == "POST":
            return success(preview=p.migration.preview(user_id, value))
        if path == "/migration/apply" and method == "POST":
            return success(**p.migration.apply(user_id, value))
        if path == "/migration/backup" and method == "GET":
            return success(backup=p.migration.backup(user_id, query.get("id")))
        if path == "/courses" and method == "POST":
            repo.ensure_course(user_id, value)
            return success(courses=repo.courses(user_id))
        if path == "/documents/upload" and method == "POST":
            rag = getattr(app.state, "rag", None)
            if rag:
                job = rag.upload(scope(), value["buffer"], query.get("name", ""), request.headers.get("idempotency-key"), previous_document_id=query.get("previousDocumentId"))
                if query.get('generatePractice') == '1':
                    document_id = json.loads(p.db.one('SELECT input FROM jobs WHERE id=?', (job['id'],))['input'])['documentId']
                    account = (app.state.account.current(request) or {}).get('username') or 'local'
                    app.state.practice_generation.watch(account, scope(), document_id)
                return success(job=job)
            return success(job=p.upload(scope(), value["buffer"], query.get("name", ""), request.headers.get("idempotency-key"), query.get("previousDocumentId")))
        if path == "/documents/import-original" and method == "POST":
            doc = p.document(scope(), query.get("documentId"))
            file = p.files.put(value["buffer"])
            require(not doc.get("fileHash") or doc["fileHash"] == file["hash"], "ORIGINAL_CONFLICT")
            saved = repo.put(scope(), "document", doc["id"], {**doc, "fileHash": file["hash"], "size": file["size"], "originalAvailable": True}, doc["version"])
            return success(document={**saved["value"], "version": saved["version"]})
        if path == "/documents" and method == "GET":
            from .document_catalog import is_demo_placeholder
            return success(documents=[d for d in repo.all(scope(), "document") if not is_demo_placeholder(d)])
        if path == "/documents/original" and method == "GET":
            doc = p.document(scope(), query.get("documentId"))
            from .rag_scope_adapter import is_platform_document
            if is_platform_document(doc, scope()):
                from fastapi.responses import JSONResponse
                return JSONResponse({"ok": False, "error": "FORBIDDEN_PLATFORM_DOCUMENT"}, status_code=403)
            return Response(p.files.read(doc.get("fileHash")), media_type="application/octet-stream", headers={"Content-Disposition": "attachment; filename*=UTF-8''"+quote(doc["name"], safe="")})
        if path == "/documents/update" and method == "POST":
            require(type(value.get("version")) is int and value["version"] > 0, "INVALID_VERSION")
            doc, changes = p.document(scope(), value.get("documentId")), value.get("changes")
            require(isinstance(changes, dict) and isinstance(changes.get("name"), str) and bool(changes["name"].strip()), "INVALID_DOCUMENT")
            tags = [str(t) for t in changes["tags"][:30]] if isinstance(changes.get("tags"), list) else doc.get("tags", [])
            saved = repo.put(scope(), "document", doc["id"], {**doc, "name": changes["name"][:200], "tags": tags, "chapter": str(changes.get("chapter", doc.get("chapter", "")))[:200]}, value.get("version"))
            return success(document={**saved["value"], "version": saved["version"]})
        if path == "/documents/remove" and method == "POST":
            require(type(value.get("version")) is int and value["version"] > 0, "INVALID_VERSION")
            rag = getattr(app.state, "rag", None)
            if rag and p.document(scope(), value.get("documentId")).get("activeArtifact"):
                return success(**rag.remove(scope(), value.get("documentId"), value["version"]))
            with db.transaction():
                doc = p.document(scope(), value.get("documentId"))
                repo.put(scope(), "document", doc["id"], doc, value.get("version"), deleted=True)
                for source in repo.all(scope(), "source"):
                    if source.get("documentId") == doc["id"]:
                        repo.put(scope(), "source", source["id"], source, deleted=True)
            return success(removed=True, retainedForRecovery=True)
        if path == "/jobs":
            if method == "GET":
                return success(jobs=p.jobs.list(user_id))
            if method == "POST":
                return success(job=p.jobs.submit(user_id, value))
        if path == "/jobs/status" and method == "GET":
            job = p.jobs.get(query.get("id"), user_id)
            require(job is not None, "JOB_NOT_FOUND")
            return success(job=job)
        if path in ("/jobs/cancel", "/jobs/retry") and method == "POST":
            return success(job=(p.jobs.cancel if path.endswith("cancel") else p.jobs.retry)(value.get("id"), user_id))
        if path == "/jobs/events" and method == "GET":
            try:
                seq = int(request.headers.get("last-event-id") or query.get("after") or "0")
            except ValueError as error:
                raise AppError("INVALID_CURSOR") from error
            p.jobs.events(query.get("id"), user_id, seq)

            async def events():
                nonlocal seq
                while True:
                    batch = p.jobs.events(query.get("id"), user_id, seq)
                    for event in batch:
                        seq = event["seq"]
                        yield f"id: {seq}\ndata: {dumps(event)}\n\n"
                    if len(batch) < 100 and p.jobs.get(query.get("id"), user_id)["status"] in TERMINAL:
                        break
                    await asyncio.sleep(.3)
            return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
        if path == "/tools" and method == "GET":
            async with open_session(platform_registry(p, scope(), rag=getattr(app.state, 'rag', None), learning=getattr(app.state, 'learning', None))) as session:
                return success(tools=await session.list_tools(namespace=True))
        if path == "/tools/call" and method == "POST":
            async def call():
                async with open_session(platform_registry(p, scope(), rag=getattr(app.state, 'rag', None), learning=getattr(app.state, 'learning', None))) as session:
                    return success(data=await session.call(value.get("name"), value.get("arguments") or {}))
            return await connected_work(request, call())
        if path == "/actions/confirm" and method == "POST":
            return success(**p.authority.confirm(scope(), value))
        if path == "/actions/cancel" and method == "POST":
            return success(**p.authority.cancel(scope(), value.get("actionId")))
        if path == "/entities" and method == "GET":
            try:
                limit = int(query.get("limit", "20"))
            except ValueError as error:
                raise AppError("INVALID_LIMIT") from error
            from .rag_scope_adapter import public_api_value
            return success(**public_api_value(p,repo.list(scope(), query.get("kind"), query.get("cursor"), limit),course_id))
        if path == "/audit" and method == "GET":
            return success(audits=[json.loads(r["data"]) for r in db.all("SELECT data FROM audits WHERE user_id=? AND course_id=? ORDER BY at DESC LIMIT 100", (user_id, scope().course_id))])
        if path == "/invocations" and method == "GET":
            return success(invocations=[{"id": r["id"], "courseId": r["course_id"], "status": r["status"], "provider": r["provider"], "at": r["at"], "usage": json.loads(r["usage_json"]) if r["usage_json"] else None, "billingStatus": r["billing_status"]} for r in db.all("SELECT * FROM invocations WHERE user_id=? AND course_id=? ORDER BY at DESC LIMIT 100", (user_id, scope().course_id))])
        return error_response("NOT_FOUND", 404)

    @app.api_route("/api/platform/{path:path}", methods=["GET", "PUT"])
    async def platform_api(request: Request, path: str):
        return await platform_route(request, "/"+path)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    async def static(request: Request, path: str):
        requested = "/"+path if path else "/index.html"
        shared = requested in PUBLIC_SHARED
        frontend = requested in ("/index.html", "/algorithm-demo.html", "/reset.html", "/sw.js") or bool(re.fullmatch(r"/(?:css/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+\.css|js/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+\.js|assets/[a-zA-Z0-9_-]+\.(?:svg|png|jpg|woff2))", requested))
        if not shared and not frontend:
            return PlainTextResponse("Not found", status_code=404)
        root = config.root if shared else config.root / "frontend"
        target = (root / requested.lstrip("/")).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            return PlainTextResponse("Not found", status_code=404)
        suffix = target.suffix.lower()
        media_types = {
            ".woff2": "font/woff2", ".woff": "font/woff", ".svg": "image/svg+xml",
            ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        }
        media_type = media_types.get(suffix)
        if suffix in (".woff2", ".woff"):
            # Icon fonts are large (multi-MB) and stable. Cache them for a year and
            # send the bytes in one response: per-64KiB chunking over localhost can
            # take seconds on Windows, which left icon ligature names visible.
            headers = {"Cache-Control": "public, max-age=31536000, immutable"}
            return Response(content=target.read_bytes(), media_type=media_type or "font/woff2", headers=headers)
        return FileResponse(target, media_type=media_type, headers={"Cache-Control": "no-cache"})
    if config.platform_enabled:
        from .rag_http import install_rag
        from .learning_integration import install_learning
        install_rag(app)
        install_learning(app)
        from .workbench_http import install_workbench
        install_workbench(app)
        from .library_http import install_library
        install_library(app)
        from .knowledge_base import install_knowledge_base
        install_knowledge_base(app)
        from .chat_attachments import install_chat_attachments
        install_chat_attachments(app)
        from .account import install_account
        install_account(app)
        from .practice_api import install_practice
        install_practice(app)
        from .study_space_api import install_study_space
        install_study_space(app)
    return app
