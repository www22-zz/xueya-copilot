"""C learning ports over the main host's single database, provider and B evidence."""
from contextlib import asynccontextmanager
import asyncio
import json
import re
import secrets
import time

from fastapi import Request

from backend.core import DomainError, clone, fingerprint, require
from backend.agent.evidence import evidence_package
from backend.agent.http_handler import LearningHandler
from backend.agent.learning_service import LearningService
from .common import AppError


class LearningRepository:
    """Namespace C artifacts; operation receipts and revisions commit atomically."""
    def __init__(self, platform, namespace="artifact"):
        self.p, self.namespace = platform, namespace

    def key(self, key):
        return "learning-"+self.namespace+"-"+fingerprint(key)

    async def get(self, course, key):
        row = self.p.repo.read(self.p.scope(course), "artifact", self.key(key))
        return clone(row["value"]) if row else None

    def all(self, course):
        scope = self.p.scope(course)
        return [json.loads(r["data"]) for r in self.p.db.all(
            "SELECT data FROM entities WHERE user_id=? AND course_id=? AND kind='artifact' AND deleted=0 AND id LIKE ?",
            (scope.user_id, scope.course_id, "learning-"+self.namespace+"-%"))]

    def operation_key(self, course, operation):
        self.p.scope(course)
        return "learning:operation:"+fingerprint([self.p.user_id, course, operation])

    async def get_operation(self, course, operation):
        row = self.p.db.one("SELECT value FROM meta WHERE key=?", (self.operation_key(course, operation),))
        return json.loads(row["value"]) if row else None

    async def commit(self, value):
        scope = self.p.scope(value["courseId"])
        with self.p.db.transaction():
            previous = await self.get_operation(value["courseId"], value["operationId"])
            if previous:
                require(previous["requestHash"] == value["requestHash"], "IDEMPOTENCY_CONFLICT")
                return previous["value"]
            current = self.p.repo.read(scope, "artifact", self.key(value["id"]))
            require((current["value"]["revision"] if current else 0) == value["expectedRevision"], "ARTIFACT_CONFLICT")
            self.p.repo.put(scope, "artifact", self.key(value["id"]), value["value"], current["version"] if current else 0)
            self.p.db.execute("INSERT INTO meta(key,value) VALUES(?,?)", (self.operation_key(value["courseId"], value["operationId"]), json.dumps({"requestHash": value["requestHash"], "value": value["value"]}, ensure_ascii=False)))
        return clone(value["value"])

    async def compare_and_set(self, course, key, revision, value):
        scope = self.p.scope(course)
        with self.p.db.transaction():
            current = self.p.repo.read(scope, "artifact", self.key(key))
            if (current["value"]["revision"] if current else 0) != revision:
                return False
            self.p.repo.put(scope, "artifact", self.key(key), value, current["version"] if current else 0)
        return True


class StoredValues:
    def __init__(self, platform, namespace, ttl=None):
        self.p, self.namespace, self.ttl = platform, namespace, ttl

    def key(self, course, key):
        self.p.scope(course)
        return "learning:"+self.namespace+":"+fingerprint([self.p.user_id, course, key])

    async def get(self, course, key):
        row = self.p.db.one("SELECT value FROM meta WHERE key=?", (self.key(course, key),))
        if not row:
            return None
        value = json.loads(row["value"])
        if self.ttl and time.time()-value["at"] > self.ttl:
            return None
        return value["value"]

    async def put(self, course, key, value):
        self.p.db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (self.key(course, key), json.dumps({"at": time.time(), "value": value}, ensure_ascii=False)))


class ScopedModel:
    """Reuses the host's API limiter, invocation ledger and cancellation."""
    def __init__(self, provider, scope):
        self.provider, self.scope = provider, scope

    async def generate(self, value):
        signal = value.get("signal")
        if signal:
            signal.check()
        operation = asyncio.create_task(self.provider.generate(value["messages"], scope=self.scope))
        monitor = asyncio.create_task(signal.event.wait()) if signal else None
        try:
            if monitor:
                done, _ = await asyncio.wait([operation, monitor], return_when=asyncio.FIRST_COMPLETED)
                if monitor in done:
                    raise asyncio.CancelledError()
            return await operation
        finally:
            if monitor:
                monitor.cancel()
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, *([monitor] if monitor else []), return_exceptions=True)


