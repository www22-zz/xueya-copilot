# Agent 工作流与 MCP 使用指南

## 安装与启动

后端已全部迁移 Python，需要 Python 3.12+。Windows 在项目根目录执行：

```bash
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m backend.server
```

项目使用锁定的官方 Python MCP SDK 及 Python 参数校验。macOS/Linux 将上述解释器换为 .venv/bin/python。现有 .env 中的 MiMo 配置继续使用；MCP 本地工具不需要新密钥。新增后端与测试使用 Python。

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
| `backend/agent/learning_workflow.py` | C：任务路由、阶段、编排、回退与结果检查 |
| `backend/mcp/course_server.py` | D：MCP 工具注册、参数验证和工具实现 |
| `backend/mcp/course_session.py` | C/D：官方 Python SDK stdio 连接、白名单与请求上下文绑定 |
| `backend/mcp/__init__.py` | D：工具网关、命名空间、超时与取消 |
| `shared/agent/context.js` | 共同维护：有界课程与学习上下文 |
| `shared/agent/tasks.js` | C：共享任务路由、追问检索语境、学习统计与计划格式 |
| `frontend/js/services/chat-service.js` | C：调用 Agent 接口，处理阶段和流式结果 |
| `frontend/js/ui/views.js` | A：阶段与处理过程的显示 |

兼容 Agent 位于 backend/agent/agent.py，题库接口和工具网关保留。后端检索位于 backend/rag/，shared/rag/ 仅供浏览器；B 接向量检索时应保持来源 ID 与原文契约。

## 独立检查 MCP

```bash
.\.venv\Scripts\python.exe -m scripts.check_mcp
```

检查会真正启动 Python 服务、发现四个工具、检索内置示例并关闭连接，不调用付费模型。

```bash
.\.venv\Scripts\python.exe -m backend.mcp.course_server
```

此命令启动等待 MCP 客户端连接的 stdio 服务；通常由应用或其他 MCP 宿主启动，无需在启动网页前手动运行。

其他 MCP 宿主可配置虚拟环境 Python 的绝对路径，参数为 -m backend.mcp.course_server，工作目录为项目根。服务无状态，外部客户端按发现的 schema 提供原文或学习记录，不能读取网页 localStorage。当前 Agent 仅使用固定课程工具白名单，不会自动执行任意发现工具；外部宿主的协议版本需另行联调。

## 接口与边界

- 新接口：`POST /api/agent`、`POST /api/agent/stream`。
- 原接口：`/api/ai`、`/api/ai/stream`、资料解析和出题接口保持兼容。
- 默认工具超时 5 秒，可通过 `.env` 的 `MCP_TOOL_TIMEOUT_MS` 调整到 1～10 秒。
- 上下文最多 48 个候选片段，每段 1500 字符；优先放入浏览器已有检索命中。题目元信息最多 100 条，最近作答最多 120 条，问题和历史继续沿用已有上限。
- 可选 `context.previousSourceIds` 最多三个，并且必须属于本次 `context.library`。只用于泛指追问检索无命中时的原文核对，不作为访问其他资料的入口。
- 工具故障会明确回退到本地检索或学习规则；模型失败、超时或引用无效时使用实际原文摘录。
- 普通问题没有相关资料时使用标明的“通用问答”；明确要求基于资料的任务没有证据时说明不足。直接打开 file: 页面可使用本地检索、学习分析和计划预览。
- 当前没有新增向量库、联网搜索、账号、云同步或自动保存计划。

## 验证方法

```bash
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.check_browser
```

单元和集成测试覆盖工具握手、发现、参数验证、资料隔离、进程退出、任务路由、生成与引用、模型或工具失败、取消和计划预览。浏览器测试使用真实 MCP 服务和受控模型，验证流程、旧功能与计划不被自动覆盖。

## 官方参考

- [官方 Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
