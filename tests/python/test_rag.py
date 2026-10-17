"""B author tests: real CPU formats + controlled upstream API, never billed calls."""
import asyncio
import io
import json
import zipfile
from dataclasses import replace

import httpx
import pytest
from docx import Document
from docx.oxml import OxmlElement
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.xueya.app import create_app
from backend.xueya.common import AppError
from backend.xueya.config import Config
from backend.xueya.platform import Platform
from backend.xueya.rag import parse_document
from backend.xueya.rag_api import ApiSettings, EmbeddingProvider, OcrProvider, RerankProvider
from backend.xueya.rag_http import install_rag
from backend.xueya.rag_parse import structured_chunks
from backend.xueya.rag_search import compress, exact, lexical, normalize, rewrite_query
from backend.xueya.rag_service import RagService


async def completed(p, job):
    p.jobs.stopped = False
    for _ in range(500):
        await p.jobs.tick()
        state = p.jobs.get(job["id"], p.user_id)
        if state["status"] in ("succeeded", "failed", "cancelled", "unknown"):
            task = p.jobs.active.get(job["id"])
            if task:
                await task
            return state
        await asyncio.sleep(.02)
    pytest.fail("job did not complete")


async def ingest(rag, text, name="course.md", *, key="upload", previous=None):
    job = rag.upload(rag.p.scope(), text.encode(), name, key, previous_document_id=previous)
    result = await completed(rag.p, job)
    assert result["status"] == "succeeded", result
    return rag.document(rag.p.scope(), result["result"]["documentId"])


def blank_pdf():
    writer, output = PdfWriter(), io.BytesIO()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    return output.getvalue()


def embedding(rag, *, revision="1", handler=None):
    calls = []
    def upstream(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if handler:
            return handler(request, payload)
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [1, 0] if "光合" in t or "photosynthesis" in t else [0, 1]} for i, t in enumerate(payload["input"])], "usage": {"total_tokens": 8}})
    rag.embedding = EmbeddingProvider(rag.p, ApiSettings(key="controlled-test", model="controlled-embedding", dimension=2, revision=revision), transport=httpx.MockTransport(upstream))
    return calls


def test_structure_offsets_atomic_blocks_and_revision_ids():
    raw = "# 树\n\nBST 查找。\n\n| 名称 | 复杂度 |\n| --- | --- |\n| 查找 | O(h) |\n\n```python\nprint('树')\n```\n\n$$x^2+y^2$$\n"
    parsed = parse_document(raw.encode(), "md")
    assert {b["type"] for b in parsed["blocks"]} >= {"heading", "paragraph", "table", "code", "formula"}
    for b in parsed["blocks"]:
        assert parsed["text"][b["start"]:b["end"]] == b["text"]
        assert b["page"] is None and b["bbox"] is None
    doc = {"id": "course", "name": "course.md", "contentRevision": 1}
    chunks = structured_chunks(parsed, doc)
    assert chunks == structured_chunks(parsed, doc)
    assert {s["id"] for s in chunks}.isdisjoint(s["id"] for s in structured_chunks(parsed, {**doc, "contentRevision": 2}))
    assert chunks[-1]["sectionPath"] == ["树"]


def test_real_docx_heading_table_formula_and_no_invented_pages():
    doc, output = Document(), io.BytesIO()
    doc.add_heading("植物", level=1)
    doc.add_paragraph("叶绿体执行光合作用。")
    table = doc.add_table(rows=2, cols=2)
    for row, values in zip(table.rows, [["名称", "位置"], ["光反应", "类囊体"]]):
        for cell, value in zip(row.cells, values):
            cell.text = value
    paragraph = doc.add_paragraph()
    math_node, run, text = OxmlElement("m:oMath"), OxmlElement("m:r"), OxmlElement("m:t")
    text.text = "x+y"
    run.append(text)
    math_node.append(run)
    paragraph._p.append(math_node)
    doc.save(output)
    parsed = parse_document(output.getvalue(), "docx")
    assert parsed["blocks"][0]["type"] == "heading"
    assert any(b["type"] == "table" for b in parsed["blocks"])
    assert parsed["blocks"][-1]["type"] == "formula" and "x+y" in parsed["blocks"][-1]["mathXml"][0]
    assert "名称 | 位置\n光反应 | 类囊体" in parsed["text"]
    assert all(p["number"] is None for p in parsed["pages"])


