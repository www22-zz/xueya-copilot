"""Tests for the companion system-guide knowledge layer (chunking, retrieval, fallback).

The fake index uses tiny deterministic vectors so retrieval behaviour is tested
without any network call. One opt-in test performs a single real embedding
request only when the local .env has an embedding key.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.xueya.companion_knowledge import (  # noqa: E402
    KNOWN_ROUTES,
    GuideKnowledge,
    _content_phrases,
    _phrase_covered,
    is_system_question,
    load_index,
    make_links,
)
from scripts.build_system_guide_vectors import (  # noqa: E402
    GUIDE_DIR,
    OUT_DIR,
    SCHEMA,
    chunk_documents,
    content_hash,
    check,
)

FAKE_IDENTITY = {"provider": "https://fake.invalid/v1", "model": "fake-guide-model", "revision": "1",
                 "adapter": "fake-adapter", "dimension": 8, "normalized": True,
                 "documentTask": "text", "queryTask": "text"}


def _fake_vector(text: str, dimension: int = 8) -> list[float]:
    """Deterministic bag-of-bigrams vector; enough to separate fake documents."""
    values = [0.0] * dimension
    for index in range(len(text) - 1):
        gram = text[index:index + 2]
        if gram.strip():
            values[int(hashlib.sha256(gram.encode("utf-8")).hexdigest(), 16) % dimension] += 1.0
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def build_fake_index(tmp_path: Path, *, documents: dict[str, str] | None = None,
                     identity: dict | None = None) -> tuple[Path, GuideKnowledge]:
    """Write a tiny valid system-guide index from markdown text and load it."""
    identity = identity or FAKE_IDENTITY
    guide_dir = tmp_path / "docs" / "guide"
    guide_dir.mkdir(parents=True, exist_ok=True)
    if documents is None:
        documents = {
            "算法学习与Hot100.md": (
                "---\ntitle: 算法学习与Hot100\nmodule: 算法学习\nroutes: [\"#space/practice/hot100\"]\n---\n\n"
                "# 算法学习与Hot100\n\n## 功能名与作用\n\n算法学习提供力扣 Hot100 题库与代码练习。\n\n"
                "## 操作步骤\n\n1. 打开侧栏算法学习。\n2. 选择题目开始练习。\n\n"
                "## 涉及路由\n\n- 页面 #space/practice/hot100 与 #space/algorithms。\n"
            ),
            "错题本.md": (
                "---\ntitle: 错题本\nmodule: 题库练习\nroutes: [\"#space/review\"]\n---\n\n"
                "# 错题本\n\n## 功能名与作用\n\n错题本按资料、算法、考研三类归集错题，支持重练。\n\n"
                "## 操作步骤\n\n1. 打开侧栏错题本。\n2. 选择分类重练错题。\n\n"
                "## 涉及路由\n\n- 页面 #space/review。\n"
            ),
        }
    for name, text in documents.items():
        (guide_dir / name).write_text(text, encoding="utf-8")
    chunks, docs, duplicates = chunk_documents(guide_dir)
    rows = []
    for chunk in chunks:
        rows.append({**{key: chunk[key] for key in
                        ("id", "docPath", "docHash", "title", "module", "feature", "sectionPath",
                         "route", "steps", "text", "contentHash")},
                     "order": chunk["order"], "embedding": _fake_vector(chunk["text"])})
    index_dir = tmp_path / "materials" / "system-guide"
    index_dir.mkdir(parents=True, exist_ok=True)
    vectors = {"schema": SCHEMA, "builtAt": "2026-01-01T00:00:00+00:00", "model": identity["model"],
               "dimension": identity["dimension"], "adapter": identity["adapter"], "identity": identity,
               "chunks": rows}
    vector_bytes = json.dumps(vectors, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (index_dir / "vectors.json").write_bytes(vector_bytes)
    manifest = {
        "schema": SCHEMA, "builtAt": vectors["builtAt"], "model": identity["model"],
        "dimension": identity["dimension"], "adapter": identity["adapter"], "identity": identity,
        "vectorFile": "vectors.json", "vectorsSha256": hashlib.sha256(vector_bytes).hexdigest(),
        "vectorsBytes": len(vector_bytes), "chunkCount": len(rows), "documentCount": len(docs),
        "contentHash": hashlib.sha256(json.dumps([[row["id"], row["contentHash"]] for row in rows],
                                                 ensure_ascii=False).encode("utf-8")).hexdigest(),
        "documents": [{"path": doc["path"], "title": doc["title"], "sha256": doc["sha256"],
                       "chunkCount": len([row for row in rows if row["docPath"] == doc["path"]])}
                      for doc in docs],
        "duplicateChunks": duplicates,
    }
    (index_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    knowledge = GuideKnowledge(tmp_path, identity=identity,
                               embed_query=lambda text: _async_value(_fake_vector(text)))
    return index_dir, knowledge


async def _async_value(value):
    return value


def test_guide_chunks_carry_real_metadata():
    chunks, documents, duplicates = chunk_documents()
    assert len(documents) >= 10, "the guide must contain at least ten documents"
    assert len(chunks) >= 60
    assert duplicates == []
    hashes = [chunk["contentHash"] for chunk in chunks]
    assert len(hashes) == len(set(hashes)), "chunks must be de-duplicated by content hash"
    names = {document["path"] for document in documents}
    for chunk in chunks:
        assert chunk["docPath"] in names
        assert chunk["docPath"].endswith(".md")
        assert chunk["title"]
        assert chunk["sectionPath"] and all(isinstance(name, str) and name for name in chunk["sectionPath"])
        assert len(chunk["text"]) <= 800, chunk["docPath"]
        assert chunk["route"] == "" or chunk["route"].startswith("#space/")
        assert chunk["contentHash"] == content_hash(chunk["text"])
    featured = [chunk for chunk in chunks if chunk["route"] and chunk["steps"]]
    assert featured, "at least some chunks must expose a route and operation steps"


def test_committed_vectors_match_docs():
    """--check must pass for the committed materials/system-guide bundle (no network)."""
    assert check(GUIDE_DIR, OUT_DIR) == 0
    manifest = json.loads((OUT_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model"] == "Qwen3-VL-Embedding-8B"
    assert manifest["dimension"] == 4096
    assert manifest["adapter"] == "moark-qwen-text-v2"
    assert manifest["documentCount"] >= 10
    assert manifest["newEmbeddingRequests"] == 0 or manifest["newEmbeddingRequests"] > 0
    vectors = json.loads((OUT_DIR / "vectors.json").read_text(encoding="utf-8"))
    assert len(vectors["chunks"]) == manifest["chunkCount"]
    assert all(len(row["embedding"]) == 4096 for row in vectors["chunks"])


def test_load_index_validates_and_reads_override(tmp_path):
    index_dir, _ = build_fake_index(tmp_path)
    loaded = load_index(index_dir)
    assert loaded["dimension"] == 8
    assert len(loaded["rows"]) == loaded["manifest"]["chunkCount"]
    # A broken dimension fails loudly instead of returning garbage vectors.
    vectors = json.loads((index_dir / "vectors.json").read_text(encoding="utf-8"))
    vectors["chunks"][0]["embedding"] = vectors["chunks"][0]["embedding"][:-1]
    (index_dir / "vectors.json").write_text(json.dumps(vectors), encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_index(index_dir)
    assert "DIMENSION" in str(error.value)


def test_lexical_search_finds_known_feature_and_reports_not_found(tmp_path):
    _, knowledge = build_fake_index(tmp_path)
    knowledge.identity = None  # force the keyword fallback
    result = asyncio.run(knowledge.search("错题本怎么用"))
    assert result.status == "ok"
    assert result.mode == "lexical"
    assert any("错题本" in match["title"] or "错题" in match["title"] for match in result.matches)
    assert any("SYSTEM_GUIDE_EMBEDDING_UNAVAILABLE" in warning for warning in result.warnings)
    missing = asyncio.run(knowledge.search("系统里有没有直播课功能"))
    assert missing.status == "not_found"
    assert missing.matches == []


def test_embedding_failure_degrades_to_lexical(tmp_path):
    async def broken(_text):
        from backend.xueya.common import AppError
        raise AppError("NOT_SENT")

    knowledge = GuideKnowledge(tmp_path, identity=FAKE_IDENTITY, embed_query=broken)
    index_dir, _ = build_fake_index(tmp_path)
    result = asyncio.run(knowledge.search("算法练习在哪里"))
    assert result.status == "ok"
    assert result.mode == "lexical"
    assert any("SYSTEM_GUIDE_EMBEDDING_UNAVAILABLE" in warning for warning in result.warnings)


def test_identity_mismatch_uses_lexical(tmp_path):
    build_fake_index(tmp_path)
    other = {**FAKE_IDENTITY, "model": "another-model"}
    knowledge = GuideKnowledge(tmp_path, identity=other,
                               embed_query=lambda text: _async_value(_fake_vector(text)))
    result = asyncio.run(knowledge.search("错题本怎么用"))
    assert result.mode == "lexical"
    assert any("IDENTITY_MISMATCH" in warning for warning in result.warnings)


def test_account_override_index_is_preferred(tmp_path):
    build_fake_index(tmp_path)
    override = tmp_path / "data" / "system-guide"
    override.mkdir(parents=True)
    (override / "manifest.json").write_text((tmp_path / "materials/system-guide/manifest.json").read_text(encoding="utf-8"),
                                            encoding="utf-8")
    (override / "vectors.json").write_text((tmp_path / "materials/system-guide/vectors.json").read_text(encoding="utf-8"),
                                           encoding="utf-8")
    knowledge = GuideKnowledge(tmp_path, data_dir=tmp_path / "data", identity=None)
    assert asyncio.run(knowledge.ensure_loaded())
    assert knowledge._active_directory() == override


def test_links_only_use_real_routes():
    matches = [
        {"title": "算法学习", "route": "#space/practice/hot100", "section": "进入路径"},
        {"title": "假入口", "route": "#space/does-not-exist", "section": "x"},
        {"title": "重复的算法学习", "route": "#space/practice/hot100", "section": "y"},
        {"title": "错题本", "route": "#space/review", "section": "z"},
        {"title": "折叠参数", "route": "#space/exams/{id}", "section": "w"},
    ]
    links = make_links(matches)
    assert [link["hash"] for link in links] == ["#space/practice/hot100", "#space/review"]
    assert all(link["hash"] in KNOWN_ROUTES for link in links)


def test_compound_unknown_feature_is_not_treated_as_covered():
    """A made-up feature must not pass just because it reuses generic guide words.

    Regression for the end-to-end acceptance failure where "怎么开启全息投影学习
    模式" was answered with a real page: the phrase shares 学习/模式 with genuine
    guide text, so a single shared bigram used to count as coverage.
    """
    corpus = " ".join(chunk["text"] for chunk in chunk_documents()[0]).casefold()
    assert not _phrase_covered("开启全息投影学习模式", corpus)
    assert not _phrase_covered("全息投影", corpus)
    assert not _phrase_covered("语音克隆", corpus)
    assert not _phrase_covered("脑机接口导入知识", corpus)
    # Real features spelled naturally still pass (no over-rejection).
    for phrase in ("开启深色模式", "算法练习", "笔记导出", "导出学习记录", "个人资料库",
                   "学情分析报告", "视频课程", "模拟考试", "今日学习任务", "知识框架"):
        assert _phrase_covered(phrase, corpus), phrase
    # Sentence glue is stripped so natural requests keep their content words.
    assert _content_phrases("怎么把笔记导出成 PDF") == ["笔记导出", "PDF"]
    assert _content_phrases("算法练习题有几种难度") == ["算法练习题", "难度"]


def test_system_question_heuristics():
    assert is_system_question("算法练习在哪里")
    assert is_system_question("怎么上传资料")
    assert is_system_question("错题本怎么用")
    assert is_system_question("系统里有没有直播课功能")
    assert not is_system_question("链表是什么")
    assert not is_system_question("今天天气怎么样")
    assert _content_phrases("系统里有没有直播课功能") == ["直播课"]
    corpus = " ".join(chunk["text"] for chunk in chunk_documents()[0]).casefold()
    assert not _phrase_covered("直播课", corpus)
    assert any(_phrase_covered(phrase, corpus) for phrase in _content_phrases("算法练习在哪里"))


@pytest.mark.skipif(not (ROOT / ".env").is_file(), reason="no local .env")
def test_real_embedding_query_hits_algorithm_learning():
    """One real embedding request (opt-in via env): 4096-dim query and a real hit."""
    import os
    if os.environ.get("COMPANION_SKIP_REAL_EMBED") == "1":
        pytest.skip("real embedding disabled")
    sys.path.insert(0, str(ROOT))
    from backend.xueya.platform import Platform
    from backend.xueya.rag_http import configured_service

    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    if not env.get("RAG_EMBEDDING_API_KEY") or not env.get("RAG_EMBEDDING_MODEL"):
        pytest.skip("embedding service is not configured")

    import tempfile
    data_dir = Path(tempfile.mkdtemp(prefix="companion-real-", dir=str(ROOT / ".tmp")))
    platform = Platform(data_dir, api_slots=2, recover=False, preserve_legacy_data=True)
    try:
        service = configured_service(platform, ROOT)
        embedding = service.embedding
        assert embedding is not None
        scope = platform.scope("course-default")
        calls = {"count": 0}

        async def embed_query(text):
            calls["count"] += 1
            vectors = await embedding.embed(scope, [text], query=True)
            assert len(vectors) == 1 and len(vectors[0]) == 4096
            return vectors[0]

        knowledge = GuideKnowledge(ROOT, identity=embedding.identity, embed_query=embed_query)
        result = asyncio.run(knowledge.search("算法练习在哪里"))
        assert calls["count"] == 1
        assert result.status == "ok"
        assert result.dimension == 4096
        top = result.matches[0]
        assert top["route"].startswith("#space/practice") or any(
            "算法" in match["title"] for match in result.matches[:3])
        assert any("算法" in match["title"] or "算法" in match["excerpt"] for match in result.matches)
    finally:
        asyncio.run(platform.close())
        import shutil
        shutil.rmtree(data_dir, ignore_errors=True)
