"""G4 scope/budget/typed-search and actual queue tests; no real paid API."""
import json
import time
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider


def call(c, path, value=None, course="course-default"):
    return c.request("POST" if value is not None else "GET", "/api/learning/search/"+path+("&" if "?" in path else "?")+"courseId="+course,
                     headers=c.platform_headers, **({"json": value} if value is not None else {}))


def seed(c, sid="plant", text="光合作用发生在叶绿体。", course="course-default"):
    p = c.platform
    p.repo.put(p.scope(course), "source", sid, {"id": sid, "documentId": "doc-"+sid, "title": "无关标题", "quote": text, "location": "第1段"})
    p.repo.put(p.scope(course), "document", "doc-"+sid, {"id": "doc-"+sid, "name": "无关标题.md"})


def artifact(c, key="my-note", kind="note", text="我把光合作用理解为能量转换", course="course-default", extra=None):
    p = c.platform
    p.repo.put(p.scope(course), "artifact", "learning-artifact-"+__import__('backend.core', fromlist=['fingerprint']).fingerprint(key),
        {"id": key, "courseId": course, "kind": kind, "revision": 1, "updatedAt": "2026-10-18T00:00:00Z", "content": {"text": text, "origin": "personal-note", **(extra or {})}})


def policy(c, session="one", value=None, revision=0):
    r = call(c, "policy", {"sessionId": session, "expectedRevision": revision, "policy": value or {}})
    assert r.status_code == 200, r.text
    return r.json()["result"]["revision"]


def finish(c, job):
    for _ in range(300):
        row = c.get("/api/platform/jobs/status?id="+job, headers=c.platform_headers).json()["job"]
        if row["status"] in ("succeeded", "failed", "unknown", "cancelled"):
            return row
        time.sleep(.02)
    pytest.fail("job timeout")


def ask(c, query="光合作用在哪里？", session="one", revision=1, **more):
    r = call(c, "ask", {"sessionId": session, "policyRevision": revision, "query": query, "operationId": str(uuid4()), **more})
    assert r.status_code == 200, r.text
    run = r.json()["result"]
    return run, finish(c, run["jobId"])


def test_policy_persists_by_course_session_and_cas(client):
    c = client
    seed(c)
    policy(c, value={"documentModes": {"doc-plant": "excluded"}, "mode": "chapter"})
    session = call(c, "workspace?sessionId=one").json()["result"]["session"]
    assert session["content"]["policy"]["documentModes"] == {"doc-plant": "excluded"}
    assert call(c, "workspace?sessionId=two").json()["result"]["session"]["revision"] == 0
    assert call(c, "policy", {"sessionId": "one", "expectedRevision": 0, "policy": {}}).status_code == 409
    c.platform.repo.ensure_course(c.platform.user_id, {"id": "other", "name": "其他"})
    assert call(c, "workspace?sessionId=one", course="other").json()["result"]["session"]["revision"] == 0
    assert call(c, "context", {"sessionId": "one", "query": "光合作用"}).json()["result"]["sources"] == []


def test_unified_body_notes_question_attempt_concept_search_and_types(client):
    c = client
    seed(c)
    for kind in ("note", "template-result", "question-draft", "attempt", "concept-graph", "memory-card"):
        artifact(c, key=kind, kind=kind, text="光合作用的人工解释", extra={"concepts": ["植物"]} if kind == "template-result" else {})
    rows = call(c, "find", {"query": "光合作用"}).json()["result"]["items"]
    assert {r["kind"] for r in rows} >= {"source", "note", "template-result", "question-draft", "attempt", "concept-graph", "memory-card"}
    assert next(r for r in rows if r["kind"] == "source")["authority"] == "textbook-original"
    assert all(r["authority"] != "textbook-original" for r in rows if r["kind"] != "source")
    notes = call(c, "find", {"query": "光合作用", "types": ["note"]}).json()["result"]["items"]
    assert len(notes) == 1 and notes[0]["id"] == "note"
    assert call(c, "find", {"query": "光合作用", "types": ["note"], "afterTime": "2026-10-19"}).json()["result"]["items"] == []
    assert call(c, "find", {"query": "光合作用", "policy": {"documentModes": {"doc-plant": "excluded"}}, "types": ["source"]}).json()["result"]["items"] == []


def test_background_is_not_authoritative_and_empty_exclusion_stays_empty(client):
    c = client
    seed(c)
    artifact(c, text="错误猜想：光合作用发生在月球。")
    policy(c, value={"noteIds": ["my-note"], "documentModes": {"doc-plant": "background"}})
    context = call(c, "context", {"sessionId": "one", "query": "光合作用"}).json()["result"]
    assert not context["sources"] and context["background"][0]["authority"] != "textbook-original"
    run, job = ask(c)
    assert job["status"] == "succeeded"
    answer = call(c, "result?id="+run["runId"]).json()["result"]["content"]["result"]
    assert answer["engine"] == "insufficient-evidence" and not answer["sources"]


