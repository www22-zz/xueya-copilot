# Agent 与 MCP 使用指南

当前后端为 Python/FastAPI，前端保持原样。安装、运行见[README](../README.md)，接口见[API 契约](api-contracts.md)。所有 AI 仅调用外部 API，普通解析和学习规则由 Python 执行。

## 已有功能

资料问答、总结、开放练习：判断任务 → MCP 搜索 → 按来源 ID 读取并核对原文 → 关闭工具连接 → 调用 MiMo → 检查最终 JSON 与引用。

薄弱点分析、复习计划：MCP 读取作答与题目 → 计算统计 → 按上海日期、考试日期和每日时长生成预览。此流程不需要模型密钥，也不会自动保存计划。

追问结合近期用户问题和仍有效的上一轮来源；历史回答不能当作原文。来源缺失时明确说明。工具或模型失败时显示降级阶段并使用实际原文/学习规则；主动停止时不保存半段回答。

HTTP 地址仍为 `/api/ai`、`/api/ai/stream`、`/api/agent`、`/api/agent/stream`、`/api/topics`、`/api/questions`、`/api/parse`。流式事件仍为 `workflow/content/reasoning/done/error`。

## 两条工具链

| 条件 | 工具链 | 数据 |
| --- | --- | --- |
| 浏览器尚未启用 SQLite 同步 | 官方 Python MCP SDK 的真实 stdio 进程 | 本次请求的有界资料/学习上下文 |
| 已保存服务端 workspace | 官方 SDK 的进程内客户端和 scoped 平台工具 | SQLite 中当前课程的来源、题目和记录；保存 Run/Checkpoint |

进程内调用使用 SDK 官方提供的内存适配，外部 stdio/HTTP 使用真实协议传输。模型不能在工具参数里自行选择用户或课程身份。进入等待用户确认阶段前关闭工具会话，不持续占用连接。

## 独立诊断

```powershell
.venv/Scripts/python.exe -m backend.xueya.mcp_server --check
.venv/Scripts/python.exe -m backend.xueya.mcp_server
```

第一条命令启动真实 stdio 子进程，发现四个工具并检索公开示例，随后关闭；不调用付费 API。第二条用于 MCP 宿主，stdout 只输出协议消息。宿主配置 `command` 为虚拟环境 Python 的绝对路径，`args` 为 `['-X','utf8','-m','backend.xueya.mcp_server']`，`cwd` 为项目根目录。

四个兼容工具名保持 `search_materials/read_source/analyze_progress/build_review_plan`，参数通过发现的 JSON Schema 验证；不能直接读取网页 localStorage。后续 scoped、HTTP 和写入工具见[MCP 开发指南](mcp-platform.md)。

## 修改位置

| 文件 | 主责 |
| --- | --- |
| `backend/xueya/agent.py` | C：路由、追问、编排、回退、出题、结果检查 |
| `backend/xueya/learning.py` | C：日期、统计和学习规则 |
| `backend/xueya/provider.py` | C：MiMo API、SSE、取消与用量 |
| `backend/xueya/mcp_core.py`、`mcp_server.py` | D：注册、会话、发现和 stdio |
| `backend/xueya/mcp_http.py`、`gateway.py`、`actions.py` | D：HTTP、调用治理、确认流程 |
| `backend/xueya/app.py`、`platform.py` | E：HTTP 与存储接线 |
| `shared/agent/`、`shared/learning.js` | A/C 协调维护浏览器离线规则；后端不执行它们 |

当前基础工作流不等于 C 大任务全部完成，OCR/向量检索/评分/概念图/多模态等增强仍按任务单继续。测试使用受控模型只能证明流程，真实质量由 F 的独立评测报告说明。
