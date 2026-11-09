"""Mind-map export tests: tree shape, XMind Zen archive, FreeMind fallback, errors.

The XMind client itself is not available in this environment, so the workbook is
validated structurally (ZIP entries + JSON/XML payloads) as documented in
``backend/xueya/learning_map.py``. No model/provider is configured or called.
"""
from __future__ import annotations

import io
import json
import secrets
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from backend.xueya import learning_map
from backend.xueya.app import create_app
from backend.xueya.common import AppError
from backend.xueya.config import Config
from backend.xueya.platform import Platform
from backend.xueya.study_space_service import StudySpaceService


# ---------------------------------------------------------------------------
# Fixtures: a stored-plan-shaped value and a minimal host for direct dispatch.
# ---------------------------------------------------------------------------

def stored_plan():
    return {
        "id": "plan-test0001",
        "title": "数据结构冲刺 14 天",
        "goal": "掌握树与图的核心算法，并完成配套练习。",
        "difficulty": "进阶",
        "status": "draft",
        "startDate": "2026-11-09",
        "endDate": "2026-11-22",
        "daysCount": 14,
        "dailyMinutes": 60,
        "restDays": [7],
        "subjects": ["数据结构"],
        "explanation": "按阶段推进，先巩固再强化。",
        "learningRoute": {
            "phases": [{
                "id": "phase-1", "title": "基础巩固",
                "startDate": "2026-11-09", "endDate": "2026-11-12", "completed": True,
                "stages": [{
                    "id": "stage-1", "title": "树的性质",
                    "startDate": "2026-11-09", "endDate": "2026-11-10",
                    "completed": True, "minutes": 60, "questionCount": 3,
                    "nodes": [
                        {"id": "node-1", "title": "二叉树遍历与性质", "date": "2026-11-09",
                         "minutes": 30, "difficulty": "中等", "completed": True,
                         "questions": [{"id": "q1"}, {"id": "q2"}],
                         "requiredCount": 2, "submittedCount": 2, "readiness": "ready"},
                        {"id": "node-2", "title": "平衡二叉树", "date": "2026-11-10",
                         "minutes": 30, "difficulty": "中等", "completed": False,
                         "questions": [], "requiredCount": 1, "submittedCount": 0,
                         "readiness": "materials-needed"},
                    ],
                }],
            }],
        },
        "days": [{
            "date": "2026-11-09", "isRestDay": False, "budgetMinutes": 60,
            "tasks": [{"id": "task-1", "title": "二叉树遍历", "phase": "基础巩固",
                       "minutes": 30, "completed": True, "resource": {"type": "question"}}],
        }, {
            "date": "2026-11-10", "isRestDay": False, "budgetMinutes": 60,
            "tasks": [{"id": "task-2", "title": "平衡二叉树", "phase": "基础巩固",
                       "minutes": 30, "completed": False, "resource": {"type": "self-study"}}],
        }],
        "frameworkCoverage": {"representedPhases": 1, "totalPhases": 2,
                              "representedTasks": 1, "totalTasks": 2, "partial": True},
    }


FRAMEWORK = {
    "title": "树的知识框架",
    "nodes": [
        {"id": "root", "label": "树", "parentId": None, "description": "树结构总览"},
        {"id": "c1", "label": "遍历", "parentId": "root", "description": "前序/中序/后序"},
        {"id": "c2", "label": "平衡", "parentId": "root", "description": "AVL 与红黑树"},
    ],
}


class FakeHost:
    def __init__(self, platform):
        self.p = platform
        self.app = SimpleNamespace(state=SimpleNamespace(account=None))


class FakeRequest:
    def __init__(self, method="GET", query=None, payload=None):
        self.method = method
        self.query_params = query or {}
        self._payload = payload

    async def stream(self):
        if self._payload is not None:
            yield self._payload


def all_nodes(node):
    yield node
    for child in node.get("children") or []:
        yield from all_nodes(child)


# ---------------------------------------------------------------------------
# Tree shape.
# ---------------------------------------------------------------------------

