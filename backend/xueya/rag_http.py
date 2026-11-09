"""Opt-in registration for E's existing FastAPI host, using its auth/lifespan/storage.

E can call install_rag(app) once after create_app; no schema migration is needed.
For isolated integration: uvicorn backend.xueya.rag_http:create_rag_app --factory.
"""
from contextlib import asynccontextmanager
import os
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import Response
from urllib.parse import quote

from .app import body, connected_work, create_app, json_body, success
from .common import require
from .document_limits import document_limit
from .rag_api import ApiSettings, EmbeddingProvider, OcrProvider, RerankProvider
from .rag_service import RagService
from .rag_moark import MinerUProvider, QwenEmbeddingProvider


def configured_service(platform, root):
    env = dict(os.environ)
    file = root / ".env"
    if file.exists():
        for line in file.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env.setdefault(key.strip(), value.strip().strip("\"'"))
    def settings(prefix, default_url, dimension=1024):
        key, model = env.get(prefix+"_API_KEY", ""), env.get(prefix+"_MODEL", "")
        if not key or not model:
            return None
        return ApiSettings(key=key, model=model, base_url=env.get(prefix+"_BASE_URL", default_url),
                           dimension=int(env.get(prefix+"_DIMENSION", str(dimension))), revision=env.get(prefix+"_REVISION", "1"),
                           timeout=float(env.get(prefix+"_TIMEOUT_SECONDS", "45")))
    embedding_kind, ocr_kind = env.get("RAG_EMBEDDING_PROVIDER", "jina"), env.get("RAG_OCR_PROVIDER", "mistral")
    require(embedding_kind in ("jina", "moark-qwen"), "INVALID_EMBEDDING_PROVIDER")
    require(ocr_kind in ("mistral", "moark-mineru"), "INVALID_OCR_PROVIDER")
    embedding = settings("RAG_EMBEDDING", "https://api.moark.com/v1" if embedding_kind == "moark-qwen" else "https://api.jina.ai/v1",
                         (4096 if "8B" in env.get("RAG_EMBEDDING_MODEL", "") else 2048) if embedding_kind == "moark-qwen" else 1024)
    rerank = settings("RAG_RERANK", "https://api.jina.ai/v1")
    ocr = settings("RAG_OCR", "https://api.moark.com/v1" if ocr_kind == "moark-mineru" else "https://api.mistral.ai/v1")
    return RagService(platform, embedding=(QwenEmbeddingProvider(platform, embedding, name="moark-qwen-embedding") if embedding_kind == "moark-qwen" else EmbeddingProvider(platform, embedding, name="jina-embedding")) if embedding else None,
                      rerank=RerankProvider(platform, rerank, name="jina-rerank") if rerank else None,
                      ocr=(MinerUProvider(platform, ocr, name="moark-mineru-ocr") if ocr_kind == "moark-mineru" else OcrProvider(platform, ocr, name="mistral-ocr")) if ocr else None)


