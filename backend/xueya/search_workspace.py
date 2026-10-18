"""G4 scoped context policies, typed search and bounded evidence-first workflows."""
import asyncio
import re
from uuid import uuid4

from fastapi.responses import JSONResponse
from backend.core import DomainError, clone, dumps, fingerprint, now_iso, require, valid_date
from backend.agent.evidence import evidence_package
from backend.agent.general_chat import general_chat
from .common import AppError, identifier
from .rag_search import compress, lexical, rewrite_query
from .rag_api import borrowed_api_permit

DEFAULT = {"mode": "relevant", "documentModes": {}, "noteIds": [], "budget": 8000, "maxQueries": 4, "maxApiCalls": 4, "retrieval": "lexical", "section": None}
KINDS = {"source", "note", "template-result", "chapter-summary", "learning-package", "question-draft", "attempt", "concept-graph", "memory-card"}


class SearchWorkspace:
    def __init__(self, host):
        self.h, self.p = host, host.p
        self.p.jobs.register("search-answer", self.execute)
        for course in self.p.repo.courses(self.p.user_id):
            if course["archived"]:
                continue
            for row in self.h.repo.all(course["id"]):
                if row["kind"] == "search-run" and row["content"]["status"] == "running":
                    self.store(course["id"], row["id"], "search-run", {**row["content"], "status": "unknown", "error": "INTERRUPTED_REQUIRES_REVIEW"})

    def configuration_identity(self):
        c = self.h.app.state.config
        rag = self.h.app.state.rag
        providers = [(provider.identity, fingerprint(provider.settings.key)) if provider else None for provider in (rag.embedding, rag.rerank)]
        return fingerprint([c.model, c.base_url, fingerprint(c.api_key), providers])

    def store(self, course, key, kind, content, expected=None):
        scope = self.p.scope(course)
        old = self.p.repo.read(scope, "artifact", self.h.repo.key(key))
        revision = old["value"]["revision"] if old else 0
        require(expected is None or expected == revision, "ARTIFACT_CONFLICT")
        self.p.repo.put(scope, "artifact", self.h.repo.key(key), {"courseId": course, "id": key, "kind": kind,
            "revision": revision+1, "updatedAt": now_iso(), "content": clone(content)}, old["version"] if old else 0)
        return revision+1

    async def session(self, course, session_id):
        identifier(session_id)
        row = await self.h.repo.get(course, "search-session:"+session_id)
        return row or {"id": "search-session:"+session_id, "revision": 0, "content": {"policy": clone(DEFAULT), "turns": [], "historySummary": None}}

    @staticmethod
    def policy(value):
        require(isinstance(value, dict) and not set(value)-set(DEFAULT), "INVALID_CONTEXT_POLICY")
        result = {**clone(DEFAULT), **value}
        require(result["mode"] in ("relevant", "chapter", "general") and result["retrieval"] in ("lexical", "vector", "hybrid", "rerank"), "INVALID_CONTEXT_POLICY")
        require(type(result["budget"]) is int and 1024 <= result["budget"] <= 32000 and type(result["maxQueries"]) is int and 1 <= result["maxQueries"] <= 4 and type(result["maxApiCalls"]) is int and 1 <= result["maxApiCalls"] <= 8, "INVALID_CONTEXT_BUDGET")
        require(isinstance(result["documentModes"], dict) and len(result["documentModes"]) <= 100 and all(isinstance(k, str) and v in ("excluded", "background", "original") for k, v in result["documentModes"].items()), "INVALID_DOCUMENT_POLICY")
        require(isinstance(result["noteIds"], list) and len(result["noteIds"]) <= 20 and all(isinstance(k, str) for k in result["noteIds"]), "INVALID_NOTE_SELECTION")
        require(result["section"] is None or isinstance(result["section"], str) and len(result["section"]) <= 200, "INVALID_SECTION")
        return result

    async def originals(self, course, policy):
        try:
            sources = await self.h.sources({"courseId": course, "selection": {"section": policy.get("section")} if policy.get("section") else {}}, generation=False)
        except DomainError as error:
            if error.code != "NO_SOURCES":
                raise
            sources = []
        documents = {d["id"]: d for d in self.p.repo.all(self.p.scope(course), "document")}
        return [s for s in sources if policy["documentModes"].get(s["documentId"], "original") == "original" and not documents.get(s["documentId"], {}).get("archived")]

    async def background(self, course, policy):
        notes = []
        for key in policy["noteIds"]:
            row = await self.h.repo.get(course, key)
            require(row and row["kind"] in ("note", "template-result", "chapter-summary"), "NOTE_NOT_FOUND")
            text = self.text(row["content"])
            notes.append({"id": key, "revision": row["revision"], "kind": row["kind"], "text": text,
                          "authority": "personal-or-derived-not-textbook"})
        summaries = []
        background_docs = {k for k, v in policy["documentModes"].items() if v == "background"}
        for row in self.h.repo.all(course):
            c = row["content"]
            if row["kind"] not in ("chapter-summary", "template-result", "note"):
                continue
            refs = c.get("evidence", []) or [r for claim in c.get("claims", []) for r in claim.get("evidence", [])]
            if refs and {r.get("documentId") for r in refs} <= background_docs:
                summaries.append({"id": row["id"], "revision": row["revision"], "text": self.text(c), "authority": "navigation-only"})
        return notes+summaries

    @staticmethod
    def text(content):
        if not isinstance(content, dict):
            return str(content)
        pieces = [content.get(k) for k in ("title", "text", "prompt", "answer", "name", "explanation") if isinstance(content.get(k), str)]
        pieces += [c.get("text", "") for c in content.get("claims", [])]
        if content.get("questions"):
            pieces += [q.get("prompt", "") for q in content["questions"]]
        if content.get("questionSnapshots"):
            pieces += [q.get("prompt", "") for q in content["questionSnapshots"]]
        if content.get("concepts"):
            pieces += [c if isinstance(c, str) else c.get("name", "") for c in content["concepts"]]
        return "\n".join(pieces)

    async def search(self, course, value):
        query = value.get("query")
        require(isinstance(query, str) and 0 < len(query.strip()) <= 4000, "INVALID_QUERY")
        mode = value.get("mode", "lexical")
        require(mode in ("lexical", "vector", "hybrid", "rerank"), "INVALID_SEARCH_MODE")
        require(mode == "lexical" or value.get("allowApi") is True, "API_CONFIRMATION_REQUIRED")
        policy = self.policy(value.get("policy", {}))
        types = value.get("types", list(KINDS))
        require(isinstance(types, list) and all(isinstance(t, str) for t in types) and set(types) <= KINDS, "INVALID_SEARCH_TYPES")
        require(type(value.get("effectiveOnly", True)) is bool, "INVALID_FILTER")
        limit = value.get("limit", 20)
        require(type(limit) is int and 1 <= limit <= 50, "INVALID_LIMIT")
        all_sources = await self.originals(course, policy)
        current_sources = {s["id"]: s for s in await self.originals(course, clone(DEFAULT))}
        items = [{**s, "kind": "source", "authority": "textbook-original", "updatedAt": "", "searchId": "source:"+s["id"]} for s in all_sources] if "source" in types else []
        after = value.get("afterTime")
        before = value.get("beforeTime")
        require(after is None or valid_date(after), "INVALID_TIME_FILTER")
        require(before is None or valid_date(before), "INVALID_TIME_FILTER")
        for row in self.h.repo.all(course):
            if row["kind"] not in types or after and row.get("updatedAt", "")[:10] < after or before and row.get("updatedAt", "")[:10] > before:
                continue
            content = row["content"]
            text = self.text(content)
            if not text.strip():
                continue
            refs = content.get("evidence", []) or [r for c in content.get("claims", []) for r in c.get("evidence", [])]
            if policy.get("section") and (not refs or any(r.get("sourceId") not in {s["id"] for s in all_sources} for r in refs)):
                continue
            # A source filter must also constrain derived items, never silently widen scope.
            if policy["documentModes"] and any(policy["documentModes"].get(r.get("documentId"), "original") == "excluded" for r in refs):
                continue
            actual = current_sources
            stale = any(r.get("sourceId") not in actual or str(actual[r["sourceId"]]["version"]) != str(r.get("version")) or r.get("quote", "") not in actual[r["sourceId"]]["quote"] for r in refs)
            if value.get("effectiveOnly", True) and stale:
                continue
            items.append({"id": row["id"], "searchId": row["kind"]+":"+row["id"], "kind": row["kind"], "revision": row["revision"],
                "title": str(content.get("title", content.get("prompt", row["kind"])))[:160], "quote": text,
                "location": "学习内容 v"+str(row["revision"]), "authority": "personal-or-derived-not-textbook", "updatedAt": row.get("updatedAt"), "evidence": refs, "needsReview": stale})
        warnings, semantic = [], []
        if mode != "lexical":
            documents = sorted({s["documentId"] for s in all_sources})
            evidence = await self.h.app.state.rag.search(self.p.scope(course), query, document_ids=documents, mode=mode, budget=min(policy["budget"], 16000))
            warnings = evidence["warnings"]+["LEARNING_CONTENT_LEXICAL_ONLY"]
            semantic = evidence["sources"]
        ranked = lexical(query, items, limit=100)
        if semantic:
            by_id = {s["id"]: s for s in items if s["kind"] == "source"}
            ranked = [(1, by_id[s["id"]]) for s in semantic if s["id"] in by_id]+ranked
        found, seen = [], set()
        for score, item in ranked:
            key = item["searchId"]
            if key in seen:
                continue
            seen.add(key)
            text = item["quote"]
            location = text.casefold().find(query.casefold())
            offset = max(0, location-60) if location >= 0 else 0
            found.append({**item, "quote": text[offset:offset+360], "snippetOffset": offset, "score": round(score, 6)})
            if len(found) == limit:
                break
        return {"items": found, "warnings": warnings, "route": mode if mode == "lexical" or not warnings else "lexical-fallback", "semanticScope": "source-only"}

    async def context(self, course, policy, query, *, history=(), complex=False, allow_api=False):
        policy = self.policy(policy)
        require(isinstance(query, str) and 0 < len(query.strip()) <= 4000, "INVALID_QUERY")
        history_used = [{"role": t["role"], "content": t["content"][:4000]} for t in list(history)[-8:]]
        history_trimmed = len(history) > 8 or any(len(t["content"]) > 4000 for t in list(history)[-8:])
        if policy["mode"] == "general":
            used = len(dumps(history_used).encode())
            require(used <= policy["budget"], "CONTEXT_BUDGET_EXCEEDED")
            return {"sources": [], "background": [], "queries": [], "warnings": ["HISTORY_NAVIGATION_TRIMMED"] if history_trimmed else [], "policy": policy, "historyUsed": history_used,
                    "estimate": {"unit": "utf8Bytes", "used": used, "limit": policy["budget"], "approximateTokens": (used+2)//3, "exactTokens": False}}
        sources = await self.originals(course, policy)
        background = await self.background(course, policy)
        rewritten = rewrite_query(query, history)
        queries = [q.strip() for q in re.split(r"[；;？?]|以及|并且", rewritten) if q.strip()] if complex else [rewritten]
        require(0 < len(queries) <= policy["maxQueries"], "QUERY_BUDGET_EXCEEDED")
        warnings, selected = [], []
        if policy["mode"] == "chapter":
            selected = sources
        else:
            seen = set()
            for q in queries:
                ranked = lexical(q, sources, limit=12)
                if policy["retrieval"] != "lexical" and allow_api:
                    found = await self.h.app.state.rag.search(self.p.scope(course), q, document_ids=sorted({s["documentId"] for s in sources}), mode=policy["retrieval"], budget=min(policy["budget"], 16000))
                    warnings += found["warnings"]
                    ids = {s["id"] for s in found["sources"]}
                    ranked = [(1, s) for s in sources if s["id"] in ids]+ranked
                for _, source in ranked:
                    if source["id"] not in seen:
                        selected.append(source)
                        seen.add(source["id"])
        # No silent truncation in chapter mode or of selected notes/history.
        omitted = []
        if policy["mode"] == "relevant":
            fitted = []
            for source in selected:
                if len(dumps({"sources": fitted+[source], "background": background, "history": history_used}).encode()) <= policy["budget"]:
                    fitted.append(source)
                else:
                    omitted.append(source["id"])
            selected = fitted
            if omitted:
                warnings.append("CANDIDATES_OMITTED_BY_BUDGET")
        if history_trimmed:
            warnings.append("HISTORY_NAVIGATION_TRIMMED")
        used = len(dumps({"sources": selected, "background": background, "history": history_used}).encode())
        require(used <= policy["budget"], "CONTEXT_BUDGET_EXCEEDED")
        return {"sources": selected, "background": background, "queries": queries, "warnings": sorted(set(warnings)), "policy": policy, "historyUsed": history_used, "omittedSourceIds": omitted,
                "missingQueries": [q for q in queries if not lexical(q, selected)],
                "estimate": {"unit": "utf8Bytes", "used": used, "limit": policy["budget"], "approximateTokens": (used+2)//3, "exactTokens": False}}

    async def submit(self, course, value):
        key = "search-run-"+fingerprint([course, value.get("sessionId"), identifier(value.get("operationId"))])[:40]
        previous = await self.h.repo.get(course, key)
        if previous:
            old = previous["content"]
            require(old["query"] == value.get("query") and old["policyRevision"] == value.get("policyRevision") and old["complex"] == bool(value.get("complex")), "IDEMPOTENCY_CONFLICT")
            return old
        session = await self.session(course, value.get("sessionId"))
        policy = session["content"]["policy"]
        require(value.get("policyRevision") == session["revision"], "CONTEXT_POLICY_CONFLICT")
        query = value.get("query")
        require(isinstance(query, str) and 0 < len(query.strip()) <= 4000, "INVALID_QUERY")
        require(not self.h.service(course).model or value.get("allowApi") is True, "API_CONFIRMATION_REQUIRED")
        # Free preflight catches scope/size errors before scheduling any paid request.
        history = session["content"]["turns"][-8:]
        preflight = await self.context(course, policy, query, history=history, complex=bool(value.get("complex")))
        query_count = len(preflight["queries"])
        calls = int(bool(self.h.service(course).model))
        if policy["retrieval"] != "lexical" and policy["mode"] == "relevant":
            calls += query_count*(int(bool(self.h.app.state.rag.embedding))+int(policy["retrieval"] == "rerank" and bool(self.h.app.state.rag.rerank)))
        require(calls <= policy["maxApiCalls"], "API_CALL_BUDGET_EXCEEDED")
        identity = fingerprint([query, session["revision"], policy, bool(value.get("complex"))])
        run = {"runId": key, "query": query, "requestHash": identity, "sessionId": value["sessionId"], "policyRevision": session["revision"],
               "policy": clone(policy), "history": history, "complex": bool(value.get("complex")), "status": "queued", "steps": [], "maxApiCalls": calls,
               "configurationIdentity": self.configuration_identity()}
        with self.p.db.transaction():
            self.store(course, key, "search-run", run)
            job = self.p.jobs.submit(self.p.user_id, {"type": "search-answer", "courseId": course, "idempotencyKey": key,
                "resource": "api" if calls else "cpu", "maxAttempts": 1, "input": {"runId": key}})
            run["jobId"] = job["id"]
            self.store(course, key, "search-run", run)
        return run

    async def execute(self, scope, args, *, progress, checkpoint, commit):
        course = scope.course_id
        row = await self.h.repo.get(course, args["runId"])
        require(row and row["kind"] == "search-run" and row["content"]["status"] == "queued", "RUN_NOT_RESUMABLE")
        run = clone(row["content"])
        service = self.h.service(course)
        job = self.p.jobs.get(run["jobId"], self.p.user_id)
        require(job["attempts"] == 1 and (not run["maxApiCalls"] or job["resource"] == "api"), "NOT_SENT")
        run["status"] = "running"
        self.store(course, row["id"], "search-run", run)
        try:
            if run.get('configurationIdentity') != self.configuration_identity():
                raise AppError('NOT_SENT')
            current = await self.session(course, run["sessionId"])
            require(current["revision"] == run["policyRevision"], "CONTEXT_POLICY_CONFLICT")
            with borrowed_api_permit(self.p) if job["resource"] == "api" else _nothing():
                context = await self.context(course, run["policy"], run["query"], history=run["history"], complex=run["complex"], allow_api=True)
                run["steps"] = [{"query": q, "sourceIds": [s["id"] for s in context["sources"] if lexical(q, [s])], "status": "evidence_found" if lexical(q, context["sources"]) else "insufficient"} for q in context["queries"]]
                progress({"label": "原文范围与查询已核对", "completed": len(run["steps"]), "total": len(run["steps"])+1})
                if run["policy"]["mode"] == "general":
                    require(service.model, "MODEL_NOT_CONFIGURED")
                    async for event in general_chat(service.model, {"question": run["query"], "history": context["historyUsed"]}):
                        if event["type"] == "done":
                            answer = event
                elif context["sources"]:
                    # Notes are navigation only. They never become C AnswerService's textbook sources.
                    answer = await service.answers.answer({"courseId": course, "question": run["query"], "sources": context["sources"], "history": context["historyUsed"], "background": context["background"]})
                else:
                    answer = {"answer": "所选范围中没有找到足够原文依据。个人笔记不是教材证据。", "sources": [], "engine": "insufficient-evidence"}
            latest = await self.session(course, run["sessionId"])
            require(latest["revision"] == run["policyRevision"], "CONTEXT_POLICY_CONFLICT")
            for background in context["background"]:
                actual_background = await self.h.repo.get(course, background["id"])
                require(actual_background and actual_background["revision"] == background["revision"], "BACKGROUND_CHANGED")
            if context["sources"]:
                actual = {s["id"]: s for s in await self.originals(course, run["policy"])}
                require(all(s["id"] in actual and s["version"] == actual[s["id"]]["version"] and s["quote"] == actual[s["id"]]["quote"] for s in context["sources"]), "STALE_EVIDENCE")
            run.update(status="completed", result={**answer, "context": context, "process": run["steps"], "missingQueries": context.get("missingQueries", [])}, finishedAt=now_iso())
            turns = latest["content"]["turns"]+[{"role": "user", "content": run["query"], "runId": row["id"]}, {"role": "assistant", "content": answer["answer"], "runId": row["id"]}]
            require(len(turns) <= 200 and sum(len(t["content"]) for t in turns) <= 120000, "SESSION_ARCHIVE_REQUIRED")
            summary = {"kind": "navigation-only", "text": "\n".join(t["content"][:120] for t in turns if t["role"] == "user"), "originalTurnsRetained": True} if len(turns) > 8 else None
            def publish():
                self.store(course, row["id"], "search-run", run)
                self.store(course, latest["id"], "search-session", {**latest["content"], "turns": turns, "historySummary": summary}, latest["revision"])
            commit(publish)
            return {"runId": row["id"], "status": "completed"}
        except (Exception, asyncio.CancelledError) as error:
            run.update(status="failed" if getattr(error, 'code', None) == 'NOT_SENT' else "unknown" if job["resource"] == "api" else "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
                       error=getattr(error, "code", "CANCELLED" if isinstance(error, asyncio.CancelledError) else "SEARCH_FAILED"))
            self.store(course, row["id"], "search-run", run)
            raise

    async def dispatch(self, path, request, course):
        if not path.startswith("search/"):
            return None
        from .app import connected_work, json_body
        operation = path[len("search/"):]
        read = operation in ("workspace", "result", "read")
        require(request.method == ("GET" if read else "POST"), "METHOD_NOT_ALLOWED")
        value = dict(request.query_params) if read else await json_body(request)
        require(value.get("courseId", course) == course, "COURSE_MISMATCH")
        async def execute():
            if operation == "workspace":
                session = await self.session(course, value.get("sessionId"))
                return {"session": session, "documents": [d for d in self.p.repo.all(self.p.scope(course), "document") if not d.get("superseded") and not d.get("archived")],
                        "notes": [{"id": r["id"], "title": r["content"].get("title", r["kind"]), "revision": r["revision"]} for r in self.h.repo.all(course) if r["kind"] in ("note", "template-result", "chapter-summary")],
                        "runs": [r for r in self.h.repo.all(course) if r["kind"] == "search-run" and r["content"]["sessionId"] == value["sessionId"]],
                        "capabilities": {"model": bool(self.h.service(course).model), "embedding": bool(self.h.app.state.rag.embedding), "rerank": bool(self.h.app.state.rag.rerank)}}
            if operation == "policy":
                require(type(value.get("expectedRevision")) is int and value["expectedRevision"] >= 0, "INVALID_REVISION")
                session = await self.session(course, value.get("sessionId"))
                revision = self.store(course, session["id"], "search-session", {**session["content"], "policy": self.policy(value.get("policy"))}, value.get("expectedRevision"))
                return {"revision": revision}
            if operation == "find":
                return await self.search(course, value)
            if operation == "context":
                session = await self.session(course, value.get("sessionId"))
                return await self.context(course, session["content"]["policy"], value.get("query", "范围预览"), history=session["content"]["turns"][-8:], complex=bool(value.get("complex")))
            if operation == "ask":
                return await self.submit(course, value)
            if operation == "cancel":
                row = await self.h.repo.get(course, value.get("id"))
                require(row and row["kind"] == "search-run", "RUN_NOT_FOUND")
                result = self.p.jobs.cancel(row["content"]["jobId"], self.p.user_id)
                if row["content"]["status"] == "queued":
                    self.store(course, row["id"], "search-run", {**row["content"], "status": "cancelled"})
                return result
            if operation == "resume":
                row = await self.h.repo.get(course, value.get("id"))
                require(row and row["kind"] == "search-run" and row["content"]["status"] in ("failed", "unknown", "cancelled"), "RUN_NOT_RESUMABLE")
                require(value.get("confirmed") is True, "CONFIRMATION_REQUIRED")
                return await self.submit(course, {**value, "sessionId": row["content"]["sessionId"], "query": row["content"]["query"], "policyRevision": row["content"]["policyRevision"], "complex": row["content"]["complex"]})
            if operation == "result":
                row = await self.h.repo.get(course, value.get("id"))
                require(row and row["kind"] == "search-run", "RUN_NOT_FOUND")
                result = clone(row)
                if result["content"].get("result", {}).get("context", {}).get("sources"):
                    old_sources = result["content"]["result"]["context"]["sources"]
                    actual = {s["id"]: s for s in await self.originals(course, result["content"]["policy"])}
                    result["content"]["stale"] = any(s["id"] not in actual or actual[s["id"]]["version"] != s["version"] or actual[s["id"]]["quote"] != s["quote"] for s in old_sources)
                return result
            if operation == "read":
                if value.get("kind") == "source":
                    sources = await self.originals(course, clone(DEFAULT))
                    source = next((s for s in sources if s["id"] == value.get("id")), None)
                    require(source, "SOURCE_NOT_FOUND")
                    return {"kind": "source", "source": source}
                row = await self.h.repo.get(course, value.get("id"))
                require(row and row["kind"] in KINDS, "ARTIFACT_NOT_FOUND")
                return {"kind": row["kind"], "artifact": row, "authority": "personal-or-derived-not-textbook"}
            require(False, "ROUTE_NOT_FOUND")
        return JSONResponse({"ok": True, "result": await execute() if read else await connected_work(request, execute())})


from contextlib import nullcontext as _nothing
