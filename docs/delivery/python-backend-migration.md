# Python 后端整体迁移交付

日期：2026-10-16。分支：`feat/python-backend`，基线：`main f149b5d`。本次不自动合并 main，也不重置其他任务分支。

## 交付范围

后端整体改为 **Python 3.11+ / FastAPI**，没有通过 Python 启动 Node 或转调旧 JS。旧后端源码、对应 Node 后端测试和 JS MCP/Zod 依赖已移除；前端 `frontend/` 与浏览器 `shared/` **无改动**。Node 仅用于可选 npm 命令、前端测试和浏览器测试工具。

| 模块 | Python 实现 | 保留行为 |
| --- | --- | --- |
| HTTP、静态页面与启动 | app.py、server.py、config.py | 原 URL、同源限制、私有文件不公开、本机监听、实例锁和安全停止 |
| RAG/普通解析 | rag.py、parse_worker.py | 关键词检索、稳定分段 ID、TXT/MD/PDF/DOCX、有界可取消解析进程 |
| Agent/学习/API | agent.py、learning.py、provider.py | 问答/总结/出题、追问、原文核对、SSE、取消、学习统计与计划预览、MiMo API |
| MCP | mcp_core.py、mcp_server.py、mcp_http.py、gateway.py、actions.py | 官方 Python SDK、四工具 stdio、scoped 工具、现代/legacy HTTP、预算、确认与幂等 |
| 数据与任务 | database.py、repository.py、platform.py、jobs.py、files.py、migration.py | SQLite v3、workspace v3、原件 hash、CAS/修订、浏览器迁移、持久作业、租约、恢复、Run/Checkpoint |
| 维护 | cli.py、backup.py、scripts/ | doctor/init/stop/export/gc、SQLite 一致性备份、校验恢复、Windows 启动脚本 |

文件均位于 `backend/xueya/`。源码分工见根 [README](../../README.md)，接口见[公共契约](../contracts/phase1.md)和[API 契约](../api-contracts.md)。

## 数据与切换

- 保留原数据目录、`.env`、端口和浏览器访问来源。没有清空数据库或 localStorage。
- 使用旧 Node 实现生成的**公开测试数据库** `tests/fixtures/legacy-node-v3/`，验证 40 条历史消息、400 条作答、原始迁移备份、来源版本摘要、已应用 receipt 和待确认动作能被 Python 正确读取/继续处理。测试冻结在原确认有效期内，正式 TTL 不放宽。
- Python 与浏览器离线规则共用冻结案例，核对示例资料、错题、记忆日期和复习计划；学习日仍按 Asia/Shanghai。
- 本机真实数据库切换前的一致备份位于 `.xueya-backups/before-python-20261016-151309/`，不提交 Git；先在 `test-results/python-real-data-copy/` 副本上核对，再安全停止旧实例并启动 Python。
- 当前本机服务已通过 Python 在 `http://127.0.0.1:4173/` 运行，健康检查和实例 ID 一致，页面/资源正常，后端源码 URL 返回 404。

备份恢复从不覆盖既有目标目录；未知付费结果不自动重试。重启后不自动重放模型请求。默认 SQLite schema 仍为 3，不为换语言强行改数据格式。

## 实际验证

环境：Windows、Python 3.13.9、sqlite3 3.51.0、独立 `.venv`；未修改全局 Anaconda。依赖锁在 `requirements.lock`，`pip check` 通过。其他操作系统与 Python 版本尚未实际跑完整矩阵，文档要求 3.11+。

| 检查 | 结果 |
| --- | --- |
| 迁移前旧 Node 基线 | 107 项通过，仅作历史对照 |
| `python -m pytest -q` | 55 项通过：API、原文/引用、解析、旧数据、CAS/迁移/恢复、任务/取消、用量、MCP 传输与治理、启动/停止 |
| `node scripts/test.js --frontend` | 41 项前端/共享规则检查通过；后端案例已迁入 pytest，数量不能与旧语言套件逐项相加比较 |
| `python -m backend.xueya.mcp_server --check` | 真实启动 stdio 子进程，发现 4 个工具，检索后释放连接 |
| `tests/e2e/browser.js` | 真实 Python HTTP + 受控上游：问答、追问、停止/重试、引用、卡片、四格式文件、出题、错题/记忆/计划、离线与 file: 预览 |
| `tests/e2e/workspace.js` | 资料版本、笔记、会话、草稿、评分/订正、计划、图谱编辑、多课程、键盘/移动端、受控可选多模态端口 |
| `tests/e2e/platform.js` | 35 条消息/350 条作答迁移、真实 UI→MCP 预览/确认→SQLite/审计、上传→作业→原件/片段→同步与刷新 |
| 真实 MiMo API | 使用现有配置、公开示例完成一次问答；model=mimo-v2.6-flash，引用 source-1，有效答案 115 字符。单次连通性检查不代替质量评测 |
| 文档链接与前端保留 | Markdown 相对链接检查通过；`git diff -- frontend shared` 无输出 |

回归修复了 SDK 异常组导致业务错误码丢失、Windows PID 检测、远程 MCP HTTP 取消问题。Windows 存活检查使用查询进程状态，避免 `os.kill(pid,0)` 被解释为 CTRL_C；MCP 使用 SDK 能监测断开的传输路径，实际验证取消到达业务函数。

测试记录、临时工具和截图均在被忽略的 `test-results/`，不带入仓库；公开旧数据库 fixture 可以提交，不含私人资料或密钥。

## 团队后续要求

需求、README、六个大任务、80 项内部规格、长计划、API/平台/MCP 指南均已同步：**A 保留前端，B/C/D/E 用 Python 后端，F 用 pytest 验证后端；所有 AI 永远只调用 API。** 历史设计/交付记录保留证据并加历史标识，旧 Node 命令不再是执行依据。

迁移尚未合并 main 时，队友以 `feat/python-backend` 为基线；合并后用最新 main。已经开发的分支合入迁移提交并解决实际冲突，不能强推重置或整文件夹覆盖。原 A/D/E 的历史交付不等于 B/C/F 的完整任务已完成。

OCR、向量/重排、真实图像/音视频 API、先修关系与增强学习算法仍按 B/C 任务继续实现；本次只迁移已有能力，不把受控前端端口当作真实后端功能。MCP 远程 HTTP 为独立宿主装配入口，默认本机学习服务不开放公网或多人账号认证。

## 运行与回退

```powershell
./scripts/start.ps1
# 或已安装依赖后：
.venv/Scripts/python.exe -m backend.xueya.server
# 关闭：
.venv/Scripts/python.exe -m backend.xueya.cli stop
```

如果需要回退，先停止 Python，在独立 Git checkout 恢复迁移前版本及其依赖；数据库使用切换前备份恢复到**新目录**并通过 XUEYA_DATA_DIR 指向它。不要以旧数据库文件覆盖正在运行的新服务，也不要清空浏览器数据。
