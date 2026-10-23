# 视觉转写兼容接口

本轮补充“无独立 OCR API 的一次性资料整理”，不把 Codex 对话能力暴露成产品 API。继续复用 B RagService、FileStore、SQLite artifact 和 JobQueue；不新增数据库/schema/根路由，挂在已有 `/api/platform/knowledge/`。

- GET `visual-pack?courseId&documentId`：返回文件 hash、资料版本、内容修订、实际页面、当前正文/图片摘要和待核对页；不接受服务器文件路径。
- POST `visual-preview`：`{courseId,documentId,version,fileHash,reviewer:"assistant-in-session"|"human",pages:[{page,kind:"transcription"|"blank",text,imageHashes:[]}]}`。只补空文本页；blank 必须无嵌入图片且说明是空白核对；识图转写须与该页实际嵌入图片 hash 完全对应。不接受图片识别指令执行、伪造图片或跨课程引用。
- POST `visual-apply`：`{courseId,previewId,confirmed:true}`。预览绑定版本，24 小时过期；同预览幂等提交单一 CPU 作业，采纳前/提交时/发布时复核来源。只发布被核对页，保留其他页面和来源方法；新来源方法 `assisted-visual-transcription` 或 `human-visual-transcription`，不自称独立人审通过。更改资料后原预览拒绝使用；取消/失败不覆盖当前知识库。

旧 RAG OCR 的 PDF API 继续保持独立，自动 OCR 未配置仍显示未配置。补录发布复用 `_publish`，按真实 hash/偏移/页码重建 source 并使旧向量身份过期；旧修订和私人学习记录保留。最新待核对状态显示页数，不能由“没有剩余空文本页”推导“所有图示已理解”。

`visual-pack.automaticOcr` 固定 false，`pdfOcrConfigured` 单独说明原 PDF OCR 配置，避免把已配置 PDF 服务冒充 PPT 自动识图。CPU 补录作业可取消/显式重试；重试前复核预览未过期及资料版本。通用队列不能发布未通过 visual-apply 明确采纳的预览。