def test_build_tree_matches_route_and_plan_fields():
    tree = learning_map.build_tree(stored_plan(), source="plan", framework=FRAMEWORK)
    assert tree["kind"] == "study-plan-mindmap"
    assert tree["planId"] == "plan-test0001"
    assert tree["title"] == "数据结构冲刺 14 天"
    assert tree["truncated"] is False
    assert tree["stats"]["phases"] == 1
    assert tree["stats"]["stages"] == 1
    assert tree["stats"]["tasks"] == 2
    assert tree["stats"]["completed"] == 1
    assert tree["stats"]["questionRefs"] == 2
    assert tree["stats"]["knowledgePoints"] == 3
    assert set(tree["limits"]) >= {"maxNodes", "maxTitleChars", "maxDetailChars", "maxPhases", "maxStages"}

    root = tree["root"]
    assert root["title"] == "数据结构冲刺 14 天"
    phase = next(child for child in root["children"] if child["kind"] == "phase")
    assert (phase["title"], phase["completed"]) == ("基础巩固", True)
    stage = phase["children"][0]
    assert (stage["title"], stage["completed"]) == ("树的性质", True)
    first, second = stage["children"]
    assert first["title"] == "二叉树遍历与性质"
    assert first["completed"] is True
    assert first["fields"] == {"date": "2026-11-09", "minutes": 30, "difficulty": "中等",
                               "questions": 2, "required": 2, "submitted": 2,
                               "unbound": False, "phase": "基础巩固"}
    assert "关联题目 2/2" in first["subtitle"]
    assert second["fields"]["unbound"] is True
    assert "未绑定本地题目" in second["subtitle"]

    info = root["children"][0]
    assert info["title"] == "计划信息"
    facts = {child["title"]: child["subtitle"] for child in info["children"]}
    assert facts["难度"] == "进阶"
    assert facts["每日可用时间"] == "60 分钟"
    assert "14 天" in facts["计划周期"]
    assert facts["固定休息日"] == "周日"

    framework = next(child for child in root["children"] if child["kind"] == "framework")
    assert framework["title"] == "树的知识框架"
    assert [child["title"] for child in framework["children"]] == ["树"]
    assert {child["title"] for child in framework["children"][0]["children"]} == {"遍历", "平衡"}
    assert "部分覆盖" in framework["subtitle"]


def test_build_tree_falls_back_to_days_without_route():
    plan = stored_plan()
    plan.pop("learningRoute")
    tree = learning_map.build_tree(plan)
    phase = next(child for child in tree["root"]["children"] if child["kind"] == "phase")
    assert phase["title"] == "基础巩固"
    titles = [node["title"] for node in phase["children"]]
    assert titles == ["二叉树遍历", "平衡二叉树"]
    assert phase["children"][0]["fields"]["date"] == "2026-11-09"
    assert phase["children"][1]["completed"] is False


def test_sanitize_draft_bounds_strings_and_lists():
    hostile = {
        "title": "目标" * 500,
        "goal": "学习" * 2000,
        "difficulty": "未知档位",
        "dailyMinutes": 99999,
        "daysCount": 99999,
        "restDays": [0, 1, 7, 9, "x"],
        "subjects": [f"学科{i}" for i in range(40)],
        "days": [{"date": "2026-13-01", "tasks": [
            {"title": "t" * 500, "phase": "p" * 500, "minutes": 99999, "completed": True},
        ]}],
        "unknown": {"nested": "ignored"},
    }
    plan = learning_map.sanitize_draft(hostile)
    assert len(plan["title"]) <= learning_map.MAX_TITLE
    assert len(plan["goal"]) <= learning_map.MAX_GOAL
    assert plan["difficulty"] == ""
    assert plan["dailyMinutes"] is None
    assert plan["daysCount"] is None
    assert plan["restDays"] == [1, 7]
    assert len(plan["subjects"]) <= 12
    assert plan["days"][0]["date"] == ""  # invalid ISO dates are dropped, not trusted
    assert plan["days"][0]["tasks"][0]["minutes"] is None
    assert "unknown" not in plan
    for bad in (None, [], "text", 42):
        with pytest.raises(AppError) as error:
            learning_map.sanitize_draft(bad)
        assert error.value.code == "INVALID_MAP_REQUEST"
    with pytest.raises(AppError):
        learning_map.sanitize_draft({"unknown": "only"})


