"""External-only Jina embeddings/rerank and Mistral OCR. No automatic paid retries.

Configuration is constructor-injected by the host, never accepted from HTTP bodies.
"""
from __future__ import annotations

import asyncio
import base64
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import math
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from .common import AppError, digest, dumps, require, utc_now
from .rag_search import normalize
from .execution_budget import current_budget

_leased_platform = ContextVar("rag_leased_api_platform", default=None)


def api_permit_held(platform):
    return _leased_platform.get() is platform


@contextmanager
def borrowed_api_permit(platform):
    """An api JobQueue handler already owns one permit on this same task."""
    token = _leased_platform.set(platform)
    try:
        yield
    finally:
        _leased_platform.reset(token)


@dataclass(frozen=True)
class ApiSettings:
    key: str = field(default="", repr=False)
    model: str = ""
    base_url: str = "https://api.jina.ai/v1"
    dimension: int = 1024
    revision: str = "1"
    timeout: float = 45

    def __post_init__(self):
        url = urlsplit(self.base_url)
        require(url.scheme == "https" and bool(url.hostname) and not url.username and not url.password and not url.query and not url.fragment, "INVALID_PROVIDER_URL")
        require(type(self.dimension) is int and 1 <= self.dimension <= 8192 and 0 < self.timeout <= 120, "INVALID_PROVIDER_CONFIG")


