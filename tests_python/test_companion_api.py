"""HTTP contract tests for /api/learning/space/companion/chat (isolated data dir)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.xueya.app import create_app  # noqa: E402
from backend.xueya.companion_api import install_companion  # noqa: E402
from backend.xueya.companion_knowledge import KNOWN_ROUTES, GuideKnowledge  # noqa: E402
from backend.xueya.config import Config  # noqa: E402
from tests_python.test_companion_knowledge import (  # noqa: E402
    FAKE_IDENTITY,
    _fake_vector,
    build_fake_index,
)


class FakeProvider:
    class config:
        api_key = "test-only"
        model = "fake-model"
        max_output_tokens = 4096

    def __init__(self, answer="模型回答：算法学习入口是 #space/practice/hot100。"):
        self.answer, self.calls = answer, []

    async def generate(self, messages, *, scope=None, temperature=.2, timeout=25,
                       max_output_tokens=None, thinking=None, response_format=None, model=None):
        self.calls.append("generate")
        return {"content": self.answer, "model": "fake-model", "usage": {}}

    async def stream(self, messages, *, scope=None, timeout=60, max_output_tokens=None,
                     thinking=None, response_format=None, fresh_connection=False):
        self.calls.append("stream")
        yield {"type": "content", "text": "通用回答：", "model": "fake-model"}
        yield {"type": "content", "text": "你好，今天也一起学习吧。", "model": "fake-model"}


def make_app(tmp_path: Path):
    app = create_app(Config(root=ROOT, data_dir=tmp_path / "data", api_key="", platform_enabled=True,
                            auto_import_demo=False, auto_import_corpus=False, auto_import_stack=False,
                            preserve_legacy_data=True))
    _, knowledge = build_fake_index(tmp_path)
    # The fake index lives under tmp_path/materials/system-guide; point the
    # knowledge instance at it (same class the host builds lazily).
    app_knowledge = GuideKnowledge(tmp_path, identity=FAKE_IDENTITY,
                                   embed_query=lambda text: _value(_fake_vector(text)))
    install_companion(app, knowledge=app_knowledge)
    return app


async def _value(value):
    return value


def client_for(app):
    return TestClient(app, base_url="http://127.0.0.1")


def chat(client, token, question, history=None):
    return client.post("/api/learning/space/companion/chat",
                       headers={"x-xueya-token": token},
                       json={"question": question, "history": history or [], "courseId": "course-default"})


def test_system_question_uses_guide_and_reports_links(tmp_path):
    app = make_app(tmp_path)
    with client_for(app) as client:
        token = app.state.token
        app.state.provider = FakeProvider()
        response = chat(client, token, "错题本在哪里")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        reply = body["reply"]
        assert reply["status"] == "ok" and reply["route"] == "system"
        assert reply["engine"] == "guide-rag"
        assert "#space/practice/hot100" in reply["answer"]
        assert reply["sources"], "guide snippets must be returned for the model answer"
        assert reply["links"], "real page links must be returned"
        assert all(link["hash"] in KNOWN_ROUTES for link in reply["links"])
        assert reply["modelUsed"] == "fake-model"
        assert "answerStatus" not in reply


def test_system_question_degrades_to_local_guide_when_model_unavailable(tmp_path):
    app = make_app(tmp_path)
    with client_for(app) as client:
        token = app.state.token  # default host provider has no api_key
        response = chat(client, token, "算法练习在哪里")
        reply = response.json()["reply"]
        assert reply["status"] == "ok" and reply["route"] == "system"
        assert reply["engine"] == "local-guide"
        assert "#space/" in reply["answer"]
        assert reply["sources"] and reply["links"]
        assert any("MODEL_UNAVAILABLE" in warning for warning in reply["warnings"])


def test_unknown_feature_is_not_found_without_inventing_entry(tmp_path):
    app = make_app(tmp_path)
    with client_for(app) as client:
        token = app.state.token
        app.state.provider = FakeProvider()
        response = chat(client, token, "系统有没有 AI 画图")
        reply = response.json()["reply"]
        assert reply["status"] == "not_found" and reply["route"] == "system"
        assert reply["answer"].strip()
        assert "没有找到" in reply["answer"]
        assert reply["sources"] == []
        assert all(link["hash"] in KNOWN_ROUTES for link in reply["links"])
        assert "answerStatus" not in reply


def test_general_question_uses_general_chat(tmp_path):
    app = make_app(tmp_path)
    with client_for(app) as client:
        token = app.state.token
        app.state.provider = FakeProvider()
        response = chat(client, token, "今天天气怎么样", history=[{"role": "user", "content": "你好"},
                                                                {"role": "assistant", "content": "你好呀"}])
        reply = response.json()["reply"]
        assert reply["status"] == "ok" and reply["route"] == "general"
        assert reply["engine"] == "general-chat"
        assert "你好" in reply["answer"]
        assert reply["sources"] == [] and reply["links"] == []


def test_general_question_reports_unavailable_without_network(tmp_path):
    app = make_app(tmp_path)
    with client_for(app) as client:
        token = app.state.token
        response = chat(client, token, "今天天气怎么样")
        reply = response.json()["reply"]
        assert reply["status"] == "unavailable" and reply["route"] == "general"
        assert reply["answer"].strip()
        assert reply["sources"] == [] and reply["links"] == []
        assert any("GENERAL_CHAT_UNAVAILABLE" in warning for warning in reply["warnings"])


def test_endpoint_requires_token_and_valid_question(tmp_path):
    app = make_app(tmp_path)
    with client_for(app) as client:
        unauthenticated = client.post("/api/learning/space/companion/chat", json={"question": "错题本在哪里"})
        assert unauthenticated.status_code == 403
        assert unauthenticated.json()["error"] == "AUTH_REQUIRED"
        empty = chat(client, app.state.token, "")
        assert empty.status_code == 400
        assert empty.json()["error"] == "EMPTY_QUESTION"


def test_guide_endpoint_reports_manifest(tmp_path):
    app = make_app(tmp_path)
    with client_for(app) as client:
        response = client.get("/api/learning/space/companion/guide", headers={"x-xueya-token": app.state.token})
        assert response.status_code == 200
        guide = response.json()["guide"]
        assert guide["installed"] is True and guide["loaded"] is True
        assert guide["chunks"] > 0 and guide["documents"] > 0
        assert guide["model"] == "fake-guide-model"
        assert guide["dimension"] == 8
