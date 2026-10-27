"""B-owned RAG service over E's repository/files/jobs. No second database.

Host integration is explicit: RagService(platform, embedding=..., ocr=..., rerank=...).
Jobs publish an entire revision atomically; failed/cancelled builds leave active data intact.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import time
from uuid import uuid4

import httpx

from .common import AppError, digest, identifier, require, utc_now
from .parse_worker import parse_artifact
from .rag_api import borrowed_api_permit
from .document_limits import document_limit
from .rag_parse import KINDS, assemble, quality, structured_chunks, text_blocks
from .rag_search import compress, conflicts, exact, fuse, lexical, normalize, rewrite_query


class RagService:
    def __init__(self, platform, *, embedding=None, ocr=None, rerank=None):
        self.p, self.repo = platform, platform.repo
        self.embedding, self.ocr, self.rerank = embedding, ocr, rerank
        for name, handler in (("rag-parse", self.parse_job), ("rag-ocr", self.ocr_job), ("rag-index", self.index_job)):
            platform.jobs.register(name, handler)

    def document(self, scope, document_id, *, active=False):
        identifier(document_id)
        self.repo.require_course(scope, archived=True)
        row = self.repo.read(scope, "document", document_id)
        require(row is not None and not row["value"].get("deleted"), "DOCUMENT_NOT_FOUND")
        value = {**row["value"], "id": document_id, "version": row["version"]}
        require(not active or not value.get("superseded"), "DOCUMENT_SUPERSEDED")
        require(not active or not value.get("archived"), "DOCUMENT_ARCHIVED")
        return value

    def artifact(self, scope, doc):
        row = self.repo.read(scope, "artifact", doc.get("activeArtifact", ""))
        require(row is not None and row["value"].get("documentId") == doc["id"] and row["value"].get("contentRevision") == doc.get("contentRevision"), "ARTIFACT_NOT_FOUND")
        return row["value"]

    def submit(self, scope, job_type, document_id, key, *, expected_version=None, pages=None):
        self.repo.require_course(scope)
        identifier(key)
        identifier(document_id)
        prior = self.p.db.one("SELECT id,input FROM jobs WHERE user_id=? AND course_id=? AND type=? AND idempotency_key=?", (scope.user_id, scope.course_id, job_type, key))
        if prior:
            import json
            original = json.loads(prior["input"])
            require(original.get("documentId") == document_id and (expected_version is None or expected_version == original.get("expectedVersion"))
                    and original.get('pages') == pages, "IDEMPOTENCY_CONFLICT")
            return self.p.jobs.get(prior["id"], scope.user_id)
        doc = self.document(scope, document_id, active=True)
        require(expected_version is None or doc["version"] == expected_version, "VERSION_CONFLICT")
        resource = "cpu" if job_type == "rag-parse" else "api"
        require(job_type in ("rag-parse", "rag-ocr", "rag-index"), "JOB_TYPE_UNAVAILABLE")
        if job_type == "rag-ocr":
            require(self.ocr is not None and self.ocr.settings.key, "OCR_UNAVAILABLE")
            require(doc['kind'] == 'pdf', 'OCR_PDF_REQUIRED')
        if pages is not None:
            require(job_type == 'rag-ocr' and isinstance(pages, list) and 0 < len(pages) <= 64
                    and all(type(page) is int for page in pages) and len(pages) == len(set(pages)), 'INVALID_OCR_PAGES')
            pending = {page['number'] for page in self.artifact(scope, doc)['pages'] if page['needsOcr']}
            require(set(pages) <= pending, 'INVALID_OCR_PAGES')
        if job_type == "rag-index":
            require(self.embedding is not None and self.embedding.settings.key, "EMBEDDING_UNAVAILABLE")
        provider = self.embedding if job_type == "rag-index" else self.ocr if job_type == "rag-ocr" else None
        return self.p.jobs.submit(scope.user_id, {"type": job_type, "courseId": scope.course_id, "resource": resource,
                                                "maxAttempts": 1 if resource == "api" else 3, "idempotencyKey": identifier(key),
                                                "input": {"documentId": document_id, "expectedVersion": doc["version"], "jobKey": key,
                                                          **({'pages': pages} if pages is not None else {}),
                                                          **({"providerIdentity": provider.identity} if provider else {})}})

    def upload(self, scope, buffer, name, key, *, previous_document_id=None, tags=None):
        self.repo.require_course(scope)
        identifier(key)
        require(isinstance(name, str) and 0 < len(name.strip()) <= 200, "INVALID_FILE_NAME")
        kind = name.rsplit(".", 1)[-1].lower()
        require(kind in KINDS, "UNSUPPORTED_FILE_TYPE")
        require(isinstance(buffer, bytes) and 0 < len(buffer) <= document_limit(kind), 'FILE_TOO_LARGE')
        require(kind not in ("txt", "md") or len(buffer) <= 1_048_576, "FILE_TOO_LARGE")
        require(tags is None or isinstance(tags, list) and len(tags) <= 30 and all(isinstance(t, str) and 0 < len(t) <= 100 for t in tags), "INVALID_TAGS")
        request_hash = digest({"file": hashlib.sha256(buffer).hexdigest(), "name": name, "previous": previous_document_id, "tags": tags})
        prior = self.p.db.one("SELECT id,input FROM jobs WHERE user_id=? AND course_id=? AND type='rag-parse' AND idempotency_key=?", (scope.user_id, scope.course_id, key))
        if prior:
            import json
            doc = self.document(scope, json.loads(prior["input"])["documentId"])
            require(doc.get("uploadHash") == request_hash, "IDEMPOTENCY_CONFLICT")
            return self.p.jobs.get(prior["id"], scope.user_id)
        file = self.p.files.put(buffer)
        with self.p.db.transaction():
            previous = self.document(scope, previous_document_id, active=True) if previous_document_id else None
            document_id = "doc-"+str(uuid4())
            self.repo.put(scope, "document", document_id, {"id": document_id, "name": name, "kind": kind,
                          "fileHash": file["hash"], "size": file["size"], "originalAvailable": True, "remote": True,
                          "status": "等待解析", "tags": tags or [], "chunks": [], "contentRevision": 0, "uploadHash": request_hash,
                          "previousDocumentId": previous_document_id, "previousVersion": previous["version"] if previous else None}, 0)
            return self.submit(scope, "rag-parse", document_id, key)

    def _job_doc(self, scope, args, job_type, *, paid=False):
        allowed = {"documentId", "expectedVersion", "jobKey", "providerIdentity"} | ({'pages'} if job_type == 'rag-ocr' else set())
        require(isinstance(args, dict) and not set(args)-allowed, "INVALID_JOB")
        # Public generic queue cannot accidentally run paid work as a retryable CPU job.
        row = self.p.db.one("SELECT resource,max_attempts,status FROM jobs WHERE user_id=? AND course_id=? AND type=? AND idempotency_key=?", (scope.user_id, scope.course_id, job_type, args.get("jobKey")))
        require(row is not None and row["status"] == "running" and (not paid or row["resource"] == "api" and row["max_attempts"] == 1), "NOT_SENT")
        if paid:
            provider = self.embedding if job_type == "rag-index" else self.ocr
            require(provider is not None and args.get("providerIdentity") == provider.identity, "NOT_SENT")
        doc = self.document(scope, args.get("documentId"), active=True)
        require(doc["version"] == args.get("expectedVersion"), "VERSION_CONFLICT")
        return doc

    def _publish(self, scope, doc, parsed, *, correction=None):
        """Must be called synchronously within the leased commit or a transaction."""
        current = self.document(scope, doc["id"], active=True)
        require(current["version"] == doc["version"], "VERSION_CONFLICT")
        revision = doc.get("contentRevision", 0)+1
        sources = structured_chunks(parsed, {**doc, "contentRevision": revision})
        artifact_id = "rag-"+digest({"document": doc["id"], "revision": revision, "text": parsed["textHash"]})[:40]
        artifact = {**parsed, "documentId": doc["id"], "contentRevision": revision, "createdAt": utc_now(), "correction": correction}
        self.repo.put(scope, "artifact", artifact_id, artifact, 0)
        for source in self.repo.all(scope, "source"):
            if source.get("documentId") == doc["id"]:
                self.repo.put(scope, "source", source["id"], source, source["version"], deleted=True)
        for source in sources:
            self.repo.put(scope, "source", source["id"], source, 0)
        # Supersede the old document only after the replacement has usable evidence.
        previous_id = doc.get("previousDocumentId")
        if previous_id and sources and not parsed["warnings"]:
            previous = self.document(scope, previous_id)
            if previous.get("replacementDocumentId") == doc["id"]:
                previous = None
        else:
            previous = None
        if previous:
            require(previous["version"] == doc.get("previousVersion"), "VERSION_CONFLICT")
            self.repo.put(scope, "document", previous_id, {**previous, "superseded": True, "replacementDocumentId": doc["id"]}, previous["version"])
            self._retire(scope, previous_id)
        updated = {**doc, "contentRevision": revision, "activeArtifact": artifact_id, "chunks": sources,
                   "embeddingIdentity": None, "indexStatus": "not_indexed", "parserVersion": parsed["parserVersion"],
                   "quality": {"warnings": parsed["warnings"], "pages": parsed["pages"], "empty": parsed["empty"]},
                   "status": "需要OCR或原图核对" if parsed["warnings"] or not sources else "已解析，可检索",
                   "meta": f"{len(sources)}个原文片段"}
        saved = self.repo.put(scope, "document", doc["id"], updated, doc["version"])
        self._prune_vectors(scope)
        return {"documentId": doc["id"], "version": saved["version"], "contentRevision": revision, "sourceCount": len(sources), "warnings": parsed["warnings"]}

    async def parse_job(self, scope, args, *, progress, checkpoint, commit):
        doc = self._job_doc(scope, args, "rag-parse")
        progress({"percent": 10, "label": "提取结构与真实位置"})
        parsed = await parse_artifact(self.p.files.read(doc["fileHash"]), doc["kind"])
        checkpoint({"documentId": doc["id"], "fileHash": doc["fileHash"], "stage": "parsed"})
        result = commit(lambda: self._publish(scope, doc, parsed))
        progress({"percent": 100, "label": "资料版本已保存"})
        return result

    async def ocr_job(self, scope, args, *, progress, checkpoint, commit):
        doc = self._job_doc(scope, args, "rag-ocr", paid=True)
        require(self.ocr is not None and doc["kind"] == "pdf", "NOT_SENT")
        old = self.artifact(scope, doc)
        pending = [page["number"] for page in old["pages"] if page["needsOcr"]]
        pages = args.get('pages', pending)
        require(isinstance(pages, list) and all(type(p) is int for p in pages) and len(pages) == len(set(pages))
                and set(pages) <= set(pending), 'INVALID_OCR_PAGES')
        require(0 < len(pages) <= 64, "OCR_PAGE_LIMIT")
        progress({"percent": 10, "label": "正在调用OCR API"})
        with borrowed_api_permit(self.p):
            recognized = await self.ocr.recognize(scope, self.p.files.read(doc["fileHash"]), pages)
        rebuilt = []
        for page in old["pages"]:
            number = page["number"]
            replacement = recognized.get(number)
            part = replacement["text"] if replacement else old["text"][page["start"]:page["end"]]
            blocks = (text_blocks(part, number, markdown=True, method=replacement['method']) if replacement else
                      [{**b, 'start': b['start']-page['start'], 'end': b['end']-page['start']} for b in old['blocks'] if b['page'] == number])
            rebuilt.append({**page, "text": part, "method": replacement["method"] if replacement else page["method"],
                            "needsOcr": not part.strip() or quality(part) < .85 if replacement else page["needsOcr"],
                            **({"images": replacement.get("images", []), "ocrDimensions": replacement.get("dimensions", {})} if replacement else {}),
                            "blocks": blocks})
        parsed = assemble(rebuilt, doc["kind"], doc["fileHash"])
        checkpoint({"documentId": doc["id"], "stage": "ocr-returned"})
        return commit(lambda: self._publish(scope, doc, parsed))

    def correct(self, scope, document_id, expected_version, block_id, replacement, reason):
        require(isinstance(replacement, str) and len(replacement) <= 100_000 and isinstance(reason, str) and 0 < len(reason) <= 1000, "INVALID_CORRECTION")
        with self.p.db.transaction():
            doc = self.document(scope, document_id, active=True)
            require(doc["version"] == expected_version, "VERSION_CONFLICT")
            old = self.artifact(scope, doc)
            block = next((b for b in old["blocks"] if b["id"] == block_id), None)
            require(block is not None, "BLOCK_NOT_FOUND")
            pages = []
            for page in old["pages"]:
                part = old["text"][page["start"]:page["end"]]
                if page["number"] == block["page"]:
                    start, end = block["start"]-page["start"], block["end"]-page["start"]
                    part = part[:start]+replacement+part[end:]
                pages.append({**page, "text": part, "method": "human-revision" if page["number"] == block["page"] else page["method"],
                              "blocks": text_blocks(part, page["number"], markdown=True, method="human-revision" if page["number"] == block["page"] else page["method"])})
            return self._publish(scope, doc, assemble(pages, doc["kind"], doc["fileHash"]), correction={"baseArtifactId": doc["activeArtifact"], "blockId": block_id, "before": block["text"], "after": replacement, "reason": reason})

    def sources(self, scope, *, document_ids=None, section=None):
        self.repo.require_course(scope, archived=True)
        require(document_ids is None or isinstance(document_ids, list) and len(document_ids) <= 100 and all(isinstance(d, str) for d in document_ids), "INVALID_FILTER")
        require(section is None or isinstance(section, str) and len(section) <= 200, "INVALID_FILTER")
        documents = {d["id"]: d for d in self.repo.all(scope, "document") if not d.get("deleted") and not d.get("superseded") and not d.get("archived")}
        result, artifacts = [], {}
        for source in self.repo.all(scope, "source"):
            doc = documents.get(source.get("documentId"))
            if doc is None or document_ids is not None and doc["id"] not in document_ids:
                continue
            if source.get("documentRevision") != doc.get("contentRevision") or not doc.get("activeArtifact"):
                continue
            if section is not None and section not in source.get("sectionPath", []):
                continue
            try:
                if doc["id"] not in artifacts:
                    artifacts[doc["id"]] = self.artifact(scope, doc)
                self._check_source(source, doc, artifacts[doc["id"]])
            except AppError:
                continue
            result.append(source)
        return result

    def read(self, scope, source_id):
        identifier(source_id)
        row = self.repo.read(scope, "source", source_id)
        require(row is not None, "SOURCE_NOT_FOUND")
        source = {**row["value"], "id": source_id, "version": row["version"]}
        doc = self.document(scope, source.get("documentId"), active=True)
        require(source.get("documentRevision") == doc.get("contentRevision"), "SOURCE_VERSION_CONFLICT")
        artifact = self.artifact(scope, doc)
        self._check_source(source, doc, artifact)
        return source

    @staticmethod
    def _check_source(source, doc, artifact):
        require(type(source.get("start")) is int and type(source.get("end")) is int and isinstance(source.get("quote"), str), "SOURCE_CONTENT_MISMATCH")
        block = next((b for b in artifact["blocks"] if b["id"] == source.get("blockId")), None)
        require(block is not None and source.get("page") == block["page"] and block["start"] <= source.get("start", -1) < source.get("end", -1) <= block["end"], "SOURCE_CONTENT_MISMATCH")
        token = f"{doc['id']}:{doc['contentRevision']}:{artifact['textHash']}:{source['start']}:{source['end']}"
        require(source["id"] == "chunk-"+hashlib.sha256(token.encode()).hexdigest()[:40], "SOURCE_CONTENT_MISMATCH")
        require(artifact["text"][source["start"]:source["end"]] == source["quote"] and source.get("fileHash") == doc["fileHash"] and source.get("textHash") == artifact["textHash"], "SOURCE_CONTENT_MISMATCH")

    def validate(self, scope, citation):
        require(isinstance(citation, dict), "INVALID_CITATION")
        source = self.read(scope, citation.get("id"))
        for key in ("documentId", "documentRevision", "fileHash", "textHash", "page", "blockId", "version"):
            require(key in citation and citation[key] == source.get(key), "INVALID_CITATION")
        start, end, quote = citation.get("start"), citation.get("end"), citation.get("quote")
        require(type(start) is int and type(end) is int and source["start"] <= start < end <= source["end"] and isinstance(quote, str) and len(quote) == end-start and source["quote"][start-source["start"]:end-source["start"]] == quote, "INVALID_CITATION")
        return True

    @staticmethod
    def _cache_id(identity, text):
        return "vec-"+digest({"identity": identity, "text": text})[:56]

    async def index_job(self, scope, args, *, progress, checkpoint, commit):
        doc = self._job_doc(scope, args, "rag-index", paid=True)
        require(self.embedding is not None, "NOT_SENT")
        identity = self.embedding.identity
        sources = self.sources(scope, document_ids=[doc["id"]])
        require(bool(sources), "NO_SOURCES")
        require(all(len(s["quote"].encode()) <= 24_000 for s in sources), "EMBEDDING_BLOCK_TOO_LARGE")
        unique = {self._cache_id(identity, s["quote"]): s["quote"] for s in sources}
        def cached(key, text):
            row = self.repo.read(scope, "vector", key)
            if not row or row["value"].get("identity") != identity or row["value"].get("textHash") != digest(text):
                return False
            try:
                normalize(row["value"].get("values"), identity["dimension"])
                return True
            except AppError:
                return False
        missing = [(key, text) for key, text in unique.items() if not cached(key, text)]
        for offset in range(0, len(missing), 16):
            batch = missing[offset:offset+16]
            with borrowed_api_permit(self.p):
                vectors = await self.embedding.embed(scope, [text for _, text in batch])
            def save_batch():
                current = self.document(scope, doc["id"], active=True)
                require(current["version"] == doc["version"], "VERSION_CONFLICT")
                for (key, text), vector in zip(batch, vectors):
                    old = self.repo.read(scope, "vector", key, include_deleted=True)
                    self.repo.put(scope, "vector", key, {"identity": identity, "textHash": digest(text), "values": vector}, old["version"] if old else 0)
            commit(save_batch)
            checkpoint({"documentId": doc["id"], "model": identity, "completed": min(offset+16, len(missing))})
            progress({"percent": int(90*min(offset+16, len(missing))/max(1, len(missing))), "label": "向量批次已缓存"})
        def promote():
            current = self.document(scope, doc["id"], active=True)
            require(current["version"] == doc["version"], "VERSION_CONFLICT")
            saved = self.repo.put(scope, "document", doc["id"], {**current, "embeddingIdentity": identity, "indexStatus": "ready"}, doc["version"])
            self._prune_vectors(scope)
            return {"documentId": doc["id"], "version": saved["version"], "vectorCount": len(sources), "computed": len(missing), "cached": len(unique)-len(missing)}
        return commit(promote)

    async def search(self, scope, query, *, history=(), new_topic=False, document_ids=None, section=None, mode="hybrid", budget=2000, limit=6):
        require(mode in ("lexical", "vector", "hybrid", "rerank"), "INVALID_SEARCH_MODE")
        require(type(budget) is int and 32 <= budget <= 16000 and type(limit) is int and 1 <= limit <= 20, "INVALID_BUDGET")
        started = time.perf_counter()
        rewritten = rewrite_query(query, history, new_topic=new_topic)
        sources = self.sources(scope, document_ids=document_ids, section=section)
        warnings, vector_rank = [], []
        lexical_rank = lexical(rewritten, sources)
        if mode != "lexical" and self.embedding:
            try:
                identity = self.embedding.identity
                eligible = []
                docs = {d["id"]: d for d in self.repo.all(scope, "document")}
                for source in sources:
                    if docs[source["documentId"]].get("embeddingIdentity") != identity:
                        continue
                    row = self.repo.read(scope, "vector", self._cache_id(identity, source["quote"]))
                    if row and row["value"].get("identity") == identity and row["value"].get("textHash") == digest(source["quote"]):
                        eligible.append((normalize(row["value"].get("values"), identity["dimension"]), source))
                if eligible:
                    vector = (await self.embedding.embed(scope, [rewritten], query=True))[0]
                    vector_rank = exact(vector, eligible)
                else:
                    warnings.append("VECTOR_INDEX_UNAVAILABLE")
            except (AppError, httpx.HTTPError, TimeoutError, ValueError):
                warnings.append("VECTOR_API_UNAVAILABLE")
        elif mode != "lexical":
            warnings.append("EMBEDDING_UNAVAILABLE")
        ranked = lexical_rank if mode == "lexical" else vector_rank if mode == "vector" and vector_rank else fuse(lexical_rank, vector_rank)
        if mode == "rerank":
            if self.rerank and ranked:
                try:
                    candidates = [source for _, source in ranked[:24]]
                    if sum(len(s["quote"].encode()) for s in candidates) <= 96_000:
                        ranked = await self.rerank.rerank(scope, rewritten, candidates)
                    else:
                        warnings.append("RERANK_BUDGET_EXCEEDED")
                except (AppError, httpx.HTTPError, TimeoutError, ValueError):
                    warnings.append("RERANK_API_UNAVAILABLE")
            else:
                warnings.append("RERANK_UNAVAILABLE")
        # Re-read after awaits: deletion/revision changes during an API call cannot resurrect sources.
        live = []
        for score, source in ranked:
            try:
                actual = self.read(scope, source["id"])
                if actual["version"] == source["version"]:
                    live.append((score, actual))
            except AppError:
                continue
        evidence, used = compress(rewritten, live, budget=budget, limit=limit)
        opposing = conflicts(evidence)
        return {"schemaVersion": "rag-1", "scope": scope.wire(), "query": query, "rewrittenQuery": rewritten,
                "sources": evidence, "status": "conflict" if opposing else "evidence_found" if evidence else "insufficient",
                "conflicts": opposing, "warnings": warnings, "budget": {"unit": "utf8Bytes", "limit": budget, "used": used},
                "elapsedMs": round((time.perf_counter()-started)*1000, 3),
                "supportChecked": False, "note": "摘录与位置已核对；论断支持度由生成模块和人工验收核对。"}

    def _retire(self, scope, document_id):
        for kind in ("source", "artifact"):
            for entity in self.repo.all(scope, kind):
                if entity.get("documentId") == document_id:
                    self.repo.put(scope, kind, entity["id"], entity, entity["version"], deleted=True)

    def _prune_vectors(self, scope):
        sources = self.sources(scope)
        # Keep partial batches reusable across explicit retries/model migration.
        allowed = {}
        identities = {digest(d["embeddingIdentity"]) for d in self.repo.all(scope, "document") if d.get("embeddingIdentity") and not d.get("superseded") and not d.get("deleted")}
        if self.embedding:
            identities.add(digest(self.embedding.identity))
        for vector in self.repo.all(scope, "vector"):
            if not vector["id"].startswith("vec-"):
                continue
            identity = vector.get("identity")
            model_key = digest(identity)
            if model_key not in allowed:
                allowed[model_key] = {self._cache_id(identity, s["quote"]) for s in sources}
            if model_key not in identities or vector["id"] not in allowed[model_key]:
                self.repo.put(scope, "vector", vector["id"], vector, vector["version"], deleted=True)

    def remove(self, scope, document_id, expected_version):
        with self.p.db.transaction():
            doc = self.document(scope, document_id)
            require(doc["version"] == expected_version, "VERSION_CONFLICT")
            self.repo.put(scope, "document", document_id, {**doc, "deleted": True}, expected_version, deleted=True)
            self._retire(scope, document_id)
            self._prune_vectors(scope)
        return {"removed": True, "retainedForRecovery": True}

    def export(self, scope, document_id):
        doc = self.document(scope, document_id, active=True)
        return {"documentId": doc["id"], "name": doc["name"], "contentRevision": doc["contentRevision"],
                "fileHash": doc["fileHash"], "artifact": copy.deepcopy(self.artifact(scope, doc))}

    def context(self, scope, source_id):
        source = self.read(scope, source_id)
        doc = self.document(scope, source["documentId"], active=True)
        artifact = self.artifact(scope, doc)
        block = next(b for b in artifact["blocks"] if b["id"] == source["blockId"])
        return {"source": source, "parent": block, "original": {"documentId": doc["id"], "fileHash": doc["fileHash"], "page": source["page"]}}