def test_pptx_uses_presentation_order_not_filename_order():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        z.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="1" r:id="r2"/><p:sldId id="2" r:id="r1"/></p:sldIdLst></p:presentation>')
        z.writestr("ppt/_rels/presentation.xml.rels", '<Relationships><Relationship Id="r1" Target="slides/slide1.xml"/><Relationship Id="r2" Target="slides/slide2.xml"/></Relationships>')
        for i in (1, 2):
            z.writestr(f"ppt/slides/slide{i}.xml", f'<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:t>slide{i}</a:t></a:r></a:p>')
    parsed = parse_document(output.getvalue(), "pptx")
    assert parsed["text"] == "slide2\nslide1"
    assert [p["number"] for p in parsed["pages"]] == [1, 2]


def test_scanned_empty_pdf_is_not_searchable_and_never_invents_text():
    parsed = parse_document(blank_pdf(), "pdf")
    assert parsed["empty"] and parsed["warnings"] == ["OCR_REQUIRED"]
    assert parsed["pages"][0]["number"] == 1 and parsed["blocks"] == []


@pytest.mark.parametrize("buffer,kind,error", [(b"\xff", "txt", "INVALID_TEXT_ENCODING"), (b"x", "pdf", "PARSE_FAILED"), (b"x", "exe", "UNSUPPORTED_DOCUMENT_TYPE"), (b"x"*1048577, "md", "FILE_TOO_LARGE")], ids=["encoding", "bad-pdf", "extension", "size"])
def test_reject_invalid_formats(buffer, kind, error):
    with pytest.raises(AppError, match=error):
        parse_document(buffer, kind)


def test_archive_bomb_and_xml_entities_rejected():
    for xml, error in [("<!DOCTYPE a><a/>", "UNSAFE_DOCUMENT_XML"), ("x"*24_000_001, "DOCUMENT_XML_TOO_LARGE")]:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", xml)
        with pytest.raises(AppError, match=error):
            parse_document(output.getvalue(), "docx")


def test_lexical_terms_followups_and_exact_baseline():
    sources = [{"id": "plant", "quote": "光合作用发生于叶绿体。", "title": "生物"}, {"id": "tree", "quote": "二叉搜索树查找与树高有关。", "title": "算法"}]
    assert lexical("BST", sources)[0][1]["id"] == "tree"
    assert lexical("photosynthesis", sources)[0][1]["id"] == "plant"
    assert lexical("火星上有几只猫", sources) == []
    history = [{"role": "user", "content": "BST查找"}, {"role": "assistant", "content": "虚构回答不能成为依据"}]
    assert rewrite_query("那复杂度呢", history) == "BST查找 那复杂度呢"
    assert rewrite_query("光合作用在哪里", history) == "光合作用在哪里"
    assert rewrite_query("那复杂度呢", history, new_topic=True) == "那复杂度呢"
    assert exact([1, 0], [([0, 1], sources[0]), ([1, 0], sources[1])])[0][1]["id"] == "tree"
    with pytest.raises(AppError, match="INVALID_EMBEDDING"):
        normalize([float("nan"), 0], 2)


def test_ingest_search_forged_citations_correction_and_delete(platform):
    async def run():
        rag, scope = RagService(platform), platform.scope()
        doc = await ingest(rag, "# 植物\n\n光合作用发生在叶绿体。\n\n光反应产生ATP。")
        result = await rag.search(scope, "photosynthesis", mode="lexical")
        assert result["status"] == "evidence_found"
        cite = result["sources"][0]
        assert rag.validate(scope, cite)
        for changes in ({"id": "forged"}, {"page": 99}, {"start": -1}, {"quote": "虚构"}, {"documentRevision": 999}, {"fileHash": "0"*64}):
            with pytest.raises(AppError):
                rag.validate(scope, {**cite, **changes})
        assert rag.context(scope, cite["id"])["parent"]["text"] == cite["quote"]
        artifact_before = rag.export(scope, doc["id"])["artifact"]
        changed = rag.correct(scope, doc["id"], doc["version"], cite["blockId"], "光合作用发生在植物的叶绿体。", "核对原件后修订")
        assert changed["contentRevision"] == 2
        with pytest.raises(AppError):
            rag.read(scope, cite["id"])
        assert rag.repo.read(scope, "artifact", doc["activeArtifact"])["value"] == artifact_before
        current = rag.document(scope, doc["id"])
        assert rag.export(scope, doc["id"])["artifact"]["correction"]["before"] == cite["quote"]
        rag.remove(scope, doc["id"], current["version"])
        assert not (await rag.search(scope, "光合作用"))["sources"]
        assert not rag.repo.all(scope, "source") and not rag.repo.all(scope, "artifact")
    asyncio.run(run())