def test_node_limit_truncates_large_plan():
    days = [{"date": "2026-11-09", "isRestDay": False, "budgetMinutes": 60,
             "tasks": [{"title": f"任务{i}-{j}", "phase": f"阶段{i}", "minutes": 30,
                        "completed": False, "resource": {"type": "self-study"}}
                       for j in range(10)]}
            for i in range(120)]
    tree = learning_map.build_tree({"title": "超大计划", "days": days})
    assert tree["truncated"] is True
    count = sum(1 for _ in all_nodes(tree["root"]))
    assert count <= learning_map.MAX_NODES + 2
    # A truncated tree still serializes into a valid workbook.
    archive = learning_map.xmind_bytes(tree)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        assert len(json.loads(bundle.read("content.json"))) == 1


# ---------------------------------------------------------------------------
# XMind Zen workbook and FreeMind fallback.
# ---------------------------------------------------------------------------

def _root_topic_tree(topic):
    children = (topic.get("children") or {}).get("attached") or []
    return [topic["title"], [_root_topic_tree(child) for child in children]]


def test_xmind_archive_is_xmind_zen_workbook():
    tree = learning_map.build_tree(stored_plan(), framework=FRAMEWORK)
    archive = learning_map.xmind_bytes(tree)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        assert set(bundle.namelist()) == {"content.json", "metadata.json", "manifest.json", "content.xml"}
        for info in bundle.infolist():
            assert info.compress_type == zipfile.ZIP_STORED
        content_raw = bundle.read("content.json")
        assert not content_raw.startswith(b"\xef\xbb\xbf")
        content = json.loads(content_raw.decode("utf-8"))
        metadata = json.loads(bundle.read("metadata.json").decode("utf-8"))
        manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
        ET.fromstring(bundle.read("content.xml"))

    assert isinstance(content, list) and len(content) == 1
    sheet = content[0]
    assert sheet["class"] == "sheet"
    assert sheet["title"] == tree["title"]
    assert sheet["rootTopic"]["class"] == "topic"
    assert sheet["rootTopic"]["structureClass"] == "org.xmind.ui.logic.right"
    assert metadata["dataStructureVersion"] == "2"
    assert metadata["layoutEngineVersion"] == "3"
    assert isinstance(metadata["creator"]["name"], str)
    assert manifest == {"file-entries": {"content.json": {}, "metadata.json": {}, "content.xml": {}}}

    ids = []

    def walk(topic):
        ids.append(topic["id"])
        for child in (topic.get("children") or {}).get("attached") or []:
            walk(child)
    walk(sheet["rootTopic"])
    assert len(ids) == len(set(ids))

    titles = _root_topic_tree(sheet["rootTopic"])
    assert titles[0] == tree["title"]
    child_titles = [child[0] for child in titles[1]]
    assert "计划信息" in child_titles and "基础巩固" in child_titles and "树的知识框架" in child_titles
    # Node titles, notes (date/minutes/difficulty) and the completion label are preserved.
    flat = json.dumps(content, ensure_ascii=False)
    assert "二叉树遍历与性质" in flat
    assert "2026-11-09 · 30 分钟 · 中等 · 已完成 · 关联题目 2/2" in flat
    assert "已完成" in flat
    assert "未绑定本地题目" in flat


