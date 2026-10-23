> 2026-10-17：已整合 B（RAG）和 C（Agent 学习服务）。统一启动仍是 `python -m backend.xueya.server`（`npm start` 等价）；`python -m backend.server` 也转到该入口。默认主服务同时注册 `/api/platform/rag/*` 和 `/api/learning/*`，共用现有 SQLite、任务队列和 API 账本。C 的进阶学习入口已接入各页面：点击“打开本页进阶学习功能”使用学习包、测验订正、FSRS、计划、图谱和多模态学习。使用流程见 [C 页面使用说明](docs/C-learning-user-guide.md)。接入方式和验证记录见 [B/C 合并说明](docs/delivery/main-C-integration.md)。

# 学涯 Copilot

基于课程资料的学习助手：资料问答、原文引用、笔记、出题、错题分析、记忆卡片和复习计划。

**前端保持 HTML/CSS/JavaScript，后端整体使用 Python/FastAPI。所有 AI 能力永久只调用外部 API，不安装本地模型，不使用 GPU/CUDA。** 语言要求见[当前需求](docs/requirements.md)，分工见[六个大任务](docs/tasks/README.md)。

## 启动

Windows 用户可直接双击项目根目录的 **`启动学涯.cmd`**：自动准备环境、启动本地服务并打开星球首页；服务已运行时也会回到星球首页。首次使用需要安装 Python 3.11 或更新版本，并联网安装项目依赖。关闭启动窗口不会停止服务，停止方式见下文。

安装 Python **3.11 或更新版本**，在项目根目录运行（Windows PowerShell）：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
.venv/Scripts/python.exe -m backend.xueya.cli doctor
.venv/Scripts/python.exe -m backend.xueya.server
```

也可运行 `./scripts/start.ps1`，自动准备虚拟环境、安装锁定依赖并启动。打开 http://127.0.0.1:4173/ 。同一个 Python 服务提供页面和接口，后端启动不需要 Node.js。

macOS/Linux 对应命令使用 `.venv/bin/python`。环境变量沿用 `.env.example`，真实配置写入项目根目录 `.env`；MiMo 密钥只由后端读取。已有 npm 的开发者可继续用 `npm start`，它只是调用 Python 的便利入口。

停止：`.venv/Scripts/python.exe -m backend.xueya.cli stop`，或 `./scripts/stop.ps1`。启动/停止、浏览器数据迁移、备份恢复详见[平台指南](docs/platform-guide.md)。

## 从旧版本更新

保持原来的项目路径、`.env`、`XUEYA_DATA_DIR` 和浏览器访问地址。先安全停止旧服务，备份数据，再按以上方式启动 Python。旧 SQLite `user_version=3`、workspace v3、原件 hash 路径和来源 ID 保持兼容；不需要清空数据库或浏览器存储。不要把私人 `.env`、`.xueya-data/` 或 `.venv/` 上传 Git。

本次迁移记录和真实验收结果见[Python 迁移交付](docs/delivery/python-backend-migration.md)。迁移提交合并 main 前，团队以 `feat/python-backend` 为新工作基线；合并后统一使用最新 main。旧分支通过合并迁移提交跟进，不能上传整个旧文件夹覆盖。

当前 A～E 接线、已修复问题与未完成工作见 [整体验收记录](docs/delivery/AE-integration-audit.md)。

2026-10-18 的 G1～G4 工作台、资料阅读、模板笔记与统一搜索联合交付，见 [集成验收记录](docs/delivery/G1-G4-main-integration.md)。

当前体验调整见 [问答与导航交付](docs/delivery/chat-experience-polish.md)：图片/语音直接加入问答，学习工具统一在“更多”，左下角“设置”提供主题、团队账号和服务数据管理。章节加工仅在“更多 → 章节学习”展示；团队账号是同一本机服务的共享登录，不会跨电脑自动同步，详见 [账号契约](docs/contracts/local-account.md)。

“知识库”入口集中提供课程知识库创建、批量文件导入、章节筛选、后台处理状态、原文检索与问答范围接入。仍使用同一课程、资料版本、数据库与任务队列；默认解析/关键词检索不调用模型。真实课件仅存本机，不随 Git 同步。操作、数据结构与算法课件的实际验收及限制见 [知识库交付](docs/delivery/dsa-knowledge-base.md)。

G1/G2 工作台提供统一的课程学习主区、“更多”中的“服务设置”和“任务与用量”，以及资料页的文字/网页/文件/媒体导入、章节设置、原文与历史阅读、显式跨课程复用和真实媒体位置关联。旧浏览器记录保留在可展开区域。免费检查不调用模型，凭据仍由本机 `.env` 管理；网页抓取会拒绝内网或保留地址。操作与兼容接口见 [工作台与资料指南](docs/contracts/workbench-library.md)，交付证据见 [G1](docs/delivery/G1-workspace.md) 和 [G2](docs/delivery/G2-workspace.md)。

G5 的录音分段、视频采样与复习音频收在“更多 → 章节学习 → 高级：模板加工与历史记录 → 录音与复习音频”，保留 #11 的主界面。见[使用说明](docs/G5-media-user-guide.md)与[整合记录](docs/delivery/G5-PR11-integration.md)；识别和合成须明确确认外部 API 调用。

下一轮整包派工与队友给 AI 的提示见 [派工说明](docs/tasks/下一轮派工与AI执行说明.md)。F 的 [技术报告](docs/reports/学涯Copilot技术报告.md)、[原创验收集与实际结果](evals/acceptance/README.md)、[演示指南](docs/demo/演示与验收指南.md)及[待验证清单](docs/delivery/F-问题与待验证清单.md)分别记录实现、证据、操作与限制；真实模型效果和人工审核尚未全部验收。

## 验证

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m backend.xueya.mcp_server --check
npm run test:frontend
```