def test_chapter_never_silently_truncated_and_relevant_reports_omission(client):
    c = client
    for i in range(4):
        seed(c, sid="long"+str(i), text="光合作用"*400)
    policy(c, value={"mode": "chapter", "budget": 1024})
    r = call(c, "context", {"sessionId": "one", "query": "光合作用"})
    assert r.status_code == 503 and r.json()["error"] == "CONTEXT_BUDGET_EXCEEDED"
    policy(c, value={"mode": "relevant", "budget": 1024}, revision=1)
    result = call(c, "context", {"sessionId": "one", "query": "光合作用"}).json()["result"]
    assert result["omittedSourceIds"] and "CANDIDATES_OMITTED_BY_BUDGET" in result["warnings"]
    assert result["estimate"]["used"] <= 1024 and not result["estimate"]["exactTokens"]


def test_bounded_multistep_excerpt_answer_and_source_deletion(client):
    c = client
    seed(c)
    seed(c, sid="tree", text="二叉搜索树查找与树高有关。")
    policy(c)
    run, job = ask(c, query="光合作用在哪里；二叉搜索树查找复杂度", complex=True)
    assert job["status"] == "succeeded"
    result = call(c, "result?id="+run["runId"]).json()["result"]["content"]
    assert len(result["steps"]) == 2 and result["result"]["engine"] == "local-excerpts"
    assert len(result["result"]["sources"]) == 2
    p = c.platform
    source = p.repo.read(p.scope(), "source", "plant")
    p.repo.put(p.scope(), "source", "plant", source["value"], source["version"], deleted=True)
    assert call(c, "result?id="+run["runId"]).json()["result"]["content"]["stale"]
    assert call(c, "read?kind=source&id=plant").status_code == 404
    session = call(c, "workspace?sessionId=one").json()["result"]["session"]
    assert len(session["content"]["turns"]) == 2


def test_query_limits_general_context_and_semantic_fallback(client):
    c = client
    seed(c)
    policy(c, value={"maxQueries": 1})
    r = call(c, "context", {"sessionId": "one", "query": "甲；乙", "complex": True})
    assert r.status_code == 503 and r.json()["error"] == "QUERY_BUDGET_EXCEEDED"
    policy(c, value={"mode": "general"}, revision=1)
    assert not call(c, "context", {"sessionId": "one", "query": "天气"}).json()["result"]["sources"]
    r = call(c, "find", {"query": "光合作用", "mode": "vector", "allowApi": True}).json()["result"]
    assert r["route"] == "lexical-fallback" and "EMBEDDING_UNAVAILABLE" in r["warnings"]
    assert r["items"]
    assert call(c, "find", {"query": "光合作用", "mode": "vector"}).status_code == 400


@pytest.mark.parametrize("failure", [False, True])
def test_controlled_model_one_slot_usage_and_unknown_no_replay(tmp_path, failure):
    def upstream(request):
        if failure:
            raise httpx.ReadError("controlled unknown")
        payload = json.loads(request.content)
        source = json.loads(payload["messages"][-1]["content"])["sources"][0]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"claims": [{"text": source["quote"], "evidence": [{"sourceId": source["id"], "quote": source["quote"]}]}]})}}], "usage": {"total_tokens": 14}})
    config = Config(data_dir=tmp_path/"api", api_key="controlled-only", api_slots=1)
    app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)))
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.platform, c.platform_headers = app.state.platform, {"X-Xueya-Token": c.get("/api/platform/bootstrap").json()["token"]}
        seed(c)
        policy(c)
        run, job = ask(c, allowApi=True)
        assert job["status"] == ("unknown" if failure else "succeeded")
        assert c.platform.db.one("SELECT count(*) n FROM invocations")["n"] == 1
        assert c.platform.db.one("SELECT status FROM invocations")["status"] == ("unknown" if failure else "succeeded")
        if failure:
            r = c.post("/api/platform/jobs/retry", headers=c.platform_headers, json={"id": run["jobId"]})
            assert r.status_code == 400


def test_course_isolation_and_free_search_large_library(client):
    c = client
    seed(c, text="needle "*60000)
    c.platform.repo.ensure_course(c.platform.user_id, {"id": "other", "name": "其他"})
    assert call(c, "find", {"query": "needle"}, course="other").json()["result"]["items"] == []
    assert call(c, "find", {"query": "needle"}).json()["result"]["items"]
    assert call(c, "read?kind=source&id=plant", course="other").status_code == 404


def test_stale_learning_content_filter_and_calendar_validation(client):
    c = client
    seed(c)
    artifact(c, text="关于光合作用的旧理解", extra={"evidence": [{"sourceId": "plant", "documentId": "doc-plant", "version": "0", "quote": "光合作用"}]})
    assert not call(c, "find", {"query": "光合作用", "types": ["note"]}).json()["result"]["items"]
    result = call(c, "find", {"query": "光合作用", "types": ["note"], "effectiveOnly": False}).json()["result"]
    assert result["items"][0]["needsReview"]
    assert call(c, "find", {"query": "x", "afterTime": "2026-99-99"}).status_code == 400
    assert call(c, "find", {"query": "x", "types": [{}]}).status_code == 400
