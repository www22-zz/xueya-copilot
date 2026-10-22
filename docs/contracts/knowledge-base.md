# 课程知识库兼容定义

基线：main `76c41c2`，2026-10-22。知识库与现有课程一一对应，`courseId` 就是知识库范围。沿用 B 的 document/source/artifact/vector、G2 的章节与阅读、原 SQLite/FileStore/JobQueue，不新增 schema 或迁移。旧课程自动可作为知识库查看，旧记录不改写。

新增独立模块 `knowledge_base.py`，挂接 `/api/platform/knowledge/*`，保持同源、账号与 token 校验。根装配仅增加 installer；前端增加独立 `#space/knowledge` 页面。

接口：GET bases（有效课程）；POST create（name、description、idempotencyKey，创建新课程，不覆盖已有课程）；GET catalog（courseId，资料元信息、最新任务、汇总、能力）；POST upload（二进制，查询 courseId/name/chapter，Idempotency-Key，最大10MiB，同请求幂等）；POST search（courseId/query/documentIds?/chapter?/mode，默认 lexical，外部检索须 confirmedExternal）；POST process（documentId/version/action=parse|index|ocr/idempotencyKey，付费动作须 confirmedExternal）；POST task（id/action=cancel|retry，仅本课程 RAG 任务，retry 仅本地解析）。原件/阅读/归档继续调用 G2/B 原接口。

上传时先在事务中写入章节元信息，再由原解析作业发布版本。目录不携带完整正文；检索来源保留 B 的原文位置、版本与引用校验。默认关键词检索、解析和导入不调用供应商；向量索引、OCR、混合与重排必须明确确认，配置缺失如实展示。

CLI `python -m scripts.import_knowledge_base` 使用同一宿主和接口；跳过 Office `~$` 文件、可恢复重复执行。真实课件、数据库与索引仅存本机忽略目录，不进入 PR。其他电脑自行导入自己的资料。

PPTX 正文保留 OOXML 原顺序、实际幻灯片页码，将同页相邻普通段落合成有上下文的父块；不跨页合并，表格独立。新 PPT 解析器标识 `structured-v1-pptx-context-v1`，canonical text/hash 不因合并改变，旧 artifact 与引用保留；旧资料须主动重新解析才产生新修订。不能由文本框读取推断图示/动画语义。OCR 仅支持 PDF，并在提交前校验格式和实际待识别页数，不把 PPT 送到 PDF OCR。

浏览器 store 增加 `adoptCourse(course)`：只接纳服务端新课程 ID，已有同 ID 的私人记录不覆盖；切换仍走原 `switchCourse`。知识库内“用于问答”先从同课程原 `/documents` 读取当前资料，再设置既有会话范围，避免只保存片段目录却让问答丢失资料选择。

上传在原事务里附加 request receipt artifact，验证相同 Idempotency-Key 不得变更内容；同课程的文件名+内容 hash+章节相同，即使另一个客户端使用新 key 也复用同一文档和原解析作业。失败/取消用显式 retry（仅 CPU）；更新课件通过原资料版本管理保留旧版本，不隐式覆盖同名不同内容。
