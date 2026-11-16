# AGENT_PLAN — 无人值守系统优化总计划

> 本文件是本次无人值守开发的唯一任务总表。每个子任务都有明确验收标准与负责人。
> 进度写入 `AGENT_PROGRESS.md`，问题写入 `AGENT_ISSUES.md`，测试结果写入 `AGENT_TEST_REPORT.md`。
> 最后更新：2026-11-15（会话开始）

## 0. 项目事实（已实际核对）

- 形态：**Python/FastAPI 后端 + 原生 HTML/CSS/JS 前端**，单机单用户，AI 推理只调用外部 API。
- 主入口：`backend/xueya/server.py`（默认 127.0.0.1:4173，`.xueya-data/workspace.sqlite`）。
- 前端：`frontend/index.html` 加载 `frontend/js/*.js`；独立算法演示页 `frontend/algorithm-demo.html` + `frontend/js/algorithm-lab.js`。
- 算法题库：`backend/xueya/data/practice_bank.json`（Hot100 100 题 + basic 100 + interview 50）、`hot100_official.json`（100 题官方编号/专题，17 个专题）、`exam408_bank.json`（300 题）。
- 工作台接口：`backend/xueya/study_space_api.py`（`/api/learning/space/*`）；练习接口：`backend/xueya/practice_api.py`（`/api/practice/*`）；题库目录：`backend/xueya/practice_catalog.py`。
- RAG：`backend/xueya/rag_service.py` + `rag_api.py`（EmbeddingProvider）+ `rag_moark.py`（QwenEmbeddingProvider）；真实 `.env` 配置为 **Qwen3-VL-Embedding-8B / 4096 维**（key 存在，禁止输出）。
- 桌宠：`frontend/js/study-companion.js`，当前通过 `window.XueyaAskInline`（app.js）走课程 RAG/通用问答。
- 主问答：`frontend/js/ui/workspace-views.js` 的 composer（`data-toggle-web-search`）、`frontend/js/workspace-controller.js`（`state.webSearch`）、`frontend/js/app.js#ask`、`backend/xueya/agent.py`（webSearch 分支）。
- 交互演示现状：后端 `algorithm_trace.py` **仅支持 h100-63(#35) 与 h100-53(#200)**；前端 `algorithm-lab.js` 为这两题写死渲染；`practice-view.js` 第 225/651 行写死这两个 id。
- 验证设施：`pytest`（tests/python + tests_python）、`node scripts/test.js --frontend`、Playwright 浏览器检查（`scripts/check_*_browser.py`）。本次新增 `scripts/agent_lab.py`：隔离数据目录 + 注册测试账号 + 浏览器会话（已解决本机 Temp 权限问题）。
- 当前 Git 分支：`codex/unattended-overhaul-20261115`（从 `codex/course-shelf-portable-rag` 的已提交状态建立；main 为该分支祖先）。
- **硬约束**：不得读取/输出/提交 `.env` 中的密钥；不得修改生产 `.xueya-data/workspace.sqlite` 做破坏性操作；测试一律用隔离数据目录；不删除既有测试来"通过"。

## 1. 任务分解（WBS）

### T1 「去提问」入口导航修复（最高优先级，Lead）
- 位置：`frontend/js/overview-view.js`（#space/overview 的 AI 伴学助手卡片，#overviewPromptInput/#overviewSubmitPromptBtn/快捷问题 chips）→ `app.js#ask`。
- 要求：点击「提问」进入提问页 `#space/ask`，问题与上下文正确进入主问答；快捷 chips 同样行为；不破坏其他导航。
- 验收：浏览器实测（隔离账号）：点击按钮 → hash=#space/ask、输入问题出现在对话线程、请求带 courseId/documentIds/课程 sources；空输入不跳转；控制台无错误。
- 状态：DONE（2026-11-16 复验：t1.overview-ask / t1.overview-chips / t1.real-answer 全部 PASS；约修复见 AGENT_ISSUES）

### T2 桌宠 → 系统专业 AI 助手（文档 + RAG + 对话）（companion-rag 负责，Lead 集成）
- T2A 系统全面分析（阅读真实代码/路由/组件，不臆测）→ 输出到 `docs/guide/`。
- T2B 系统百科 Markdown（≥10 篇：总览、功能总览、页面/路由目录、课程学习、算法学习、408 学习、个人资料库、AI 助手/主问答、学习计划/分析、错题/练习、设置/账号/数据、常见问题、功能索引、功能限制）。
- T2C 桌宠专属 RAG：`materials/system-guide/` 切分与向量索引（Qwen3-VL-Embedding-8B，4096 维；与课程 RAG 逻辑隔离；内容哈希去重；增量构建/重建/校验脚本 `scripts/build_system_guide_vectors.py`；运行时 `backend/xueya/companion_knowledge.py`；检索返回功能名/路径/步骤；资料不足明确说明）。
- T2D 对话集成：新端点 `POST /api/learning/space/companion/chat`；系统类问题检索百科后作答并返回可点击导航 links；普通问题走通用问答；检索失败/模型不可用有降级与明确提示。
- T2E 测试：真实 embedding 调用验证 4096 维与检索命中；≥8 类查询（功能介绍/位置/步骤/多轮/普通聊天/不存在功能/检索失败/API 不可用）；浏览器实测桌宠对话。
- 验收：文档真实覆盖系统功能；向量文件带 manifest（model/dimension/维度校验/内容哈希）；检索接口真实返回相关片段；不存在功能明确说没有；普通聊天不受影响。
- 状态：DONE（17 篇文档 + 131 chunks×4096 维真实向量 + companion 端点 + 桌宠 UI；25 项验收中 7 项 T2 检查全 PASS）

### T3 AI 助手检索机制（assistant-search 负责前端 + 审计；Lead 做后端必要修改）
- UI 文案：`全网 + 课程知识库混合检索` → `联网搜索`；默认关闭；课程知识库默认检索（无需勾选）。
- 逻辑：`state.webSearch` 默认 false（首次进入）；关闭时任何路径都不得触发 Tavily/联网（含 MCP 工具、回退、durable agent）；开启后才检索互联网并结合课程资料。
- 保持聊天记录、引用、流式输出正常；UI 状态与实际请求参数一致。
- 验收：代码审计 + 单元测试 + 浏览器实测（关闭时无 search_web 事件/网络请求；开启时出现）；文案/aria/title 一致。
- 状态：DONE（t3.toggle-ui / t3.payloads / t3.search-events 全部 PASS；后端默认白名单不含 search_web）

### T4 算法学习模块（ui-practice + demo-engine + demo-frontend）
- T4.1 删除「返回算法学习」按钮（`practice-view.js` hot100Toolbar），布局正常，不影响浏览器返回。
- T4.2 搜索框放大镜图标垂直居中（`.hot100-search-wrap` 图标与输入行几何中心对齐；1440/1024/390 宽度验证）。
- T4.3 知识点分类完整性：审计 100 题 ↔ 官方 17 专题映射（当前已确认数据 100/100 且每题 tags 含 topic）；修复「全部知识点」视图遗漏/找不到问题：用官方 topic 生成知识点导航与计数（17 组并集=100），列表按知识点分组或保持全量，筛选后选中题滚入可视区；补回归测试；不得硬编码 #200 特例。
- T4.5 代码编辑器初始内容：首次打开显示可写的骨架（类/签名/参数，无核心实现），三语言；用户已保存代码不覆盖；「查看完整题解」仍可用；判题不受影响。
- T4.4 全题库 3D 交互演示：
  - 后端：通用追踪引擎（执行官方 Python 参考解，记录真实状态变化；校验 result==sample.output；设计类 4 题单独实现；trace 缓存）；接口沿用 `GET /api/learning/space/algorithm-demo/{id}?sample=N`，返回 **demo-2 schema**（见 §2）。
  - 前端：重写 `algorithm-lab.js` 为数据驱动 3D 演示（grid/matrix/array/tree/linked-list/graph/dp/string/stack-queue/backtracking/design），步骤/播放/暂停/重置/调速/当前状态/关键高亮/示例输入输出/文字解释/拖拽旋转缩放。
  - 集成：`frontend/js/algorithm-demo-registry.js`（由脚本从后端导出）驱动练习列表「交互演示」标记与详情「打开交互演示」入口；替换写死 id。
  - 验收：逐题校验 trace 最终结果与官方样例一致；无渲染错误/控制台错误；演示覆盖数量真实统计（禁止空壳/同一无关动画冒充）。
- 状态：DONE（T4.1/T4.2/T4.3/T4.4/T4.5 共 8 项浏览器+数据检查 PASS；Hot100 100/100 演示，213/213 样例校验）

### T5 回归与最终验收（verifier 负责，Lead 复核）
- 基线：`python -m pytest -q`、`node scripts/test.js --frontend` 结果记录。
- 新增端到端：`scripts/check_agent_overhaul_browser.py`（任务一/T3/T4 UI/桌宠/T4.4 演示）。
- 输出 `AGENT_TEST_REPORT.md`、`AGENT_FINAL_REPORT.md`；统计算法演示覆盖数量、RAG 真实检索结果。
- 状态：DONE（scripts/check_agent_overhaul_browser.py：PASS 25 / FAIL 0 / SKIP 0，238.9s；报告 AGENT_TEST_REPORT.md）

## 2. 关键契约（跨人并行必须遵守）

### 2.1 算法演示 trace schema v2（demo-engine 实现，demo-frontend 消费）
`GET /api/learning/space/algorithm-demo/{id}?sample=N` →
```json
{"ok":true,"demo":{"schemaVersion":"demo-2","questionId":"h100-53","title":"岛屿数量","number":200,
 "topic":"图论","difficulty":"中等","sample":{...},"sampleIndex":0,"sampleCount":2,
 "inputs":{"grid":[...]},
 "code":["第1行...","第2行..."],"codeLanguage":"python",
 "viz":"grid","layout":{"primary":"grid","pointers":["r","c"],"legend":[...]},
 "steps":[{"line":3,"note":"...","state":{"grid":[...],"visited":[...],"count":1},"highlight":["count"]}],
 "result":1,"meta":{"coreIdea":"...","hints":[...],"complexity":{...},
 "summary":"..."},"warnings":[]}}
```
- `viz` ∈ array|matrix|grid|tree|linked-list|graph|dp|string|stack-queue|backtracking|design|scalar。
- `state` 必须 JSON-safe、单步快照；`note` 中文可读；`line` 为 `code` 的 1-based 行号（无对应行时可为 0）。
- 向后兼容：旧字段缺失时前端可降级；旧的 h100-63/h100-53 响应允许保留旧字段，但必须包含 schemaVersion=demo-2。
- 任何错误返回 `{ok:false,error:'DEMO_*'}`，不得返回伪造步骤。

### 2.2 演示注册表
`frontend/js/algorithm-demo-registry.js`：
```js
window.XueyaAlgorithmDemoIds=['h100-63','h100-53',...];
window.XueyaAlgorithmDemoMeta={'h100-53':{viz:'grid',title:'岛屿数量'},...};
```
由 `scripts/export_algorithm_demos.py --write` 从后端 `algorithm_demo.available_ids()` 生成；`--check` 模式只校验是否最新。

### 2.3 桌宠接口
`POST /api/learning/space/companion/chat`，请求 `{question, history:[{role,content}], courseId}`；
响应 `{ok:true,reply:{status:'ok'|'not_found'|'unavailable',route:'system'|'general',engine,answer,
sources:[{title,path,location,excerpt}],links:[{title,hash}],confidence,modelUsed}}`。
- 与课程 RAG 隔离：系统百科向量文件位于 `materials/system-guide/`，不写入用户课程向量表。
- 不含密钥/凭据；`links.hash` 仅限已存在的路由。

### 2.4 初始代码骨架
`backend/xueya/data/hot100_starters.json`：`{version, questions:{id:{python,cpp,java}}}`。
`practice_bank.load()` 校验并附加 `q['starterCode']`（三语言均含题目要求的方法签名，无解题实现）。
前端：初次打开题目编辑器显示 starterCode；用户已保存代码/草稿优先；`查看完整题解` 逻辑不变。

## 3. 并行写入范围（避免冲突）
| 工作流 | 独占写入 |
| --- | --- |
| Lead | `frontend/js/app.js`、`frontend/js/overview-view.js`、`backend/xueya/agent.py`、`backend/xueya/app.py`（路由注册）、`scripts/agent_lab.py`、`AGENT_*.md`、`backend/xueya/study_space_api.py`（companion 端点注册，与 verifier 协调） |
| ui-practice | `frontend/js/practice-view.js`、`frontend/css/stitch-theme.css`（仅 practice 相关段）、`backend/xueya/practice_bank.py`、`backend/xueya/data/hot100_starters.json`、`scripts/build_practice_starters.py`、`tests_python/test_practice_*.py`（新增文件） |
| demo-engine | `backend/xueya/algorithm_demo.py`（新）、`backend/xueya/algorithm_trace.py`、`scripts/export_algorithm_demos.py`、`tests_python/test_algorithm_demo.py`（新） |
| demo-frontend | `frontend/js/algorithm-lab.js`、`frontend/css/algorithm-lab.css`、`frontend/js/algorithm-demo-registry.js`（生成文件）、`frontend/algorithm-demo.html` |
| companion-rag | `docs/guide/**`、`materials/system-guide/**`、`scripts/build_system_guide_vectors.py`、`backend/xueya/companion_knowledge.py`、`backend/xueya/companion_api.py`、`frontend/js/study-companion.js`、`tests_python/test_companion_*.py` |
| assistant-search | `frontend/js/ui/workspace-views.js`、`frontend/js/workspace-controller.js`、`tests/python/test_web_search*.py`（新增）、只读审计 `backend/xueya/agent.py` |
| verifier | `scripts/check_agent_overhaul_browser.py`、`AGENT_TEST_REPORT.md`、只读其余 |

> 禁止同时修改同一文件。确需跨界时先在任务里说明并由 Lead 调整。所有编辑前先读文件；使用 edit 精准替换。
> 运行服务一律用隔离数据目录（`scripts.agent_lab.Server`），不得重启/打断 4173 生产服务，不得写生产库。

## 4. 执行顺序
1. 基线（Git 检查点、pytest/前端测试基线）→ 2. T1/T3/T4.1/4.2/4.5/T4.3（前端与数据）→ 3. T2 文档+向量+桌宠 → 4. T4.4（引擎→渲染→分批验证）→ 5. 全面回归 + 报告。
依赖：demo-frontend 依赖 demo-engine 的 schema（契约已固定，可并行）；companion 前端依赖 Lead 提供 app.js 挂点（Lead 先改 app.js 接口调用，companion-rag 提供后端与 UI 组件）。

## 5. 验收与状态
状态：TODO / IN_PROGRESS / VERIFYING / DONE / BLOCKED / FAILED。只有实跑测试通过才标 DONE。
