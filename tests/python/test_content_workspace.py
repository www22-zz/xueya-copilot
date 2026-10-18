"""G3 author integration tests; temporary SQLite and controlled model responses only."""
import asyncio
import json
import time
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider


def seed(client, course="course-default", sid="original", text="光合作用发生在叶绿体。"):
    p = client.platform
    scope = p.scope(course)
    p.repo.put(scope, "source", sid, {"id": sid, "documentId": "doc-"+sid, "title": "植物资料", "quote": text, "location": "原文第1段"})


def call(c, path, body=None, course="course-default"):
    result = c.request("POST" if body is not None else "GET", "/api/learning/content/"+path+"?courseId="+course,
                       headers=c.platform_headers, **({"json": body} if body is not None else {}))
    return result


def adopted(c, preview, *, operation=None, status=200):
    r = c.post("/api/learning/draft/adopt", headers=c.platform_headers,
               json={"draftId": preview["draftId"], "confirmed": True, "operationId": operation or str(uuid4())})
    assert r.status_code == status, r.text
    return r.json()


def wait_job(c, job_id):
    for _ in range(300):
        row = c.get("/api/platform/jobs/status?id="+job_id, headers=c.platform_headers).json()["job"]
        if row["status"] in ("succeeded", "unknown", "failed", "cancelled"):
            return row
        time.sleep(.02)
    pytest.fail("job timeout")


def run_template(c, key="run1", **extra):
    response = call(c, "run", {"templateId": "builtin-guide", "templateRevision": 1, "operationId": key, **extra})
    assert response.status_code == 200, response.text
    return response.json()["result"]["items"]


def test_catalog_template_preview_adopt_edit_cas_and_scope(client):
    c = client
    assert len(call(c, "workspace").json()["result"]["templates"]) == 7
    body = {"id": "my-template", "content": {"title": "植物导读", "goal": "理解能量", "prompt": "保留依据", "subject": "生物"}}
    preview = call(c, "template/preview", body).json()["result"]
    assert len(call(c, "workspace").json()["result"]["templates"]) == 7
    adopted(c, preview)
    assert len(call(c, "workspace").json()["result"]["templates"]) == 8
    assert call(c, "template/preview", {**body, "expectedRevision": 0}).status_code == 409
    preview = call(c, "template/preview", {**body, "expectedRevision": 1}).json()["result"]
    adopted(c, preview)
    c.platform.repo.ensure_course(c.platform.user_id, {"id": "other", "name": "其他"})
    assert len(call(c, "workspace", course="other").json()["result"]["templates"]) == 7
    assert call(c, "note/preview", {"id": "n", "text": "x", "courseId": "other"}).status_code == 403


def test_run_is_preview_only_convert_note_card_question_and_edit_history(client):
    c = client
    seed(c)
    runs = run_template(c)
    assert wait_job(c, runs[0]["jobId"])["status"] == "succeeded"
    assert not call(c, "workspace").json()["result"]["items"]
    preview = call(c, "recover-preview", {"id": runs[0]["runId"]}).json()["result"]
    result = adopted(c, preview)["result"]
    assert result["content"]["origin"] == "original-excerpt"
    assert result["content"]["template"]["revision"] == 1
    for kind in ("note", "memory-card", "question-draft"):
        r = call(c, "convert/preview", {"id": kind, "target": kind, "parentId": result["id"], "parentRevision": 1, "prompt": "光合作用在哪里？"})
        assert r.status_code == 200, r.text
        saved = adopted(c, r.json()["result"])["result"]
        assert saved["content"]["derivedFrom"] == [{"id": result["id"], "revision": 1}]
        if kind == "question-draft":
            assert saved["content"]["status"] == "candidate"
        if kind == "memory-card":
            assert saved["content"]["reviewEvents"] == []
    note = call(c, "note/preview", {"id": "note", "expectedRevision": 1, "text": "我修订了自己的理解", "pendingQuestions": "适用条件？"}).json()["result"]
    adopted(c, note)
    assert call(c, "workspace").json()["result"]["items"]
    history = c.get("/api/learning/history?id=note", headers=c.platform_headers).json()["result"]
    assert len(history["items"]) == 2
    # Running the template again makes another result, never overwriting an edited note.
    again = run_template(c, "run2")
    assert wait_job(c, again[0]["jobId"])["status"] == "succeeded"
    note = next(a for a in call(c, "workspace").json()["result"]["items"] if a["id"] == "note")
    assert note["content"]["text"] == "我修订了自己的理解" and note["revision"] == 2


