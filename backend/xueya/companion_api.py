"""Companion (桌宠小涯) chat endpoint: system-guide RAG first, ordinary chat second.

Contract (AGENT_PLAN §2.3):
    POST /api/learning/space/companion/chat
    request  {question, history:[{role,content}], courseId}
    response {ok:true, reply:{status, route, engine, answer, sources, links,
                              confidence, modelUsed, warnings}}
- system questions search materials/system-guide (isolated from the course RAG)
  and answer with the guide snippets; links only contain real #space routes.
- general questions reuse the existing general chat; when the model is
  unavailable the reply is explicitly "unavailable" instead of failing the UI.
- no web search is ever triggered from this endpoint.
"""
from __future__ import annotations

import re
import secrets
from contextlib import aclosing

from fastapi import APIRouter, Request

from .common import require
from .companion_knowledge import GuideKnowledge, KNOWN_ROUTES, is_system_question, make_links

MAX_QUESTION = 2000
MAX_HISTORY = 12
MAX_HISTORY_CHARS = 4000
MAX_ANSWER = 16000

SYSTEM_PROMPT = (
    "你是学涯 Copilot 的系统使用助手「小涯」。用户询问的是这个学习系统本身的功能、页面位置或操作方式。"
    "只依据下面提供的《系统使用指南》片段回答：准确说出功能名、页面路径（形如 #space/xxx）和操作步骤。"
    "片段没有提到的功能或页面必须明确说“系统使用指南暂未收录”，不得编造不存在的入口、按钮、接口或数据。"
    "不要联网、不要猜测。用简体中文简洁回答，通常 3 到 8 行；如果有操作步骤，用数字列表。"
)