def test_xmind_ids_stay_unique_for_duplicate_titles():
    tree = learning_map.build_tree({"title": "重复节点", "days": [{
        "date": "2026-11-09", "tasks": [{"title": "同名任务", "phase": "阶段", "minutes": 10},
                                       {"title": "同名任务", "phase": "阶段", "minutes": 10}]}]})
    with zipfile.ZipFile(io.BytesIO(learning_map.xmind_bytes(tree))) as bundle:
        content = json.loads(bundle.read("content.json"))
    ids = []

    def walk(topic):
        ids.append(topic["id"])
        for child in (topic.get("children") or {}).get("attached") or []:
            walk(child)
    walk(content[0]["rootTopic"])
    assert len(ids) == len(set(ids))


def test_freemind_fallback_is_valid_xml():
    tree = learning_map.build_tree(stored_plan(), framework=FRAMEWORK)
    raw = learning_map.mm_bytes(tree)
    assert raw.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(raw.decode("utf-8"))
    assert root.tag == "map"
    nodes = root.findall("node")
    assert len(nodes) == 1
    assert nodes[0].get("TEXT") == tree["title"]
    texts = [node.get("TEXT") for node in root.iter("node")]
    assert "计划信息" in texts and "二叉树遍历与性质" in texts
    images = [element for element in root.iter() if element.tag == "richcontent"]
    assert images and images[0].get("TYPE") == "NOTE"
    note_text = "".join(element.text or "" for element in root.iter() if element.tag == "p")
    assert "2026-11-09 · 30 分钟 · 中等 · 已完成 · 关联题目 2/2" in note_text


def test_download_name_is_bounded_and_attachment_safe():
    tree = learning_map.build_tree({"title": '非法/名称:带*字符?"<>| ' * 20})
    name = learning_map._download_name(tree, "xmind")
    assert name.endswith(".xmind")
    assert not any(character in name for character in '/:*?"<>|')
    assert len(name) <= 70


# ---------------------------------------------------------------------------
# Dispatch contract (direct) and HTTP mounting.
# ---------------------------------------------------------------------------

def make_platform():
    return Platform(_scratch("platform") / "data")


def make_plan(platform, account="local"):
    service = StudySpaceService(platform)
    return service.create_plan_draft(account, {
        "title": "操作系统 7 天", "goal": "复习进程与内存管理", "dailyMinutes": 30,
        "daysCount": 7, "subjects": ["操作系统"], "restDays": [6, 7], "difficulty": "基础",
    })


async def test_dispatch_tree_export_and_mm():
    platform = make_platform()
    try:
        await _dispatch_tree_export_and_mm(platform)
    finally:
        await platform.close()


async def _dispatch_tree_export_and_mm(platform):
    host = FakeHost(platform)
    plan = make_plan(platform)

    tree_response = await learning_map.dispatch(
        "tree", FakeRequest("GET", {"planId": plan["id"]}), "course-default", host)
    assert tree_response["ok"] is True
    assert tree_response["tree"]["planId"] == plan["id"]
    assert tree_response["tree"]["source"] == "plan"
    assert tree_response["tree"]["stats"]["tasks"] >= 1

    draft_response = await learning_map.dispatch(
        "tree", FakeRequest("POST", payload=json.dumps({"draft": stored_plan()}).encode()),
        "course-default", host)
    assert draft_response["tree"]["source"] == "draft"
    assert draft_response["tree"]["title"] == "数据结构冲刺 14 天"

    for operation, extension, media_type in (
        ("export", ".xmind", learning_map.XMindMediaType),
        ("xmind", ".xmind", learning_map.XMindMediaType),
        ("mm", ".mm", learning_map.FreeMindMediaType),
    ):
        response = await learning_map.dispatch(
            operation, FakeRequest("POST", payload=json.dumps({"planId": plan["id"]}).encode()),
            "course-default", host)
        assert response.headers["content-type"].startswith(media_type)
        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment;")
        assert "filename*=UTF-8''" in disposition
        assert extension in disposition
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"


async def test_dispatch_errors_do_not_leak_other_accounts():
    platform = make_platform()
    try:
        await _dispatch_errors_do_not_leak_other_accounts(platform)
    finally:
        await platform.close()


