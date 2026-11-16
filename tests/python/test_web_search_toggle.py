"""T3 联网搜索开关验收：默认关闭、仅显式开启才联网、课程资料默认参与检索。

只读审计依据（2026-11-15 工作区，行号见各断言）：
- backend/xueya/agent.py:42-56 normalize_request 把 webSearch 归一为 bool，缺省 False。
- backend/xueya/agent.py:342-345 direct() 只有 request["webSearch"] 为真才 import/调用 search_tavily。
- backend/xueya/agent.py:435-448 _web_search_stream() 是 UI 联网的唯一路径，显式 MCP 调用 search_web。
- backend/xueya/agent.py:636-644 workflow() 只有 webSearch 为真才进入 _web_search_stream()。
- backend/xueya/agent.py:764 联网回答不写答案缓存（关闭时也不相关）。
- backend/agent/tool_adapter.py:6-15 READ_ONLY_TOOLS 不含 search_web。
- backend/xueya/durable_agent.py:122-123 与 backend/xueya/learning_integration.py:129-133
  动态 agent 的工具白名单都是 READ_ONLY_TOOLS，因此不会自动联网。
- backend/xueya/mcp_core.py:159-162,247-250 注册 search_web，仅显式 session.call 才会执行；
  HTTP 的 /api/platform/tools* 是外部 MCP 客户端路径（backend/xueya/app.py:390-397），UI 问答不调用。
- backend/agent/general_chat.py 与 RAG fallback 不引用联网模块：关闭时不存在隐式联网。

运行：
    .venv\\Scripts\\python.exe -m pytest -q tests/python/test_web_search_toggle.py
浏览器实验室（隔离 server + Playwright，需显式开启，避免常规回归变慢）：
    $env:XUEYA_RUN_BROWSER_LAB='1'; .venv\\Scripts\\python.exe -m pytest -q tests/python/test_web_search_toggle.py -k browser
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VIEWS = ROOT / "frontend/js/ui/workspace-views.js"
CONTROLLER = ROOT / "frontend/js/workspace-controller.js"
APP = ROOT / "frontend/js/app.js"
CHAT_SERVICE = ROOT / "frontend/js/services/chat-service.js"

WEB_SEARCH_LABEL = "联网搜索"
WEB_SEARCH_ARIA = "联网搜索（开启后结合互联网与课程知识库）"
COURSE_MATERIAL_HINT = "课程资料默认参与检索"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def node_executable() -> str | None:
    found = shutil.which("node")
    if found:
        return found
    # The unattended harness keeps Node outside PATH; this fallback is best-effort
    # and the test skips elsewhere instead of depending on a machine-specific path.
    if os.name == "nt":
        candidate = Path.home() / ".dsh" / "dsh-runtimes" / "dsh-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
        if candidate.exists():
            return str(candidate)
    return None


def test_composer_web_search_copy_is_plain_opt_in() -> None:
    views = read(VIEWS)
    # 「🌐 联网搜索」替掉旧的「全网 + 课程知识库混合检索」。
    assert "data-toggle-web-search" in views
    assert 'aria-label="' + WEB_SEARCH_ARIA + '"' in views
    assert ">联网搜索</span>" in views
    assert "联网搜索已开启（结合互联网与课程知识库）" in views
    assert "开启联网搜索（结合互联网与课程知识库）" in views
    # 开关状态只认严格 true；首次 undefined 不会渲染成开启。
    assert 'aria-pressed="${Boolean(state.webSearch)}"' in views
    # 课程资料默认参与检索的静态提示，不依赖开关。
    assert COURSE_MATERIAL_HINT in views
    # 旧文案不应残留（否则用户仍会以为默认混合检索）。
    for legacy in ("全网 + 课程知识库混合检索", "全网搜索已开启", "开启全网搜索", "联网获取最新信息"):
        assert legacy not in views, legacy


def test_controller_defaults_web_search_off_and_toast_copy() -> None:
    controller = read(CONTROLLER)
    # 首次进入 undefined 或任何非 true 值都归一为关闭；本页会话内用户开启仍保留。
    assert "if(state.webSearch!==true)state.webSearch=false;" in controller
    assert "state.webSearch=!Boolean(state.webSearch);" in controller
    assert "联网搜索已开启（课程知识库始终参与检索）" in controller
    assert "联网搜索已关闭（课程知识库始终参与检索）" in controller
    assert "全网搜索已开启" not in controller


def test_ask_request_keeps_course_sources_and_sends_boolean_switch() -> None:
    app = read(APP)
    # 课程资料检索与 webSearch 无关：sources 始终进入请求，documentIds 由当前资料范围决定。
    assert "webSearch:Boolean(state.webSearch)" in app
    assert "const sources=state.selectedDocuments.length?allSources()" in app
    assert "request.documentIds=" in app
    # 桌宠/内嵌问答固定 webSearch:false，不会绕过主开关联网。
    assert "webSearch:false" in app
    # 只有显式 true 才会被写入请求体（undefined/false 不产生 webSearch 键）。
    service = read(CHAT_SERVICE)
    assert "if(input.webSearch)request.webSearch=true;" in service


def test_chat_service_omits_web_search_unless_explicitly_enabled() -> None:
    node = node_executable()
    if not node:
        pytest.skip("Node is required for the frontend request-body check")
    script = r'''
const assert = require('node:assert/strict');
const {createChatService} = require('./frontend/js/services/chat-service.js');
(async () => {
  const bodies = [];
  const fetchImpl = async (url, init) => {
    bodies.push(JSON.parse(init.body));
    const payload = {type: 'done', ok: true, answer: '受控回答。', sources: [], engine: 'controlled'};
    return new Response('data: ' + JSON.stringify(payload) + '\n\n', {headers: {'Content-Type': 'text/event-stream'}});
  };
  const service = createChatService({fetchImpl});
  await service.stream({question: '课程资料里的问题', sources: []}, {workflow: true});
  await service.stream({question: '课程资料里的问题', sources: [], webSearch: true}, {workflow: true});
  assert.equal(Object.prototype.hasOwnProperty.call(bodies[0], 'webSearch'), false, 'off must not send a webSearch key');
  assert.equal(bodies[1].webSearch, true, 'explicit enable must send webSearch=true');
  assert.ok(Array.isArray(bodies[0].sources), 'course sources stay in the request');
  assert.ok(Array.isArray(bodies[0].history), 'history stays in the request');
  console.log('web-search-request-contract-ok');
})().catch(error => { console.error(error); process.exit(1); });
'''
    checked = subprocess.run([node, "-e", script], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert checked.returncode == 0, checked.stderr or checked.stdout
    assert "web-search-request-contract-ok" in checked.stdout


def test_normalize_request_defaults_web_search_off() -> None:
    from backend.xueya.agent import normalize_request

    assert normalize_request({"question": "队列是什么？"})["webSearch"] is False
    assert normalize_request({"question": "队列是什么？", "webSearch": False})["webSearch"] is False
    assert normalize_request({"question": "队列是什么？", "webSearch": True})["webSearch"] is True


async def test_workflow_without_flag_never_calls_tavily(monkeypatch) -> None:
    from backend.xueya.agent import Agent
    from backend.xueya.config import Config

    calls = []

    async def forbidden(query, limit=5):
        calls.append((query, limit))
        raise AssertionError("联网搜索不应在开关关闭时执行")

    monkeypatch.setattr("backend.xueya.web_search.search_tavily", forbidden)

    class Model:
        config = Config(api_key="controlled-only", agent_planning_enabled=False)

        async def stream(self, messages, **options):
            yield {"type": "content", "text": "受控回答。"}

        async def generate(self, messages, **options):
            return {"content": "受控回答。", "model": "controlled"}

    events = [event async for event in Agent(Model()).workflow({"question": "请依据课程资料解释队列的先进先出。"})]
    assert calls == [], "关闭时任何路径都不得触达 Tavily"
    assert events[-1]["type"] == "done"
    assert all(not (isinstance(event, dict) and event.get("stage") == "web_search") for event in events)


async def test_direct_without_flag_never_calls_tavily(monkeypatch) -> None:
    from backend.xueya.agent import Agent
    from backend.xueya.common import AppError
    from backend.xueya.config import Config

    calls = []

    async def forbidden(query, limit=5):
        calls.append((query, limit))
        raise AssertionError("联网搜索不应在开关关闭时执行")

    monkeypatch.setattr("backend.xueya.web_search.search_tavily", forbidden)

    class Model:
        config = Config(api_key="controlled-only")

    with pytest.raises(AppError) as error:
        [event async for event in Agent(Model()).direct({"question": "请解释队列的先进先出。"})]
    assert error.value.code == "NO_SOURCES"
    assert calls == []


def test_dynamic_agent_tool_whitelist_cannot_reach_web_search() -> None:
    from backend.agent.tool_adapter import READ_ONLY_TOOLS, TOOL_DESCRIPTIONS

    assert "search_web" not in READ_ONLY_TOOLS
    assert "search_web" not in TOOL_DESCRIPTIONS
    durable = read(ROOT / "backend/xueya/durable_agent.py")
    assert "registry.allowed_tools = READ_ONLY_TOOLS" in durable
    integration = read(ROOT / "backend/xueya/learning_integration.py")
    assert "registry.allowed_tools = READ_ONLY_TOOLS" in integration


def test_only_the_guarded_web_search_path_calls_the_mcp_tool() -> None:
    from backend.xueya.agent import Agent

    direct = inspect.getsource(Agent.direct)
    assert 'if request.get("webSearch"):' in direct
    assert direct.index('if request.get("webSearch"):') < direct.index("search_tavily")

    learning = inspect.getsource(Agent._learning_stream)
    assert 'web_search_enabled = bool(request.get("webSearch"))' in learning
    assert "if web_search_enabled and not course_first:" in learning
    assert learning.index('web_search_enabled = bool(request.get("webSearch"))') < learning.index("self._web_search_stream(")
    assert "search_web" not in learning, "常规课程问答路径不得直接调用 search_web"

    web_stream = inspect.getsource(Agent._web_search_stream)
    assert 'session.call("search_web"' in web_stream
    assert "search_tavily" not in web_stream, "联网只应经 MCP 执行一次，禁止直连付费回放"


def test_frontend_never_calls_the_external_mcp_tools_endpoint() -> None:
    # /api/platform/tools* 会让任何持有 token 的外部 MCP 客户端显式调用 search_web；
    # 它不属于 UI 自动问答路径，前端源码不应触达。
    frontend = "".join(path.read_text(encoding="utf-8") for path in (ROOT / "frontend/js").rglob("*.js"))
    assert "/tools/call" not in frontend
    assert "/api/platform/tools" not in frontend
    routes = read(ROOT / "backend/xueya/app.py")
    assert 'if path == "/tools/call" and method == "POST":' in routes
    # 常规通用回答/RAG fallback 不引用联网模块，关闭时没有隐式联网。
    for relative in ("backend/agent/general_chat.py", "backend/xueya/rag_fallback.py"):
        source = read(ROOT / relative)
        assert "search_web" not in source and "tavily" not in source.lower(), relative


@pytest.mark.skipif(
    os.environ.get("XUEYA_RUN_BROWSER_LAB") != "1",
    reason="浏览器实验室需显式开启：XUEYA_RUN_BROWSER_LAB=1（隔离 server + Playwright）",
)
def test_browser_default_off_then_explicit_web_search_payload() -> None:
    from scripts.agent_lab import Server, browser_page

    output = ROOT / "test-results" / "agent-lab"
    output.mkdir(parents=True, exist_ok=True)
    # 隔离子进程：清空模型/搜索/共享向量密钥，测试不会产生任何付费请求。
    safe_env = {
        "MIMO_API_KEY": "",
        "TAVILY_API_KEY": "",
        "RAG_EMBEDDING_API_KEY": "",
        "RAG_OCR_API_KEY": "",
        "RAG_RERANK_API_KEY": "",
        "OPENAI_API_KEY": "",
        "XUEYA_SHARED_EMBEDDING": "0",
    }
    init_script = r"""