# --- request helpers ---------------------------------------------------
def _clean_history(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    rows: list[dict] = []
    for item in value[-MAX_HISTORY:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()[:MAX_HISTORY_CHARS]
        if content:
            rows.append({"role": role, "content": content})
    return rows


def _clean_question(value) -> str:
    require(isinstance(value, str), "EMPTY_QUESTION")
    question = value.strip()
    require(0 < len(question) <= MAX_QUESTION, "EMPTY_QUESTION")
    return question


def _course_id(value) -> str:
    course = value.get("courseId") if isinstance(value, dict) else None
    if not isinstance(course, str) or not course.strip() or len(course) > 150:
        return "course-default"
    return course.strip()


def _platform(app):
    return getattr(app.state, "platform", None)


def _scope(app, course_id: str):
    platform = _platform(app)
    require(platform is not None, "PLATFORM_DISABLED")
    try:
        return platform.scope(course_id)
    except Exception:  # noqa: BLE001 - unknown course falls back to the default scope
        return platform.scope("course-default")


def _embedder(app, course_id: str):
    """One query-embedding callable bound to the configured RAG embedding provider."""
    rag = getattr(app.state, "rag", None)
    embedding = getattr(rag, "embedding", None)
    if embedding is None or _platform(app) is None:
        return None
    scope = _scope(app, course_id)

    async def embed_query(text: str) -> list[float]:
        vectors = await embedding.embed(scope, [text], query=True)
        require(isinstance(vectors, list) and len(vectors) == 1, "INVALID_EMBEDDING")
        return vectors[0]

    return embed_query


def _knowledge(app) -> GuideKnowledge:
    existing = getattr(app.state, "companion_knowledge", None)
    if existing is not None:
        return existing
    config = app.state.config
    rag = getattr(app.state, "rag", None)
    embedding = getattr(rag, "embedding", None)
    instance = GuideKnowledge(
        config.root,
        data_dir=config.data_dir,
        identity=getattr(embedding, "identity", None),
        embed_query=_embedder(app, "course-default"),
    )
    app.state.companion_knowledge = instance
    return instance


# --- answer builders ---------------------------------------------------
def _provider(app):
    return getattr(app.state, "provider", None)


def _model_name(provider) -> str | None:
    config = getattr(provider, "config", None)
    return str(getattr(config, "model", "") or "") or None


class _ChatModel:
    """Adapt the host MimoProvider to the shape expected by general_chat()."""

    def __init__(self, provider, scope):
        self.provider, self.scope = provider, scope

    @staticmethod
    def _messages(value):
        messages = value.get("messages") if isinstance(value, dict) else None
        require(isinstance(messages, list) and messages, "AI_INVALID_RESPONSE")
        return [dict(message) for message in messages]

    async def stream(self, value):
        messages = self._messages(value)
        async with aclosing(self.provider.stream(messages, scope=self.scope, thinking={"type": "disabled"})) as events:
            async for event in events:
                yield event

    async def generate(self, value, **kwargs):
        messages = self._messages(value)
        result = await self.provider.generate(messages, scope=self.scope, thinking={"type": "disabled"},
                                              max_output_tokens=1024)
        return {"content": result.get("content", ""), "model": result.get("model")}


def _source_rows(matches: list[dict]) -> list[dict]:
    return [{
        "title": match.get("title", ""),
        "path": match.get("path", ""),
        "location": match.get("section", ""),
        "excerpt": (match.get("excerpt") or "")[:600],
    } for match in matches]


def _best_routed(matches: list[dict]) -> dict | None:
    for match in matches:
        if match.get("route") in KNOWN_ROUTES:
            return match
    return matches[0] if matches else None


def _deterministic_answer(question: str, matches: list[dict], *, note: str = "") -> str:
    top = _best_routed(matches)
    if not top:
        return "系统使用指南暂未收录这个问题。"
    lines = [f"关于「{question}」，系统里的入口是：{top['title']}（{top['route']}）。"]
    steps = [step for step in top.get("steps") or [] if step][:6]
    if steps:
        lines.append("操作步骤：")
        lines.extend(f"{index}. {step}" for index, step in enumerate(steps, 1))
    else:
        excerpt = re.sub(r"\s+", " ", str(top.get("excerpt") or "")).strip()
        if excerpt:
            lines.append(excerpt[:160])
    others: list[dict] = []
    seen_routes = {top.get("route")}
    for match in matches:
        route = match.get("route")
        if route and route in KNOWN_ROUTES and route not in seen_routes:
            seen_routes.add(route)
            others.append(match)
        if len(others) >= 2:
            break
    if others:
        lines.append("相关页面：" + "；".join(f"{match['title']}（{match['route']}）" for match in others))
    if top.get("docTitle"):
        lines.append(f"依据：系统使用指南《{top['docTitle']}》· {top.get('section') or '总览'}。")
    if note:
        lines.append(note)
    return "\n".join(lines)


def _not_found_answer(question: str, knowledge: GuideKnowledge) -> str:
    areas = [area["title"] for area in knowledge.known_areas(8)]
    lines = [f"系统使用指南里没有找到与「{question}」对应的功能，我不能凭空编造一个入口。"]
    if areas:
        lines.append("目前指南覆盖的主要功能有：" + "、".join(areas) + "。")
    lines.append("可以换一种说法（例如说出具体功能名），或从左侧栏的五个学习中心入口浏览。")
    if knowledge.error:
        lines.append(f"（系统使用指南索引暂不可用：{knowledge.error}）")
    return "\n".join(lines)


def _messages(question: str, match_list: list[dict], history: list[dict]) -> list[dict]:
    lines = []
    for index, match in enumerate(match_list, 1):
        steps = " / ".join((match.get("steps") or [])[:8]) or "见原文"
        lines.append(
            f"[{index}] 功能：{match.get('title')}；页面：{match.get('route') or '见文档'}；"
            f"章节：{match.get('section') or '总览'}；步骤：{steps}；"
            f"原文：{re.sub(r'\\s+', ' ', str(match.get('excerpt') or ''))[:520]}")
    system = SYSTEM_PROMPT + "\n\n《系统使用指南》片段：\n" + "\n\n".join(lines)
    return [{"role": "system", "content": system}, *history, {"role": "user", "content": question}]


def _links(match_list: list[dict]) -> list[dict]:
    return make_links(match_list, limit=4)


async def _system_reply(app, question: str, history: list[dict], course_id: str) -> dict:
    knowledge = _knowledge(app)
    result = await knowledge.search(question, limit=5)
    warnings = list(result.warnings)
    sources = _source_rows(result.matches)
    if result.status != "ok" or not result.matches:
        return {
            "status": "not_found",
            "route": "system",
            "engine": "guide-not-found",
            "answer": _not_found_answer(question, knowledge),
            "sources": [],
            "links": [{"title": area["title"], "hash": area["hash"]} for area in knowledge.known_areas(6)],
            "confidence": None,
            "modelUsed": None,
            "warnings": warnings,
        }
    links = _links(result.matches)
    confidence = round(float(result.matches[0].get("score") or 0), 4)
    provider = _provider(app)
    if provider is not None:
        try:
            response = await provider.generate(_messages(question, result.matches, history),
                                               scope=_scope(app, course_id), temperature=.1, timeout=45,
                                               max_output_tokens=1200, thinking={"type": "disabled"})
            answer = str(response.get("content") or "").strip()
            require(0 < len(answer) <= MAX_ANSWER, "AI_EMPTY")
            return {
                "status": "ok",
                "route": "system",
                "engine": "guide-rag",
                "answer": answer,
                "sources": sources,
                "links": links,
                "confidence": confidence,
                "modelUsed": response.get("model") or _model_name(provider),
                "warnings": warnings,
            }
        except Exception as error:  # noqa: BLE001 - deterministic guide answer takes over
            code = getattr(error, "code", None) or type(error).__name__
            warnings.append("SYSTEM_GUIDE_MODEL_UNAVAILABLE:" + str(code)[:60])
    answer = _deterministic_answer(question, result.matches,
                                   note="（当前模型服务不可用，以上为本地系统使用指南检索结果，未经模型润色。）")
    return {
        "status": "ok",
        "route": "system",
        "engine": "local-guide",
        "answer": answer,
        "sources": sources,
        "links": links,
        "confidence": confidence,
        "modelUsed": None,
        "warnings": warnings,
    }


async def _general_reply(app, question: str, history: list[dict], course_id: str) -> dict:
    provider = _provider(app)
    try:
        require(provider is not None, "AI_UNAVAILABLE")
        from backend.agent.general_chat import general_chat

        scope = _scope(app, course_id)
        model = _ChatModel(provider, scope)
        answer, model_used = "", _model_name(provider)
        async with aclosing(general_chat(model, {"question": question, "history": history},
                                         plain_text=True)) as events:
            async for event in events:
                if event.get("type") == "done":
                    answer = str(event.get("answer") or "").strip()
                    model_used = event.get("model") or model_used
        require(bool(answer), "AI_EMPTY")
        return {
            "status": "ok",
            "route": "general",
            "engine": "general-chat",
            "answer": answer[:MAX_ANSWER],
            "sources": [],
            "links": [],
            "confidence": None,
            "modelUsed": model_used,
            "warnings": [],
        }
    except Exception as error:  # noqa: BLE001 - explicitly report unavailable instead of raising
        code = getattr(error, "code", None) or type(error).__name__
        return {
            "status": "unavailable",
            "route": "general",
            "engine": "general-unavailable",
            "answer": ("通用问答服务暂时不可用。你也可以问我系统功能在哪里，例如「算法练习在哪里」，"
                       "我会用系统使用指南给出入口和步骤。"),
            "sources": [],
            "links": [],
            "confidence": None,
            "modelUsed": None,
            "warnings": ["GENERAL_CHAT_UNAVAILABLE:" + str(code)[:60]],
        }


def install_companion(app, *, knowledge: GuideKnowledge | None = None):
    """Register the companion endpoint. Safe to call once inside create_app()."""
    if getattr(app.state, "companion_installed", False):
        if knowledge is not None:
            app.state.companion_knowledge = knowledge
        return app
    app.state.companion_installed = True
    if knowledge is not None:
        app.state.companion_knowledge = knowledge
    from .app import json_body, success

    router = APIRouter(prefix="/api/learning/space")

    def authorize(request: Request):
        require(bool(re.fullmatch(r"(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?", request.headers.get("host", ""))),
                "ORIGIN_FORBIDDEN")
        supplied = request.headers.get("origin")
        require(not supplied or supplied == str(request.base_url).rstrip("/"), "ORIGIN_FORBIDDEN")
        require(secrets.compare_digest(request.headers.get("x-xueya-token", ""), app.state.token), "AUTH_REQUIRED")

    @router.post("/companion/chat")
    async def companion_chat(request: Request):
        authorize(request)
        value = await json_body(request, 65536)
        question = _clean_question(value.get("question") if isinstance(value, dict) else None)
        history = _clean_history(value.get("history") if isinstance(value, dict) else None)
        course_id = _course_id(value)
        reply = await (_system_reply(app, question, history, course_id) if is_system_question(question)
                       else _general_reply(app, question, history, course_id))
        return success(reply=reply)

    @router.get("/companion/guide")
    async def companion_guide(request: Request):
        authorize(request)
        knowledge = _knowledge(app)
        loaded = await knowledge.ensure_loaded()
        manifest = knowledge.manifest
        return success(guide={
            "installed": True,
            "loaded": bool(loaded),
            "error": knowledge.error,
            "chunks": int(manifest.get("chunkCount") or 0),
            "documents": int(manifest.get("documentCount") or 0),
            "model": manifest.get("model", ""),
            "dimension": int(manifest.get("dimension") or 0),
            "adapter": manifest.get("adapter", ""),
            "builtAt": manifest.get("builtAt", ""),
            "routes": len(KNOWN_ROUTES),
        })

    count = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[count:]
    del app.router.routes[count:]
    app.router.routes[0:0] = added
    return app
