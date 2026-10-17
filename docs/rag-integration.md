# B 资料库 / RAG 接线与验证

> 2026-10-17 当前宿主补充：默认上传、删除、MCP 检索及网页原文纠错已接 B；资料页进阶区域可显式提交 OCR/向量索引，配置模板在根 `.env.example`，进度和取消在“本地数据”。真实 API 质量仍待独立验收。见 [A～E 验收](delivery/AE-integration-audit.md)。下文保留 B 最初的集成契约。

本分支实现 B 服务，不更改 E 的根路由、启动脚本、配置结构或 SQL 迁移，不更改 A/C/D 的业务代码。
以下是兼容注册定义；E 在集成分支接线，负责人审查后自行合并。
共享 `jobs.py` 有一个必需的取消清理修复：心跳清理被第二次取消时仍释放 permit/移除 active。
此小 diff 与确定性回归测试单独交 E 审查；不改变其作业接口或状态语义。

## E：挂到原宿主

在既有 `create_app` 返回应用后、启动应用前：

```python
from backend.xueya.app import create_app
from backend.xueya.rag_http import install_rag

app = install_rag(create_app(config))
```

只调用一次。注册器扩展原 lifespan，在原 Platform 建立之后初始化服务，并将新路由放在原 catch-all 之前。
仍使用同一个 Platform、SQLite v3、FileStore、JobQueue、Resources 和原同源/token 中间件。
测试工厂可注入 `install_rag(app, service_factory=lambda p: RagService(p, ...))`。

不修改默认入口也可验证已注册的同一宿主：

```powershell
.venv/Scripts/python.exe -X utf8 -m uvicorn backend.xueya.rag_http:create_rag_app --factory --host 127.0.0.1 --port 4173
```

不要同时启动两个宿主占用同一端口/目录。上述命令只是现有应用的组合工厂。
旧启动的 `/api/parse` 自动使用新的兼容 CPU 提取器；旧 `retrieve` 仍为原关键词规则。

E 应让旧 `/documents/upload`、`/documents/remove` 等资料入口委派到 `app.state.rag`，
并让工作区投影保留 B 的 `activeArtifact/contentRevision/embeddingIdentity` 和服务端来源。
旧平台上传在解析之前将旧资料 supersede，不能拿它代替 B 的成功后发布语义。
旧删除路由只删除 source，不能替代 B 对 artifact/vector 的完整生命周期清理。
本分支新入口已独立测试，A/E 完成委派前不能声称旧 UI 已接通这些新能力。

## 服务端配置

使用根目录已有 `.env`，真实密钥不提交 Git。缺少 key 或 model 时不启用该 Provider。
进程环境优先于 `.env`。服务地址只由宿主配置，不接受 HTTP 传入 URL/模型/key。
不增加依赖，继续使用已锁定的 httpx/pypdf/python-docx。

以下模型名称是官方文档核对过的可配置示例，尚未以团队账号实测；请按团队权限确定。

```dotenv
RAG_EMBEDDING_API_KEY=your_server_side_jina_key
RAG_EMBEDDING_BASE_URL=https://api.jina.ai/v1
RAG_EMBEDDING_MODEL=jina-embeddings-v3
RAG_EMBEDDING_DIMENSION=1024
RAG_EMBEDDING_REVISION=1

RAG_RERANK_API_KEY=your_server_side_jina_key
RAG_RERANK_BASE_URL=https://api.jina.ai/v1
RAG_RERANK_MODEL=jina-reranker-v2-base-multilingual
RAG_RERANK_REVISION=1

RAG_OCR_API_KEY=your_server_side_mistral_key
RAG_OCR_BASE_URL=https://api.mistral.ai/v1
RAG_OCR_MODEL=mistral-ocr-2512
RAG_OCR_REVISION=1
```

