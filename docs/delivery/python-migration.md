# 后端 Python 迁移（2026-10-16）

用户要求后端全部改为 Python，以后后端新增、修改与测试也使用 Python。此要求优先于旧任务单中的 Node.js 技术栈，已写入仓库根 AGENTS.md 和 D:/web/AGENTS.md。前端 HTML/CSS/JavaScript 保留。

## 运行与依赖

Python 3.12+，本机验证为 3.14.0。FastAPI/Uvicorn、httpx、官方 Python MCP、Py-FSRS、pypdf、python-docx。requirements.txt 为直接依赖范围，requirements.lock 为完整锁定版本（pywin32 带 Windows 条件）。

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m backend.server
```

macOS/Linux 使用 python3 与 .venv/bin/python。当前页面保持 http://127.0.0.1:4173，已切换 Python，健康接口增加 runtime=python。激活虚拟环境后 npm 命令只是 Python 别名；项目运行不需要 Node。Python 后端不执行 shared/ 中的浏览器 JS。

## 迁移范围

| 原模块 | Python 实现 |
| --- | --- |
| HTTP/SSE、静态文件、配置与契约 | backend/app.py、server.py、config.py、contracts.py、core.py |
| MiMo 图文/流式/工具、路由、ASR/TTS | backend/providers/mimo.py、router.py、speech.py |
| 检索、分块、PDF/DOCX | backend/rag/__init__.py |
| 兼容 Agent、提示词、题库、知识点 | backend/agent/agent.py、learning_workflow.py |
| 问候、通用问答、学习上下文 | backend/agent/tasks.py、general_chat.py |
| 严格回答、引用与语义审核 | backend/agent/answer_service.py、answer_policy.py、evidence.py |
| 全章总结/比较、组合学习包 | backend/agent/content_service.py、package_composer.py |
| 五题型、评分、人工审核、选题 | backend/agent/assessment.py、question_service.py |
| 概念抽取/订正、先修与路径 | backend/agent/concept_service.py、concepts.py |
| 掌握、逐日计划、重排、学习闭环 | backend/agent/study.py、planning.py、study_session.py |
| 复习卡/推荐反馈、错因订正 | backend/agent/review_service.py、recommendation_feedback.py、diagnosis_service.py |
| 产物版本/明确采纳、CAS 状态机 | backend/agent/artifact_service.py、run_service.py |
| 图片/拍照步骤诊断、录音、抽帧、朗读 | backend/agent/media_service.py |
| MCP stdio 服务/客户端/网关 | backend/mcp/course_server.py、course_session.py、__init__.py |
| 学习装配、可选鉴权学习接口 | backend/agent/learning_service.py、http_handler.py |
| 分组实验、合成规则比较、验证 CLI | backend/agent/experiments.py、local_experiments.py、scripts/*.py |

内部 Python 方法使用 snake_case，对前端 JSON 继续 camelCase。E 注入的仓库为 get/get_operation/commit/compare_and_set；cache/checkpoint 为 get/put。本次没有另建生产数据库，也没有默认挂载无鉴权的学习存储。

## 已执行验证

- 最终 pytest **72 项通过，0 失败、0 跳过**，记录 test-results/python-regression.log。新增网关元数据/取消/原子注册及 SSE 无尾空行覆盖；这是 Python 迁移测试集，不把它的数量直接等同旧 142 项 JS 测试。
- 7 项对照使用迁移前真正执行 JS 捕获的固定输出，验证逐日计划、过期/部分完成/跳过、掌握、推荐与选题兼容（tests_python/fixtures/js-parity.json），不是从 Python 反抄预期。
- Python Playwright + 本机 Edge 回归通过：真实 Python HTTP/MCP、问候/日常/课程问答、原文引用、追问、停止生成并取消模型、知识卡片、AI 题库、DOCX 与响应式。受控模型，不收费；截图位于忽略的 test-results/browser-python/。
- Python 合成实验已实际重跑：4 个规划场景、固定/自适应选题、5 条 FSRS 复习事件，结果位于 docs/delivery/c-local-experiments-python/；4 个候选规划均无超预算。没有将实验结果当作真实学习收益。
- compileall、pip check 与 git diff --check 通过。
- Python 真实 MiMo 调用 6/6 通过：Flash JSON/SSE/工具/图片、TTS、ASR。实际 usage 按公开国内价估算本轮约 0.000695667 元，未读取账单。
- scripts/check_c_live_api.py 复用原累计预算账本，保留历史预留 7 元，6 次有界短请求各预留 0.1 元，合计约 7.6 元低于用户 10 元授权。预留不是实际费用。无自动付费重试，密钥不输出/上传；报告与媒体保存在忽略的 test-results/。

## 版本与限制

旧后端/测试/CLI 共 85 个 JS 文件和旧 README、npm manifests 先归档 .migration-backup/node-backend-before-python.zip，逐文件 SHA-256 验证后移到 node-source/；备份被 Git 忽略，不运行、不上传，不含 .env。backend/ 和 scripts/ 不再有 JS。

Py-FSRS 6.3.2 关闭 fuzzing，使用稳定卡片 ID，按不可变事件重放；algorithm 明确为 py-fsrs-6.3.2，不把它的调度冒称与旧 ts-fsrs-5.4.2 一样。历史实验保留，Python 实验单独版本化。

Python MCP 1.30.0 已验证自身客户端/服务端 stdio；外部宿主和旧 JS SDK 跨版本联调未宣称通过。

迁移完成不等于 C 整包验收完成：E 生产持久化/鉴权/队列、B 真实课程与媒体定位、A 新学习交互接线和 F 黄金集仍为原有待办。合成短样例不能证明真人录音、长视频、GPU 或真实学习收益。

仍在 feat/large-C-agent-learning，未提交、推送或合并。提交署名尚未提供，不影响本地运行。

## 最新 main 平台接入更新

收尾 fetch 检测到 origin/main 更新到 **f149b5da41e94948dbd5fc267387a500fc9371c8**（含 A/D/E 新交付），随后完整核对并纳入。新增 Node 后端没有留在运行目录：

- backend/platform/ 使用 Python sqlite3 保留 E 的 schema v3（同表/列），实现课程隔离、工作区 CAS、不可变版本、原件哈希存储、进程隔离解析、租约/心跳/取消/未知付费结果、迁移预览/备份、用量记录、在线备份/恢复、导出和 GC。
- backend/platform/learning_repository.py 给 C 提供真实 SQLite get/get_operation/commit/compare_and_set 适配，不再把“没有 SQLite 端口”当作本地阻塞。
- MCP 已迁移作用域工具、写入预览/宿主确认/原子 audit+receipt、恢复确认状态、参数 schema/调用/并发/耗时/成本单位限制、公开 DOI 元数据可选适配，以及实际验证的 Python Streamable HTTP 服务/客户端。
- 最新前端 A/E 文件已同步，保留 C 的通用问答分流并补合 courseId。浏览器旧数据迁移仍先预览、由用户明确确认；没有自动导入用户真实 localStorage。
- 最新平台专项 9 项及 MCP HTTP 3 项通过；最终综合回归 85 项通过、0 失败/跳过。两套实际浏览器回归通过，新增真实确认面板、SQLite 重启恢复与原件解析任务验证。
- 分支旧 HEAD 是 main 的祖先且没有本地独有提交、暂存区为空；保存备份引用 backup/python-migration-base-20261016 及 231 个工作文件哈希后，仅更新 Git 基线到 f149b5d，逐文件确认工作内容未变化。没有提交、强推或合并 main。最新远程参考与被替换前端原文件在忽略的 .migration-backup/main-f149b5da/。

当前默认启用平台，数据位于忽略的 .xueya-data/；/api/platform/bootstrap 提供本机同源 token，写入/原件/迁移接口要求该 token。python -m backend.platform.cli 提供 doctor/start/stop/init/backup/restore/export/gc；没有本地 AI 推理。

上文“E 的整个持久化/队列未就绪”为早期检查点，现由本段替代：基础平台和 C SQLite 仓库已接入并验证；C 的新 /api/learning/* 仍为注入式接口，尚未全部挂到默认前端，真实课程/长期学习效果与独立 F 验收依然未完成。Python MCP SDK 对外部 2026-07-28 专属协议模式不承诺兼容，当前已验证协议协商的 stdio/内存/HTTP。
