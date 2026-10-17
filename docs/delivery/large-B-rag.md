> 当前状态补充（2026-10-17）：默认 Python 宿主的 A～E 接线、修复与剩余工作以 [整体验收记录](AE-integration-audit.md) 为准。下文保留原阶段证据。

# B 完整资料库与 RAG 交付进度

分支：`feat/large-B-rag`。基线：`58c7805`（已包含 Python 迁移）。2026-10-17 开工。
状态：模块实现可供审查，真实 API 与跨模块接线待验收；不标为六项任务的最终“已完成”。
阶段一提交：`b2f0803`；阶段二包含资源/缓存恢复加固、模型绑定、评测与接线文档。

## 范围和当前状态

已阅读 README、当前需求、B 完整任务单、平台契约，以及 W-024/026/032 等内部规格。
不更改 A/C/D 的实现；默认 SQLite/FileStore/JobQueue/Resources 全部复用，数据库 schema 仍为 3。
E 的共享 `jobs.py` 只有一个取消清理修复，详见下方交接；不改其数据库、启动、路由或配置。

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
- [x] B 专项测试、原有 Python 回归与前端规则检查，详见下方实测记录。
- [x] 自编 12 问、4 文档黄金摘录集；同预算固定分块/结构分块词法实测；真实模型模式明确 not_evaluated。
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

## 实测与交付

Python 3.12.2 / Windows，锁定依赖全部安装于项目 `.venv`；无新增运行时依赖。
Git 作者按用户提供的信息仅配置于此仓库；没有更改全局代理或 Git 全局身份。

- `npm run test:frontend`：41 passed。
- 第一轮完整 Python 回归：72 passed，1 条 Windows 子进程 GBK 解码 warning。
- 增补恢复用例后一次全量检查：79 passed，平台旧队列测试 teardown 发生 `Event loop is closed`。
  该用例单独复核 1 passed；随后 UTF-8 全量检查 80 passed（63.49 秒）。未改动 E 的代码或旧测试。
- 新增来源篡改验证后全量出现 81 passed + 同一旧队列 teardown error；修复共享队列清理根因并增加确定性回归后，
  最终 `.venv/Scripts/python.exe -X utf8 -m pytest -q`：**82 passed，79.16 秒，无 warning/error**，其中 B 专项 27 项。
- `.venv/Scripts/python.exe -X utf8 -m backend.xueya.rag_eval --output evals/rag/results-cpu-2026-10-17.json` 已实际运行。
  固定分块词法与结构分块词法各 12/12，gold excerpt recall@6=1.0；不可答 2/2；共享 2000 UTF-8 bytes 上限。
  固定分块 p50/p95=1.597/2.734 ms；结构分块=9.565/13.642 ms，包含 SQLite 有效版本与原文校验。
  Python tracemalloc 峰值 319423 bytes（仅本次 Python 分配跟踪，不是进程 RSS）。API 调用 0，无费用估计。
  小型作者集不能证明对真实资料的提升，也没有把结构分块描述成比固定分块更快。

专项测试实际覆盖真实 CPU TXT/MD、PDF 内容/空页、DOCX 表格/公式、PPTX 页顺序，
以及受控 API 的逐页 OCR、向量/查询任务、重排、错误维度/模型、单并发、取消、重启、
缓存增量/迁移、排队配置变更、未知结果不重放、引用伪造、删除竞态、纠错与替换失败保留。
OCR 图像 bbox 仅保存供应商真实返回并通过边界校验的数据；文字 bbox/置信度缺失保持 null。

详细接口、配置示例、E 的注册/旧路由委派、A 的偏移换算、C/D 调用以及 F 复现说明见
[`docs/rag-integration.md`](../rag-integration.md)。

## 尚需团队条件与下一步

1. E 在默认宿主调用 `install_rag(app)`，将旧资料入口委派给 B，避免混用两种生命周期；按文档保留工作区中的服务端来源。
2. A/C/D 接入新的服务与证据校验端口后做端到端联调；当前没有修改或冒称这些模块已完成接线。
3. 用户尚未提供团队 OCR/Embedding/Rerank 凭据/选型；按已验证官方协议提供可配置适配器，真实账户权限/返回/质量/费用仍未验证。
4. F 提供独立真实教材、扫描讲义、图表公式/多栏样本与人工支持度评审；随后运行显式 live-api 实验及真实规模性能/ANN 对比。
5. 当前 PDF CPU 布局为启发式、DOCX 页码未知；PPTX 保留形状/表格顺序但非视觉阅读顺序保证；
   不具备本地图片语义识别，也没有 Windows Job Object 硬内存配额。
6. 供负责人审查分支与结果，不自行合并 main，不强推或覆盖其他分支。

## E 的共享队列最小修复

`JobQueue._execute` 原先在 finally 中 await 心跳任务后才释放资源/移除 active。
取消一次进入该 await，随后的 stop 再次 task.cancel 可中断 finally，遗留已关闭事件循环上的 task 和 API permit。
将 heartbeat gather 包在 try/finally 中，保证 pop/release 始终执行；不更改任务状态、租约、重试或付费 unknown 语义。
专项测试用受控 heartbeat 精确阻塞清理，再执行第二次取消，验证 active 清空、资源归零及重复 stop。
这是 B 索引/OCR 取消与关闭正确性所需的共享接线修复，请 E 单独审查此小 diff。