def install_rag(app, *, service_factory=None):
    if getattr(app.state, "rag_installed", False):
        if service_factory:
            app.state.rag_service_factory = service_factory
        return app
    app.state.rag_installed = True
    app.state.rag_service_factory = service_factory
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(host):
        async with previous(host):
            require(host.state.platform is not None, "RAG_REQUIRES_PLATFORM")
            factory = host.state.rag_service_factory
            host.state.rag = factory(host.state.platform) if factory else configured_service(host.state.platform, host.state.config.root)
            yield
    app.router.lifespan_context = lifespan
    router = APIRouter(prefix="/api/platform/rag")

    def service(request):
        require(secrets.compare_digest(request.headers.get("x-xueya-token", ""), app.state.token), "AUTH_REQUIRED")
        return app.state.rag

    @router.api_route("/{operation}", methods=["GET", "POST"])
    async def route(operation: str, request: Request):
        rag = service(request)
        binary = operation == "upload"
        value = ({"buffer": await body(request, document_limit(request.query_params.get('name')))} if binary else await json_body(request, 524288)) if request.method == "POST" else {}
        q = request.query_params
        scope = rag.p.scope((q.get("courseId") or "course-default") if binary or request.method == "GET" else value.get("courseId", "course-default"))
        post = request.method == "POST"
        if operation == "capabilities" and not post:
            return success(capabilities={"formats": ["txt", "md", "pdf", "docx", "pptx"], "embedding": bool(rag.embedding), "ocr": bool(rag.ocr), "rerank": bool(rag.rerank), "index": "exact-cosine", "storage": "sqlite-entities", "inference": "external-api-only"})
        if operation == "upload" and post:
            return success(job=rag.upload(scope, value["buffer"], q.get("name"), request.headers.get("idempotency-key"), previous_document_id=q.get("previousDocumentId")))
        if operation in ("parse", "ocr", "index") and post:
            require(type(value.get("version")) is int and value["version"] > 0, "INVALID_VERSION")
            return success(job=rag.submit(scope, "rag-"+operation, value.get("documentId"), value.get("idempotencyKey"), expected_version=value["version"], pages=value.get('pages')))
        if operation == "search" and post:
            allowed = {"courseId", "query", "history", "newTopic", "documentIds", "section", "mode", "budget", "limit"}
            require(not set(value)-allowed and isinstance(value.get("history", []), list) and len(value.get("history", [])) <= 12 and type(value.get("newTopic", False)) is bool, "INVALID_SEARCH")
            from .rag_scope_adapter import ScopeAdapter
            adapter = ScopeAdapter(rag.p, scope.user_id)
            evidence = await connected_work(request, adapter.search(rag, scope.course_id, value.get("query"), history=value.get("history", []), new_topic=value.get("newTopic", False),
                            document_ids=value.get("documentIds"), section=value.get("section"), mode=value.get("mode", "hybrid"), budget=value.get("budget", 2000), limit=value.get("limit", 6)))
            from .rag_scope_adapter import public_api_value
            return success(evidence=public_api_value(rag.p,evidence,scope.course_id))
        if operation == "read" and not post:
            from .rag_scope_adapter import is_platform_source, public_source_projection
            source_id = q.get("sourceId")
            from .rag_scope_adapter import ScopeAdapter
            adapter = ScopeAdapter(rag.p, scope.user_id)
            origin, original = adapter.resolve_source(source_id, scope.course_id)
            source = adapter.read(rag, source_id, scope.course_id)
            doc = rag.document(origin, source.get('documentId'), active=True) if source.get('documentId') else None
            if is_platform_source(source, origin, doc):
                return success(source=public_source_projection(source, True), protected=True)
            return success(**rag.context(origin, original))
        if operation == "validate" and post:
            from .rag_scope_adapter import ScopeAdapter
            adapter = ScopeAdapter(rag.p, scope.user_id)
            citation = value.get("citation")
            try:
                valid = adapter.validate_citation(rag, citation, scope.course_id)
            except Exception:
                valid = False
            return success(valid=valid)
        if operation == "export" and not post:
            from .rag_scope_adapter import is_platform_document
            doc = rag.document(scope, q.get("documentId"), active=True)
            if is_platform_document(doc, scope):
                return success(id=doc["id"], name=doc["name"], protected=True, chunks=[])
            return success(**rag.export(scope, q.get("documentId")))
        if operation == "original" and not post:
            from .rag_scope_adapter import is_platform_document
            from fastapi.responses import JSONResponse
            doc = rag.document(scope, q.get("documentId"), active=True)
            if is_platform_document(doc, scope):
                return JSONResponse({"ok": False, "error": "FORBIDDEN_PLATFORM_DOCUMENT"}, status_code=403)
            return Response(rag.p.files.read(doc["fileHash"]), media_type="application/octet-stream", headers={"Content-Disposition": "attachment; filename*=UTF-8''"+quote(doc["name"], safe="")})
        if operation == "correct" and post:
            require(type(value.get("version")) is int and value["version"] > 0, "INVALID_VERSION")
            return success(**rag.correct(scope, value.get("documentId"), value["version"], value.get("blockId"), value.get("replacement"), value.get("reason")))
        if operation == "remove" and post:
            require(type(value.get("version")) is int and value["version"] > 0, "INVALID_VERSION")
            return success(**rag.remove(scope, value.get("documentId"), value["version"]))
        require(False, "NOT_FOUND")

    # Existing host has catch-all API/static routes. Registration must precede those.
    count = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[count:]
    del app.router.routes[count:]
    app.router.routes[0:0] = added
    return app


def create_rag_app():
    return install_rag(create_app())
