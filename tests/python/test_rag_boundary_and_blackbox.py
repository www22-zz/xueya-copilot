"""Unit tests for RAG Platform Boundary & Blackbox Protection (Specs 3.5 - 3.9).
No external network or billed calls.
"""
import io
import pytest
from fastapi.testclient import TestClient

from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.common import Scope
from backend.xueya.rag_http import install_rag
from backend.xueya.rag_service import RagService
from backend.xueya.rag_scope_adapter import (
    ScopeAdapter,
    is_platform_document,
    is_platform_source,
    public_source_projection,
    sanitize_event,
    sanitize_tool_call,
)


def test_public_source_projection_protects_platform_quotes():
    platform_source = {
        "id": "chunk-test1",
        "title": "数据结构与算法",
        "location": "第1章第2节",
        "quote": "栈是只能在表尾进行插入和删除操作的线性表。",
        "documentId": "doc-preset",
        "version": 1,
        "isPlatform": True,
    }
    projected = public_source_projection(platform_source)
    assert projected["id"] == "chunk-test1"
    assert projected["title"] == "数据结构与算法"
    assert projected["location"] == "第1章第2节"
    assert projected["isPlatform"] is True
    # Quote MUST be completely stripped for platform sources
    assert "quote" not in projected

    # Personal source retains quote if provided
    personal_source = {
        "id": "chunk-personal1",
        "title": "我的复习笔记",
        "location": "第1页",
        "quote": "这是我个人的复习重点。",
        "documentId": "doc-mine",
        "version": 1,
        "isPlatform": False,
    }
    projected_personal = public_source_projection(personal_source)
    assert projected_personal["quote"] == "这是我个人的复习重点。"
    assert projected_personal["isPlatform"] is False


def test_sanitize_tool_call_and_events():
    tool_call = {
        "id": "1",
        "tool": "search_materials",
        "arguments": {"query": "栈"},
        "status": "completed",
        "data": {
            "sources": [
                {
                    "id": "chunk-preset",
                    "title": "教材第3章",
                    "location": "第90页",
                    "quote": "绝密正文不得输出",
                    "isPlatform": True,
                }
            ]
        }
    }
    sanitized = sanitize_tool_call(tool_call)
    assert "quote" not in sanitized["data"]["sources"][0]

    event = {
        "type": "done",
        "ok": True,
        "answer": "栈是先进后出结构",
        "sources": ["chunk-preset"],
        "sourceObjects": [
            {
                "id": "chunk-preset",
                "title": "教材第3章",
                "location": "第90页",
                "quote": "绝密正文不得输出",
                "isPlatform": True,
            }
        ],
        "toolCalls": [tool_call],
        "claims": [
            {
                "text": "栈是先进后出",
                "evidence": [{"sourceId": "chunk-preset", "quote": "绝密正文不得输出"}]
            }
        ]
    }
    sanitized_event = sanitize_event(event)
    assert "quote" not in sanitized_event["sourceObjects"][0]
    assert "quote" not in sanitized_event["toolCalls"][0]["data"]["sources"][0]
    assert "quote" not in sanitized_event["claims"][0]["evidence"][0]


def test_platform_blackbox_http_endpoints(tmp_path, http_root):
    app = install_rag(create_app(Config(root=http_root, data_dir=tmp_path / "http-data")))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        token = client.get("/api/platform/bootstrap").json()["token"]
        headers = {"X-Xueya-Token": token}

        # 1. Upload a platform document
        rag = app.state.rag
        scope = app.state.platform.scope("course-default")
        # Ingest a platform document
        import asyncio
        from tests.python.test_rag import completed
        job = rag.upload(scope, b"# Preset\nPlatform textbook text.", "week1_intro.md", "idemp-preset")
        asyncio.run(completed(app.state.platform, job))
        doc_id = app.state.platform.repo.all(scope, "document")[-1]["id"]

        # Mark document as platform
        saved_doc = app.state.platform.repo.read(scope, "document", doc_id)
        app.state.platform.repo.put(scope, "document", doc_id, {**saved_doc["value"], "isPlatform": True}, saved_doc["version"])

        # 2. Test original download -> Should return 403 Forbidden!
        res_orig = client.get(f"/api/platform/rag/original?documentId={doc_id}", headers=headers)
        assert res_orig.status_code == 403
        assert res_orig.json().get("error") == "FORBIDDEN_PLATFORM_DOCUMENT"

        # 3. Test export -> Should return empty chunks and protected=True
        res_exp = client.get(f"/api/platform/rag/export?documentId={doc_id}", headers=headers)
        assert res_exp.status_code == 200
        assert res_exp.json().get("protected") is True
        assert res_exp.json().get("chunks") == []

        # A source without its own isPlatform flag still inherits protection
        # from the server-owned document, through read/list/search projections.
        source = app.state.platform.repo.all(scope, 'source')[0]
        read = client.get('/api/platform/rag/read',params={'sourceId':source['id']},headers=headers)
        assert read.json()['protected'] is True
        assert 'Platform textbook text.' not in read.text
        entities=client.get('/api/platform/entities?kind=source',headers=headers)
        assert 'Platform textbook text.' not in entities.text
        from backend.xueya.rag_scope_adapter import public_api_value
        payload={'type':'done','answer':'这是AI整理的解释','sourceObjects':[{'id':source['id'],'quote':'Platform textbook text.'}],
                 'toolCalls':[{'data':{'source':{'id':source['id'],'quote':'Platform textbook text.'}}}]}
        sanitized=public_api_value(app.state.platform,payload)
        assert sanitized['answer']==payload['answer']
        assert 'Platform textbook text.' not in __import__('json').dumps(sanitized)

        # 4. Now upload a user's personal document
        personal_job = rag.upload(scope, b"# Personal\nMy private notes.", "personal_notes.md", "idemp-personal")
        asyncio.run(completed(app.state.platform, personal_job))
        personal_id = next(d["id"] for d in app.state.platform.repo.all(scope, "document") if d["name"] == "personal_notes.md")

        # Personal document download MUST be allowed
        res_pers = client.get(f"/api/platform/rag/original?documentId={personal_id}", headers=headers)
        assert res_pers.status_code == 200
        assert b"My private notes" in res_pers.content