class LearningHost:
    def __init__(self, app):
        self.app, self.p = app, app.state.platform
        self.repo, self.runs = LearningRepository(self.p), LearningRepository(self.p, "run")
        self.previews = StoredValues(self.p, "preview", 86400)
        self.snapshots = StoredValues(self.p, "snapshot")
        self.checkpoints = StoredValues(self.p, "checkpoint")
        self.services = {}
        from .learning_ui_api import LearningPages
        self.pages = LearningPages(self)
        from .content_workspace import ContentWorkspace
        self.content_workspace = ContentWorkspace(self)
        self.p.jobs.register("learning-chapter", self.execute)
        from .search_workspace import SearchWorkspace
        self.search_workspace = SearchWorkspace(self)

    def service(self, course):
        scope = self.p.scope(course)
        if course not in self.services:
            model = ScopedModel(self.app.state.provider, scope) if self.app.state.config.api_key else None
            self.services[course] = LearningService(self.repo, runs=self.runs, model=model,
                model_id=self.app.state.config.model, checkpoint=self.checkpoints, verify_snapshot=self.verify_snapshot)
        return self.services[course]

    async def sources(self, value, *, catalog=False, generation=True):
        scope = self.p.scope(value["courseId"])
        selection = value.get("selection") or {}
        require(isinstance(selection, dict) and not set(selection)-{"documentIds", "section", "sourceIds"}, "INVALID_SELECTION")
        selected = selection.get("sourceIds")
        require(selected is None or isinstance(selected, list) and len(selected) <= 1000 and all(isinstance(s, str) for s in selected), "INVALID_SELECTION")
        rag = getattr(self.app.state, "rag", None)
        found = rag.sources(scope, document_ids=selection.get("documentIds"), section=selection.get("section")) if rag else []
        # Older imported documents have no B artifact. Only use server-owned rows;
        # never substitute browser-provided quotations or superseded B revisions.
        documents = {d["id"]: d for d in self.p.repo.all(scope, "document")}
        for source in self.p.repo.all(scope, "source"):
            doc = documents.get(source.get("documentId"))
            if source["id"] in {s["id"] for s in found} or doc and (doc.get("activeArtifact") or doc.get("superseded") or doc.get("deleted")):
                continue
            if selection.get("documentIds") is not None and (source.get("documentId") or "legacy-"+source["id"]) not in selection["documentIds"]:
                continue
            if selection.get("section") and selection["section"] not in source.get("sectionPath", []) and selection["section"] != source.get("section"):
                continue
            found.append(source)
        result = []
        for source in found:
            if selected is not None and source["id"] not in selected:
                continue
            doc = documents.get(source.get("documentId"), {})
            result.append({**source, "courseId": scope.course_id, "documentId": source.get("documentId") or "legacy-"+source["id"], "version": str(source.get("documentRevision", doc.get("contentRevision", source["version"]))), "quote": source.get("quote", source.get("text", ""))})
        require(result, "NO_SOURCES")
        if catalog:
            # The page catalog must remain accessible even when a whole course
            # exceeds a generation budget. Commands still load complete evidence.
            return [{**s, 'quote': s['quote'][:1500]} for s in result[:256]]
        if not generation:
            return result
        require(sum(len(s["quote"]) for s in result) <= 384000, "CHAPTER_BUDGET_EXCEEDED")
        version = evidence_package({"courseId": scope.course_id, "sources": result})["version"]
        await self.snapshots.put(scope.course_id, version, {"sourceIds": [s["id"] for s in result]})
        return result

    async def verify_snapshot(self, course, snapshot):
        stored = await self.snapshots.get(course, snapshot)
        if not stored:
            return False
        try:
            sources = await self.sources({"courseId": course, "selection": stored})
            return evidence_package({"courseId": course, "sources": sources})["version"] == snapshot
        except (DomainError, AppError):
            return False

    async def validate_draft(self, course, draft):
        content = draft["content"]
        if draft['kind'] in ('concept-graph', 'quiz'):
            try:
                if draft['kind'] == 'concept-graph':
                    refs = [r for item in content['concepts']+content['edges'] for r in item.get('evidence', [])]
                    ids = list({r['sourceId'] for r in refs})
                else:
                    ids = list({q['sourceId'] for q in content['questions']})
                sources = await self.sources({'courseId': course, 'selection': {'sourceIds': ids}}, generation=False) if ids else []
                if draft['kind'] == 'concept-graph':
                    from backend.agent.concepts import validate_graph
                    validate_graph(content, sources)
                else:
                    from backend.agent.assessment import validate_question
                    for question in content['questions']:
                        validate_question(question, sources)
            except DomainError:
                raise DomainError('STALE_EVIDENCE') from None
        snapshot = content.get("evidenceVersion") if isinstance(content, dict) else None
        if snapshot:
            require(await self.verify_snapshot(course, snapshot), "STALE_EVIDENCE")
        refs = content.get("evidence", []) if isinstance(content, dict) else []
        if refs:
            sources = await self.sources({"courseId": course, "selection": {"sourceIds": list({r["sourceId"] for r in refs})}})
            for ref in refs:
                source = next((s for s in sources if s["id"] == ref["sourceId"]), None)
                require(source and source["version"] == ref["version"] and ref["quote"] in source["quote"], "STALE_EVIDENCE")

    async def study_context(self, course):
        scope = self.p.scope(course)
        artifacts = self.repo.all(course)
        attempts = [r["content"] for r in artifacts if r.get("kind") == "attempt"]
        graph = (await self.pages.graph(course))["content"]
        return {"courseId": course, "graph": graph,
            "questions": self.p.repo.all(scope, "question"), "events": [e for a in attempts for e in a.get("events", [])],
            "diagnoses": [d for a in attempts for d in a.get("diagnoses", [])],
            "cardIds": [r["id"] for r in artifacts if r.get("kind") == "memory-card"]}

    @staticmethod
    def scope_study_context(value, sources):
        """A selected chapter must not inherit unrelated or retired graph evidence."""
        by_id = {s['id']: s for s in sources}
        graph = clone(value['graph'])
        def supported(ref):
            source = by_id.get(ref.get('sourceId'))
            return source and source['version'] == ref.get('version') and ref.get('quote') and ref['quote'] in source['quote']
        concepts = []
        for item in graph['concepts']:
            refs = [r for r in item.get('evidence', []) if supported(r)]
            if refs and item.get('status') != 'rejected':
                concepts.append({**item, 'evidence': refs})
        ids = {c['id'] for c in concepts}
        edges = []
        for item in graph['edges']:
            refs = [r for r in item.get('evidence', []) if supported(r)]
            if item['from'] in ids and item['to'] in ids and (refs or item.get('inferred') and item.get('reason')):
                edges.append({**item, 'evidence': refs})
        filtered = len(concepts) != len(graph['concepts']) or len(edges) != len(graph['edges'])
        return {**value, 'graph': {**graph, 'concepts': concepts, 'edges': edges},
                'contextWarnings': ['GRAPH_OUTSIDE_SELECTED_EVIDENCE'] if filtered else []}

    async def enqueue(self, value):
        run = await self.service(value["courseId"]).workflow.get(value["courseId"], value["runId"])
        return self.p.jobs.submit(self.p.user_id, {"type": "learning-chapter", "courseId": value["courseId"],
            "input": {"runId": value["runId"]}, "resource": "cpu", "maxAttempts": 1,
            "idempotencyKey": "learning-"+fingerprint([value["runId"], run["revision"]])})

    async def execute(self, scope, args, **callbacks):
        run = await self.service(scope.course_id).workflow.execute(scope.course_id, args["runId"])
        return {"runId": run["id"], "status": run["status"], "revision": run["revision"]}

    async def handle(self, path, request):
        require(bool(re.fullmatch(r"(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?", request.headers.get("host", ""))), "ORIGIN_FORBIDDEN")
        require(secrets.compare_digest(request.headers.get("x-xueya-token", ""), self.app.state.token), "AUTH_REQUIRED")
        course = request.query_params.get("courseId", "course-default")
        self.p.scope(course)
        content_response = await self.content_workspace.dispatch(path, request, course)
        if content_response is not None:
            return content_response
        extended = await self.pages.dispatch(path, request, course)
        if extended is not None:
            return extended
        search_response = await self.search_workspace.dispatch(path, request, course)
        if search_response is not None:
            return search_response

        async def context(_):
            return {"courseId": course, "userId": self.p.user_id, "loadStudyContext": lambda: self.study_context(course), 'scopeStudyContext': self.scope_study_context}

        async def questions(value):
            result = []
            for key in value["ids"]:
                row = self.p.repo.read(self.p.scope(value["courseId"]), "question", key)
                require(row is not None, "QUESTION_NOT_FOUND")
                result.append(row["value"])
            return result

        handler = LearningHandler(self.service(course), context, self.sources, questions, self.previews, self.enqueue, self.validate_draft)
        return await handler.handle(path, request)


