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
from .rag_api import ApiSettings, EmbeddingProvider, OcrProvider, RerankProvider
from .rag_service import RagService


def configured_service(platform, root):
    env = dict(os.environ)
    file = root / ".env"
    if file.exists():
        for line in file.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env.setdefault(key.strip(), value.strip().strip("\"'"))
    def settings(prefix, default_url):
        key, model = env.get(prefix+"_API_KEY", ""), env.get(prefix+"_MODEL", "")
        if not key or not model:
            return None
        return ApiSettings(key=key, model=model, base_url=env.get(prefix+"_BASE_URL", default_url),
                           dimension=int(env.get(prefix+"_DIMENSION", "1024")), revision=env.get(prefix+"_REVISION", "1"))
    embedding = settings("RAG_EMBEDDING", "https://api.jina.ai/v1")
    rerank = settings("RAG_RERANK", "https://api.jina.ai/v1")
    ocr = settings("RAG_OCR", "https://api.mistral.ai/v1")
    return RagService(platform, embedding=EmbeddingProvider(platform, embedding, name="jina-embedding") if embedding else None,
                      rerank=RerankProvider(platform, rerank, name="jina-rerank") if rerank else None,
                      ocr=OcrProvider(platform, ocr, name="mistral-ocr") if ocr else None)


def install_rag(app, *, service_factory=None):
    require(not getattr(app.state, "rag_installed", False), "RAG_ALREADY_INSTALLED")
    app.state.rag_installed = True
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(host):
        async with previous(host):
            require(host.state.platform is not None, "RAG_REQUIRES_PLATFORM")
            host.state.rag = service_factory(host.state.platform) if service_factory else configured_service(host.state.platform, host.state.config.root)
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
        value = ({"buffer": await body(request, 10_485_760)} if binary else await json_body(request, 524288)) if request.method == "POST" else {}
        q = request.query_params
        scope = rag.p.scope((q.get("courseId") or "course-default") if binary or request.method == "GET" else value.get("courseId", "course-default"))
        post = request.method == "POST"
        if operation == "capabilities" and not post:
            return success(capabilities={"formats": ["txt", "md", "pdf", "docx", "pptx"], "embedding": bool(rag.embedding), "ocr": bool(rag.ocr), "rerank": bool(rag.rerank), "index": "exact-cosine", "storage": "sqlite-entities", "inference": "external-api-only"})
        if operation == "upload" and post:
            return success(job=rag.upload(scope, value["buffer"], q.get("name"), request.headers.get("idempotency-key"), previous_document_id=q.get("previousDocumentId")))
        if operation in ("parse", "ocr", "index") and post:
            require(type(value.get("version")) is int and value["version"] > 0, "INVALID_VERSION")
            return success(job=rag.submit(scope, "rag-"+operation, value.get("documentId"), value.get("idempotencyKey"), expected_version=value["version"]))
        if operation == "search" and post:
            allowed = {"courseId", "query", "history", "newTopic", "documentIds", "section", "mode", "budget", "limit"}
            require(not set(value)-allowed and isinstance(value.get("history", []), list) and len(value.get("history", [])) <= 12 and type(value.get("newTopic", False)) is bool, "INVALID_SEARCH")
            return success(evidence=await connected_work(request, rag.search(scope, value.get("query"), history=value.get("history", []), new_topic=value.get("newTopic", False),
                            document_ids=value.get("documentIds"), section=value.get("section"), mode=value.get("mode", "hybrid"), budget=value.get("budget", 2000), limit=value.get("limit", 6))))
        if operation == "read" and not post:
            return success(**rag.context(scope, q.get("sourceId")))
        if operation == "validate" and post:
            return success(valid=rag.validate(scope, value.get("citation")))
        if operation == "export" and not post:
            return success(**rag.export(scope, q.get("documentId")))
        if operation == "original" and not post:
            doc = rag.document(scope, q.get("documentId"), active=True)
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