def test_source_changes_flag_transitive_impacts_and_block_new_adoption(client):
    c = client
    seed(c)
    runs = run_template(c)
    wait_job(c, runs[0]["jobId"])
    preview = call(c, "recover-preview", {"id": runs[0]["runId"]}).json()["result"]
    parent = adopted(c, preview)["result"]
    converted = call(c, "convert/preview", {"id": "note", "target": "note", "parentId": parent["id"], "parentRevision": 1}).json()["result"]
    adopted(c, converted)
    p = c.platform
    p.repo.put(p.scope(), "source", "original", {"id": "original", "documentId": "doc-original", "quote": "已修正的定义", "title": "资料"}, 1)
    impacts = call(c, "impacts").json()["result"]["items"]
    assert all(i["status"] == "needs_review" for i in impacts if i["id"] in (parent["id"], "note"))
    assert call(c, "recover-preview", {"id": runs[0]["runId"]}).status_code == 409
    assert adopted(c, converted, status=409)["error"] == "STALE_EVIDENCE"
    assert any(a["id"] == "note" for a in call(c, "workspace").json()["result"]["items"])


def test_legacy_and_personal_notes_not_promoted_to_original_evidence(client):
    c = client
    value = call(c, "legacy/preview", {"id": "old-note", "title": "旧笔记", "text": "个人猜想"}).json()["result"]
    note = adopted(c, value)["result"]
    assert note["content"]["origin"] == "legacy-untracked"
    r = call(c, "convert/preview", {"id": "bad-card", "parentId": "old-note", "parentRevision": 1, "target": "memory-card", "prompt": "猜想？"})
    assert r.status_code == 400 and r.json()["error"] == "TEXTBOOK_EVIDENCE_REQUIRED"


def test_batch_each_document_independent_and_idempotent(client):
    c = client
    seed(c)
    seed(c, sid="second", text="光反应产生 ATP。")
    runs = run_template(c, batch=True)
    assert len(runs) == 2 and len({r["jobId"] for r in runs}) == 2
    assert run_template(c, batch=True)[0]["runId"] == runs[0]["runId"]
    assert all(wait_job(c, r["jobId"])["status"] == "succeeded" for r in runs)
    assert call(c, "run", {"templateId": "builtin-guide", "operationId": "empty", "selection": {"documentIds": []}}).status_code == 400


@pytest.mark.parametrize("invalid", [True, False])
def test_controlled_model_quality_and_paid_unknown_are_separate(tmp_path, invalid):
    def upstream(request):
        if invalid:
            raise httpx.ReadError("controlled unknown outcome")
        payload = json.loads(request.content)
        source = json.loads(payload["messages"][-1]["content"])["materials"][0]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"claims": [{"text": source["quote"], "evidence": [{"sourceId": source["id"], "quote": source["quote"]}]}]})}}], "usage": {"total_tokens": 12}})
    config = Config(data_dir=tmp_path/"controlled", api_key="controlled-only")
    app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)))
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.platform, c.platform_headers = app.state.platform, {"X-Xueya-Token": c.get("/api/platform/bootstrap").json()["token"]}
        seed(c)
        assert call(c, "run", {"templateId": "builtin-guide", "operationId": "denied"}).status_code == 400
        run = run_template(c, allowApi=True)[0]
        state = wait_job(c, run["jobId"])
        persisted = call(c, "workspace").json()["result"]["runs"][0]["content"]
        assert persisted["status"] == ("unknown" if invalid else "awaiting_confirmation")
        assert c.platform.db.one("SELECT count(*) n FROM invocations")["n"] == 1
        assert c.platform.db.one("SELECT status FROM invocations")["status"] == ("unknown" if invalid else "succeeded")
        if invalid:
            # Generic queue retry must never replay the paid operation.
            response = c.post("/api/platform/jobs/retry", headers=c.platform_headers, json={"id": run["jobId"]})
            assert response.status_code == 400
