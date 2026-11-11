# 课程知识库兼容定义

2026-11-11 名称同步修复：指定单文件资料库的正式名称统一为“栈与队列知识库”。显式安装时保存 `source-bound-knowledge-base` 来源绑定配置；课程同步、工作区保存与读取都采用这个名称，旧浏览器提交“数据结构”不会将其覆盖。前端接纳同 ID 的服务端课程名更新时只改名称，保留会话和资料数据。普通未绑定课程仍可按原有逻辑命名。

## 2026-11-10 真实资料目录修正

新浏览器空间使用“个人参考资料”作为未指定学科的名称，不再注入三个示例文件。已保存的同 ID、同名称、“示例已索引”且无原件/正文的旧示例，不参与课程资料目录和数量；迁移也不会再次发布它们或默认示例证据。真实同名上传和其他旧资料记录保留。

目录新增 `originalAvailable` 与汇总 `missingOriginals`；原件缺失时保留恢复记录、切片计为零，并明确提示原件缺失。无切片不等于待解析：已核对空白、待 OCR、缺少原件分别显示。受保护资料保留格式、大小、切片数及页面数量等目录元信息，不放开正文、原件或证据导出。

按用户 2026-11-10 最新要求，显式本机导入工具 `python -m scripts.sync_local_knowledge` 仅选择 `materials/stack-queue/栈与队列知识库.md`。停止服务后使用 `--apply --owner <当前账号owner> --course-id <目标课程> --backup <新备份目录>`，先备份，再接入此文件、将上次由该工具接入的其他资料归档停用；不删除原件和学习记录。当前资料库名为“栈与队列”。其他课件、教材、知识库暂不接入，课件包默认自动导入关闭，跨课程预置清单收窄为这份 Markdown。不调用外部模型，不自动生成向量或题目。私人数据库和账号 owner 不进入通用导入默认值。

基线：main `76c41c2`，2026-10-22。知识库与现有课程一一对应，`courseId` 就是知识库范围。沿用 B 的 document/source/artifact/vector、G2 的章节与阅读、原 SQLite/FileStore/JobQueue，不新增 schema 或迁移。旧课程自动可作为知识库查看，旧记录不改写。

新增独立模块 `knowledge_base.py`，挂接 `/api/platform/knowledge/*`，保持同源、账号与 token 校验。根装配仅增加 installer；前端增加独立 `#space/knowledge` 页面。

接口：GET bases（有效课程）；POST create（name、description、idempotencyKey，创建新课程，不覆盖已有课程）；GET catalog（courseId，资料元信息、最新任务、汇总、能力）；POST upload（二进制，查询 courseId/name/chapter，Idempotency-Key，PDF最大64MiB、其他二进制10MiB、文本1MiB，同请求幂等）；POST search（courseId/query/documentIds?/chapter?/mode，默认 lexical，外部检索须 confirmedExternal）；POST process（documentId/version/action=parse|index|ocr/idempotencyKey，OCR可选pages，付费动作须 confirmedExternal）；POST task（id/action=cancel|retry，仅本课程 RAG 任务，retry 仅本地解析）。原件/阅读/归档继续调用 G2/B 原接口。大扫描PDF显式分批识别及新PDF验收后替换旧PPT的预览接口见 [PDF教材换库契约](pdf-knowledge.md)。

上传时先在事务中写入章节元信息，再由原解析作业发布版本。目录不携带完整正文；检索来源保留 B 的原文位置、版本与引用校验。默认关键词检索、解析和导入不调用供应商；向量索引、OCR、混合与重排必须明确确认，配置缺失如实展示。

CLI `python -m scripts.import_knowledge_base` 使用同一宿主和接口；跳过 Office `~$` 文件、可恢复重复执行。真实课件、数据库与索引仅存本机忽略目录，不进入 PR。其他电脑自行导入自己的资料。

PPTX 正文保留 OOXML 原顺序、实际幻灯片页码，将同页相邻普通段落合成有上下文的父块；不跨页合并，表格独立。新 PPT 解析器标识 `structured-v1-pptx-context-v1`，canonical text/hash 不因合并改变，旧 artifact 与引用保留；旧资料须主动重新解析才产生新修订。不能由文本框读取推断图示/动画语义。OCR 仅支持 PDF，并在提交前校验格式和实际待识别页数，不把 PPT 送到 PDF OCR。

浏览器 store 增加 `adoptCourse(course)`：只接纳服务端新课程 ID，已有同 ID 的私人记录不覆盖；切换仍走原 `switchCourse`。知识库内“用于问答”先从同课程原 `/documents` 读取当前资料，再设置既有会话范围，避免只保存片段目录却让问答丢失资料选择。

上传在原事务里附加 request receipt artifact，验证相同 Idempotency-Key 不得变更内容；同课程的文件名+内容 hash+章节相同，即使另一个客户端使用新 key 也复用同一文档和原解析作业。失败/取消用显式 retry（仅 CPU）；更新课件通过原资料版本管理保留旧版本，不隐式覆盖同名不同内容。
