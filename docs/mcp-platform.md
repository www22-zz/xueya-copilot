# Python MCP 工具平台开发指南

对应 D 大任务；当前使用官方 `mcp==2.3.0` Python SDK，依赖及传递依赖锁在根 `requirements.lock`。前端、公共 HTTP 字段和工具名不因迁移改变。启动和数据维护见[平台指南](platform-guide.md)。

## 入口

```python
from backend.xueya.mcp_core import open_session, platform_registry

scope = platform.scope("course-default")  # 只能来自可信宿主
async with open_session(platform_registry(platform, scope)) as session:
    tools = await session.list_tools(namespace=True)
    data = await session.call("list_notes", {"limit": 20})
```

`open_session(stdio=True, context=normalized_context)` 使用四工具真实 stdio 服务；`stdio_params=StdioServerParameters(...)` 可对接宿主指定的可信服务。命令、URL、Token 均不能由模型参数指定。`Registry/create_server` 提供低层官方 SDK 注册入口，可由 B/C 注入异步业务函数；业务算法归 B/C，协议治理归 D。

平台工具协议结果为 `{schemaVersion:'2.0',data:...}`，`session.call` 自动解包；兼容四工具保持原结果。工具结果版本与 MCP 协议版本独立。

## 工具与范围

默认 HTTP 宿主向 `platform_registry` 注入 B 的 `rag` 和 C 的 `learning`。资料检索使用 B；学习查询合并旧实体与 C 产物，`analyze_progress` / `list_wrong_questions` 纳入已评分 C 测验。新工具 `get_review_queue` 返回 C 的实际 FSRS 到期队列，`get_course_graph` 返回课程图谱。直接调用工厂时可显式传入 `rag=...`、`learning=...`；未注入时保留兼容行为。

| 工具 | 参数 |
| --- | --- |
| `search_materials` | query、limit 默认 4/最大 6 |
| `read_source` | sourceId |
| `list_sections`、`list_concepts`、`list_question_drafts`、`list_attempts`、`list_wrong_questions`、`list_reviews`、`list_plans`、`list_notes` | cursor、limit 默认 20/最大 50 |
| `read_section` | sectionId、cursor、limit |
| `analyze_progress`、`build_review_plan` | 空对象；读取宿主范围和设置 |
| `prepare_action` | kind、entityId、expectedVersion、after |
| `preview_action`、`apply_action` | actionId |
| `lookup_reference` | doi；仅在宿主显式启用时发现 |

平台工具严格拒绝额外参数，模型不能传 sources/userId/courseId 来覆盖范围。范围是不可变 `Scope(user_id,course_id)`；所有仓库查询按两者过滤，分页游标同样绑定范围。当前没有真实先修关系业务，不广告 `get_prerequisites`；空概念列表只表示尚无记录，不伪造算法结果。

## 写入流程

1. `prepare_action` 只创建持久化预览：before/after、版本、来源版本与摘要、到期时间、digest。
2. 在宿主 UI 展示预览，用户通过同源、有 nonce 的 `/api/platform/actions/confirm` 明确确认。**确认永远不注册为模型工具。**
3. 在新工具会话调用 `apply_action`，只执行确认过的精确内容。
4. 一个 SQLite 事务校验实体 CAS/来源版本，并保存数据、审计和幂等 receipt，同时更新浏览器兼容 workspace 版本。

默认有效期 5 分钟，最多 100 个待处理动作。跨课程、内容摘要不符、过期、来源变化或 CAS 冲突拒绝写入。重复已成功执行返回同一 receipt；执行中断先查 receipt，存在则恢复 applied，否则 uncertain，不自动重放。

笔记 after 为 `{title,content,sourceIds}`，题目为 `{prompt,answer,sourceIds}`，计划为 `{title,days:[{date,tasks:[{title,minutes}]}]}`。字段和日期严格验证。没有确认不会写入业务实体。

## 调用治理

`gateway.ToolGateway` 提供宿主白名单、服务命名空间、JSON Schema 校验、参数 64KiB/结果 128KiB、默认并发 4、64 次调用/64 成本单位、60 秒生命周期与超时。成本单位是调用预算，不能当作真实 API 费用。远端工具只读注释不会自动授予权限；风险由宿主登记，默认 unknown。发现失败不部分注册。

`Session` 对 SDK 发现执行分页、重复名/游标、128 工具/256KiB 上限检查，并控制每次调用。stdio 最多 4 个拥有的子进程，进程内连接最多 8，工具执行最多 8。超时/取消后，未退出的执行仍持有许可；不通过提前释放许可突破上限。

## Streamable HTTP

`mcp_http.create_mcp_http_app(platform, authenticate=..., allowed_hosts=..., allowed_origins=...)` 返回可由 Uvicorn 运行的 ASGI 应用。认证函数从可信宿主验证请求，返回 Scope；每个请求将该 Scope 绑定给官方 SDK 处理器。支持多课程范围，身份不取自工具 JSON。

`connect_http(url, allowed_origins=[...], token=..., protocol='2026-07-28')` 对接可信端点；兼容 `protocol='legacy'`。默认要求 HTTPS，只有明确 `allow_localhost=True` 才允许回环 HTTP。拒绝非白名单域、URL 凭据、query/fragment、重定向；响应流上限 512KiB，连接最多 4，超时 5 秒、生命周期 60 秒。

服务端固定 `/mcp`，校验 Host/Origin、认证、256KiB 请求上限、并发 8、每范围每分钟 120 次。当前 stateless 服务只接受 POST，GET 返回 405；新旧协议协商与取消由官方 SDK 处理。默认本机学习服务未开放此独立远程端点，多人认证/OAuth/公网 TLS 仍是后续工程范围。

## 可选公开参考文献

显式 `reference=True` 才启用 Crossref DOI 查询。只能发送 DOI，固定 `https://api.crossref.org/works/`，禁止任意 URL；5 秒/256KiB/并发 4，核对返回 DOI，输出 `courseEvidence:false`。公开元数据不能冒充课程证据，不发送课程原文或模型密钥。

## 验证与交接

```powershell
.venv/Scripts/python.exe -m backend.xueya.mcp_server --check
.venv/Scripts/python.exe -m pytest -q tests/python/test_mcp.py
```

覆盖真实 stdio、官方进程内客户端、现代/legacy HTTP、取消、退出清理、范围、分页、确认/CAS/receipt、预算和异常结果。API/跨模块测试另见 `tests/python/`，真实浏览器确认流程见 `tests/e2e/platform.js`。

新增工具先确定 B/C 服务端口和 E 的持久化语义，再在 Registry 注册严格 schema，并补范围/异常/取消测试。不能为接 MCP 在 D 中复制另一套资料库、学习算法或任意文件/命令执行工具。