def test_failed_replacement_keeps_previous_usable(platform):
    async def run():
        rag, scope = RagService(platform), platform.scope()
        old = await ingest(rag, "光合作用发生在叶绿体。")
        failed = rag.upload(scope, b"broken pdf", "bad.pdf", "bad", previous_document_id=old["id"])
        platform.jobs.timeout = 3
        row = platform.db.one("SELECT id FROM jobs WHERE id=?", (failed["id"],))
        platform.db.execute("UPDATE jobs SET max_attempts=1 WHERE id=?", (row["id"],))
        assert (await completed(platform, failed))["status"] == "failed"
        assert not rag.document(scope, old["id"]).get("superseded")
        assert (await rag.search(scope, "光合作用", mode="lexical"))["sources"]
        new = await ingest(rag, "光合作用由叶绿体完成。", key="new", previous=old["id"])
        assert rag.document(scope, old["id"])["superseded"]
        assert all(s["documentId"] == new["id"] for s in rag.sources(scope))
    asyncio.run(run())


def test_embedding_batch_cache_migration_usage_and_restart(platform):
    async def run():
        rag, scope = RagService(platform), platform.scope()
        calls = embedding(rag)
        doc = await ingest(rag, "光合作用发生在叶绿体。\n\n广度优先使用队列。")
        job = rag.submit(scope, "rag-index", doc["id"], "index1")
        assert (await completed(platform, job))["status"] == "succeeded"
        assert calls[0]["task"] == "retrieval.passage"
        result = await rag.search(scope, "photosynthesis", mode="vector")
        assert result["sources"][0]["quote"] == "光合作用发生在叶绿体。"
        assert calls[-1]["task"] == "retrieval.query"
        indexed = rag.document(scope, doc["id"])
        repeat = await completed(platform, rag.submit(scope, "rag-index", doc["id"], "index2"))
        assert repeat["result"]["computed"] == 0
        embedding(rag, revision="2")
        before = await rag.search(scope, "光合作用", mode="hybrid")
        assert "VECTOR_INDEX_UNAVAILABLE" in before["warnings"]
        assert (await completed(platform, rag.submit(scope, "rag-index", doc["id"], "index3")))["result"]["computed"] == 2
        assert platform.db.one("SELECT count(*) n FROM invocations WHERE status='succeeded'")["n"] == 3
        assert json.loads(platform.db.one("SELECT usage_json FROM invocations")["usage_json"])["total_tokens"] == 8
        assert indexed["embeddingIdentity"]["revision"] == "1"
        platform.repo.ensure_course(platform.user_id, {"id": "other", "name": "其他"})
        assert not (await rag.search(platform.scope("other"), "光合作用"))["sources"]
        assert not (await rag.search(scope, "光合作用", document_ids=[], mode="lexical"))["sources"]
        return doc["id"]
    document_id = asyncio.run(run())
    # Open a second host on the exact same SQLite, verifying durable artifacts/vectors.
    other = Platform(platform.data_dir, recover=False)
    try:
        rag = RagService(other)
        embedding(rag, revision="2")
        result = asyncio.run(rag.search(other.scope(), "photosynthesis", mode="vector"))
        assert result["sources"][0]["documentId"] == document_id
    finally:
        asyncio.run(other.close())


