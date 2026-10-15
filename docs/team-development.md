# 四人协作开发指南

本次整理只拆分代码职责，保留现有功能。首次分工前，先把这一版整理合并并推送到 `main`，四位成员再从同一个最新版本创建分支。

## 分工与文件归属

| 任务 | 建议首轮分支 | 主要维护文件 | 验收重点 |
| --- | --- | --- | --- |
| A：界面美化 | `feat/ui-polish` | `frontend/index.html`、`frontend/css/`、`frontend/js/ui/`、`visual.js`、`pointer.js`、`motion.js` | 页面、响应式、键盘操作、加载和错误状态 |
| B：RAG | `feat/rag-pipeline` | `shared/rag/`、`backend/rag/`（含 PDF/DOCX 解析器）、`frontend/js/services/library-service.js`、`shared/fixtures/` | 文档解析、分段、检索、正确出处、无资料时不编造 |
| C：Agent | `feat/agent-workflow` | `backend/agent/`、`backend/providers/`、前端问答/出题服务、`shared/agent/` | 流式问答、上下文、资料约束、引用校验、知识点与题库、模型失败回退 |
| D：MCP | `feat/mcp-integration` | `backend/mcp/` | 工具发现、命名、适配真实客户端、调用、超时与取消 |

每个人同时负责自己模块的测试。`tests/unit/modules.test.js` 是首次整理的跨模块契约回归；新增功能可以分别在 `tests/unit/` 或 `tests/integration/` 新建对应的 `*.test.js`，避免四人持续修改同一个测试文件。

## 公共文件与联调负责人

以下文件不属于某个独立功能，改动前需要相关成员确认：

- `shared/contracts/index.js`：跨模块数据格式、模式和限制。B/C/A 共同使用；D 的工具格式也在此约定。
- `shared/learning.js`：旧接口兼容入口，不继续堆放新的检索或 Agent 逻辑。
- `frontend/js/app.js`：页面状态、存储、路由与事件。UI 由 A 维护，涉及资料或聊天的数据交互时与 B/C 协调。
- `backend/app.js`：装配模块、HTTP 路由；新增 RAG 或 MCP 实例在这里接入。
- `backend/server.js`：启动服务；功能逻辑不再写进这个文件。
- `backend/config.js`、`backend/http/`、`package.json`、`.env.example`：由联调负责人统筹。

联调负责人可由 C 或项目负责人兼任。各模块应通过导出的函数调用，避免跨模块修改内部实现。模块接口有变化时，PR 中写清对其他成员的影响。

## 当前连接关系

```text
页面与控制器（A）
  ├─ 资料服务（B）→ TXT/MD 读取或 /api/parse 文档解析 → 共用分段 → 浏览器保存资料
  └─ 问答服务（C）→ 共用关键词检索（B）
       ├─ /api/ai/stream（兼容 /api/ai）→ Agent（C）→ RAG 来源规范化（B）→ 模型适配器（C）
       └─ 请求失败或 file: 预览 → 本地摘录（C）

Agent 的显式工具调用入口（C）→ 工具网关（D）→ 后续真实 MCP 客户端适配器
题库界面（A）→ 出题服务（C）→ /api/topics、/api/questions → Agent 练习模块（C）
```

当前前端先检索，后端接收已选的来源；详细契约见 [接口约定](api-contracts.md)。后端 RAG 的异步 `ingest`、`retrieve`、`parseDocument` 可以独立开发和验证。`/api/parse` 只临时接收文件以返回文本，不保存文件。要把资料迁入向量库，B/C 应一起约定持久化、资料 ID、检索接口和访问范围，再接入。

## 每个人怎样开始

以 A 为例，在没有未提交改动时：

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/ui-polish
```

其他成员替换为自己的分支名称。每个分支保留完整项目，不能删除其他人负责的目录。分支名称是首轮任务的例子，后续按具体小任务重新创建分支。

提交前先检查文件，避免上传依赖、真实资料、密钥或构建产物：

```bash
git status
git add 你实际修改的文件路径
git commit -m "说明本次修改"
git push -u origin feat/ui-polish
```

`git add` 后面的文字要替换成实际文件路径。`.env` 已在忽略规则中，每个人按 `.env.example` 配置自己的本地密钥。

## PR 与合并规则

1. 尽早提交小 PR：一次集中完成一个可验证的改动，base 选 `main`，compare 选自己的分支。
2. 相关成员检查接口和文件归属；联调负责人检查整条学习流程。
3. 无未提交改动时，在自己的功能分支运行 `git fetch origin`、`git merge origin/main`。同步后处理冲突并重新验证。
4. 合并前运行 `node --test`。UI 或端到端流程变化时，另运行 `node tests/e2e/browser.js`（需 Playwright 和浏览器）。
5. 合并后删除完成的任务分支。下一个任务重新从最新 `main` 创建分支。

自动合并不代表运行正确。特别检查：来源字段、请求格式、模型输出、工具返回格式和 CSS/DOM 选择器是否仍然一致。冲突时由相关成员一起确认最终内容，不要整文件直接选“保留我的”。

## 推荐开发顺序

- A 使用固定的来源与回答数据制作 UI，不依赖外部服务。
- B 先验证 TXT/MD、文本型 PDF 与 DOCX 的解析和检索，再分批增加解析器覆盖或向量库适配。
- C 保持流式课程问答、知识点与出题功能，再接入多步骤工作流；错误不能丢失本地回退。
- D 先连接一个明确需要的 MCP 服务，通过网关向 C 提供工具；客户端连接、凭据、输入验证和关闭连接由 D 的适配器负责。
- 先打通“上传 → 问答 → 引用 → 保存”，再增加外部工具路径。MCP 工具不要求每次问答都执行。

## 当前能力边界

- RAG 仍是浏览器保存资料、关键词检索，尚无向量数据库或账号隔离。
- TXT/MD 能解析；PDF/DOCX 已接入服务端基础文本解析，扫描件没有 OCR，解析失败仍保留待解析记录。
- MCP 网关已具备可测试的注册、适配、发现和调用接口，但未安装 MCP SDK、未连接外部服务，默认工具列表为空。
- 不改变现有 localStorage 键、资料 ID、历史引用和启动方式。真实密钥只由后端读取。
