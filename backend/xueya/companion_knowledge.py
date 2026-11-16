"""System-guide knowledge retrieval for the companion (桌宠小涯), isolated from course RAG.

The companion must answer "这个功能在哪里 / 怎么用" from the shipped guide in
docs/guide (vectors in materials/system-guide, optional account override in
.xueya-data/system-guide). It never reads the user's course documents, never
writes to their vector tables and never touches .xueya-data unless an override
index exists there.

Loading is lazy and cached. Retrieval is hybrid: cosine similarity over the
guide index plus a keyword/heading pass reusing the course RAG lexical code.
When the query embedding is unavailable the search degrades to keywords and
reports a warning instead of failing. No hit means "not found" - the companion
must not invent features.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .rag_search import exact, lexical, terms

log = logging.getLogger(__name__)

SCHEMA = "system-guide-vectors-v1"
VECTOR_FILE = "vectors.json"
MANIFEST_FILE = "manifest.json"
DEFAULT_LIMIT = 5
MAX_LIMIT = 6
VECTOR_THRESHOLD = .18
HYBRID_THRESHOLD = .30
LEXICAL_TITLE_BOOST = .10
MAX_PER_DOCUMENT = 2
ZH_PAIR = re.compile(r"[\u4e00-\u9fff]{2}")


def _pairs(text: str) -> set[str]:
    """Chinese bigrams plus ascii tokens, used for heading/title overlap scoring."""
    value = str(text or "").casefold()
    pairs = set(ZH_PAIR.findall(re.sub(r"[^\u4e00-\u9fff]", "", value)))
    pairs.update(token for token in re.findall(r"[a-z0-9_]{2,}", value))
    return pairs

# Only real, reachable front-end routes may become clickable links (AGENT_PLAN §2.3).
KNOWN_ROUTES = frozenset("""
#space/overview #space/ask #space/courses #space/materials #space/materials/corpus
#space/materials/video #space/materials/plan #space/practice #space/practice/hot100
#space/practice/exam408 #space/practice/foundation #space/practice/interview
#space/practice/legacy #space/practice/ai #space/review #space/review/materials
#space/review/algorithms #space/review/exams #space/exams #space/knowledge
#space/analysis #space/analysis/plans #space/frameworks #space/media
""".split())
ROUTE_RE = re.compile(r"^#space/[a-z0-9][a-z0-9/_-]*$")

SYSTEM_NOUNS = (
    "功能", "入口", "页面", "路由", "界面", "按钮", "菜单", "侧栏", "设置", "账号",
    "资料库", "知识库", "错题本", "题库", "学习计划", "计划", "学情分析", "分析报告",
    "课程", "视频课", "桌宠", "小涯", "助手", "导出", "导入", "上传", "签到", "框架",
    "知识框架", "算法学习", "算法练习", "408", "练习", "检索", "搜索", "笔记", "随手记",
    "小测", "模拟考试", "学习路线", "今日学习", "主题", "快捷键", "历史记录", "对话",
    "附件", "深度思考", "联网", "模式", "数据", "备份", "登录", "注册", "系统", "学涯",
)
SYSTEM_MARKERS = ("哪里", "在哪", "怎么", "如何", "入口", "功能", "怎么用", "怎么打开", "有没有",
                  "支持", "可以", "能做什么", "是什么", "介绍一下", "找不到", "位置", "教程", "步骤")


def is_system_question(question: str) -> bool:
    """Cheap language heuristic before spending one embedding call on a chat message."""
    text = str(question or "").strip().casefold()
    if not text:
        return False
    if not any(noun in question for noun in SYSTEM_NOUNS):
        return False
    return any(marker in text for marker in SYSTEM_MARKERS)


@dataclass
class GuideSearchResult:
    status: str = "not_found"  # ok | not_found | unavailable
    mode: str = "lexical"  # hybrid | lexical
    matches: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    query: str = ""
    index_at: str = ""
    model: str = ""
    dimension: int = 0

    def top(self) -> dict | None:
        return self.matches[0] if self.matches else None


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_index(directory: Path) -> dict:
    """Load and validate one guide index directory. Raises ValueError with a stable code."""
    directory = Path(directory)
    manifest_path, vector_path = directory / MANIFEST_FILE, directory / VECTOR_FILE
    if not manifest_path.is_file() or not vector_path.is_file():
        raise ValueError("SYSTEM_GUIDE_INDEX_MISSING")
    try:
        manifest = _read_json(manifest_path)
        vectors = _read_json(vector_path)
    except (OSError, ValueError) as error:
        raise ValueError("SYSTEM_GUIDE_INDEX_UNREADABLE") from error
    if manifest.get("schema") != SCHEMA or vectors.get("schema") != SCHEMA:
        raise ValueError("SYSTEM_GUIDE_SCHEMA_MISMATCH")
    if vectors.get("identity") != manifest.get("identity"):
        raise ValueError("SYSTEM_GUIDE_IDENTITY_MISMATCH")
    dimension = manifest.get("dimension")
    if type(dimension) is not int or dimension <= 0:
        raise ValueError("SYSTEM_GUIDE_DIMENSION_INVALID")
    chunks = vectors.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("SYSTEM_GUIDE_CHUNKS_MISSING")
    rows: list[dict] = []
    matrix: list[list[float]] = []
    for row in chunks:
        embedding = row.get("embedding")
        if not isinstance(embedding, list) or len(embedding) != dimension:
            raise ValueError("SYSTEM_GUIDE_DIMENSION_INVALID")
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("SYSTEM_GUIDE_CHUNK_INVALID")
        matrix.append([float(value) for value in embedding])
        rows.append({
            "id": row.get("id") or "guide-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:20],
            "title": str(row.get("title") or "").strip(),
            "feature": str(row.get("feature") or row.get("title") or "").strip(),
            "module": str(row.get("module") or "").strip(),
            "docPath": str(row.get("docPath") or ""),
            "sectionPath": [str(value) for value in (row.get("sectionPath") or []) if str(value).strip()],
            "route": str(row.get("route") or ""),
            "routes": [str(value) for value in (row.get("routes") or []) if str(value).strip()],
            "steps": [str(value) for value in (row.get("steps") or []) if str(value).strip()][:12],
            "text": text,
            "contentHash": str(row.get("contentHash") or ""),
            "quote": text,
        })
    return {"manifest": manifest, "rows": rows, "matrix": matrix, "dimension": dimension,
            "directory": str(directory)}


def _route_ok(route: str) -> bool:
    return bool(route) and bool(ROUTE_RE.fullmatch(route)) and route in KNOWN_ROUTES


ROUTE_HINTS = (
    ("错题", "#space/review"),
    ("算法", "#space/practice/hot100"),
    ("模拟考试", "#space/exams"),
    ("模拟", "#space/exams"),
    ("408", "#space/exams"),
    ("个性化学习", "#space/materials/plan"),
    ("学习计划", "#space/analysis/plans"),
    ("计划", "#space/analysis/plans"),
    ("上传", "#space/knowledge"),
    ("资料库", "#space/knowledge"),
    ("资料", "#space/knowledge"),
    ("知识框架", "#space/frameworks"),
    ("框架", "#space/frameworks"),
    ("视频", "#space/courses"),
    ("课程", "#space/courses"),
    ("分析", "#space/analysis"),
    ("签到", "#space/materials"),
    ("图谱", "#space/materials/corpus"),
)


def _pick_route(row: dict, question: str, doc_routes: dict[str, list[str]]) -> str:
    """Choose the route that best matches the question topic, keeping only real ones."""
    candidates = [route for route in (row.get("routes") or []) if _route_ok(route)]
    if not candidates and _route_ok(row.get("route") or ""):
        candidates = [row["route"]]
    document = row.get("docPath", "")
    for route in doc_routes.get(document) or []:
        if route not in candidates:
            candidates.append(route)
    if not candidates:
        return ""
    for keyword, route in ROUTE_HINTS:
        if keyword in question and route in candidates:
            return route
    return candidates[0]


def _link_title(row: dict) -> str:
    title = row.get("feature") or row.get("title") or "打开页面"
    title = re.sub(r"\s+", " ", title).strip()
    return title[:40]


class GuideKnowledge:
    """Lazy, injectable retrieval over the system-guide vectors."""

    def __init__(self, root: Path, *, data_dir: Path | None = None, identity: dict | None = None,
                 embed_query=None, limit: int = DEFAULT_LIMIT):
        self.root = Path(root)
        self.bundled = self.root / "materials" / "system-guide"
        self.override = (Path(data_dir) / "system-guide") if data_dir else None
        self.identity = identity or None
        self.embed_query = embed_query
        self.limit = max(1, min(MAX_LIMIT, int(limit)))
        self._loaded: dict | None = None
        self._error: str | None = None
        self._lock = asyncio.Lock()
        self._warned_identity = False

    # --- loading -------------------------------------------------------
    def _active_directory(self) -> Path:
        if self.override and (self.override / MANIFEST_FILE).is_file():
            return self.override
        return self.bundled

    async def ensure_loaded(self) -> bool:
        if self._loaded is not None:
            return True
        if self._error:
            return False
        async with self._lock:
            if self._loaded is not None:
                return True
            if self._error:
                return False
            directory = self._active_directory()
            try:
                self._loaded = await asyncio.to_thread(load_index, directory)
            except ValueError as error:
                self._error = str(error)
                log.warning("system-guide index unavailable: %s", self._error)
                return False
            except Exception as error:  # noqa: BLE001 - never break the companion on a bad file
                self._error = type(error).__name__
                log.warning("system-guide index failed to load: %s", self._error)
                return False
            return True

    @property
    def loaded(self) -> bool:
        return self._loaded is not None

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def manifest(self) -> dict:
        return (self._loaded or {}).get("manifest") or {}

    def known_areas(self, limit: int = 8) -> list[dict]:
        """Distinct guide areas for a "not found" answer; index/FAQ docs are skipped."""
        rows = (self._loaded or {}).get("rows") or []
        skip = ("01-", "02-", "14-", "15-", "16-")
        doc_routes: dict[str, list[str]] = {}
        for row in rows:
            bucket = doc_routes.setdefault(row.get("docPath", ""), [])
            for route in [row.get("route") or ""] + list(row.get("routes") or []):
                if _route_ok(route) and route not in bucket:
                    bucket.append(route)
        areas: dict[str, dict] = {}
        for row in rows:
            document = row.get("docPath", "")
            if document.startswith(skip):
                continue
            title = (row.get("title") or "").strip()
            if not title or title in areas:
                continue
            route = _pick_route(row, title, doc_routes)
            if not _route_ok(route):
                continue
            areas[title] = {"title": title[:40], "hash": route}
            if len(areas) >= limit:
                break
        return list(areas.values())

    # --- retrieval -----------------------------------------------------
    def _embedding_usable(self) -> bool:
        """Compare the configured embedding identity with the index identity."""
        index_identity = (self._loaded or {}).get("manifest", {}).get("identity")
        configured = self.identity or {}
        if not index_identity or not configured:
            return False
        for key in ("model", "dimension", "adapter"):
            if configured.get(key) != index_identity.get(key):
                if not self._warned_identity:
                    self._warned_identity = True
                    log.info("system-guide vector identity mismatch on %s; using lexical retrieval", key)
                return False
        return True

    async def _vector(self, query: str, warnings: list[str]) -> list[float] | None:
        index = self._loaded or {}
        if not self.identity:
            warnings.append("SYSTEM_GUIDE_EMBEDDING_UNAVAILABLE")
            return None
        if not self._embedding_usable():
            warnings.append("SYSTEM_GUIDE_VECTOR_IDENTITY_MISMATCH")
            return None
        if not callable(self.embed_query):
            warnings.append("SYSTEM_GUIDE_EMBEDDING_UNAVAILABLE")
            return None
        try:
            vector = await self.embed_query(query)
        except Exception as error:  # noqa: BLE001 - degrade to keywords instead of failing the chat
            code = getattr(error, "code", None) or type(error).__name__
            warnings.append("SYSTEM_GUIDE_EMBEDDING_UNAVAILABLE:" + str(code)[:60])
            return None
        if not isinstance(vector, list) or len(vector) != index.get("dimension"):
            warnings.append("SYSTEM_GUIDE_EMBEDDING_MISMATCH")
            return None
        values = [float(value) for value in vector]
        norm = math.sqrt(sum(value * value for value in values))
        if not math.isfinite(norm) or norm <= 0:
            warnings.append("SYSTEM_GUIDE_EMBEDDING_INVALID")
            return None
        return [value / norm for value in values]

    async def search(self, query: str, *, limit: int | None = None) -> GuideSearchResult:
        text = str(query or "").strip()
        limit = max(1, min(MAX_LIMIT, int(limit or self.limit)))
        if not text:
            return GuideSearchResult(status="not_found", query="")
        loaded = await self.ensure_loaded()
        if not loaded:
            return GuideSearchResult(status="not_found", mode="lexical",
                                     warnings=[self._error or "SYSTEM_GUIDE_INDEX_MISSING"], query=text)
        index = self._loaded or {}
        rows, matrix = index["rows"], index["matrix"]
        manifest = index.get("manifest") or {}
        warnings: list[str] = []
        vector = await self._vector(text, warnings)

        keyword_rows = lexical(text, rows, limit=16)
        max_keyword = max((score for score, _ in keyword_rows), default=0.0)
        query_pairs = _pairs(text)
        scores: dict[str, dict] = {}

        def bucket(row: dict) -> dict:
            return scores.setdefault(row["id"], {"row": row, "vector": 0.0, "keyword": 0.0, "title": 0.0})

        if vector is not None:
            for score, row in exact(vector, list(zip(matrix, rows)), limit=16, threshold=VECTOR_THRESHOLD):
                bucket(row)["vector"] = float(score)
        query_terms = set(terms(text))
        heading_pairs: dict[str, set[str]] = {}
        meta_terms: dict[str, set[str]] = {}
        for row in rows:
            heading = " ".join([row.get("feature", ""), row.get("title", ""), row.get("module", ""),
                                " ".join(row.get("sectionPath") or [])])
            heading_pairs[row["id"]] = _pairs(heading) & query_pairs
            meta_terms[row["id"]] = set(terms(heading))
        for score, row in keyword_rows:
            entry = bucket(row)
            entry["keyword"] = float(score) / max_keyword if max_keyword > 0 else 0.0
            overlap = heading_pairs.get(row["id"]) or set()
            if overlap and query_pairs:
                entry["title"] = LEXICAL_TITLE_BOOST * min(1.0, len(overlap) / len(query_pairs))
            if query_terms:
                entry["meta"] = len(query_terms & (meta_terms.get(row["id"]) or set())) / len(query_terms)

        ranked: list[tuple[float, dict]] = []
        for entry in scores.values():
            row = entry["row"]
            heading_ratio = min(1.0, len((heading_pairs.get(row["id"]) or set())) / max(1, len(query_pairs)))
            meta_ratio = float(entry.get("meta") or 0.0)
            if vector is None:
                combined = .42 * entry["keyword"] + .32 * meta_ratio + .16 * heading_ratio + entry["title"]
            else:
                combined = .58 * entry["vector"] + .22 * entry["keyword"] + .12 * meta_ratio + .08 * heading_ratio + entry["title"]
            # Prefer chunks that carry a real page route: they are the actionable ones.
            if _route_ok(row.get("route") or ""):
                combined += .03
            if combined <= 0:
                continue
            ranked.append((combined, row))
        ranked.sort(key=lambda item: (-item[0], item[1].get("docPath", ""), item[1].get("id", "")))

        mode = "hybrid" if vector is not None else "lexical"
        threshold = HYBRID_THRESHOLD if vector is not None else .02
        doc_routes: dict[str, list[str]] = {}
        for row in rows:
            bucket_routes = doc_routes.setdefault(row.get("docPath", ""), [])
            for route in [row.get("route") or ""] + list(row.get("routes") or []):
                if _route_ok(route) and route not in bucket_routes:
                    bucket_routes.append(route)
        matches: list[dict] = []
        per_document: dict[str, int] = {}
        for score, row in ranked:
            if score < threshold:
                continue
            document = row.get("docPath", "")
            if per_document.get(document, 0) >= MAX_PER_DOCUMENT:
                continue
            per_document[document] = per_document.get(document, 0) + 1
            steps = list(row.get("steps") or [])
            excerpt = row.get("text", "")
            matches.append({
                "title": row.get("feature") or row.get("title") or "系统功能",
                "docTitle": row.get("title", ""),
                "path": row.get("docPath", ""),
                "section": " › ".join(row.get("sectionPath") or []),
                "route": _pick_route(row, text, doc_routes),
                "steps": steps,
                "excerpt": excerpt[:900],
                "score": round(float(score), 4),
                "module": row.get("module", ""),
            })
            if len(matches) >= limit:
                break
        # A system question whose substantive phrases never appear in the guide is
        # treated as "not found": semantic similarity alone must not invent an
        # entry point for a feature the system does not have (e.g. 直播课).
        phrases = _content_phrases(text)
        corpus = " ".join(row.get("feature", "") + " " + row.get("title", "") + " " +
                          " ".join(row.get("sectionPath") or []) + " " + row.get("text", "")
                          for row in rows).casefold()
        if phrases and not all(_phrase_covered(phrase, corpus) for phrase in phrases):
            matches = []
            warnings.append("SYSTEM_GUIDE_NO_SUBSTANTIVE_COVERAGE")
        elif max_keyword <= 0:
            matches = []
            warnings.append("SYSTEM_GUIDE_LOW_KEYWORD_MATCH")
        if not matches:
            warnings.append("SYSTEM_GUIDE_NO_MATCH")
            return GuideSearchResult(status="not_found", mode=mode, warnings=warnings, query=text,
                                     index_at=str(manifest.get("builtAt") or ""), model=str(manifest.get("model") or ""),
                                     dimension=int(manifest.get("dimension") or 0))
        return GuideSearchResult(status="ok", mode=mode, matches=matches, warnings=warnings, query=text,
                                 index_at=str(manifest.get("builtAt") or ""), model=str(manifest.get("model") or ""),
                                 dimension=int(manifest.get("dimension") or 0))


PHRASE_STOP = ("有没有", "能不能", "哪些", "什么", "怎么", "如何", "哪里", "在哪", "支持",
               "提供", "实现", "可以", "使用", "打开", "找到", "查找", "查看", "设置", "建立",
               "制定", "开始", "完成", "保存", "删除", "修改", "管理", "生成", "功能", "入口",
               "页面", "位置", "步骤", "方法", "教程", "介绍", "系统", "学涯", "这个", "那个",
               "一下", "多少", "几个", "几种", "几道", "能", "做", "用", "我", "你", "它", "想", "要", "请",
               "问", "里", "中", "上", "下", "的", "了", "是", "有", "和", "与", "或", "在",
               "吗", "呢", "吧",
               # Sentence glue: dropping it keeps the content words of a natural
               # request (把笔记导出成 -> 笔记导出) without loosening the gate.
               "把", "被", "让", "给", "从", "向", "对", "到", "成", "着", "过", "也",
               "都", "还", "就", "才", "又", "并", "及", "以", "为", "会", "该")


def _content_phrases(question: str) -> list[str]:
    """Substantive topic phrases left after generic verbs/interrogatives are removed."""
    text = str(question or "")
    for stop in sorted(PHRASE_STOP, key=len, reverse=True):
        text = text.replace(stop, " ")
    phrases = [part.strip() for part in re.split(r"[^\u4e00-\u9fffA-Za-z0-9]+", text) if part.strip()]
    return [phrase for phrase in phrases if len(phrase) >= 2][:6]


def _phrase_covered(phrase: str, corpus: str) -> bool:
    """A topic phrase counts as covered only when most of it really exists in the guide.

    CJK runs are matched by their character bigrams: at least three fifths of
    the bigrams (and never fewer than two of them) must appear in the guide.
    Requiring one shared bigram is not enough, because a made-up feature name
    can glue onto generic words - 全息投影学习模式 shares 学习/模式 with real
    guides while the feature itself does not exist. Ascii tokens must appear as
    tokens, and a mixed phrase such as AI 画图 is only covered when both AI and
    画图 appear.
    """
    groups = re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]{2,}", str(phrase).casefold())
    if not groups:
        return False
    for group in groups:
        if re.fullmatch(r"[a-z0-9_]{2,}", group):
            if group not in corpus:
                return False
            continue
        grams = ([group[index:index + 2] for index in range(len(group) - 1)]
                 if len(group) >= 2 else [group])
        matched = sum(1 for gram in grams if gram in corpus)
        # Integer ceil(3/5) keeps 开启深色模式 (3 of 5 grams) covered without a
        # float rounding trap, while rejecting 2-of-5 style guesses.
        needed = min(len(grams), max(2, (len(grams) * 3 + 4) // 5))
        if matched < needed:
            return False
    return True


def make_links(matches: list[dict], limit: int = 4) -> list[dict]:
    """Turn matched guide routes into clickable links; only real hashes survive."""
    links: list[dict] = []
    seen: set[str] = set()
    for match in matches:
        route = str(match.get("route") or "")
        if not _route_ok(route) or route in seen:
            continue
        seen.add(route)
        links.append({"title": _link_title(match), "hash": route})
        if len(links) >= limit:
            break
    return links