def test_unknown_paid_job_not_replayed_and_cancel_during_query(platform):
    async def run():
        rag, scope = RagService(platform), platform.scope()
        doc = await ingest(rag, "光合作用发生在叶绿体。")
        def fail(request, payload):
            raise httpx.ReadError("controlled ambiguous failure")
        calls = embedding(rag, handler=fail)
        job = rag.submit(scope, "rag-index", doc["id"], "ambiguous")
        assert (await completed(platform, job))["status"] == "unknown"
        await platform.jobs.tick()
        assert len(calls) == 1
        with pytest.raises(AppError, match="JOB_NOT_RETRYABLE"):
            platform.jobs.retry(job["id"], platform.user_id)
        assert platform.db.one("SELECT status FROM invocations")["status"] == "unknown"
        assert platform.resources.active["api"] == 0
        embedding(rag)
        assert (await completed(platform, rag.submit(scope, "rag-index", doc["id"], "fresh-explicit-request")))["status"] == "succeeded"
        entered = asyncio.Event()
        async def slow(request):
            entered.set()
            await asyncio.Event().wait()
        rag.embedding.transport = httpx.MockTransport(slow)
        task = asyncio.create_task(rag.search(scope, "光合作用"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert platform.resources.active["api"] == 0
    asyncio.run(run())


def test_delete_while_query_inflight_and_lexical_fallback(platform):
    async def run():
        rag, scope = RagService(platform), platform.scope()
        doc = await ingest(rag, "光合作用发生在叶绿体。")
        embedding(rag)
        assert (await completed(platform, rag.submit(scope, "rag-index", doc["id"], "index")))["status"] == "succeeded"
        entered, resume = asyncio.Event(), asyncio.Event()
        async def slow(request):
            entered.set()
            await resume.wait()
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 0]}]})
        rag.embedding.transport = httpx.MockTransport(slow)
        task = asyncio.create_task(rag.search(scope, "光合作用"))
        await entered.wait()
        current = rag.document(scope, doc["id"])
        rag.remove(scope, doc["id"], current["version"])
        resume.set()
        assert not (await task)["sources"]
        assert not platform.repo.all(scope, "vector")
    asyncio.run(run())


def test_controlled_ocr_pages_and_rerank(platform):
    async def run():
        rag, scope = RagService(platform), platform.scope()
        parsed_job = rag.upload(scope, blank_pdf(), "scan.pdf", "scan")
        result = await completed(platform, parsed_job)
        assert result["status"] == "succeeded"
        doc = rag.document(scope, result["result"]["documentId"])
        def ocr(request):
            payload = json.loads(request.content)
            assert payload["pages"] == [0] and payload["document"]["document_url"].startswith("data:application/pdf;base64,")
            return httpx.Response(200, json={"pages": [{"index": 0, "markdown": "# 生物\n\n光合作用发生在叶绿体。"}], "usage_info": {"pages_processed": 1}})
        rag.ocr = OcrProvider(platform, ApiSettings(key="controlled", model="controlled-ocr", base_url="https://api.mistral.ai/v1"), transport=httpx.MockTransport(ocr))
        ocr_job = rag.submit(scope, "rag-ocr", doc["id"], "ocr")
        assert (await completed(platform, ocr_job))["status"] == "succeeded"
        def rerank(request):
            payload = json.loads(request.content)
            assert payload["query"] == "光合作用"
            return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": .9}], "usage": {"total_tokens": 5}})
        rag.rerank = RerankProvider(platform, ApiSettings(key="controlled", model="controlled-rerank"), transport=httpx.MockTransport(rerank))
        evidence = await rag.search(scope, "光合作用", mode="rerank")
        assert evidence["sources"][0]["page"] == 1 and evidence["sources"][0]["confidence"] is None
        assert rag.validate(scope, evidence["sources"][0])
    asyncio.run(run())