def install_learning(app):
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(host):
        async with previous(host):
            host.state.learning = LearningHost(host) if host.state.platform else None
            host.state.agent.rag = getattr(host.state, 'rag', None)
            host.state.agent.learning = host.state.learning
            if host.state.learning:
                learning = host.state.learning
                for course in learning.p.repo.courses(learning.p.user_id):
                    if course["archived"]:
                        continue
                    for row in learning.runs.all(course["id"]):
                        if row.get("status") == "running":
                            await learning.service(course["id"]).workflow.recover(course["id"], row["id"], lease_expired=True)
            yield

    app.router.lifespan_context = lifespan

    async def domain_error(request, error):
        from .app import error_response
        from backend.agent.http_handler import http_status
        status = 403 if 'AUTH' in error.code or 'ORIGIN' in error.code else 413 if 'TOO_LARGE' in error.code else http_status(error.code)
        return error_response(error.code, status)

    app.add_exception_handler(DomainError, domain_error)

    async def route(path: str, request: Request):
        require(app.state.learning is not None, "PLATFORM_DISABLED")
        return await app.state.learning.handle(path, request)

    from fastapi import APIRouter
    router = APIRouter()
    router.add_api_route("/api/learning/{path:path}", route, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    count = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[count:]
    del app.router.routes[count:]
    app.router.routes[0:0] = added
    return app
