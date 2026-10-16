# B 完整资料库与 RAG 交付进度

分支：`feat/large-B-rag`。基线：`58c7805`（已包含 Python 迁移）。2026-10-17 开工。

## 范围和当前状态

已阅读 README、当前需求、B 完整任务单、平台契约，以及 W-024/026/032 等内部规格。
不更改 A/C/D/E 的实现；默认 SQLite/FileStore/JobQueue/Resources 全部复用，数据库 schema 仍为 3。

- [x] TXT/MD、文本 PDF、DOCX、PPTX 的有界 CPU 提取；UTF-8、ZIP/XML 安全限制。
- [x] 页/幻灯片、块、规范化正文偏移、文件 hash、解析器与正文版本；DOCX/TXT 不猜页码。
- [x] Markdown/DOCX 标题、表格、公式/代码块边界；结构块父子关系、章节路径、稳定 chunk ID。
- [x] 资料上传、幂等键、原件、导出、人工纠错审计、新修订与 CAS 发布。
- [x] 替换解析成功后才退役旧资料；失败/取消保留上次可用版本。
- [x] 扫描/低质量页明确标记；Mistral OCR API 适配与逐页合并（受控 API 测试）。
- [x] Jina 文档/查询 Embedding API、批量、同课程内容缓存、模型/维度/修订隔离、增量与显式重建。
- [x] 精确 cosine 基线、中文二元词法/术语词典、RRF、资料/章节过滤、去重、有界重排与抽取预算。
- [x] 多轮问题仅以用户问题为锚；显式换题，不把历史回答当原文。
- [x] EvidencePackage、引用 ID/页/版本/hash/偏移/真实摘录校验；异步返回后重新检查删除与版本。
- [x] 沿用 E 的租约与 API 资源池/调用账本；取消、未知结果不自动重放。
- [x] 导出 `install_rag(app)` 注册模块，复用 E 的 token/同源检查与服务生命周期。
- [x] 17 个 B 专项测试已通过；原前端 41 个检查通过；完整 Python 回归进行中。
- [ ] 无真实 API 凭据，未进行真实 OCR/Embedding/Rerank 质量与费用验收。
- [ ] E 将注册模块挂到默认启动入口；A/C/D 使用新的服务端口替换旧的检索/读取调用后跨模块联调。
- [ ] F 的独立课程黄金集和人工证据支持度验收；近似索引应在精确基线和真实规模测量后决定。

## 已实现接口

`rag_parse.py`：`parse_structured`、`structured_chunks`；兼容 `rag.py` 的 `parse_document` 与 `extract_chunks`。
旧 `retrieve`/浏览器离线规则保持兼容；新能力通过 `RagService` 使用，不能把旧入口称为已启用混合检索。

`RagService(platform, embedding=None, ocr=None, rerank=None)`：
`upload/submit/document/export/correct/remove/context/read/validate/sources/search`。
作业注册名：`rag-parse`（cpu）、`rag-ocr`/`rag-index`（api，maxAttempts=1）。
付费队列已持有 API permit，供应商调用复用当前任务的 permit，避免 api_slots=1 时死锁。
不共享跨线程/用户的 permit，不把 CPU 作业伪装为付费作业。

`rag_http.install_rag(app)` 需在应用启动前调用一次。提供 `create_rag_app` 工厂用于独立集成验证；
它仍复用现有 `create_app`，不是另一套存储或另造前端。E 的根路由/启动文件不在本分支直接修改。

## 真实边界

没有本地 AI、GPU、CUDA 或模型下载。API 不可用时检索给出词法回退及 warnings；
扫描空页不造正文，OCR/索引未配置时返回不可用。
已识别文本的位置是规范化文本偏移；PDF CPU 提取没有文字 bbox，明确为 null。
OCR 文字 bbox/置信度没有供应商可靠字段时同样为 null，不能从页尺寸推造。
PPTX 的页是演示文稿顺序，视觉多栏顺序/图片理解不等同于已验证。
图像引用只作定位数据，不当作识别完成的文字证据。
代码/公式/表格作为完整块保留，超过 API/上下文预算时明确拒绝或跳过，不截断后冒充完整证据。
`evidence_found` 只表示找到原文；`supportChecked=false`，不宣称机器已经证明生成论断。
冲突检测目前是保守的简单否定冲突提示，不是通用语义蕴含模型。

## 接下来继续

1. 跑完完整回归，修复差异；补充并运行可复现评测素材。
2. 增加针对单 API permit、恶意供应商输出、索引取消/恢复的专项验证。
3. 完成接线说明、实测命令/结果、提交并推送 B 分支供负责人审查。
4. 获得团队 API 配置和真实课程样本后继续真实验收；不将 Mock 结果标为真实模型效果。