def test_rag_http_registration_auth_scope_and_jobs(tmp_path):
    app = install_rag(create_app(Config(data_dir=tmp_path/"http")), service_factory=RagService)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        token = c.get("/api/platform/bootstrap").json()["token"]
        h = {"X-Xueya-Token": token}
        assert c.get("/api/platform/rag/capabilities").status_code == 403
        assert c.get("/api/platform/rag/capabilities", headers=h).json()["capabilities"]["inference"] == "external-api-only"
        assert c.post("/api/platform/rag/search", headers=h, json={"query": "x", "baseUrl": "https://evil.example"}).status_code == 400
        response = c.post("/api/platform/rag/upload?name=course.md", headers={**h, "Idempotency-Key": "http"}, content="光合作用发生在叶绿体。".encode())
        assert response.status_code == 200, response.text
        import time
        job = response.json()["job"]
        for _ in range(300):
            state = c.get("/api/platform/jobs/status?id="+job["id"], headers=h).json()["job"]
            if state["status"] in ("succeeded", "failed"):
                break
            time.sleep(.02)
        assert state["status"] == "succeeded", state
        evidence = c.post("/api/platform/rag/search", headers=h, json={"query": "光合作用", "mode": "lexical"}).json()["evidence"]
        assert evidence["sources"]
        source = evidence["sources"][0]
        assert c.post("/api/platform/rag/validate", headers=h, json={"citation": source}).json()["valid"]
        assert c.get("/api/platform/rag/original?documentId="+source["documentId"], headers=h).content == "光合作用发生在叶绿体。".encode()


def test_one_api_slot_does_not_double_acquire(platform):
    async def run():
        platform.resources.limits["api"] = 1
        rag = RagService(platform)
        calls = embedding(rag)
        doc = await ingest(rag, "光合作用发生在叶绿体。")
        state = await completed(platform, rag.submit(platform.scope(), "rag-index", doc["id"], "single-slot"))
        assert state["status"] == "succeeded" and len(calls) == 1
        assert platform.resources.active["api"] == 0
    asyncio.run(run())


def test_cancelled_index_keeps_prior_model_and_reuses_completed_batch(platform):
    async def run():
        rag, scope = RagService(platform), platform.scope()
        doc = await ingest(rag, "\n\n".join(f"光合作用样例{i}。" for i in range(20)))
        embedding(rag)
        assert (await completed(platform, rag.submit(scope, "rag-index", doc["id"], "first")))["status"] == "succeeded"
        entered, calls = asyncio.Event(), []
        embedding(rag, revision="2")
        async def slow(request):
            data = json.loads(request.content)
            calls.append(data)
            if len(calls) == 2:
                entered.set()
                await asyncio.Event().wait()
            return httpx.Response(200, json={"data": [{"index": i, "embedding": [1, 0]} for i, _ in enumerate(data["input"])]})
        rag.embedding.transport = httpx.MockTransport(slow)
        job = rag.submit(scope, "rag-index", doc["id"], "migration")
        await platform.jobs.tick()
        await asyncio.wait_for(entered.wait(), 3)
        platform.jobs.cancel(job["id"], platform.user_id)
        state = await completed(platform, job)
        assert state["status"] == "unknown"
        assert rag.document(scope, doc["id"])["embeddingIdentity"]["revision"] == "1"
        resumed = embedding(rag, revision="2")
        state = await completed(platform, rag.submit(scope, "rag-index", doc["id"], "explicit-resume"))
        assert state["status"] == "succeeded" and state["result"]["computed"] == 4
        assert len(resumed[0]["input"]) == 4
    asyncio.run(run())


@pytest.mark.parametrize("response", [
    {"data": [{"index": 0, "embedding": [1]}]},
    {"data": [{"index": 0, "embedding": [0, 0]}]},
    {"data": [{"index": 1, "embedding": [1, 0]}]},
    {"model": "wrong-model", "data": [{"index": 0, "embedding": [1, 0]}]}
], ids=["dimension", "zero", "wrong-index", "model"])
def test_bad_embedding_response_does_not_publish_index(platform, response):
    async def run():
        rag = RagService(platform)
        embedding(rag, handler=lambda request, data: httpx.Response(200, json=response))
        doc = await ingest(rag, "光合作用发生在叶绿体。")
        result = await completed(platform, rag.submit(platform.scope(), "rag-index", doc["id"], "bad-upstream"))
        assert result["status"] == "unknown"
        assert rag.document(platform.scope(), doc["id"])["embeddingIdentity"] is None
        assert not platform.repo.all(platform.scope(), "vector")
        assert (await rag.search(platform.scope(), "光合作用", mode="lexical"))["sources"]
    asyncio.run(run())


