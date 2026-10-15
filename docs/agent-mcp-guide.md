# Agent 工作流与 MCP 使用指南

## 安装与启动

需要 Node.js 20 或更新版本。首次下载或同步此版本后，在项目根目录执行：

```bash
npm ci
npm start
```

项目锁定官方 MCP Client/Server SDK 和 Zod 依赖，`npm ci` 按 `package-lock.json` 安装。直接使用 `node backend/server.js` 启动也可以，但仍需先安装依赖。现有 `.env` 中的 MiMo 配置继续使用；MCP 本地工具不需要新密钥。

## 可以直接试的任务

在资料问答中输入：

- “二叉搜索树的查找复杂度是什么？”——检索、核对原文，再生成带引用的答案。
- “总结二叉搜索树的查找复杂度。”——检索相关来源并整理知识重点。
- 使用“开放练习”模式提问——依据原文整理练习与参考内容；原有“AI 题库”仍负责持久化选择题。
- “我有哪些薄弱知识点？”——从近期作答统计待巩固内容和到期复习项。
- “帮我安排一份复习计划。”——按当前考试日期、每日时长与近期错题生成计划预览。

回答过程中可以看到处理阶段；完成后展开“查看处理过程”查看已完成或已回退的步骤。计划预览不会自动替换现有计划。统计和日期使用实际学习规则计算，不依赖模型重新计算；考试日期已过时会明确提示更新。

支持连续追问“再解释一下”或点击“继续追问”：检索会参考近期用户问题，并核对当前仍有效的上一轮来源。历史回答不会被当作原文，已从当前资料目录移除的材料不会重新加入检索。

生成过程中可点击“停止生成”。这会取消请求并通知后端停止工具或模型工作；未校验的半段回答不会保存为正式答案，输入框会保留问题，便于修改和重试。超时或网络失败则使用本地回退；网络断开或直接打开 HTML 时，薄弱点分析和复习计划仍可依据浏览器已有记录完成。

## 工作流结构

```text
浏览器提供有界的课程与学习上下文
  → 规则路由：问答 / 总结 / 开放练习 / 薄弱点 / 计划
  → 建立独立 MCP stdio 连接并发现课程工具
  → 课程任务：搜索资料 → 按 ID 核对原文 → 模型生成 → 来源检查
  → 学习任务：分析作答 → 生成计划预览 → 返回实际计算结果
  → 关闭 MCP 连接，清理所属子进程
```

这是结构化工作流，工具顺序由应用的任务路由控制，不是让模型无限自主调用任意工具。每次请求最多检索一次、读取三个片段，或执行分析和计划两步。将来若引入模型工具循环，应另加轮数、重复调用、总时长和权限边界测试。

## 四个真实 MCP 工具

| 服务工具 | 网关名称 | 作用 |
| --- | --- | --- |
| `search_materials` | `course__search_materials` | 检索本请求中的课程原文 |
| `read_source` | `course__read_source` | 按稳定 ID 核对原文与位置 |
| `analyze_progress` | `course__analyze_progress` | 统计近期正确率、薄弱点与到期复习项 |
| `build_review_plan` | `course__build_review_plan` | 计算最多七天的复习计划预览 |

实现使用官方 SDK 的初始化、工具发现、调用和关闭流程，不是普通函数调用冒充 MCP。服务通过 stdio 的 JSON-RPC 通信，stdout 只用于协议；无文件扫描、文件写入或联网搜索工具。

每个请求使用独立服务连接，资料和作答作为本次上下文传入，不在工具服务里持久化。网关绑定上下文，工具参数不能覆盖绑定的资料或学习记录。工具服务不读取项目 `.env`，也不继承 MiMo 密钥。

## 开发入口

| 文件 | 负责人和用途 |
| --- | --- |
| `backend/agent/learning-workflow.js` | C：任务路由、阶段、编排、回退与结果检查 |
| `backend/mcp/course-server.js` | D：MCP 工具注册、参数验证和工具实现 |
| `backend/mcp/stdio-client.js` | D：连接、分页发现、调用、取消与关闭 |
| `backend/mcp/course-session.js` | C/D：工具白名单和请求上下文绑定 |
| `shared/agent/context.js` | 共同维护：有界课程与学习上下文 |
| `shared/agent/tasks.js` | C：共享任务路由、追问检索语境、学习统计与计划格式 |
| `frontend/js/services/chat-service.js` | C：调用 Agent 接口，处理阶段和流式结果 |
| `frontend/js/ui/views.js` | A：阶段与处理过程的显示 |

原有 `backend/agent/index.js`、题库接口和工具网关继续保留。RAG 的关键词检索规则仍位于 `shared/rag/`；D 修改工具适配时不必修改页面，B 后续接向量检索时应保持来源 ID 与真实原文契约。

## 独立检查 MCP

```bash
npm run mcp:check
```

检查会真正启动服务、发现四个工具、检索内置示例并关闭连接。也可用 `node backend/mcp/check.js`。整个检查不调用付费模型。

```bash
npm run mcp:server
```

此命令启动等待 MCP 客户端连接的 stdio 服务；通常由应用或其他 MCP 宿主启动，无需在启动网页前手动运行。

若在其他 MCP 宿主中使用，可配置 Node 命令和 `backend/mcp/course-server.js` 的绝对路径。该服务是无状态工具服务，外部客户端需按发现的参数 schema 提供原文或学习记录，不能直接读取网页 localStorage。使用 `connectStdio` 加 `registerServer` 可以适配其他可信 stdio 服务，但当前 Agent 只使用固定的课程工具白名单，不会自动执行新发现的任意工具。

## 接口与边界

- 新接口：`POST /api/agent`、`POST /api/agent/stream`。
- 原接口：`/api/ai`、`/api/ai/stream`、资料解析和出题接口保持兼容。
- 默认工具超时 5 秒，可通过 `.env` 的 `MCP_TOOL_TIMEOUT_MS` 调整到 1～10 秒。
- 上下文最多 48 个候选片段，每段 1500 字符；优先放入浏览器已有检索命中。题目元信息最多 100 条，最近作答最多 120 条，问题和历史继续沿用已有上限。
- 可选 `context.previousSourceIds` 最多三个，并且必须属于本次 `context.library`。只用于泛指追问检索无命中时的原文核对，不作为访问其他资料的入口。
- 工具故障会明确回退到本地检索或学习规则；模型失败、超时或引用无效时使用实际原文摘录。
- 没有资料时明确说明不足，不要求模型补造答案。直接打开 `file:` 页面可使用本地检索、学习分析和计划预览。
- 当前没有新增向量库、联网搜索、账号、云同步或自动保存计划。

## 验证方法

```bash
npm test
npm run test:browser
```

单元和集成测试覆盖工具握手、发现、参数验证、资料隔离、进程退出、任务路由、生成与引用、模型或工具失败、取消和计划预览。浏览器测试使用真实 MCP 服务和受控模型，验证流程、旧功能与计划不被自动覆盖。

## 官方参考

- [MCP Client](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/docs/get-started/first-client.md)
- [MCP Server](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/docs/get-started/first-server.md)