适配格式依据 [Jina API](https://api.jina.ai/docs)、[Embedding 任务与维度说明](https://jina.ai/news/migration-from-jina-embeddings-v2-to-v3/)、
[Mistral OCR API](https://docs.mistral.ai/api/endpoint/ocr)、[OCR 3 模型](https://docs.mistral.ai/models/ocr-3-25-12)。
文档/查询使用同模型与维度，分别为 `retrieval.passage` / `retrieval.query`，向量经过有限数/维度/非零检查及 L2 归一化。
供应商改变模型内容但不变名称时，宿主必须递增 REVISION，显式新建索引作业。
排队作业绑定 Provider identity；重启切换配置后旧作业在发送前失败，不悄悄换模型。

API 资源用 E 的池与 invocations 账本。无自动付费重试；不猜费用。
队列取消/超时/断线，已发出的请求记 unknown；unknown 作业禁止 E 的 retry 自动重放。
用户检查账本后可用新幂等键显式提交，成功批次可复用。不得承诺供应商只扣一次。

## A：HTTP 与原文定位

所有新接口前缀为 `/api/platform/rag/`，保留原宿主 token 与同源要求。
从既有 bootstrap 获得 token 后带 `X-Xueya-Token`。读取接口使用 query 的 courseId，
JSON POST 使用 body 的 courseId，默认 `course-default`。课程身份仍来自宿主固定本地用户。

| 方法 / 后缀 | 输入与输出 |
| --- | --- |
| GET `capabilities` | formats、实际已配置 Provider、exact-cosine、external-api-only |
| POST `upload?name=x.md&courseId=…` | 原始 bytes + `Idempotency-Key`；可附 previousDocumentId；返回 job |
| POST `parse` / `ocr` / `index` | documentId、version、idempotencyKey；返回 E 的持久化 job |
| POST `search` | query、可选 history/newTopic/documentIds/section/mode/budget/limit；返回 evidence |
| GET `read?sourceId=…` | 验证后的 source、原父块、original 定位 |
| GET `original?documentId=…` | 原件 bytes；业务 ID 不作为文件路径 |
| GET `export?documentId=…` | 结构化 artifact、正文、页、块、文件 hash/版本和纠错记录 |
| POST `correct` | documentId、version、blockId、replacement、reason；生成新正文修订 |
| POST `remove` | documentId、version；原子退役并清理来源/解析物/不再使用的向量 |
| POST `validate` | citation；核对 ID、scope、文档版本、hash、块、页、区间与实际摘录 |

作业状态/取消/SSE 继续用既有 `/api/platform/jobs*`。
批量导入由 A 为每个文件分别上传并显示独立 job/失败，不能用一个成功状态覆盖所有文件。
metadata/tags 沿用 document 实体及 E 的 CAS 更新接口；不可将它当成正文版本。
`contentRevision` 是正文修订，`version` 是 E 实体的 CAS 版本；索引/改名也会递增后者。

DOCX/TXT/MD 的 page 为 null（不能猜渲染页）。PDF 页码从 1 开始；PPTX 是 presentation.xml 顺序。
start/end 为规范化 text 的 Unicode 字符偏移，不是字节或浏览器 UTF-16 下标；A 需要转换 code point 偏移。
没有文字 bbox 时回到页或字符区间。OCR 返回的图像 bbox 保存在页 images 中，坐标单位为供应商页像素；
它不等于 PDF point，也不等于文字框。原件始终可供对照。
DOCX 原始公式 XML 仅作为导出数据，显示时必须转义，不能直接插入 DOM；其 text 为线性提取，非保真公式渲染。

## C/D：检索与证据

```python
evidence = await rag.search(scope, question, history=recent_user_messages,
                            mode="hybrid", document_ids=selected_ids, budget=2000)
source = rag.read(scope, evidence["sources"][0]["id"])
rag.validate(scope, evidence["sources"][0])
```

`mode`：lexical/vector/hybrid/rerank；向量不可用时明确 warnings 并回退词法。
Rerank 只排序已验证候选，不接受供应商新增的证据 ID。最多 24 候选、96 KB 文字。
预算单位为 utf8Bytes，范围 32–16000，是保守字节上限而非供应商 token 计数；默认 limit=6。
父块可由 context/read 读取，不能把父块无预算地追加到模型输入。
历史只改写问题，助手答案不会加入原文。调用者显式 newTopic=true 可清除历史锚点。

EvidencePackage 的 scope、query/rewrittenQuery、sources、status、conflicts、warnings、budget、elapsedMs 可供追踪。
status 是 `insufficient` / `conflict` / `evidence_found`；supportChecked 固定 false：内容支持度需 C/F 验收。
引用返回前及读取时检查有效版本；删除/换版发生在 API await 期间也会剔除失效证据。
生成以后再次 validate 可防止生成期间发生的版本变更。
长原子表格/代码/公式不截断；超过预算可被略过，过大块的索引作业明确失败，不假称完整索引。

常见错误：VERSION_CONFLICT、IDEMPOTENCY_CONFLICT、SOURCE_NOT_FOUND、SOURCE_VERSION_CONFLICT、
SOURCE_CONTENT_MISMATCH、INVALID_CITATION、OCR_UNAVAILABLE、EMBEDDING_UNAVAILABLE、OCR_PAGE_LIMIT。
OCR 每次最多处理 64 个待识别页；超出范围需分批策略扩展，当前不隐式产生一串付费调用。

## F：复现实测

```powershell
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe -m pytest -q
npm run test:frontend
.venv/Scripts/python.exe -m backend.xueya.rag_eval
```

评测素材 `evals/rag/golden.json` 是 B 作者自编的公开微型集合，黄金为文档名+摘录，不依赖 chunk ID。
默认只测普通 CPU，不读取 API key，不产生付费请求。结果写到忽略目录 `test-results/rag-eval.json`。
只有显式 `--live-api` 才加载配置并调用已配置服务；F 需先准备真实、独立的课程资料和黄金证据。
未配置的向量/混合/重排以 not_evaluated 记录；Mock 测试不能替代它们的真实质量分数。

精确 cosine 是当前默认基线；没有引入 ANN 存储，也未宣称做过 ANN 性能实验。
并发/超时、文件 10 MiB（TXT/MD 1 MiB）、最多 3000 页、ZIP 解压累计 64 MB、XML 24 MB、
规范化正文 120 万字符限制实际执行；解析在可终止子进程中运行。
当前没有 Windows Job Object 的硬 RSS 配额；子进程超时/大小边界不等价于内存硬隔离。