def test_extract_budget_preserves_table_and_conflicts_are_explicit(platform):
    async def run():
        rag = RagService(platform)
        await ingest(rag, "# 条件\n\n实验允许使用计算器。", name="allow.md", key="allow")
        await ingest(rag, "# 条件\n\n实验不允许使用计算器。", name="deny.md", key="deny")
        result = await rag.search(platform.scope(), "实验允许使用计算器吗", mode="lexical", budget=200)
        assert result["status"] == "conflict" and not result["supportChecked"]
        assert result["budget"]["used"] <= 200
        source = {"id": "table", "documentId": "d", "start": 0, "end": 100, "quote": "x"*100, "blockType": "table"}
        assert compress("x", [(1, source)], budget=32) == ([], 0)
        # Invalid budgets are rejected before invoking an external API.
        with pytest.raises(AppError, match="INVALID_BUDGET"):
            await rag.search(platform.scope(), "x", budget=-1)
    asyncio.run(run())


def test_queued_model_change_is_rejected_before_send_and_submission_is_idempotent(platform):
    async def run():
        rag, scope = RagService(platform), platform.scope()
        calls = embedding(rag)
        doc = await ingest(rag, "光合作用发生在叶绿体。")
        job = rag.submit(scope, "rag-index", doc["id"], "queued", expected_version=doc["version"])
        new_calls = embedding(rag, revision="2")
        state = await completed(platform, job)
        assert state["status"] == "failed" and state["error"] == "NOT_SENT"
        assert not calls and not new_calls
        job = rag.submit(scope, "rag-index", doc["id"], "v2", expected_version=doc["version"])
        assert (await completed(platform, job))["status"] == "succeeded"
        assert rag.submit(scope, "rag-index", doc["id"], "v2", expected_version=doc["version"])["id"] == job["id"]
        assert rag.upload(scope, "光合作用发生在叶绿体。".encode(), "course.md", "upload")["status"] == "succeeded"
    asyncio.run(run())


def test_tampered_stored_source_never_enters_retrieval_or_paid_index(platform):
    async def run():
        rag, scope = RagService(platform), platform.scope()
        doc = await ingest(rag, "光合作用发生在叶绿体。")
        source = rag.sources(scope)[0]
        platform.repo.put(scope, "source", source["id"], {**source, "quote": "伪造原文", "start": "0"}, source["version"])
        assert not rag.sources(scope)
        assert not (await rag.search(scope, "伪造原文", mode="lexical"))["sources"]
        with pytest.raises(AppError, match="SOURCE_CONTENT_MISMATCH"):
            rag.read(scope, source["id"])
        calls = embedding(rag)
        state = await completed(platform, rag.submit(scope, "rag-index", doc["id"], "tampered"))
        assert state["status"] == "unknown" and not calls
    asyncio.run(run())


def test_repeated_cancel_during_heartbeat_cleanup_releases_shared_queue_permit(platform):
    async def run():
        ready, draining = asyncio.Event(), asyncio.Event()
        async def heartbeat(job_id, execution):
            try:
                await asyncio.Event().wait()
            finally:
                draining.set()
                await asyncio.Event().wait()
        async def handler(scope, args, **ctx):
            ready.set()
            await asyncio.Event().wait()
        platform.jobs._heartbeat = heartbeat
        platform.jobs.register("rag-cancel-regression", handler)
        platform.jobs.stopped = False
        job = platform.jobs.submit(platform.user_id, {"type": "rag-cancel-regression", "courseId": "course-default", "idempotencyKey": "double-cancel", "resource": "api"})
        await platform.jobs.tick()
        await asyncio.wait_for(ready.wait(), 2)
        platform.jobs.cancel(job["id"], platform.user_id)
        await asyncio.wait_for(draining.wait(), 2)
        await platform.jobs.stop()
        assert not platform.jobs.active
        assert platform.resources.active["api"] == 0
        assert platform.jobs.get(job["id"], platform.user_id)["status"] == "unknown"
        await platform.jobs.stop()
    asyncio.run(run())