后端检查使用 pytest；浏览器规则测试才需要 Node。可选的三套 Chrome 回归为 `npm run test:browser`、`npm run test:workspace`、`npm run test:platform`，需要准备 Playwright 和浏览器，可设置 `CHROME_PATH`。测试会启动真实 Python 临时服务，使用受控上游 API，不产生付费模型调用；截图写入被 Git 忽略的 `test-results/`。

## 目录与分工

| 工作包 | 主要代码 | 职责 |
| --- | --- | --- |
| A 前端 | `frontend/`、浏览器 `shared/` | 页面、样式、交互、状态与浏览器 API 适配 |
| B RAG | `backend/xueya/rag.py`、`parse_worker.py` | 资料解析、分段、检索；后续 OCR/Embedding/Rerank API |
| C Agent | `backend/xueya/agent.py`、`learning.py`、`provider.py` | 工作流、学习规则、提示词、MiMo 与后续多模态 API |
| D MCP | `backend/xueya/mcp_core.py`、`mcp_server.py`、`mcp_http.py`、`gateway.py`、`actions.py` | 官方 SDK、传输、工具发现、治理与写入确认 |
| E 工程 | `backend/xueya/app.py`、`server.py`、`config.py`、`common.py`、`platform.py`、`database.py`、`repository.py`、`jobs.py`、`files.py`、`migration.py`、`backup.py`、`cli.py`、`sql/`、根依赖和脚本 | 公共接口、SQLite、任务、恢复、配置和模块接线 |
| F 质量与报告 | `tests/python/`、`tests/unit/`、`tests/e2e/`、评测与报告文档 | 独立验收、实验和技术报告 |

`shared/` 是浏览器离线规则和前端测试代码；Python 后端不导入或执行 JS。学习规则的两种实现由跨语言基线和浏览器测试核对。公共 HTTP 字段保持 camelCase，Python 内部方法采用 snake_case。

详细接口见[API 契约](docs/api-contracts.md)、[平台契约](docs/contracts/phase1.md)、[Agent 使用](docs/agent-mcp-guide.md)、[MCP 开发](docs/mcp-platform.md)。完整功能与实验规划保留在[长计划书](docs/plans/2026-10-15-学涯Copilot开发计划书.md)，内部细项见[规格索引](docs/tasks/完整任务索引.md)。

## 当前使用流程

1. 首页进入学习空间，默认有数据结构示例资料。
2. 上传 TXT/MD 或文本型 PDF/DOCX，查看原文、整理标签或新增独立版本。
3. 资料问答先检索、核对原文，再调用 MiMo；引用可回到原文或保存为卡片。
4. 笔记页按章节记录标题和正文，保存后可筛选、继续编辑；高级模板加工统一收在“更多 → 章节学习”。
5. 提取知识点、生成选择题，作答后进入错题、记忆卡片和复习计划。
6. 直接询问薄弱点或复习计划，Agent 通过 MCP 计算统计和预览；预览不会自动覆盖已保存计划。
7. “本地数据”中可备份浏览器记录、预览迁移、启用本机 SQLite 同步，并确认 MCP 笔记写入。

仍支持双击 `frontend/index.html` 的离线预览。该模式不请求 HTTP，不能调用 MiMo；与本机 HTTP 页面的浏览器存储来源不同。前端视觉、动效和原有功能不因后端语言迁移重做。

## 数据与能力边界

默认服务只监听本机，数据在 `.xueya-data/`，支持导出与一致性备份恢复。可配置三人共用的本机团队账号，仍使用同一学习空间；当前没有云同步，团队通过 Git 同步代码，私人数据库不随代码同步。

生成失败时明确回退实际原文，不伪造回答；流式内容只有通过检查的最终 `done` 才保存。当前已接 B 的结构解析、可配置 OCR/向量/重排以及 C 的图谱、FSRS 和图像/语音服务；未配置的外部服务明确不可用，真实课程质量仍需独立验收。视频当前是实际抽帧分析。受控 API 测试不代表真实模型效果已通过。扫描 PDF 不生成虚假正文。

TXT/MD 上限 1 MiB，PDF/DOCX 上限 10 MiB，解析最多保留 120 万字符。密钥不会发送给浏览器；选定资料和近期对话会发到配置的模型 API。付费请求结果未知时记录 unknown，不自动重放，不把 Token 用量当作实际账单。