async def _dispatch_errors_do_not_leak_other_accounts(platform):
    host = FakeHost(platform)
    local_plan = make_plan(platform, "local")
    alice_plan = make_plan(platform, "alice")
    assert alice_plan["id"] != local_plan["id"]

    with pytest.raises(AppError) as missing:
        await learning_map.dispatch(
            "tree", FakeRequest("GET", {"planId": "plan-does-not-exist"}), "course-default", host)
    assert missing.value.code == "PLAN_NOT_FOUND"

    # The request account ("local") must not be able to read alice's plan.
    with pytest.raises(AppError) as forbidden:
        await learning_map.dispatch(
            "tree", FakeRequest("GET", {"planId": alice_plan["id"]}), "course-default", host)
    assert forbidden.value.code == "PLAN_NOT_FOUND"

    with pytest.raises(AppError) as invalid:
        await learning_map.dispatch(
            "tree", FakeRequest("POST", payload=b"{}"), "course-default", host)
    assert invalid.value.code == "INVALID_MAP_REQUEST"

    with pytest.raises(AppError) as method:
        await learning_map.dispatch(
            "export", FakeRequest("GET", {"planId": local_plan["id"]}), "course-default", host)
    assert method.value.code == "METHOD_NOT_ALLOWED"

    assert await learning_map.dispatch("unknown", FakeRequest("GET"), "course-default", host) is None


# ---------------------------------------------------------------------------
# HTTP mounting through /api/learning/space/workbench/map/*
# ---------------------------------------------------------------------------

# The shared sandbox on this host cannot enumerate directories created with the
# restrictive mode pytest's tmp_path uses, so these tests build their scratch
# paths with the default mode under the git-ignored test-results directory.
SCRATCH = Path(__file__).resolve().parents[1] / "test-results" / "planmap-tests"


def _scratch(name):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / f"{name}-{secrets.token_hex(4)}"
    path.mkdir()
    return path


@pytest.fixture(scope="module")
def http_root():
    root = _scratch("http-root")
    project = Path(__file__).resolve().parents[1]
    for directory in ("frontend", "shared"):
        shutil.copytree(project / directory, root / directory)
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def client(http_root):
    data_dir = _scratch("data")
    app = create_app(Config(root=http_root, data_dir=data_dir))
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        test_client.platform = app.state.platform
        test_client.token_headers = {"X-Xueya-Token": test_client.get("/api/platform/bootstrap").json()["token"]}
        yield test_client
    shutil.rmtree(data_dir, ignore_errors=True)


def test_http_tree_export_and_errors(client):
    plan = make_plan(client.platform)
    headers = client.token_headers

    tree = client.get("/api/learning/space/workbench/map/tree", params={"planId": plan["id"]}, headers=headers)
    assert tree.status_code == 200, tree.text
    value = tree.json()
    assert value["ok"] is True
    assert value["tree"]["planId"] == plan["id"]

    export = client.post("/api/learning/space/workbench/map/export", headers=headers, json={"planId": plan["id"]})
    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith(learning_map.XMindMediaType)
    assert "attachment" in export.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(export.content)) as bundle:
        content = json.loads(bundle.read("content.json"))
        assert content[0]["rootTopic"]["title"] == value["tree"]["title"]

    mm = client.post("/api/learning/space/workbench/map/mm", headers=headers, json={"planId": plan["id"]})
    assert mm.status_code == 200, mm.text
    assert mm.headers["content-type"].startswith(learning_map.FreeMindMediaType)
    ET.fromstring(mm.content)

    tree_without_id = client.get("/api/learning/space/workbench/map/tree", headers=headers)
    assert tree_without_id.json()["error"] == "INVALID_MAP_REQUEST"

    missing = client.get("/api/learning/space/workbench/map/tree",
                         params={"planId": "plan-does-not-exist"}, headers=headers)
    assert missing.status_code == 404
    assert missing.json()["error"] == "PLAN_NOT_FOUND"

    unauth = client.get("/api/learning/space/workbench/map/tree", params={"planId": plan["id"]})
    assert unauth.status_code == 403
    assert unauth.json()["error"] == "AUTH_REQUIRED"