(() => {
  if (window.__xueyaLab) return;
  const original = window.fetch;
  window.__xueyaLab = {streams: []};
  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const isStream = url.indexOf('/api/agent/stream') !== -1 || url.indexOf('/api/ai/stream') !== -1;
    let record = null;
    if (isStream) {
      record = {url, body: init && typeof init.body === 'string' ? init.body : '', responseText: null, done: false, error: null};
      window.__xueyaLab.streams.push(record);
    }
    const response = await original(input, init);
    if (record) {
      try {
        response.clone().text().then(
          text => { record.responseText = text; record.done = true; },
          error => { record.error = String(error); record.done = true; }
        );
      } catch (error) {
        record.error = String(error);
        record.done = true;
      }
    }
    return response;
  };
})();
"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        with Server(name=f"web-search-toggle-{os.getpid()}", fresh=True, env=safe_env) as server:
            session = server.register()
            with browser_page(server.base, session=session, viewport={"width": 1440, "height": 1000}) as (page, context, errors):
                page.add_init_script(init_script)
                page.goto(server.base + "/#space/ask", wait_until="networkidle", timeout=90000)
                page.wait_for_selector("#chatForm [data-toggle-web-search]", timeout=60000)

                def button_state():
                    return page.evaluate(
                        "() => {const b = document.querySelector('[data-toggle-web-search]');"
                        "return {pressed: b.getAttribute('aria-pressed'), label: b.getAttribute('aria-label'),"
                        "title: b.getAttribute('title'), text: b.innerText};}"
                    )

                initial = button_state()
                assert initial["pressed"] == "false", initial
                assert initial["label"] == WEB_SEARCH_ARIA, initial
                assert WEB_SEARCH_LABEL in initial["text"] and "全网" not in initial["text"], initial
                assert WEB_SEARCH_LABEL in (initial["title"] or ""), initial
                assert page.locator(".composer-web-hint").count() >= 1
                assert COURSE_MATERIAL_HINT in page.locator(".composer-web-hint").first.inner_text()
                page.screenshot(path=str(output / "search-toggle-off.png"), full_page=True)

                # 新的浏览器存储：刷新后仍默认关闭（开关不写入 localStorage）。
                page.reload(wait_until="networkidle", timeout=90000)
                page.wait_for_selector("#chatForm [data-toggle-web-search]", timeout=60000)
                assert button_state()["pressed"] == "false"

                page.fill("#chatInput", "请依据课程资料解释队列的先进先出。")
                page.click("#chatForm .send-button")
                page.wait_for_function(
                    "window.__xueyaLab && window.__xueyaLab.streams.length >= 1 && window.__xueyaLab.streams[0].done === true",
                    timeout=120000,
                )
                first = page.evaluate("window.__xueyaLab.streams[0]")
                first_body = json.loads(first["body"])
                assert "webSearch" not in first_body, first_body
                assert "sources" in first_body
                first_response = (first["responseText"] or "").replace(" ", "")
                assert "search_web" not in first_response, first_response[:3000]
                assert "web_search" not in first_response, first_response[:3000]
                page.wait_for_function("!document.querySelector('#chatForm .stop-button')", timeout=60000)

                # 切换开关：草稿与已有对话都要保留，aria/toast 同步。
                page.fill("#chatInput", "这段草稿应在切换开关后保留。")
                page.click("[data-toggle-web-search]")
                assert button_state()["pressed"] == "true"
                page.wait_for_function(
                    "document.querySelector('#toast')?.classList.contains('show')"
                    " && document.querySelector('#toast').textContent.includes('联网搜索已开启')",
                    timeout=15000,
                )
                assert "课程知识库始终参与检索" in page.inner_text("#toast")
                assert page.input_value("#chatInput") == "这段草稿应在切换开关后保留。"
                assert "请依据课程资料解释队列的先进先出。" in page.inner_text("#chatThread")
                page.wait_for_function("!document.querySelector('#toast').classList.contains('show')", timeout=15000)
                page.wait_for_timeout(600)  # 等 toast 的 200ms 淡出结束，截图只展示开关本身
                page.screenshot(path=str(output / "search-toggle-on.png"), full_page=True)

                page.fill("#chatInput", "联网搜索一下队列和栈的区别。")
                page.click("#chatForm .send-button")
                page.wait_for_function(
                    "window.__xueyaLab && window.__xueyaLab.streams.length >= 2 && window.__xueyaLab.streams[1].done === true",
                    timeout=120000,
                )
                second = page.evaluate("window.__xueyaLab.streams[1]")
                second_body = json.loads(second["body"])
                assert second_body.get("webSearch") is True, second_body
                second_response = (second["responseText"] or "").replace(" ", "")
                assert '"stage":"web_search"' in second_response, second_response[:3000]
                assert '"tool":"search_web"' in second_response, second_response[:3000]
                assert "TAVILY_API_KEY_NOT_CONFIGURED" in second_response, "隔离环境不得产生真实联网调用"
                page.wait_for_function("!document.querySelector('#chatForm .stop-button')", timeout=60000)
                assert not errors, errors