class ApiClient:
    def __init__(self, platform, settings: ApiSettings, *, transport=None, name="rag-api"):
        self.platform, self.settings, self.transport, self.name = platform, settings, transport, name

    @property
    def identity(self):
        return {"provider": self.settings.base_url, "model": self.settings.model, "revision": self.settings.revision}

    async def post(self, scope, path, payload):
        require(self.settings.key and self.settings.model, "NOT_SENT")
        self.platform.repo.require_course(scope)
        release = (lambda: None) if _leased_platform.get() is self.platform else self.platform.resources.acquire("api")
        require(release is not None, "NOT_SENT")
        request_id, sent, complete, usage = str(uuid4()), False, False, None
        try:
            budget = current_budget.get()
            if budget:
                budget.model([], 0, capability='rag', model=self.settings.model)
            self.platform.db.execute("INSERT INTO invocations(id,user_id,course_id,status,provider,request_hash,at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                                     (request_id, scope.user_id, scope.course_id, "pending", self.name, digest({"model": self.settings.model, "revision": self.settings.revision, "payload": payload}), utc_now(), utc_now()))
            from .invocation_context import attach_invocation
            purpose = 'embedding' if isinstance(self, EmbeddingProvider) else 'rerank' if isinstance(self, RerankProvider) else 'ocr'
            attach_invocation(self.platform, scope, request_id, capability=purpose, model=self.settings.model,
                              base_url=self.settings.base_url, key=self.settings.key)
            async with asyncio.timeout(min(self.settings.timeout, budget.remaining() if budget else self.settings.timeout)):
                async with httpx.AsyncClient(timeout=self.settings.timeout, follow_redirects=False, transport=self.transport,
                                             headers={"Authorization": "Bearer "+self.settings.key}) as client:
                    sent = True
                    async with client.stream("POST", self.settings.base_url.rstrip("/")+path, json={"model": self.settings.model, **payload}) as response:
                        require(response.is_success, "RAG_API_REJECTED")
                        buffer = bytearray()
                        async for part in response.aiter_bytes():
                            buffer.extend(part)
                            require(len(buffer) <= 16_000_000, "RAG_API_RESPONSE_TOO_LARGE")
                        value = json.loads(buffer)
                        require(isinstance(value, dict), "INVALID_RAG_API_RESPONSE")
                        usage = value.get("usage", value.get("usage_info"))
                        complete = True
                        return value
        finally:
            try:
                status = "succeeded" if complete else "unknown" if sent else "not_sent"
                self.platform.db.execute("UPDATE invocations SET status=?,updated_at=?,usage_json=?,billing_status=? WHERE id=?",
                                         (status, utc_now(), dumps(usage) if isinstance(usage, dict) else None, "unknown" if sent and not complete else "not_reported", request_id))
            finally:
                release()


class EmbeddingProvider(ApiClient):
    """Jina embedding API; cache/index identity includes model revision/dimensions/tasks."""
    @property
    def identity(self):
        return {"provider": self.settings.base_url, "model": self.settings.model, "revision": self.settings.revision,
                "dimension": self.settings.dimension, "normalized": True, "documentTask": "retrieval.passage", "queryTask": "retrieval.query"}

    async def embed(self, scope, texts, *, query=False):
        require(isinstance(texts, list) and 1 <= len(texts) <= 32 and all(isinstance(t, str) and 0 < len(t.encode()) <= 24_000 for t in texts), "INVALID_EMBEDDING_INPUT")
        data = await self.post(scope, "/embeddings", {"input": texts, "task": "retrieval.query" if query else "retrieval.passage",
                                                   "dimensions": self.settings.dimension, "normalized": True, "embedding_type": "float"})
        require(data.get("model", self.settings.model) == self.settings.model, "EMBEDDING_MODEL_MISMATCH")
        rows = data.get("data")
        require(isinstance(rows, list) and len(rows) == len(texts), "INVALID_EMBEDDING")
        require(all(isinstance(row, dict) and type(row.get("index")) is int for row in rows), "INVALID_EMBEDDING")
        require({row["index"] for row in rows} == set(range(len(texts))), "INVALID_EMBEDDING")
        return [normalize(row.get("embedding"), self.settings.dimension) for row in sorted(rows, key=lambda row: row["index"])]


class RerankProvider(ApiClient):
    async def rerank(self, scope, query, sources, *, limit=12):
        require(len(sources) <= 24 and sum(len(s["quote"].encode()) for s in sources) <= 96_000, "RERANK_INPUT_TOO_LARGE")
        if not sources:
            return []
        data = await self.post(scope, "/rerank", {"query": query, "documents": [s["quote"] for s in sources],
                                               "top_n": min(limit, len(sources)), "return_documents": False})
        rows = data.get("results")
        require(isinstance(rows, list) and len(rows) <= min(limit, len(sources)), "INVALID_RERANK")
        result, seen = [], set()
        for row in rows:
            require(isinstance(row, dict), "INVALID_RERANK")
            index, score = row.get("index"), row.get("relevance_score")
            require(type(index) is int and 0 <= index < len(sources) and index not in seen and type(score) in (int, float) and math.isfinite(score), "INVALID_RERANK")
            seen.add(index)
            result.append((score, sources[index]))
        return sorted(result, key=lambda row: -row[0])


class OcrProvider(ApiClient):
    async def recognize(self, scope, buffer, pages):
        require(isinstance(buffer, bytes) and 0 < len(buffer) <= 10_485_760 and isinstance(pages, list) and 0 < len(pages) <= 64 and all(type(p) is int and p >= 1 for p in pages), "INVALID_OCR_INPUT")
        data = await self.post(scope, "/ocr", {"document": {"type": "document_url", "document_url": "data:application/pdf;base64,"+base64.b64encode(buffer).decode()},
                                             "pages": [p-1 for p in pages], "include_image_base64": False, "table_format": "markdown"})
        rows = data.get("pages")
        require(isinstance(rows, list) and len(rows) <= len(pages), "INVALID_OCR_RESPONSE")
        result = {}
        for row in rows:
            require(isinstance(row, dict) and type(row.get("index")) is int and row["index"]+1 in pages and row["index"]+1 not in result and isinstance(row.get("markdown"), str) and len(row["markdown"]) <= 1_200_000, "INVALID_OCR_RESPONSE")
            # Full-page text has no asserted bbox/confidence unless supplied by a validated adapter.
            dimensions = row.get("dimensions", {})
            images = row.get("images", [])
            require(isinstance(dimensions, dict) and isinstance(images, list) and len(images) <= 1000, "INVALID_OCR_RESPONSE")
            located = []
            for image in images:
                require(isinstance(image, dict) and isinstance(image.get("id"), str) and len(image["id"]) <= 200, "INVALID_OCR_RESPONSE")
                box = [image.get(k) for k in ("top_left_x", "top_left_y", "bottom_right_x", "bottom_right_y")]
                require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in box) and box[0] < box[2] and box[1] < box[3], "INVALID_OCR_RESPONSE")
                require(type(dimensions.get("width")) in (int, float) and type(dimensions.get("height")) in (int, float) and box[2] <= dimensions["width"] and box[3] <= dimensions["height"], "INVALID_OCR_RESPONSE")
                located.append({"id": image["id"], "bbox": box, "coordinateSystem": "ocr-page-pixels"})
            result[row["index"]+1] = {"text": row["markdown"], "method": "ocr-api:"+self.settings.model,
                                      "confidence": None, "bbox": None, "images": located,
                                      "dimensions": {k: dimensions[k] for k in ("width", "height", "dpi") if k in dimensions}}
        require(set(result) == set(pages), "OCR_PAGES_MISSING")
        return result
