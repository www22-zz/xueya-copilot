# C 学习功能前端交付

日期：2026-10-17。实现分支：`codex/c-learning-ui`。设计已获用户确认，原 main 基线为 `e82bce3`。

## 实现

- 在已有学习空间各页面增加进阶学习入口和相应业务区域，沿用现有样式，未替换 A 的浏览器数据模型。
- `frontend/js/learning-ui.js` 管理资料选择、任务、预览/确认、产物查询、测验/订正、记忆卡、计划、图谱、媒体与浏览器草稿。请求按课程隔离，旧请求不能覆盖切换后的课程。
- `frontend/js/services/platform-client.js` 复用主平台令牌和课程建立，新增学习接口适配，不存储或传送用户 API 密钥到浏览器。
- `backend/xueya/learning_ui_api.py` 补齐分页查询、服务端草稿恢复、笔记历史恢复预览、候选题持久化/审核/编辑/变式、图谱、总结/对照及媒体接口。仍使用同一 SQLite、文件库、作业与调用账本。
- 原有工作区同步不再覆盖 C 审核后的题目，也不覆盖 B 的有效证据字段。拒绝后的服务端题目不会被旧浏览器记录恢复成可用题。
- 章节生成、学习包、测验、记忆卡、图谱和计划的采纳检查版本与证据；笔记恢复生成新版本。已保存内容、复习日志、识别/转写/视频结果可在刷新后查询。
- 图片先校正再诊断，媒体由服务端保存并绑定课程/版本；ASR/TTS/图片均复用主平台调用账本、并发与取消。视频仅报告实际抽帧位置。

具体使用流程见 [C 学习功能使用说明](../C-learning-user-guide.md)。

## 验证

- Python 完整回归：180 项通过，无跳过。覆盖分页与作用域、候选题审核回执、版本恢复、B 数据保护、客观/主观题评分、过期图谱拒绝采纳、原生媒体调用和持久化。
- 原有前端回归：41 项通过。
- 新增实际 Chrome 验证：`python -m scripts.check_learning_browser`。隔离数据库及受控 API，覆盖章节任务确认/刷新、候选题到测验订正、未提交测验恢复、FSRS、图谱/计划重排、笔记预览恢复、图片校正、音频转写、手机无横向溢出。截图与报告位于忽略的 `test-results/c-learning-browser/`。
- 原有基础、A 工作区、E 平台三套浏览器回归全部通过。
- Python 编译、`pip check`、JS 语法及 Git 空白检查通过。本次真实付费 API 调用为 0；没有用这些测试冒称真实模型质量或学习效果已被验证。

## 数据与配置

本地数据库升级前已备份到忽略目录 `.xueya-backups/before-c-learning-ui-20261017`；测试未使用生产数据库。模型配置仍在本地 `.env`，未提交密钥或学习数据。浏览器测试新增小型 Python 开发依赖 `websockets==16.0`，不需要安装另一个模型或 Node 后端。

旧浏览器练习保留原记录；无法证明当时题目和原文版本的记录不作为 C 的新掌握度证据。新流程的服务端产物与旧页面并存，入口文案明确导向本页进阶区域；不将旧按钮未绑定的状态误报成新服务已执行。

## 页面接入接口补充

- `GET /api/learning/workspace`：当前课程的首页数据、有效来源、任务、图谱、反馈和能力状态。产物列表分 20 条；继续读取 `artifacts?after=...`，也可按 `id` / `kind` 查询。
- `GET history?id=...` / `review-history?id=...` / `draft?id=...`：产物版本、复习历史和服务端预览恢复，均绑定当前课程。
- `POST questions/manual|review|edit|variant`：新建候选题、审核、编辑和变式。写入带 `operationId` / `expectedRevision`，审核另带题目 `expectedVersion`；审核人由服务端绑定。
- `POST note/preview` / `history/preview` / `summary/preview` / `compare`：返回服务端 `draftId`，通过原有 `draft/adopt` 确认后写入。历史恢复仅用于笔记，避免覆盖不可变的练习与复习日志。
- `POST graph/extract|preview|correct|path`：候选提取、整图预览、核对编辑和先修学习路径。整图预览中也可提交空图并确认重建，版本历史保留。
- `POST media/upload`：原始文件字节，MIME 在 Content-Type；音频附真实 `durationMs`。后续操作通过服务端文件 ID/版本，不接收任意外部 URL。
- `POST media/recognize|confirm|diagnose|transcribe|video-register|video|speak`：识别、校正、步骤核对、转写、抽帧登记/分析和语音。朗读从服务端指定产物及版本取正文；转写与视频结果同样持久化。
- 所有路径共用 `?courseId=...` 和 `X-Xueya-Token`，与主平台同源；客户端不能覆盖课程身份。状态码区分权限、版本冲突、输入错误与不可用配置。
