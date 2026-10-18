# G4 可控检索与综合问答兼容定义

基线 bc3a36b；用户分支 codex/g4-workspace，进度 G4-workspace.md。
复用 LearningHost/B RagService/C AnswerService、单一 SQLite/队列/API账本；不迁移 schema。
新增独立 SearchWorkspace(host)，鉴权后委派 /api/learning/search/*。
当前课程/浏览器 sessionId 绑定 context-policy，资料可 excluded/background/original，
模式 relevant/chapter/general；笔记为非权威背景。UTF-8字节估计明确非精确token/账单。
全文搜索首先免费；语义/混合只用已配置B适配器，笔记/题目等仍明确词法检索。
复杂回答在现有JobQueue分步记录query/evidence/result，最多4查询、显式API调用数上限，
不输出隐藏推理，不自动重试未知付费请求。所有来源在发布/读取时复核有效版本。
G3产物通过同一学习repo按kind查询，不复制笔记数据库、不将笔记当教材原文。
前端独立 search-workspace.js，app只初始化组件，组件自行维护可关闭对话框，不改旧聊天契约。
G1共享接线仅审查鉴权后委派/脚本初始化和API许可复用的小diff，不替换主路由/状态。

## HTTP 操作与持久化

统一前缀 /api/learning/search/；既有X-Xueya-Token/localhost同源鉴权，courseId沿用query或同值body，不能请求其他身份。

| 操作 | 输入/语义 |
| --- | --- |
| GET workspace | sessionId；返回本会话policy/revision/原对话/导航摘要、当前资料/笔记目录、运行和能力布尔值 |
| POST policy | sessionId、expectedRevision、policy；显式保存设置，CAS冲突不覆盖 |
| POST find | query、types、policy、mode、allowApi、afterTime/beforeTime、effectiveOnly、limit；默认免费词法 |
| POST context | sessionId、query、complex；免费范围预览，给原文/背景/版本/省略ID/粗略预算 |
| POST ask | sessionId、policyRevision、query、complex、allowApi、operationId；同一操作重放返回原运行 |
| POST cancel | id；取消既有任务，等待取消不冒称供应商未收费 |
| POST resume | id、confirmed、allowApi、operationId；核对后显式新提交，不自动重放unknown |
| GET result | id；历史结果、过程和当前stale标记 |
| GET read | id、kind；重新读取当前课程的真实原文或非教材学习内容 |

policy字段：mode relevant/chapter/general；documentModes映射excluded/background/original；noteIds；
section精确章节名；budget 1024–32000 UTF-8 bytes；maxQueries 1–4；maxApiCalls 1–8；retrieval lexical/vector/hybrid/rerank。
没有可靠tokenizer，approximateTokens仅导航估计，不是账单。相关片段省略明确列ID；整章超预算拒绝，不截后半章。
搜索时间过滤针对学习内容的更新时间，原文没有可靠时间不伪造日期。

同库artifact中search-session仅保存此会话设置/原对话，search-run保存过程/结果与原文版本；
不重写原浏览器session或旧作答。运行绑定宿主/检索配置指纹，配置变更时NOT_SENT，不悄悄换供应商。
请求上限是供应商调用次数上限，不估金额；供应商费用需用户另行确认配置与预算。

G3可选协作：结果页发xueya:content-convert {courseId,parent}，由G3打开同一preview/adopt。
G3未挂载时明确说明，仍可搜索/回答/查看实际原文。非教材对象绝不成为AnswerService原文sources。
sources(generation=False)只放宽免费读取的旧生成总量限制，生成默认限制与证据规则保持。
