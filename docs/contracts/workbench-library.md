# G1/G2 兼容接线与操作

日期：2026-10-17。主入口 `python -m backend.xueya.server` 不变。所有新增路由在主平台 catch-all 前注册，同源、loopback Host 与 `X-Xueya-Token` 校验保持；token 从既有 bootstrap 获取，课程字段沿用 `courseId`。前端 HTML/CSS/JS，新增后端/测试/浏览器脚本均为 Python，无新增依赖、数据库迁移、队列或用量账本。

## 页面操作

1. 打开课程资料，导入文件、课堂文字、公开网页或媒体原件。选择章节；普通解析走原队列，不自动索引或调用学习模型。
2. 点击“阅读与版本”核对正文、位置、来源快照与历史，查找正文或下载原件。点击“按这份资料学习”进入问答；章节筛选后可按本章进入学习概览。
3. 学习主区使用已有的学习包、候选题审核、测验、笔记、FSRS、计划与图谱服务。预览和明确采纳规则保持；原浏览器记录可展开查看，不自动转成带证据的新成绩。
4. 在“服务设置”逐项查看文字、图片、ASR、TTS、向量、重排和 OCR。免费检查不连接供应商。密钥和用途模型仍在本机 .env 中更换/移除，系统环境变量优先；重启生效。页面不保存或回显凭据，私人 .env 单独安全备份，课程包不携带它。
5. “任务与用量”可查看当前课程或全部课程的有界任务、待确认运行和实际 usage；可以取消后台执行，或重试已知的普通本地任务。关闭对话框/停止等待不等于取消后台任务。unknown 不自动重放，CPU 外层中的模型任务也不视作免费任务。
6. 媒体不依赖 ASR 配置即可保存原件；人工选择实际页或片段后确认关联，再从关联跳回播放器。识别、长文件分段和讲解沿用 C/G5 服务，不把播放当作掌握事件。

## G1 端口

`GET /api/platform/workbench/capabilities` 返回 `capabilities[]`：id、label、model、configured、status、connectionVerified，以及可选最近调用时间/状态。`unconfigured`、`configured_unverified`、`connection_verified`、`last_outcome_unknown` 分开表示。成功只说明相同配置的该用途协议调用完成，不说明模型质量；更换凭据/模型/地址后不沿用旧验证。旧账本无用途元数据时不猜测历史验证。

`POST .../check` 接受 `{courseId, mode:"local"}`，返回 `networkRequests:0`、配置语法检查与逐项能力；拒绝 paid 或任意密钥/URL 字段。没有用户授权的付费探测入口。

`GET .../tasks?courseId=...&scope=course|all` 返回 tasks/pending/invocations。最近 100 条调用以实际数值 usage 展示，缺失保持 null，无可靠计费单位时 `currencyEstimate:null`。任务有 canCancel/canRetry/hasCheckpoint/hasResult/invocationIds，不回显任务输入、原始错误或正文。`POST .../task-action` 接受 `{courseId,id,action:"cancel"|"retry"}`；重试仅允许已失败/取消的已知免费类型，拒绝 API 和未知结果。

调用仍写原 invocations。现有 meta 仅附加 `invocation-context:<id>` 关联用途、配置指纹和可空 jobId，不存密钥、正文或第二份 usage；JobQueue 的 ContextVar 只在实际执行任务时设置，跨课程不继承。G3/G4/G5 只需复用原 provider/native/RAG 适配器和队列即可自动获得关联；历史调用不伪造任务归属。

## G2 端口

前缀 `/api/platform/library/`：

| 方法/操作 | 输入及兼容行为 |
| --- | --- |
| GET catalog | 课程资料、版本化 profile、媒体元数据和人工关联；私人历史不删除 |
| POST profile | description/goals/prerequisites/examScope/chapters 与 expected `version`，CAS 保存 |
| POST text | title/text/chapter/idempotencyKey，可选 previousDocumentId；返回 B 解析 job |
| POST url | url/title/chapter/idempotencyKey、confirmed:true，可选 previousDocumentId；先抓取作业，再 B 解析作业；外层 result 带 parseJobId/documentId |
| POST organize | documentId/version、action=chapter/detach/archive/restore、chapter、confirmed:true；移出章节不删除，归档可恢复 |
| POST reuse | documentId/version/targetCourseId/chapter/idempotencyKey/confirmed:true；独立来源与课程索引，原件 hash 可复用；目标解析成功后页面才按显式选择归档原课程记录 |
| GET read | documentId，可选 version；返回当时 document/artifact 与版本目录；退役正文仅用于历史阅读 |
| POST media-link | documentId/documentVersion、mediaId/mediaVersion、location:{page?,startMs?,endMs?}、idempotencyKey/confirmed:true；页必须真实存在，时间在已知时长内；存储 documentContentRevision |
| GET media-original | id/version，原 token 和课程范围；支持单个明确起止的 bytes Range，无授权 URL 外泄 |

网页正文快照带 originalUrl/finalUrl/capturedAt/contentHash，原件仓库保存提取后的正文，不执行脚本。抓取每跳检查公开 DNS 并连接检查过的 IP，TLS 保留真实域名验证；限制重定向、大小、协议、端口与时间，失败不发布替换。系统代理/DNS 将公开域名映射到保留地址时会拒绝；不降低防护适配该环境。动态登录网页改用手动粘贴。

主聊天新增可选 `documentIds`：省略保留旧规则，空数组明确排除全部，非空限定当前课程文档。C/聊天范围按课程/会话共用选择；不涉及 G4 的新上下文模式/笔记检索策略。归档或退役资料不会进入当前回答，也在完成前复查。

## 验证与后续包

运行 `python -m pytest -q`、`python -m scripts.check_workbench_browser`、`python -m scripts.check_library_browser`。浏览器脚本复用现有受控服务，使用临时数据；CHROME_PATH 可指定 Edge。原有浏览器与前端规则检查继续保留。

G3 继续模板与学习产物，不重复导入生命周期；G4 通过 B 和资料版本接检索，不把历史快照当当前证据；G5 复用课程媒体 ID/版本/位置，长片段识别单独预算与任务；F 按两个进度文件独立验收。没有代发队友消息。
