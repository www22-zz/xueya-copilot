"""G3 templates/notes over the existing learning ports, artifacts and leased jobs."""
import asyncio
from uuid import uuid4

from fastapi.responses import JSONResponse
from backend.core import DomainError, clone, fingerprint, now_iso, require
from backend.agent.assessment import validate_question
from backend.agent.evidence import evidence_package
from .common import AppError, identifier
from .rag_api import borrowed_api_permit

BUILTINS = [
    ("guide", "章节导读", "梳理本章目标、先修概念、重要定义和待确认问题"),
    ("concepts", "概念与公式表", "按概念、定义、公式条件和逐字依据整理"),
    ("example", "例题步骤讲解", "按题干、步骤、适用条件与待核对推断整理"),
    ("compare", "易混淆概念对照", "分别保留定义、条件、差异和互相冲突的依据"),
    ("explain", "自我解释问题", "提出需要学习者用自己的话解释的问题，并列原文核对点"),
    ("exam", "考前提纲", "整理重点、条件、易错点和原文依据，不预测未经资料说明的考点"),
    ("reading", "文献阅读笔记", "整理问题、方法、结果、限制及逐字引用")]


class ContentWorkspace:
    def __init__(self, host):
        self.h, self.p = host, host.p
        self.p.jobs.register("learning-template", self.execute)
        for course in self.p.repo.courses(self.p.user_id):
            if course["archived"]:
                continue
            scope = self.p.scope(course["id"])
            for row in self.h.repo.all(course["id"]):
                if row["kind"] == "template-run" and row["content"]["status"] == "running":
                    row["content"].update(status="unknown", error="INTERRUPTED_REQUIRES_REVIEW")
                    row["revision"] += 1
                    self.p.repo.put(scope, "artifact", self.h.repo.key(row["id"]), row)

    def templates(self, course):
        builtin = [{"id": "builtin-"+key, "revision": 1, "kind": "learning-template", "courseId": course,
                    "content": {"title": title, "goal": goal, "prompt": goal, "subject": "通用", "format": "claims-with-evidence", "modelPurpose": "course-content", "sourcePolicy": "selected-originals", "builtin": True}} for key, title, goal in BUILTINS]
        return builtin+[r for r in self.h.repo.all(course) if r["kind"] == "learning-template"]

    async def template(self, course, key, revision=None):
        row = next((r for r in self.templates(course) if r["id"] == key), None)
        require(row and (revision is None or row["revision"] == revision), "TEMPLATE_VERSION_CONFLICT")
        return clone(row)

    async def preview(self, course, key, kind, content, revision=0):
        draft = await self.h.service(course).artifacts.preview({"courseId": course, "id": identifier(key), "kind": kind,
                                                              "content": content, "expectedRevision": revision})
        return await self.h.pages.preview(course, draft)

    async def operational(self, course, key, kind, content):
        old = await self.h.repo.get(course, key)
        return await self.h.repo.commit({"courseId": course, "id": key, "operationId": str(uuid4()), "requestHash": fingerprint(content),
            "expectedRevision": old["revision"] if old else 0, "value": {"courseId": course, "id": key, "kind": kind,
            "revision": old["revision"]+1 if old else 1, "updatedAt": now_iso(), "content": content}})

    def save_run(self, course, key, content):
        scope = self.p.scope(course)
        old = self.p.repo.read(scope, "artifact", self.h.repo.key(key))
        revision = old["value"]["revision"]+1 if old else 1
        self.p.repo.put(scope, "artifact", self.h.repo.key(key), {"id": key, "courseId": course, "kind": "template-run",
            "revision": revision, "updatedAt": now_iso(), "content": clone(content)}, old["version"] if old else 0)

    async def start(self, course, value):
        template = await self.template(course, value.get("templateId"), value.get("templateRevision"))
        selection = value.get("selection", {})
        sources = await self.h.sources({"courseId": course, "selection": selection})
        documents = list(dict.fromkeys(s["documentId"] for s in sources))
        require(len(documents) <= 10, "TEMPLATE_BATCH_LIMIT")
        require(not self.h.service(course).model or value.get("allowApi") is True, "API_CONFIRMATION_REQUIRED")
        groups = [[s for s in sources if s["documentId"] == doc] for doc in documents] if value.get("batch") else [sources]
        require(all(sum(len(s["quote"]) for s in group) <= 24000 for group in groups), "TEMPLATE_INPUT_BUDGET")
        key = identifier(value.get("operationId"))
        request_hash = fingerprint({"template": template, "sourceIds": [s["id"] for s in sources], "batch": bool(value.get("batch"))})
        jobs = []
        # Per-file idempotency keeps completed files when a different file fails.
        for index, group in enumerate(groups):
            run_id = "template-run-"+fingerprint([course, key, index])[:40]
            existing = await self.h.repo.get(course, run_id)
            if existing:
                require(existing["content"]["requestHash"] == request_hash, "IDEMPOTENCY_CONFLICT")
                jobs.append(existing["content"])
                continue
            pack = evidence_package({"courseId": course, "sources": group})
            await self.h.snapshots.put(course, pack["version"], {"sourceIds": [s["id"] for s in group]})
            run = {"runId": run_id, "requestHash": request_hash, "template": template, "sourceIds": [s["id"] for s in group],
                   "evidenceVersion": pack["version"], "status": "queued", "createdAt": now_iso()}
            with self.p.db.transaction():
                self.save_run(course, run_id, run)
                job = self.p.jobs.submit(self.p.user_id, {"type": "learning-template", "courseId": course, "resource": "api" if self.h.service(course).model else "cpu", "maxAttempts": 1,
                    "idempotencyKey": run_id, "input": {"runId": run_id}})
                run["jobId"] = job["id"]
                self.save_run(course, run_id, run)
            jobs.append(run)
        return {"items": jobs, "modelConfigured": bool(self.h.service(course).model), "maxCallsPerItem": 4}

    async def execute(self, scope, args, *, progress, checkpoint, commit):
        course = scope.course_id
        row = await self.h.repo.get(course, args["runId"])
        require(row and row["kind"] == "template-run", "RUN_NOT_FOUND")
        run = clone(row["content"])
        # CPU envelope only; the existing provider owns API permits/ledger. Never retry this type.
        job = self.p.jobs.get(run["jobId"], scope.user_id)
        require(job and job["status"] == "running" and job["attempts"] == 1 and run["status"] == "queued", "UNKNOWN_OUTCOME_REQUIRES_REVIEW")
        service = self.h.service(course)
        require(not service.model or job["resource"] == "api", "NOT_SENT")
        try:
            require(await self.h.verify_snapshot(course, run["evidenceVersion"]), "STALE_EVIDENCE")
            run["status"] = "running"
            await self.operational(course, row["id"], "template-run", run)
            sources = await self.h.sources({"courseId": course, "selection": {"sourceIds": run["sourceIds"]}})
            task = run["template"]["content"]["prompt"]+"；模板版本 "+str(run["template"]["revision"])
            async def report(value):
                progress({"completed": value["completed"], "total": value["total"], "label": "正在核对分段产物"})
            if service.model:
                with borrowed_api_permit(self.p):
                    result = await service.content.summarize({"courseId": course, "sources": sources, "task": task}, max_batches=4, on_progress=report)
            else:
                result = await service.content.summarize({"courseId": course, "sources": sources, "task": task}, max_batches=4, on_progress=report)
            require(await self.h.verify_snapshot(course, run["evidenceVersion"]), "STALE_EVIDENCE")
            result.update(template={"id": run["template"]["id"], "revision": run["template"]["revision"], "promptHash": fingerprint(task)},
                          origin="ai-generated" if service.model else "original-excerpt", evidenceVersion=run["evidenceVersion"],
                          title=run["template"]["content"]["title"], evidence=[ref for c in result["claims"] for ref in c["evidence"]])
            draft = await self.preview(course, "result-"+run["runId"], "template-result", result)
            run.update(status="awaiting_confirmation", preview=draft, finishedAt=now_iso())
            commit(lambda: self.save_run(course, row["id"], run))
            checkpoint({"runId": run["runId"], "draftId": draft["draftId"]})
            return {"runId": run["runId"], "draftId": draft["draftId"], "status": run["status"]}
        except (Exception, asyncio.CancelledError) as error:
            run.update(status="unknown" if service.model and run["status"] == "running" else "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
                       error=getattr(error, "code", "CANCELLED" if isinstance(error, asyncio.CancelledError) else "TEMPLATE_FAILED"))
            await self.operational(course, row["id"], "template-run", run)
            raise

    async def impact(self, course, rows=None):
        rows = self.h.repo.all(course) if rows is None else rows
        try:
            actual = {s["id"]: s for s in await self.h.sources({"courseId": course})}
        except DomainError as error:
            if error.code != "NO_SOURCES":
                raise
            actual = {}
        by_id, result = {r["id"]: r for r in rows}, []
        for row in rows:
            if row["kind"] in ("learning-template", "template-run", "media"):
                continue
            content = row["content"]
            refs, parents = [], []
            def dependencies(value):
                if isinstance(value, dict):
                    if all(k in value for k in ("sourceId", "version", "quote")):
                        refs.append(value)
                    if all(k in value for k in ("sourceId", "sourceVersion", "evidenceQuote")):
                        refs.append({"sourceId": value["sourceId"], "version": value["sourceVersion"], "quote": value["evidenceQuote"]})
                    parents.extend(value.get("derivedFrom", []))
                    if isinstance(value.get("sourcePackage"), dict):
                        parents.append(value["sourcePackage"])
                    for nested in value.values():
                        dependencies(nested)
                elif isinstance(value, list):
                    for nested in value:
                        dependencies(nested)
            dependencies(content)
            reasons = []
            for ref in refs:
                source = actual.get(ref.get("sourceId"))
                if not source:
                    reasons.append("source_removed")
                elif str(source["version"]) != str(ref.get("version")) or ref.get("quote", "") not in source["quote"]:
                    reasons.append("source_changed")
            for parent in parents:
                current = by_id.get(parent["id"])
                if not current or current["revision"] != parent["revision"]:
                    reasons.append("parent_changed")
            snapshot = content.get("evidenceVersion")
            if snapshot and not await self.h.verify_snapshot(course, snapshot):
                reasons.append("source_snapshot_changed")
            result.append({"id": row["id"], "kind": row["kind"], "revision": row["revision"], "parents": parents,
                           "status": "needs_review" if reasons else "current" if refs or snapshot else "untracked",
                           "reasons": sorted(set(reasons)), "origin": content.get("origin", "legacy-untracked")})
        # Propagate source impact through derived content without rewriting any historical artifact.
        for _ in range(min(len(result), 32)):
            stale = {r["id"] for r in result if r["status"] == "needs_review"}
            changed = False
            for item in result:
                parents = item["parents"]
                if item["status"] != "needs_review" and any(p["id"] in stale for p in parents):
                    item.update(status="needs_review", reasons=["parent_needs_review"])
                    changed = True
            if not changed:
                break
        return result

    async def convert(self, course, value):
        parent = await self.h.repo.get(course, identifier(value.get("parentId")))
        require(parent and parent["revision"] == value.get("parentRevision"), "ARTIFACT_CONFLICT")
        content, service = parent["content"], self.h.service(course)
        if parent['kind'] == 'search-run':
            require(content.get('status') == 'completed' and content.get('result'), 'RESULT_NOT_READY')
            result = content['result']
            content = {'text': result['answer'], 'origin': 'original-excerpt' if result.get('engine') == 'local-excerpts' else 'ai-generated',
                       'evidence': [{'sourceId': s['id'], 'documentId': s['documentId'], 'version': s['version'], 'quote': s['quote']} for s in result.get('context', {}).get('sources', [])]}
        refs = content.get("evidence") or [r for c in content.get("claims", []) for r in c.get("evidence", [])]
        text = value.get("text") or content.get("text") or "\n\n".join(c["text"] for c in content.get("claims", []))
        require(isinstance(text, str) and 0 < len(text.strip()) <= 120000, "INVALID_NOTE")
        kind = value.get("target", "note")
        sources = await self.h.sources({"courseId": course, "selection": {"sourceIds": list({r["sourceId"] for r in refs})}}) if refs else []
        for ref in refs:
            s = next((s for s in sources if s["id"] == ref["sourceId"]), None)
            require(s and s["version"] == ref["version"] and ref["quote"] in s["quote"], "STALE_EVIDENCE")
        provenance = {"origin": "human-revised" if value.get("text") else content.get("origin", "personal-note"),
                      "derivedFrom": [{"id": parent["id"], "revision": parent["revision"]}], "evidence": refs,
                      "template": content.get("template"), "personalHypothesis": not bool(refs)}
        key = identifier(value.get("id"))
        if kind == "note":
            return await self.preview(course, key, "note", {**provenance, "title": value.get("title", "学习笔记")[:160],
                "text": text, "understanding": text, "pendingQuestions": str(value.get("pendingQuestions", ""))[:4000]})
        require(refs, "TEXTBOOK_EVIDENCE_REQUIRED")
        if kind == "memory-card":
            draft = await service.reviews.preview({"courseId": course, "id": key, "prompt": value.get("prompt"), "answer": text,
                                                   "evidence": refs, "sources": sources})
            draft = await service.artifacts.preview({**draft, "content": {**draft["content"], **provenance}})
            return await self.h.pages.preview(course, draft)
        require(kind == "question-draft", "INVALID_CONVERSION")
        question = validate_question({"id": key, "courseId": course, "version": fingerprint([text, refs])[:24], "type": "short",
            "prompt": value.get("prompt"), "sourceId": refs[0]["sourceId"], "sourceVersion": refs[0]["version"],
            "evidenceQuote": refs[0]["quote"], "rubric": [{"id": "point-1", "description": text[:8000], "points": 1}], "status": "candidate"}, sources)
        return await self.preview(course, "question:"+key, "question-draft", {**question, **provenance})

    async def dispatch(self, path, request, course):
        if not path.startswith("content/"):
            return None
        from .app import json_body, connected_work
        operation = path[len("content/"):]
        reads = {"workspace", "impacts"}
        require(request.method == ("GET" if operation in reads else "POST"), "METHOD_NOT_ALLOWED")
        value = {} if operation in reads else await json_body(request)
        require(value.get("courseId", course) == course, "COURSE_MISMATCH")
        async def execute():
            if operation == "workspace":
                rows = self.h.repo.all(course)
                return {"templates": self.templates(course), "items": [r for r in rows if r["kind"] in ("note", "template-result", "question-draft", "memory-card")],
                        "runs": [r for r in rows if r["kind"] == "template-run"], "impacts": await self.impact(course, rows),
                        "documents": [d for d in self.p.repo.all(self.p.scope(course), "document") if not d.get("superseded") and not d.get("archived")],
                        "modelConfigured": bool(self.h.service(course).model)}
            if operation == "impacts":
                return {"items": await self.impact(course)}
            if operation == "template/preview":
                c = value.get("content")
                require(isinstance(c, dict) and all(isinstance(c.get(k), str) and 0 < len(c[k].strip()) <= 6000 for k in ("title", "goal", "prompt")), "INVALID_TEMPLATE")
                return await self.preview(course, value.get("id"), "learning-template", {**{k: c[k] for k in ("title", "goal", "prompt")},
                    "subject": str(c.get("subject", "通用"))[:100], "format": "claims-with-evidence", "sourcePolicy": "selected-originals", "modelPurpose": "course-content"}, value.get("expectedRevision", 0))
            if operation == "run":
                return await self.start(course, value)
            if operation == "cancel":
                row = await self.h.repo.get(course, value.get("id"))
                require(row and row["kind"] == "template-run", "RUN_NOT_FOUND")
                result = self.p.jobs.cancel(row["content"]["jobId"], self.p.user_id)
                if row["content"]["status"] == "queued":
                    await self.operational(course, row["id"], "template-run", {**row["content"], "status": "cancelled"})
                return result
            if operation == "resume":
                row = await self.h.repo.get(course, value.get("id"))
                require(row and row["kind"] == "template-run" and row["content"]["status"] in ("failed", "cancelled", "unknown"), "RUN_NOT_RESUMABLE")
                require(value.get("confirmed") is True and (not self.h.service(course).model or value.get("allowApi") is True), "CONFIRMATION_REQUIRED")
                require(await self.h.verify_snapshot(course, row["content"]["evidenceVersion"]), "STALE_EVIDENCE")
                return await self.start(course, {"templateId": row["content"]["template"]["id"], "templateRevision": row["content"]["template"]["revision"],
                    "selection": {"sourceIds": row["content"]["sourceIds"]}, "allowApi": value.get("allowApi"), "operationId": value.get("operationId")})
            if operation == "recover-preview":
                row = await self.h.repo.get(course, value.get("id"))
                require(row and row["kind"] == "template-run" and row["content"].get("preview"), "PREVIEW_NOT_READY")
                draft = row["content"]["preview"]["draft"]
                await self.h.validate_draft(course, draft)
                return await self.h.pages.preview(course, draft)
            if operation == "convert/preview":
                return await self.convert(course, value)
            if operation in ("note/preview", "legacy/preview"):
                old = await self.h.repo.get(course, value.get("id"))
                require(not old or old["kind"] == "note", "ARTIFACT_KIND_CONFLICT")
                text = value.get("text")
                require(isinstance(text, str) and 0 < len(text.strip()) <= 120000, "INVALID_NOTE")
                content = {**(clone(old["content"]) if old else {}), "title": str(value.get("title", "学习笔记"))[:160], "text": text,
                    "understanding": text, "pendingQuestions": str(value.get("pendingQuestions", ""))[:4000], "origin": "human-revised" if old else "legacy-untracked" if operation == "legacy/preview" else "personal-note", "editedBy": "user"}
                return await self.preview(course, value.get("id"), "note", content, value.get("expectedRevision", 0))
            require(False, "ROUTE_NOT_FOUND")
        return JSONResponse({"ok": True, "result": await connected_work(request, execute()) if operation not in reads else await execute()})
