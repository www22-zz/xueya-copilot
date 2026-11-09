# 模块接口约定

## 2026-11-09 学习工作台：代码运行、AI 复杂度和思维导图

以下接口挂在既有学习路由下，使用同一登录 Cookie、`X-Xueya-Token` 和同源校验；分发出现在 `backend/xueya/workbench_api.py`，业务实现在 `backend/xueya/code_runner.py` 与 `backend/xueya/learning_map.py`。它们不替换任何既有接口。

| 接口 | 行为 |
| --- | --- |
| `GET /api/learning/space/workbench/code/capabilities?refresh=1` | 返回本机评测能力快照 `{capabilities:{python,cpp,java}, languages, detectedAt}`。每个语言含 `available/path/version/label/reason`；检测方式为可执行文件查找 + 版本探测 + 最小程序编译/运行探针，结果缓存 300 秒，`refresh=1` 或“重新检测”按钮强制重探。不可用时返回明确原因，不回退成假能力。 |
| `POST /api/learning/space/workbench/code/run` | `{questionId,language,code,caseIndex?}`。`python` 使用后端解释器；`cpp`/`java` 在检测到工具链时本地编译执行（临时目录、独立子进程、编译 20 秒/运行 5 秒超时、输出 64KiB 上限、最小环境变量），按题目 `samples` 的 `name = value` 字面量构造 ListNode/TreeNode 等参数并逐用例比对。返回逐用例 `input/expected/actual/passed/error/durationMs`、整体 `passed`、`compiler` 与 `sandbox` 说明。编译错误返回 `ok:true` 且 `passed:false` + 编译诊断，不伪造通过。语言不可用时返回 `supported:false` + 原因。设计类题（146/155/208/295）与环/随机指针/公共结点等特殊结构在编译语言中返回 `supported:false` 及原因。代码执行是本机单用户功能，不是强安全沙箱。 |
| `POST /api/learning/space/workbench/code/analyze` | `{questionId,language,code}`，`code` 最长 20000 字符。复用主平台 `LearningHost.service(course).model`（API 并发许可、预算、调用账本、限流），返回真实时/空复杂度、结论、风险点与模型名。`AI_UNAVAILABLE/AI_TIMEOUT/AI_INVALID_RESPONSE` 等错误码原样返回，不自动重试。 |
| `GET/POST /api/learning/space/workbench/map/tree` | GET `?planId=`；POST `{planId}` 或受限 `{draft}`（白名单字段、长度上限、不写库）。返回只读路线树 `{ok,tree}`：计划→阶段→任务组/知识点，节点带日期、时长、难度、完成状态、绑定题目数。跨账号/不存在统一 `PLAN_NOT_FOUND`。 |
| `POST /api/learning/space/workbench/map/export`（别名 `xmind`） | 同一入参，返回 XMind Zen 工作簿 `.xmind` 附件（`content.json/metadata.json/manifest.json` + `content.xml` 兼容桩，ZIP_STORED），文件名用 `filename*=UTF-8''`。未在本机 XMind 客户端验证，界面同时提供 `.mm` 兜底，不声称客户端已验证。 |
| `POST /api/learning/space/workbench/map/mm` | 同一入参，返回 FreeMind `.mm` XML 附件。 |

前端同轮变更：侧栏“算法学习”直接打开 `#space/practice/hot100`（旧 `#space/algorithms` 自动重定向，仍归属 algorithms 视图标识）；408 页移除“课程视频”入口；课程资料学习的视频目录改为展示全部已核验课程总览，不再按已就绪资料学科过滤。均为前端路由/展示变化，未改动既有 HTTP 契约。

## 2026-11-05 整门课程图谱

- GET `/api/learning/space/course-graph?courseId=...&subject=...`：鉴权后返回当前可访问文档、课程/资料/知识点包含图、无原文引用位置、已存在questionIds、输入范围进度与unknown/failed批次；只读不提交。
- POST `/api/learning/space/course-graph/continue`：`courseId,subject,callLimit`（整数1—50）、`confirmedExternal:true`。按预算提交未开始范围，返回jobIds/maximumCalls，不自动重放未知请求。服务器重建输入范围，不接受客户端sourceScope、原文或题目。 网络预检在权限/次数检查后、队列提交前执行：无密钥、无资料、非推理同origin GET；传输失败返回`AI_CONNECTION_FAILED`且不创建作业，HTTP根路径404可通过。不保证鉴权、模型响应质量或费用。
- 既有Question/Attempt与阶段导图接口不替换；资料题增加courseSubject，阶段节点带真实questionIds及已验证存在的video资源。课程总览标识保留，不冒充精确分集。

## 2026-11-04 资料学习与模拟考试

以下接口统一使用 `/api/learning/space` 前缀、既有登录Cookie和 `X-Xueya-Token`。学习实体仍位于当前账号稳定的 `space:<learningOwner>/learning-space`，不能由客户端自报owner。来源资料仍回原Scope核验。

| 接口 | 行为 |
| --- | --- |
| `GET /materials?courseId=…` | 只读列出本人全部活动课程资料及按该请求课程可访问的原公共范围；返回真实解析状态、ready、生成jobId/status/error、知识点、题目ID和截取覆盖统计，不返回原文。 |
| `POST /materials/prepare` | `{documentId,sourceCourseId,courseId,public}`；public仅在可信公共owner内解析，不接受任意源owner。可信解析后按当前账号、源课程、文件哈希、内容修订去重，同一批次不自动重发。 |
| `GET/POST /attendance` | 返回/记录Asia/Shanghai当天签到及历史，同日一次，不读客户端日期，不修改课程、计划或掌握度。 |
| `GET /exams` | 本人试卷、组卷作业、408科目及原卷/解析原站索引。 |
| `POST /exams` | `{mode:fixed或ai,subject,count:1..40,minutes:1..180,operationId}`；fixed返回session，ai返回持久job。模拟卷不是历年真题。 |
| `GET /exams/{id}` | 本人试卷和serverNow；超时会确认交卷。未交卷不返回答案和解析。 |
| `POST /exams/{id}/start` | `{expectedRevision}`；服务器记录startedAt/deadline。 |
| `POST /exams/{id}/answers` | `{expectedRevision,answers:{questionId:选项下标}}`；只接受本卷题目和合法答案，过期不接受新答案。 |
| `POST /exams/{id}/submit` | `{expectedRevision}`；评分与题目快照一致，重复交卷返回已存结果，不重复生成Attempt。 |

题目新增 `multiple/boolean/fill`。多选答案为无重复下标数组，完全匹配计分；判断为严格bool；填空为逐空字符串数组，仅匹配保存的标准形式，否则 `pending-review` 且无score/correct。未作答fill仅投影blankCount，不返回标准答案。人工修正及复核继续保留评阅版本。聊天按明确题型提交相同服务。

资料生成 `material-learning` 单次最多读取18,000字符，遵守本机输出预算，最多六知识点/24题；4096预算对应最多两点/8题。对部分截取明确标记，不声称全书覆盖。确认解析质量后自动触发私人资料生成；新页面每次加载会话最多自动准备20份已有资料，超出可明确点击准备。发布前重查权限/修订，拒绝大段原文输出；API失败沿用主队列保守unknown语义，不自动重放。

资料题目保存 `materialId/conceptId`。计划资源可引用这些题目及同知识点阶段节点，保留真实ID。计划新增startDate/endDate/difficulty；视频关联只使用实际课程/章节ID，课程总览标注为总览而非精确分集。模型缺少说明字段时可由程序依据实际任务生成明确标注的排程说明，任务合法性验证不放宽。

AI组卷候选经过科目筛选及数量限制。返回的ID必须存在于提供候选内且无重复；不足目标题数拒绝。超额合法候选由程序按科目轮选到精确配额，明确标为“AI推荐＋程序配额选编”，保存recommendedCount/selectedCount/method，不假称模型恰好遵从题量。

原卷PDF目前提供原站链接，站内客观模拟卷单题等权，主观题仍走原分科参考评阅。新增四科MOOC为已核对元信息的官方课程总览链接，不宣称站内嵌入播放或逐分集播放已验收。

## 2026-10-31 六份预置教材跨课程问答（已批准）

用户明确批准仅[六份完整SHA256清单](contracts/public-preset-scope-map.md)。现有 `rag/search`、`knowledge/search`、问答内部来源及MCP `search_materials/read_source` 复用同一ScopeAdapter：本人当前课程+同课程原有公共兼容范围+其他预置课程中实际fileHash命中该清单的材料。仅枚举可信预置owner，不遍历其他账号私人库；文件名、isPlatform/sample、sourceFileHash声明均不能扩大跨课程范围。匿名旧单机调用维持原兼容范围。

公开来源仍无quote，兼容增加服务端 `originCourseId/originCourseName`；它们描述实际原课程，不能相信客户端重标。`pub-…`别名绑定owner/course/source；同内容跨课程副本合并重复命中，各副本旧别名仍独立回原Scope核验。不同textHash/位置/正文不合并。documentIds/section过滤及原总字节预算、条数上限继续生效。

`rag/validate`/检索末次检查按**请求课程**解析允许范围，再回实际原Scope执行原文档修订、fileHash、textHash、block/page、version及片段起止核验；不能用citation自报courseId将非清单材料升级为跨课程公共。停用/删除/撤回确认/哈希变化或等待期间权限变化均失效。MCP旧文本回退在返回前再次核验；旧归一化上下文缺失的版本号和截短位置从已存来源还原后校验，不关闭版本或原文断言。

公共来源读取仍只返元信息；raw source ID、原文/导出及其他账号任务/历史权限不扩大。未做正式库迁移、资料复制或新索引；本轮结果来自隔离实际MD解析及受控回归，不代表本机五份PPT/真实向量已全部联调。

## 2026-10-31 课程记录、多源报告与框架版本补充

以下扩展继续使用可信会话、稳定 learningOwner、本机Host/同源及 bootstrap token，不相信客户端账号字段；不新建数据库。旧字段及兼容路径保留。

| 方法/路径 | 请求、结果与约束 |
| --- | --- |
| GET `/api/learning/space/courses` | 平台目录+本人私人课，以及本人进度；原目录明确标记 legacy-unverified，不代表原站播放验收。 |
| POST `/api/learning/space/courses/save` | `{course,expectedRevision,operationId}` → 私人课程。仅 custom- ID，可新建/更新本人课，不覆盖平台课；视频URL校验但不冒充内容核验。 |
| POST `/api/learning/space/courses/delete` | `{courseId,expectedRevision,operationId}` → 软删除本人课程，历史事件/修订保留。 |
| POST `/api/learning/space/courses/progress` | `{courseId,episodeId,completed?,seconds?,positionSource?,expectedRevision?,operationId}`。completed仅bool、手动确认；位置来源仅 html5-observed/user-position，不接受“官方iframe遥测”。完成与匹配的课程任务同事务同步，重复不新增事件。计划反向完成也更新课程；不应用到新的review实例。 |
| GET `/api/learning/space/today` | 兼容新增 lastCourse，含账号内实际课程/章节续学链接与可获取的位置来源。 |
| POST `/api/learning/space/quiz/fixed-attempt` | `{questionId,answer,operationId}` → Attempt；服务端读取原Hot100/408静态题与版本生成快照，主观评阅仍用共享版本链。无明确rubric仅反馈，原自评分开保留；不执行代码、不抓取PDF。忽略客户端score/rubric。 |
| POST `/api/learning/space/framework/jobs` | generate `{subject,topic?,sessionId?,operationId}`；expand `{mode:expand,frameworkId,nodeId,expectedRevision,instruction,operationId}` → 持久job。扩展只在原revision应用新增概念分支，迟到冲突不覆盖人工编辑，不自动重发模型。 |
| GET `/api/learning/space/framework/list` | 兼容增加 jobs；framework增加服务端revision。历史按学科/专题筛选不调用模型。 |
| POST `/api/learning/space/framework/:id/patch` | 兼容增 expectedRevision、undo:true，撤销最近完整编辑/AI扩展，最多20步；不修改计划/课程/掌握度。冲突 FRAMEWORK_REVISION_CONFLICT。 |
| GET `/api/practice/analysis/sources` | 本人会话元信息、调度设置与待分析候选；不跨账号取workspace。默认识别学习会话，可手动纳入/排除。 |
| POST `/api/practice/analysis` | 原filters兼容增 includeConversations/Courses/Quizzes/Plans、excludedSessionIds、includedSessionIds。快照包含activitySources.counts/evidence/options/truncated，截止时固定；程序统计，模型引用questionIds/evidenceIds须在本快照内。无练习但有其他真实活动可分析，空记录拒绝。 |
| POST `/api/practice/analysis/schedule` | `{enabled,periodDays:1..90,weekday:1..7,time,timezone,options?,expectedRevision,operationId,automaticExternalDispatch?,confirmedExternalDispatch?}`。外部自动默认关；首次开启须 confirmedExternalDispatch:true 并保存同意时间。周期/范围/停用持久化，设置冲突不覆盖。 |
| POST `/api/practice/analysis/candidates/:id/submit` | `{confirmed:true}` 明确提交本人的固定候选快照，不读取新记录冒充旧快照。重复读取/重放返回原job，不重放unknown。 |

新草稿记录 adoptionBase；竞争采用另一份草稿或原计划已变化时返回 PLAN_CURRENT_CHANGED（调整预览仍保留 REPLAN_SOURCE_CHANGED）。依赖任务key必须存在且无环，程序拓扑排序后按共享每日预算排程。

调度只在本机进程运行时检查已初始化设置；未开启外部调用时不创建付费作业。开启后复用已有JobQueue/预算/许可/账本、一次尝试；同一证据快照去重，停机只合并一份实际窗口，历史报告不可变。failed/unknown不因下周/重启自动重发。默认外部关闭是本轮自动审批边界下的明确实现差异，不宣称满足“默认自动付费周报”。

旧评阅缺题目快照的记录仍只读；没有批量改写历史评分。旧章节标题/作者/播放器真实核验及跨课程公共预置清单授权见交付说明，不能以目录ID合法代替内容验收。

## 2026-10-31 测试分支账号资料兼容扩展

本节优先于下文“多个账号共用当前空间”的历史说明。登录 Cookie 决定服务端账号；请求体 accountId/userId、`X-Xueya-Account` 均不能选择资料 owner。新增账号使用独立的持久资料/工作区/任务作用域，不自动继承 `local-user` 下归属未知的旧资料。旧未登录单机兼容调用保留原空间；已配置登录后仍必须先登录。`GET /api/account/status` 增加 `dataOwner`（稳定资料 owner）及 `sharedSpace:false`；改名保留该 owner。

浏览器可附 `X-Xueya-Owner` 作为会话新鲜度条件；与当前 Cookie 的 owner 不符时返回 HTTP 409 / `ACCOUNT_CHANGED`，不执行请求。该字段不能用于授权。新客户端按 dataOwner 分隔浏览器工作区/同步队列，未知旧键需显式迁移，不能自动复制给各账号。

上传、目录、原件、修订、实体、工作区、作业/事件、旧学习接口和 HTTP MCP 出口均沿用原路径/业务字段，但仅能访问本人作用域。公共预置源为管理员明确标记/哈希核对的旧资料，通过问答适配器聚合，不公开其他旧文件。公共 `id` 为稳定 `pub-…` 别名，服务端解析回原 Scope 验证；不会信任客户端 `scopeOrigin`。旧 citation 验证继续核对 documentRevision、fileHash、textHash、位置和 version。

公开平台来源使用 `id/title/location/documentId/version/isPlatform` 等元信息，不含 quote；私人来源合法旧 quote 契约保留。JSON/SSE 对工具预览、claims、解析产物与历史输出统一投影。存在受保护来源时正文在最终核验后以兼容 content/done 发布；失败不发布分片原文，不把 verbatim-only 平台摘录伪装成成功回答。旧非问答生成接口不得使用受保护 RAG（`RAG_USE_CASE_FORBIDDEN`）。本节不更改 B 的解析/检索/索引/证据校验协议，也不声明完成了真实服务质量验收。

## 2026-10-31 测试分支规划与小测闭环

以下路径前缀均为 `/api/learning/space/`，沿用本机 Host、同源、Cookie 和 `X-Xueya-Token`。账号从会话解析；改名保留既有学习 namespace，不能通过改名或注册已保留的旧用户名接管历史记录。生成/评阅复用主平台 JobQueue、预算、并发与调用账本，每个付费作业一次尝试；GET/恢复不重新提交模型。

| 方法/路径 | 请求与结果 |
| --- | --- |
| POST `chat/plan` | `{question,sessionId,operationId,history?,useDefaults?}` → `handled:false`，或 `status:collecting/conditions/missing/answer`，或 `status:queued/jobId`。规划概念解释不创建作业；缺项补问与用户选择默认分开。 |
| POST `plan/generate` | `{goal,daysCount,dailyMinutes,restDays?,subjects?,title?,operationId}` → `{job}`。与聊天走同一种持久生成，实际完成后保存草稿和独立框架；`result` 为 `{planId,frameworkId,sessionId}`。 |
| GET `jobs/:id`；POST `jobs/:id/cancel` | 仅本人学习空间作业；复用真实 queued/running/succeeded/failed/cancelled/unknown。没有自动付费 retry 接口。 |
| GET `plan/list`、`plan/:id`、`plan/active` | 既有 plan DTO 兼容增加 `jobs`、`generationStatus`、`frameworkId`、`sessionId`、条件来源和 `completedHistory`。`framework-pending` 部分草稿可核对但不可采用。 |
| POST `plan/adopt` | `{planId,expectedRevision,confirmed:true,operationId?}`。新客户端必带 operationId；相同回执重放，不同请求复用 ID 冲突。事务中只留一个当前计划。 |
| POST `plan/adjust-preview` | `{planId,expectedRevision,dailyMinutes?,endDate?,startDate?,restDays?,operationId?}` → 新 `plan` 草稿与 `changePreview`；不调用模型，不直接替换当前计划。采用时再次核对来源计划 revision，变化返回 `REPLAN_SOURCE_CHANGED`。 |
| POST `plan/task/toggle`、`plan/task/delay` | 旧字段兼容，新客户端加 `expectedRevision/operationId`。任务变更、事件及回执同一事务；重复完成不重复记事件，延期仍校验每日总预算/休息日/截止日期。 |
| POST `plan/task/link` | `{planId,taskId,url,title?,expectedRevision,operationId}` → `{plan,resource}`。仅 http/https，无任意 HTML；用户提供、未做网站内容或可用性核验。 |
| POST `chat/quiz` | `{question,sessionId,operationId}` → `handled:false`，或固定题 `questionIds`，或生成 `jobId`。主动命令才触发；唯一适合的固定单选优先，否则按主题生成，不能调用受保护 RAG。 |
| POST `quiz/jobs` | `{subject,type:single/short,count?:1..5,sessionId?,operationId}` → `{job}`；全部题目结构通过后才发布，重复题干不作为成功题卡。 |
| GET `quiz/list`、`quiz/question/:id` | 本人题目白名单视图/作答/作业；未作答题不含答案、rubric、解释。问题含服务器 revision；来源区分 fixed / ai-generated。 |
| POST `quiz/attempts` | `{questionId,questionRevision,answer,operationId}` → `{attempt}`。原题/答案/rubric 快照由服务端保存；客观判定在服务端，主观原答案先保存再入评阅作业。客户端 score/correct 不作为评分依据。 |
| GET `quiz/attempts/:id` | `{attempt}`，含原答案、题目版本、原题白名单快照、evaluations 与 effectiveEvaluation。queued 作业取消/失败后读取会对齐真实状态，不产生零分。 |
| POST `quiz/attempts/:id/review` | `{expectedRevision,reason,operationId}` → 同一 attempt 的新评阅版本；客观仍按服务器答案复核，主观沿用原作答与标准调用模型，不新增 Attempt。 |
| POST `quiz/attempts/:id/correct` | 同上，加 `correct:boolean`（客观）或 `score:number`（有 rubric 的主观）或 `disputed:true`。无 rubric 不接受凭空总分；人工来源不会伪装成 AI。 |

`evaluations` 记录 source/status/createdAt/理由及可用的模型、时间、参考分/点评。有效结果按版本请求顺序取最新已完成或明确争议版本；迟到的早期 AI 结果不覆盖较新的人工修正。原评阅保留，失败、取消和未知结果不是错误/零分。旧形状评阅以 `legacy-assessment` 只读呈现，缺失题目版本保持 null，缺完整快照时不可复核；不把历史缺失补造成新模型评阅。

原 `quiz/generate` 兼容同步题目生成；原 `quiz/grade` 的客观 `result` 保留，主观增加 queued/jobId 与 Attempt，后续用作业/Attempt 读取，不等待或伪造模型分数。新页面统一走上述持久路径。原 `/api/practice/bank/ops/state`、固定题 ID、原自评与笔记保留；本页较新补充已增加固定主观题主动评阅入口及小测多源分析，但没有批量补造旧评分版本。

## 2026-10-28 朗读与联网搜索补充

`POST /api/tts` 使用本机 Host、同源校验及 `X-Xueya-Token`（从 `/api/platform/bootstrap` 获取）。请求为 `{text:string, voice?:string, courseId?:string}`；默认声音 `mimo_default`、课程 `course-default`，清理 Markdown 后最多朗读1000字。成功返回 `{ok:true,audio:"data:audio/wav;base64,...",model:string}`；未配置或合成失败返回 `{ok:false,error:string,fallback:true}`，客户端可使用浏览器朗读。非法输入及鉴权错误沿用公共错误响应。

合成复用学习服务 Speech、主平台并发许可、预算与模型账本；未知结果不自动重试。停止朗读会取消等待并阻止迟到响应播放。预算不允许未定价音频调用时在上游调用前拒绝。联网搜索经 MCP `search_web` 调用，MCP 失败记录工具失败，不再直接重放一次搜索；既有问答 HTTP/SSE 字段不变。

后端统一Python/FastAPI，前端保持原代码；本文件、`backend/xueya/common.py`与浏览器`shared/contracts/index.js`一起维护。下面JS对象是HTTP字段示意，不要求后端使用JavaScript。公共格式变更应由相关负责人共同检查，不能只改发送端或接收端。

2026-10-17 兼容补充：`GET /api/learning/workspace` 与 `artifacts` 支持可选 `kinds`（逗号分隔，最多 10 类），先过滤再分页；workspace 的 `documentIds` 为 JSON 数组字符串，仅过滤原文预览。旧请求不带这些字段时保持原行为。workspace 新增 `documents` 与 `ragCapabilities`，sources 为最多 256 段、每段最多 1500 字符的页面预览；生成/证据校验继续读取完整服务端原文。原 HTTP/SSE 字段、确认与取消语义保留。默认 `/api/platform/documents/upload` 已委派 B 的 `rag-parse`，响应仍是持久化 job。

## 1. 课程来源 Source（A/B/C）

```js
{
  id: 'upload-abc-chunk-0',       // 稳定、唯一，用于历史引用
  documentId: 'upload-abc',      // 本地完整来源可包含
  title: '课程笔记.md',
  location: '文本片段 1',        // 真实位置；不编造 PDF 页码
  quote: '实际原文',
  keywords: [],                  // 本地检索可包含
  sample: false                 // 本地来源可包含
}
```

`id/title/location/quote` 是 HTTP 传递和回答引用依赖的核心字段。后端规范化时剔除其他字段。已有来源的 `id` 不应随排序改变，浏览器中的历史消息和卡片会保留来源快照。

## 2. HTTP（A/C，联调负责人）

### GET /api/health

```js
{ ok: true, engine: 'xiaomi-mimo', model: 'mimo-v2.6-flash' }
```

没有配置密钥时 `engine` 为 `local-fallback`。配置存在只代表已配置，不保证上游在线。

### POST /api/ai

```js
{
  question: '二叉搜索树的查找复杂度？',
  mode: 'ask',                 // ask | summarize | quiz；未知值按 ask
  sources: [source],           // 已选原文对象，也兼容内置 source ID
  history: [{ role: 'user', content: '上一个问题' }]
}
```

当前由浏览器检索后提交原文；`sources: []` 明确表示没有资料，不会自动替换成示例来源。历史只用于理解追问，不能作为引用依据。此接口保留为非流式兼容接口；页面默认使用下面的流式接口。

成功响应（HTTP 200）：

```js
{ ok: true, answer: '答案', sources: ['source-1'], knowledgePoints: ['树高'], model: 'mimo-v2.6-flash' }
```

响应 `sources` 是本次实际提供的来源 ID 子集，不是完整来源对象。A 的问答服务将 ID 映射回原文对象，UI 不需要再次检索。

可回退失败（HTTP 200）：

```js
{ ok: false, error: 'AI_UNAVAILABLE', engine: 'local-fallback' }
```

错误码：`NO_SOURCES`、`EMPTY_QUESTION`、`AI_TIMEOUT`、`AI_UNAVAILABLE`。模型格式错误对 HTTP 调用方统一返回 `AI_UNAVAILABLE`；内部抛出 `AI_INVALID_RESPONSE`。

请求本身的错误：无效 JSON → HTTP 400 / `INVALID_JSON`；空问题或无效请求对象 → HTTP 400 / `EMPTY_QUESTION`；请求超过 512 KiB → HTTP 413 / `REQUEST_TOO_LARGE`。错误响应包含 `ok:false,error`。不支持的方法返回 HTTP 405。

限制：问题 4000 字符；来源只处理前 6 条、每条原文最多 3000 字符；历史先取最后 8 条再保留 user/assistant 文本，每条最多 5000 字符；回答最多 16000 字符。非流式模型请求上限 25 秒，前端非流式请求上限 30 秒。

### POST /api/ai/stream

请求与 `/api/ai` 相同。响应为 `text/event-stream`，每条事件是 `data: JSON` 加空行：

```js
{ type: 'content', text: '模型 JSON 文本增量', model: 'mimo-v2.6-flash' }
{ type: 'reasoning', text: '上游模型提供的生成过程增量', model: 'mimo-v2.6-flash' }
{ type: 'done', ok: true, answer: '最终答案', sources: ['source-1'], knowledgePoints: [], model: 'mimo-v2.6-flash' }
{ type: 'error', error: 'AI_UNAVAILABLE' }
```

`reasoning` 是否出现取决于上游模型。只有 `done` 才表示经过 Agent 格式与引用检查的完整回答；正文增量本身不是完整结果。连接结束而没有 `done`、事件损坏或服务报错时，前端回退本地摘录，不保存半段 JSON 为成功答案。模型流式请求上限 60 秒，前端上限 90 秒；客户端断开后向模型请求传递取消信号。

无效 JSON 或空问题在发送流头之前返回 HTTP 400。流内运行失败通过 `error` 事件返回，可能是 `AI_TIMEOUT`、`AI_UNAVAILABLE`、`AI_INVALID_RESPONSE` 或 `NO_SOURCES`。

### POST /api/topics、POST /api/questions

两者都是 JSON 请求和非流式响应，使用相同来源规范化规则。

```js
// /api/topics
{ sources: [source] }
// → {ok:true,topics:[{name:'树的高度',sourceId:'source-1'}],model:'...'}

// /api/questions
{ sources: [source], topic: '课程资料名', focus: '树的高度、查找', count: 5 }
// → {ok:true,questions:[{topic:'树的高度',prompt:'题干',options:['A','B','C','D'],answer:1,explanation:'解析',sourceId:'source-1'}],model:'...'}
```

`focus` 优先于 `topic`；数量限制 1～8。题目选项保留 2～6 项，答案必须是保留选项的有效下标。知识点去重。沿用队友版本：无效 `sourceId` 回落到本次第一条来源 ID；调用方不能将 ID 合法视为模型内容已经逐句核实。

服务失败返回 HTTP 200 的 `{ok:false,error}`，错误码含 `NO_SOURCES`、`AI_EMPTY`、`AI_TIMEOUT`、`AI_UNAVAILABLE`。模型知识点请求上限 45 秒、题目请求上限 60 秒；前端分别为 50 和 65 秒。

### POST /api/parse?type=pdf 或 type=docx

请求体是文件原始二进制，`Content-Type: application/octet-stream`，上限 10 MiB：

```js
{ok:true,text:'解析得到的原文',kind:'docx'}
{ok:true,text:'',kind:'pdf',empty:true}
{ok:false,error:'PARSE_FAILED'}
```

解析正文最多保留 120 万字符；服务器不保存上传原文件。不支持的类型返回 HTTP 400 / `UNSUPPORTED_DOCUMENT_TYPE`，超限返回 HTTP 413 / `FILE_TOO_LARGE`。空正文不伪造内容，前端显示未识别到文字。Python pypdf解析器处理文本PDF、CMap与压缩流，不提供 OCR，也不承诺支持全部 PDF 编码或布局。

## 3. RAG（B）

浏览器离线实现保留`shared/rag/index.js`。Python后端使用`backend/xueya/rag.py`：

```python
extract_chunks(text, {"id": document_id, "name": name})  # 600字符窗口、520步长
retrieve(question, sources)  # 当前关键词检索，最多4条
sanitize_sources(sources, catalog=None, limit=6, quote_limit=3000)
parse_document(buffer, kind)  # TXT/MD/PDF/DOCX；CPU处理
```

HTTP和持久作业经`parse_worker.parse_artifact`执行可取消的普通Python解析进程；持久化由E的Repository/Platform负责。B后续接入OCR/Embedding/Rerank API，保留真实来源ID与定位。Python后端不执行shared JS。浏览器资料读取接口保持不变：

```js
await prepareDocument(file) // → {id,name,bytes,status,meta,chunks?}
```

TXT/MD 在浏览器读取文本，限制 1 MiB、12 万字符；PDF/DOCX 限 10 MiB，调用服务端解析后加入相同分段检索。解析失败或 `file:` 预览时保存待解析记录；空正文显示未识别到文字。校验失败抛出 `error.code === 'INVALID_DOCUMENT'`，`error.message` 为可展示文案。读取失败由页面统一提示；保存与去重由控制器处理。

## 4. Agent 与模型（C）

```python
agent = Agent(provider, platform=None)
async for event in agent.direct(chat_request, stream=True):
    ...  # 兼容 /api/ai 和 /api/ai/stream
async for event in agent.workflow(chat_request):
    ...  # /api/agent 和 /api/agent/stream；持久模式保存Run/Checkpoint
await agent.practice("topics", request)
await agent.practice("questions", request)
```

Agent负责规范化、编排、提示词、答案/引用检查与练习；普通学习规则在`learning.py`，MiMo传输在`provider.py`。课程文本/模型输出不会隐式触发任意工具。内部异常使用安全AppError代码，取消使用asyncio任务取消并关闭底层请求。

```python
await provider.generate(messages, scope=scope, temperature=.2, timeout=25)
async for event in provider.stream(messages, scope=scope, timeout=60):
    ...
```

模型返回原始文本，Agent检查最终结构。MimoProvider的httpx传输可注入受控Mock；正式密钥/URL/model仅服务端从.env读取。API并发和调用状态/usage记录统一接E，未知付费请求不自动重试。

前端问答服务 `createChatService(options?)`：

```js
await chat.ask({ question, mode, sources, history, previousSources? })
// → {answer, sources: Source[], engine, online, knowledgePoints, model?}
await chat.stream(request, {onUpdate({answer,reasoning}) { /* 更新 UI */ }})
// → 同上，可包含上游 reasoning 文本
```

这里的 `sources` 是浏览器候选来源集合，服务先检索再发 HTTP。没有直接命中且问题包含追问词时，可使用 `previousSources`。网络、超时、服务失败或响应格式异常时返回本地摘录；`file:` 页面不请求 HTTP。不要在 UI 模板中重复实现这套逻辑。

前端出题请求由 `frontend/js/services/practice-service.js` 的 `createPracticeService()` 提供 `topics(sources)` 和 `questions({sources,topic,focus,count})`。题库保存在同一个 localStorage 记录的 `bank` 中，知识点缓存在 `bankTopics` 中；新增或删除资料会清除知识点缓存。新增题库接入错题回顾、记忆卡片和计划优先级；学习规则函数可接收包含内置题与题库的合并题池。

## 5. Agent 学习流程（C/D）

`POST /api/agent` 和 `POST /api/agent/stream` 接收兼容的 ChatRequest，另可传入有界的 `context`：

```js
{
  question: '帮我安排复习计划', mode: 'ask', sources: [], history: [],
  context: {
    library: [source],
    questions: [{id:'q3',topic:'中序遍历',sourceId:'source-3'}],
    records: [{questionId:'q3',correct:false,createdAt:'2026-10-15T02:00:00Z'}],
    examDate: '2026-11-08', minutes: 30
  }
}
```

不传 `context.library` 时兼容使用请求 `sources`；前端默认提供命中优先的候选片段和题库元信息。服务器计算上海时区当前日期，不接受客户端伪造的 `baseDate`。日期无效时使用默认设置，日期已过时保留设置并提示更新。

响应保留 `ok/answer/sources/knowledgePoints/model`，并增加：

```js
{
  engine: 'xiaomi-mimo', // 或 local-workflow，明确表示本地工具/规则结果
  workflow: {intent:'ask',steps:[{stage:'read',label:'原文和引用位置已核对',status:'completed'}]},
  artifacts: {progress:{total:1,correct:0,weakTopics:['中序遍历'],dueTopics:[]},plan:{examDate:'2026-11-08',minutes:30,days:[]}}
}
```

`artifacts` 只在薄弱点分析或计划任务中返回。计划任务的 `days` 是真实计算出的任务数组，上面只是形状示例。计划不自动保存。

流式接口额外发送 `{type:'workflow',stage,label,status}`，状态包括 `running/completed/degraded`；最终是兼容的 `done` 事件。前端仅在有效 `done` 后保存最终回答。课程型任务先搜索并核对实际原文；学习统计和计划通过只读工具计算，可以在没有 AI 密钥时完成。工具失败会标注回退，来源不足会明确说明。

实现入口为`Agent.workflow(input)`异步生成器；HTTP非流式接口收集最终done。`Agent.direct`及`practice`保留原问答和出题能力。

追问可提供 `context.previousSourceIds`，最多三个，仅保留当前 `context.library` 内的 ID。泛指追问结合近期用户问题生成检索词；没有命中时读取这些有效来源并核对原文，不把历史回答作为原文。常规新问题不会自动使用上一轮来源。

前端 `createChatService().stream(input,{workflow:true,onUpdate,signal})` 接受调用方的 AbortSignal。主动取消向外抛出取消原因，不返回本地摘录；页面清除未校验的片段，保留重试输入。网络失败或超时可本地回退，学习任务使用与服务端相同的 `shared/agent/tasks.js`，返回 `workflow` 和 `artifacts`，不写入已保存计划。SSE 单事件最多 1 Mi 字符，累计模型正文和推理最多 200,000 字符。

## 6. MCP工具与宿主确认（C/D/E）

Python接口、工具schema、官方SDK传输、白名单/预算/取消、写入确认、HTTP认证和可选DOI查询见[MCP开发指南](mcp-platform.md)。主要入口：

```python
async with open_session(platform_registry(platform, trusted_scope)) as session:
    tools = await session.list_tools(namespace=True)
    result = await session.call("search_materials", {"query": "课程问题", "limit": 4})
```

未启用持久数据时，聊天工作流使用官方 SDK 同进程会话调用四个课程工具，独立 stdio 入口仍可使用；启用后工具读取 SQLite 中可信宿主选择的课程。模型不能覆盖 userId/courseId。宿主确认路由不注册为工具。公共平台 HTTP 接口与错误/CAS/迁移语义见[平台指南](platform-guide.md)及[统一契约](contracts/phase1.md)。

模块装配统一在`backend/xueya/app.py`、`platform.py`；不再保留Node后端或Python到Node桥接。客户端JSON字段仍为camelCase，Python内部方法使用snake_case，不要求前端随语言迁移改名。
# G1/G2 增量接口

新增工作台能力/任务投影与课程资料导入/阅读接口，旧 HTTP/SSE 保持。兼容定义、鉴权、字段、调用关联和操作流程见 [工作台与资料接线](contracts/workbench-library.md)。

G5 复用同一学习主平台，新增分段媒体任务与有出处复习音频，旧媒体路由保留；见 [G5 媒体与音频契约](contracts/G5-media-audio.md)。

### 提问附件与麦克风输入（2026-10-20）

加号选择图片/文档；直接录音停止后，客户端转换为16kHz单声道PCM WAV，复用现有 `media/upload`、`media/transcribe`。ASR 使用 `mimo-v2.5-asr`，识别文字回填草稿，用户发送后才调用配置的 LLM（默认 `mimo-v2.6-flash`）。文档复用原上传/解析接口，并加入该次问答的 `documentIds` 及有效来源范围；无新增HTTP/SSE接口。详见[交付与使用说明](delivery/FINAL-DELIVERY.md)。

### Agent P0 可信执行（2026-10-20）

原路径、基础字段和 SSE 类型保持。资料问答的正文在逐条证据核验后以 `content/done` 发布，核验期间仍发送 `workflow` 进度；通用问答继续流式。未审核改写退回原文，额外返回 `verification/reason`；生成期间资料修订会阻止发布失效来源。

主服务通用聊天直接接收模型回答正文，不向上游强制 JSON 格式；宿主将每个正文增量做 JSON 字符串转义，继续以既有 `content` JSON 增量和最终 `done.answer` 发布。因此普通文字、Markdown 和用户要求的代码/JSON 示例不会因为不是 `{"answer":...}` 而丢弃。结构化课程任务和旧兼容调用仍执行原有格式/证据校验。工作流失败沿用 `general-chat-unavailable`、降级 `workflow` 和最终 `done`：空正文提示没有返回回答，截断/缺失结束帧提示回答不完整；仅确认本机未配置密钥时提示配置密钥，其他服务故障提示稍后重试。不透出上游原始错误或自动重试付费请求。

#### 可选：知识库失败后的单次自主回答（2026-10-31）

宿主开关`AI_RAG_GENERAL_FALLBACK=1`启用网页文字问答的单次MiMo自主回答；客户端不能修改这个开关。它覆盖资料不足、证据核对失败、模型引文格式错误、文字生成超时或不完整，以及只读规划未生成答案。原本正常的资料回答继续保留引用。图片、学习记录写操作及需要用户确认的任务不因此自动改用通用回答。

切换前关闭原生成器及工具会话，新请求只携带问题和对话语境，不携带当前检索材料/证据包。旧的超时请求不重放；最多新发一次不同的通用请求（90秒上限），共用原调用数、token、时间和费用预算。取消、权限错误、资料版本失效及已耗尽的预算不触发额外请求。新请求仍失败时返回未完成，不循环重试。

成功的自主回答固定以“模型自主回答（未使用知识库证据）”标注，`engine='general-chat'`、`verification='general-knowledge-not-course-verified'`，`sources/sourceObjects/sourceDetails/claims`均为空。可选`fallback={from:'course-rag',reason,attempts:1,sameRequestReplayed:false}`记录原失败原因，不能把该结果宣称为知识库支持的答案。

沿用既有SSE事件类型：切换的`workflow`帧可增加`resetAnswer:true`，客户端先清空原答案/推理增量，再接收新的`content`，以最终`done`为准；旧客户端仍可依据最终done替换正文。浏览器显示“MiMo 自主回答”，后续通用追问不继承更早的课程引用。主聊天流的等待上限调整为240秒，用户取消保持有效。`/api/health`可选返回`ragGeneralFallbackEnabled`，用于核对当前宿主开关是否已加载。

主服务通用聊天请求显式设置 `thinking: {type: "disabled"}`，并引导简单问题简短作答以减少等待；仍调用同一外部模型并由宿主保证 JSON 接口、流式事件和调用账本。课程资料问答及学习规划不自动套用此设置，继续使用原有推理模式。该优化不承诺固定响应时间，网络和服务端排队仍影响延迟。

聊天工作流的浏览器上下文通过同进程 MCP 会话调用原有课程工具，不再逐条消息启动 stdio 子进程；独立 stdio MCP 入口仍保留。工具参数校验、只读白名单、预算及课程隔离不变。主模型 HTTP 连接池随应用启动和关闭，逐请求超时仍独立生效，SSE 在 `[DONE]` 后消费 HTTP 收尾以允许安全复用连接，不再转发收尾后的内容，不自动重发失败请求。

聊天请求可选 `previousAnswerKind: "general"`：浏览器仅在所选历史范围的上一条助手回答为通用问答时提供此提示，契约层只保留该枚举值。`ask` 模式的指代/编辑追问可据此继续通用聊天；旧会话中针对已存在代码块的编辑也可直接续答。此提示不能绕过明确的课程依据要求或有效的上轮课程引用，不能改变用户、课程或权限。它不对其他新话题强制通用路由，也不会新增模型意图判定调用。

主模型调用增加输出上限与结束状态检查；原 `error` 字段可返回 `AI_TRUNCATED`、`AI_INCOMPLETE`、`AI_UNEXPECTED_TOOL_CALL`、`STALE_EVIDENCE`、`AI_RUN_TIMEOUT`、`AI_MODEL_BUDGET_EXCEEDED`、`AI_TOOL_BUDGET_EXCEEDED`、`AI_OUTPUT_BUDGET_EXCEEDED`、`AI_COST_BUDGET_EXCEEDED`、`AI_PRICING_REQUIRED`。工作流可继续采用已存在的原文/规则回退，但不发布被拒绝的模型正文，也不额外重试收费请求。

预算仅由服务器 `.env` 配置；请求体不能提高限额或工具权限。主聊天 MCP 仅能使用四个兼容只读工具；原宿主鉴权和具体预览确认写入路径保留。默认限额、费用计价边界及验收见 [P0 交付说明](delivery/FINAL-DELIVERY.md)。

### Agent P1 动态只读流程（2026-10-20）

保留原 `/api/agent` 与 `/api/agent/stream` 请求、基础响应字段和SSE类型。已配置模型的文本课程学习请求默认进入动态规划，服务器决定是否启用；`/api/ai`、问候/通用聊天、图片聊天、无模型规则与原学习业务接口保留。

动态流程额外返回 `agent`：`status`（completed/partial/awaiting_user）、`plan`、`planHistory`、`planRevision`、`completedStepIds`、`observations`、`decisions`、`decisionCount`、`replans`和`stopReason`。中间进度仍为workflow，经过证据校验的正文仍为content/done。前端继续使用原处理进度区，持久化可选agent元数据。

完成指本轮只读准备，不是学习掌握或保存确认。缺少条件时显示补充问题；用户下条消息仍走原接口，不新增或承诺P2恢复协议。现有run/checkpoint保存审计状态；partial/awaiting_user不会伪装为整个任务成功。

动态工具白名单在P0基础上增加现有平台的错题、到期复习卡和课程图谱只读查询；仅暴露实际可用项。`build_review_plan`兼容增加可选examDate/minutes，生成只读预览，不修改设置或采纳计划。原固定流程四工具、宿主鉴权与人工确认写入路径保持。开关与限额见 [P1交付说明](delivery/FINAL-DELIVERY.md)。
# 动态 Agent 持久化运行（P2，增量接口）

`POST /api/learning/agent-runs?courseId=...` 接收 `{id,question,mode?,documentIds?,context?,scenario?}`，scenario 为 prepare/chapter/wrong/exam，返回 `{ok:true,result:{id,courseId,revision,status,state,result,budget}}`。相同 id/请求幂等，内容不同冲突。

`GET /api/learning/agent-runs/{id}?courseId=...` 查询；`POST .../{id}/pause|resume|cancel` 接收 `{revision,...}`。unknown 恢复需 `acknowledgeUnknown:true`，awaiting_user 恢复需 `userInput`。所有调用沿用学习 API Host 和 X-Xueya-Token 鉴权。暂停在步骤边界生效。新接口不修改既有 HTTP/SSE 字段和事件类型。

P3–P5 增量：创建可带 `sourceIds`（1–48 个当前服务器来源 id）。`GET .../features` 返回 `{durable,interactive,configured}`。运行 `scenario` 为 prepare/chapter/wrong/exam；结果带可选 `interaction`（confirmation/quiz/diagnosis/missing_questions/missing_graph/awaiting_review/completed）。仅公开计划/观察，内部工具缓存及含答案试卷不随运行查询返回。

`POST .../{id}/confirm`：`{revision,confirmed:true,digest}`，绑定服务器预览。`answer`：`{revision,responses:[{questionId,answer,reasoning?}]}`，要求实际完整作答，评分复用原服务。`diagnose`：`{revision,confirmed:true,cause,reason}`，用户身份由服务器绑定。`refresh`：`{revision}`，重新准备预览或读取已有人工评分。`replan`：`{revision,settings:{examDate?,minutes?,availability?}}`，支持 exam 运行在 completed 后再次预览，需再次 confirm。

新增状态 awaiting_confirmation/paused/unknown 与既有 awaiting_user/partial/completed；响应包装仍为 `{ok:true,result}`。确认期间资料失效返回 STALE_EVIDENCE，学习状态变化返回 LEARNING_STATE_CHANGED，修订号不匹配返回 RUN_CONFLICT（409）。开关停用返回 AGENT_DISABLED / AGENT_INTERACTIVE_DISABLED。



### 首次启动演示课件（2026-10-24）

生产主服务默认启用 `XUEYA_AUTO_IMPORT_DEMO=1`。仅无任何文档历史的新数据目录向 `course-default` 后台准备仓库演示资料，不调用外部 API。复用原 SQLite artifact、FileStore 和 CPU JobQueue；已有文档、归档/删除历史及完成标记阻止重复初始化。

既有 `GET /api/platform/knowledge/catalog?courseId=course-default` 在已启动自动准备时增量返回可选 `demoImport`，包含 `{status,completed,total,currentFile,error,courseId,bundleHash?}`。status 为 preparing/running/completed/interrupted/failed。运行中页面轮询现有 catalog，完成后停止；原 documents/summary/capabilities 字段保持。

`POST /api/platform/knowledge/demo-retry` 接受 `{courseId:"course-default",confirmed:true}`，沿用主服务身份和 token 检查，只能重试已经存在的 failed/interrupted 自动准备；关闭自动准备或非默认课程不可强制初始化。重复点击运行中的任务返回当前状态，不新增协调任务。失败码仅在状态/日志中供诊断，界面显示可理解的资料修复提示。

### 网页 MCP 调用记录（2026-10-23）

保留原 HTTP 基础字段和 SSE 事件类型。动态流程的 `agent.decisions` 在 `call_tool` 时增量携带 `arguments`；工具观察增量携带 `round`，与决策轮次关联。UI/检查点保留所有有界观察，后续模型上下文仍只使用最近 8 条。

四工具固定流程的 `workflow`/`done` 可增量返回 `toolCalls`：`[{id,tool,arguments,status,data?}]`，运行中为 `running`，成功为 `completed`，失败为 `failed`。不新增固定流程的 `agent` 字段。浏览器保存记录供诊断，默认聊天界面只显示等待提示、正文和引用，不渲染工具明细或执行步骤。取消或断流时不得把没有返回的工具标为成功；诊断渲染器对参数与结果转义、限制长度并隐藏敏感键。


### 账号注册与资料入口（2026-10-24）

- 新增 `POST /api/account/register`，同源、本机 Host，JSON 为 `username`、`password`、`confirmPassword`。账号为3–40位字母、数字、点、横线、下划线；密码8–16个字符，至少一个英文字母和数字，两次一致。重复账号返回 `USERNAME_TAKEN`；密码格式和确认错误分别返回 `PASSWORD_FORMAT`、`PASSWORD_MISMATCH`（400）。成功返回 `{ok:true, username}` 并设置 HttpOnly / SameSite=Strict 会话 cookie。
- 账号哈希仍保存在主平台 SQLite meta 中，PBKDF2-SHA256、独立盐、600000次；既有账号及登录、初始化、改密接口保持兼容。注册多个账号共用当前本机学习空间，不新增私人数据隔离语义。服务重启后需要重新登录。
- 首页跳转学习空间前显示登录；未初始化空间可注册首个账号。`#space/knowledge` 为统一课程资料入口，原 `#space/library` 进入同一入口；详细阅读与版本管理保留在 `#space/library/manage`。
- 资料首页只展示资料总量及上传/查看入口，列表点击后展开。上传、原件读取、问答选择及回答引用继续使用既有 API；独立检索表单不再展示，后台 RAG 检索契约保留。
- 验证：`python -m scripts.check_auth_materials` 使用临时数据库与真实浏览器，覆盖注册校验、登录、上传解析、原文阅读、问答入口及移动端布局，不调用付费模型。


### 普通资料问答提速与耗时（2026-10-24）

`/api/agent`、`/api/agent/stream` 保留原有 HTTP/SSE 事件类型和必需字段。普通 `ask` 问题使用固定的检索、原文读取、单次模型回答流程，跳过外部模型规划。章节学习、复习计划、跨资料综合、多步骤任务、总结与出题保留原 Agent 路由。检索仍复用主平台 RAG、MCP、权限、资料范围与调用预算；不增设后端或本地模型。

快速路径关闭回答模型的扩展思考，优先输出带证据的 `claims`。只有完整解析、通过既有逐字引用验证且资料版本仍有效的段落才会作为 `content` 事件提前发送；部分 JSON、伪造引用和未经审核的改写不发布。没有可提前验证的段落时等待完整验证。前端以最终 `done.answer` 和 `done.sources` 为准；取消、截断、错误、资料版本变化继续沿用既有中断与降级行为，不自动付费重试。复杂 Agent 的证据验证要求不变。

完成事件新增可选 `timings` 对象：`route`（fast-qa/agent/general/no-evidence/direct）、`totalMs`、`firstContentMs`（首次已验证内容发出时间）、`firstModelTokenMs`（首次模型流式 token 时间）、`modelMs`（模型调用累计时间）、`modelCalls`、`phasesMs`（各流程阶段累计时间）。时间使用单调时钟，单位毫秒；未出现的首内容/首 token 为 null。非流式规划不能观测首 token，故该值可能为 null。阶段时间与模型时间有包含关系，不应直接相加。API 并发满时沿用 API_BUSY，不虚报排队耗时。

耗时附在已有主平台 run.result、浏览器会话消息中，取消/中断 run 也记录当前耗时；同时提供只含耗时及结果状态的 `qa_latency` INFO 日志，不记录问题、原文或密钥。回答旁显示总耗时。离线验证：`python -m pytest -q tests/python/test_fast_qa.py`、`python -m scripts.check_fast_qa`。浏览器验证用受控上游故意阻塞后半段，确认首段在上游完成前可见、点击引用能打开原文、普通问答1次模型调用而复杂问题继续多轮 Agent；不产生真实模型费用。


### 可解释的资料回答与语义核对（2026-10-24）

本节更新上节“普通问答单次模型调用”的说明：仍跳过多轮任务规划，但自然语言改写需要单独的批量证据核对，因此通常为一次回答生成加一次核对；纯逐字摘录仍只调用一次。复杂只读 Agent 和可恢复只读 run 共享相同核对逻辑。

- 提示词要求先直接回答，再用自己的话解释原因，必要时给出标注为假设的例子。每段用 `claims[].text` 表达，`kind` 为 paraphrase/inference，`evidence[].quote` 保留逐字原文，不再要求解释正文等于引文。answer 不可绕过 claims 校验。
- 第一层在服务端核对来源ID与逐字引文，并在生成、核对完成及发布前复查已有资料版本。无效引用在模型语义核对前拒绝。逐字摘录仅保留实际匹配该段文字的引用，避免附带无关来源。
- 第二层只把需要核对的改写/推理与有效引文发送到外部模型的新调用。判断包含条件、否定、数量、大小关系、因果与范围是否保持；推理只允许直接逻辑或基本算术推导。由服务端按 claim 索引关联 verdict，不接受回答模型自报审核结果，也不允许核对模型新增引用。
- 每个答案最多一次批量核对、最多12项改写或推理，输入最大96000 UTF-8字节，20秒上限及最多1536输出tokens（同时受总预算约束）。复用主平台provider、并发、调用账本与同一执行预算。失败、预算不足、结果不明、重复/缺失索引、非严格状态值均不授权解释；不自动重试，不额外引入模型服务。
- 只发布 supported 的解释，inference 在正文标为“基于资料的推理”。部分未通过则省略并提示；全部未通过时保留现有原文摘录降级。伪造引文、未审核改写不流入正文。语义核对仍是自动模型判断，并不等同于人工验收或事实正确性的数学保证。
- 原文片段仍可通过现有流式路径提前发布；改写/推理等核对通过后再通过既有 content/done SSE输出，前端以 done 为准。含原文前缀的流会补齐已核对解释，保持同一份合法JSON；取消与资料更新会停止发布。
- 新增可选 `omittedClaims` 数量；保留 `verification` 为 verbatim-only/reviewed-claims。`timings.phasesMs.evidenceReview` 记录语义核对耗时，modelCalls 与 modelMs 同时计入核对调用。

验证：`python -m pytest -q tests/python/test_explanatory_qa.py`，覆盖四个HTTP/SSE端点、改写、推理、部分拒绝、真实引文不支持结论、伪造引文、核对失败、预算限制、取消、资料版本变化和复杂Agent；`python -m scripts.check_fast_qa` 通过真实浏览器验证通俗解释、原文引用与调用次数。所有测试使用受控上游，不调用付费API。


### 练习模块 /api/practice/*（2026-10-25）

> 本节无课程参数的固定题库仅保留旧调用方兼容；当前页面已切换到下文2026-10-28的资料生成题库，只显示Hot 100和基础100，不再提供面试题入口。

固定内置题库的练习与复习接口。题库不依赖 AI 生成，作答判定在本地完成；以下题库、状态、作答及笔记接口不发起任何付费模型调用。新增的 AI 学习分析接口见下一节。
调用需同源、本机 Host，并带 `/api/platform/bootstrap` 返回的 `X-Xueya-Token`。已配置账号时还需有效的会话 cookie。

- `GET /api/practice/bank` → `{ok:true, version:'bank-2026-10-24', questions:[Question…]}`。整份 250 题随响应下发，数组顺序即题目列表的固定顺序；浏览器缓存后离线可练。题目按 `category` 区分形状：
  - `hot100`（100 题，`type:'code'`）：`samples`、`dataRange`、`hints`、`coreIdea`、`solutions{python,cpp,java}`、`complexity{time,space}`、`pitfalls`、`leetcodeUrl`。
  - `basic`（100 题 = 5 科 × 10 单选 + 10 填空）：单选 `options[4]` + `answer`（0 基下标）；填空 `answer` + `acceptedAnswers`（首项等于 `answer`）。
  - `interview`（50 题 = 5 科 × 10）：`answer`（一句话核心答案）、`keyPoints`、`followUps`。
  Hot 100 额外返回官方题号 `leetcodeNumber`、专题 `topic`、官方题单顺序 `officialOrder`，按专题和难度固定排序；其余题目按科目、知识点和难度固定排序。
  公共字段：`id`、`category`、`subject`、`type`、`title`、`prompt`、`difficulty`、`tags`、`explanation`。难度取值：Hot 100 为 简单/中等/困难，基础题与面试题为 基础/进阶/挑战。
- `GET /api/practice/state` → `{ok:true, serverSeq, statuses, notes}`。`statuses[qid]` 为 `{status:'pending'|'mastered'|'wrong', confidence:'unknown'|'fuzzy'|'mastered', wrongCount, correctCount, wrongEnteredAt, lastWrongAt, lastResult, masteredAt, lastOperationAt, revision}`，对应待刷/已掌握/错题本（互斥）与待巩固权重。`notes[qid]` 为 `{text, revision, updatedAt, conflicts:[{text,createdAt,deviceTag,baseRevision}]}`。
- `POST /api/practice/ops`，请求体 `{ops:[…], deviceTag?}`，单次最多 200 条、每条不超过 1MB。`op` 为 `{opId, kind, questionId, payload, clientTs, deviceTag}`，`kind` 取 `answer`（`payload.result` 为 correct/wrong）、`correct`（此答案也正确，仅填空；`payload.attemptId` 指向本次错误作答的 `opId`）、`master`、`conquer`、`fuzzy`、`mark-wrong`、`reset`、`note-save`（`payload.text`/`baseRevision`）。响应 `{ok:true, accepted, duplicates, rejected, serverSeq, statuses, notes}`。
  - `correct` 校验目标作答属于当前账号、当前填空题且原结果为错误；同一作答重复纠正不会再次改动计数。`statuses` 可含 `correctedAttemptIds`。未知或已移除题目也按单条 `rejected` 返回，不阻塞同批次其他保存。
  - **幂等**：按 `opId` 去重。重放同一 `opId` 进入 `duplicates` 且不改变任何计数，断连重试必须复用原 `opId`，否则会重复累计错误次数。
  - 单条 op 的非法之处进入 `rejected`，批次内其余 op 照常生效；整个请求体不合法才返回 4xx。
  - 状态始终由有序事件日志重导，不按字段覆盖，因此多浏览器合并是确定的。作答记录按 `opId` 合并去重，掌握状态以最后一次操作为准。
  - `note-save` 的 `baseRevision` 与服务端不一致时**两份都保留**：服务端文本不变，冲突文本追加到 `conflicts[]`，由用户选择保留哪一份。
  - 规则（与 `backend/xueya/practice_rules.py` 和 `frontend/js/state/practice-store.js` 为跨语言一致性实现）：单选/填空答错自动进错题本并 `wrongCount+1`，每次重新作答答错各计一次；算法题加入错题本、面试题点忘记只记录时间不加次数；错题本内答对**仍留在错题本**，需「已攻克」才移出；「此答案也正确」只撤销本次新增次数并把题目移回待刷，保留历史与随手记；「已掌握」「已攻克」移入已掌握，「移回待刷」恢复常规练习资格且不清空历史次数；「待巩固」只提高随机抽题权重，不改变列表排序。
- `GET /api/practice/notes/{questionId}` → `{ok:true, note}`，含 `conflicts`。

账号隔离：进度、作答与随手记按登录账号分键存储（未配置账号时为隐式 `local` 账号），跨课程共享，不写入共享学习空间；其他账号读不到也写不进。随手记草稿仅存浏览器、按账号隔离；临时作答和面试草稿刷新时清空。草稿不作为权威数据。

前端路由：`#space/practice/hot100`、`#space/practice/foundation`、`#space/practice/interview`、`#space/review`；练习默认入口为 Hot 100。筛选、选中题目与列表位置走路由参数或本地浏览状态，不新增顶部导航项。

验证：`python -m pytest -q tests/python/test_practice_bank.py tests/python/test_practice_rules.py tests/python/test_practice_api.py`，覆盖题库计数与形状、状态迁移、错误计数、等价答案纠正、幂等重放、账号隔离、随手记冲突保留两份。

> `POST /api/topics`、`POST /api/questions` 的接口契约保持不变；AI 生成题目入口已按产品要求移除，服务端能力仍在，不影响既有契约调用方。

### AI 学习分析 /api/practice/analysis（2026-10-27）

沿用练习接口的同源、本机 Host、令牌与账号会话鉴权。所有报告、快照、作业和追问按账号隔离，跨课程共享。仅明确提交生成或追问时调用外部模型，每个任务最多调用一次，无自动付费重试。

- `GET /api/practice/analysis` → `{ok:true, available, reports:[{id,createdAt,filters,title,cutoff,serverSeq}], jobs:[Job]}`。返回最近30份报告摘要及最近20个分析/追问任务。读取不调用模型。
- `POST /api/practice/analysis` 请求 `{days:7|30|0, category:'all'|'hot100'|'basic'|'interview', includeNotes:boolean, idempotencyKey:string}` → `{ok:true,job:Job}`。默认最近7天、全部题库、附带随手记摘录；0为全部历史。服务器从当前账号的已同步权威记录制作快照，不接受客户端传入统计或其他账号。无练习记录返回 `ANALYSIS_NO_RECORDS`，不发起模型调用。
- `GET /api/practice/analysis/reports/{reportId}` → `{ok:true,report:{id,kind:'practice-analysis',createdAt,filters,cutoff,serverSeq,title,model,analysis,snapshot,conversation}}`。`analysis` 为 `{title,summary,findings:[{kind,title,detail,questionIds}],recommendations:[{title,reason,questionIds}],limitations}`；kind取weakness/progress/pattern/coverage。题目ID必须属于快照范围，前端以纯文本安全展示模型输出。
- `POST /api/practice/analysis/reports/{reportId}/chat` 请求 `{message:string,idempotencyKey:string}` → `{ok:true,job:Job}`。message为1～1000字，结合报告快照与最近6条对话回答。会话保留最近30条消息，不重新读取最新学习记录。
- `GET /api/practice/analysis/jobs/{jobId}` → `{ok:true,job:Job}`。使用主平台 JobQueue 状态与字段，成功结果为 `{reportId}`。异步生成可在刷新后恢复，同一账号同时仅有一个分析或追问任务。

重复提交同一幂等键及同一请求返回原任务，即使之后有新练习记录也不重复调用；同一键参数变化返回 `IDEMPOTENCY_CONFLICT`。已有进行中任务返回 `ANALYSIS_BUSY`。未知调用结果保留 `unknown`，用户核对后才可用新的幂等键发起新的任务。

时间范围按 Asia/Shanghai 自然日计算，截止于快照生成时刻。单选/填空的作答数和正确数与掌握自评分别统计，填空纠正修改原作答的结果与原作答日期，不新增作答次数。当前错题、自评掌握数单独标明为截止时状态。报告保存当时快照，后续练习不改写历史报告。随手记最多每题240字，过大时明确标记省略。快照有大小上限，避免长历史造成无界模型请求。


## 2026-10-27 问答结果兼容补充

兼容现有全网搜索响应的`sourceObjects`来源元数据；客户端同时接受`sourceDetails`与`sourceObjects`，优先使用`sourceDetails`，并仅显示`sources`声明的ID。网页来源的`url/isWeb`字段保留，PDF资料范围与`webSearch`开关可以同时提交。

原`ok/answer/sources/knowledgePoints/model`及SSE事件形状保留。`sources`继续为ID数组；可选`sourceDetails`包含这些ID对应的真实来源对象（含title/quote/location及已有资料版本字段），用于显示服务端新检索到、浏览器初始预览中没有的引用。客户端只使用`sources`声明的条目。

新增可选`answerStatus=unavailable`与`reason`用于明确生成/审核未完成，`verification=not-generated`不表示内容已验证；此时正文不粘贴原文、不作为可学习的已完成回答，多步Agent以partial结束。`ok=true`仅表示请求已处理，不能忽略`answerStatus`。模型身份响应可为`engine=assistant-info / verification=server-config`，来自当前应用配置，无模型调用或课程证据。

## 2026-10-28 资料自动生成练习

同日精选题库补充：当前数据结构课程可通过 `practice-curated-selection` artifact选择固定的200题课程快照。`GET /api/practice/bank?courseId=...` 形状保持不变，选中时只返回该套Hot100与基础100。generation摘要增加 `curated:true,units,contentHash`；units为 `{id,name,hot100:10,basic:10}` 数组，页面用其展示知识单元导航并复用原tag筛选。题目增加 `curated:true,subtopic,origin,references`，origin区分authored新编与selected已有经典题选编，并保留原题ID与链接；generated为false。教材摘录只表示知识点背景，不宣称原题出处。安装将原文证据绑定本地实际sourceId、documentId、sourceVersion，资料修订失效时停止作为当前题库。历史快照继续参与旧作答/笔记ID检查和学习分析；个人练习记录仍按账号隔离。不新增HTTP根路由、数据库或模型调用，其他课程不自动启用本套题。

当前页面默认读取 `GET /api/practice/bank?courseId=...`，鉴权沿用练习接口。响应为 `{ok,version,questions,generations,available}`，仅含当前账号、指定课程中已完成且资料修订仍有效的生成题库。未生成时返回空数组，不冒用内置算法题作为当前课程的题目。无courseId的旧调用继续返回原固定题库以保留兼容；其面试题数据不删除，当前页面不显示。

每份资料目标为 `hot100:100` 和 `basic:100`，无 `interview`。Hot100表示该资料的经典重点与综合应用，不声称具有外网热度统计；基础100侧重概念和直接应用。题型为 `single/multiple/fill/boolean`，仅有编程证据时允许 `code`。非编程资料两类题库均包含四种客观题，编程资料可混入代码题。单选answer为下标，多选answer为去重下标数组（至少两个答案），判断answer为布尔值，填空保留answer及acceptedAnswers；代码有solutions语言映射和samples，不执行代码或自动判分。

生成题增加 `generated:true,number,documentId,documentName,sourceId,sourceVersion,evidenceQuote,quality`，保留原练习公共字段。number为该资料在相应类别内的1～100题号；持久化仍使用稳定id。sourceVersion绑定内容修订，逐字依据必须属于服务端提供的原文。生成复用C的QuestionService及题目校验；quality.answerSupport为pending，页面明确提示AI生成、答案需核对，不冒充人审。

`POST /api/platform/knowledge/upload` 保留原job/documentId响应，增加 `practiceGeneration`。首次用户上传登记出题，在RAG发布可读正文后自动启动；同文件导入幂等，不重复生成。旧资料管理上传可用 `/api/platform/documents/upload?...&generatePractice=1` 显式接入相同流程。附件解析、演示导入和CLI导入不因此自动发起出题。知识库catalog增加 `practiceGenerations`，供上传页面展示进度。

generation摘要含 `{id,courseId,documentId,name,status,revision,jobId,completed,target:200,error}`。状态包括waiting_parse、generating、model_unavailable、insufficient_material、succeeded，以及队列的failed/cancelled/unknown和资料失效stale。模型未配置、可读正文不足800字符或原文已变更时明确阻止；800字符仅为最低检查，不保证足以出200道高质量题。只有两类各100道全部完成后才发布到练习；中间成果保存在主平台artifact中，失败不冒充完成。

后台使用主平台JobQueue、API并发许可与模型账本，每批最多5道，代码每批最多2道，受已有单次执行预算限制。每个API作业maxAttempts=1，成功提交一批后原子登记下一批；进程重启保留已提交批次，未知付费调用不自动重放。`POST /api/practice/generation/{id}/resume` 在用户明确操作后继续未完成批次；`POST /api/practice/generation/{id}/cancel` 停止当前作业。两者沿用账号鉴权；其他账号不可访问。整个200题过程可能需要多次外部API调用并产生费用，页面上传前已说明。

原ops/state/notes契约保留，增加生成题ID可用性检查。多选及判断与单选/填空相同，答错自动进错题本；多选答案必须集合完全相等，判断严格按布尔值判定。学习分析快照纳入当前账号生成题及这两类客观题记录。浏览器题库缓存按账号和课程隔离；资料归档、替换或正文修订后，当前题库停止使用失效资料，历史题目依据和学习记录仍保留。

2026-10-28 选择性整合补充：学习分析快照超过原大小限制时，可省略从未有个人作答、操作、自评或笔记的题目明细；`stats.bankQuestions`及作答/错题等整体统计保持完整，增加可选`omittedUnpracticedQuestions`并在`limitations`说明省略范围。已记录题目仍保留；若实际个人记录本身过大，继续返回`ANALYSIS_TOO_LARGE`，不放宽原请求大小上限。客观正确率包含单选、多选、判断和填空，算法仍为自评。


## 2026-10-29：固定练习来源与综合题自评

本节覆盖此前自动200题的生产行为说明，旧接口兼容读取保留。

- `GET /api/practice/bank?source=workspace`：账号鉴权与原接口一致，返回固定算法100、408共300题、可追溯旧历史来源；不依赖courseId。旧无source调用仍保留原固定250契约。
- `bankSource`取algorithm、exam408、legacy。不能只靠category=hot100分辨来源；旧生成和精选题也有此category。算法原ID、力扣链接和题解不变。
- 408 `origin.kind`取adapted或authored；year及originalNumber是参考考点的来源身份。改编题自己的条件和答案不等于原卷。`topic`为章，`subtopic`为细分点，`tags`含两者；version随固定内容改变。
- 综合题type=short，有parts数组，每项`{id,label,points,reference}`。points为练习建议上限，reference为该问参考解答与评分点。题干/解答均在本地，不要求远程PDF读取。
- `POST /api/practice/ops`增加kind=`written-save`，例：`{opId:"unique",kind:"written-save",questionId:"e408-2021-41",payload:{questionType:"short",answers:{p1:"我的过程"},scores:{p1:2.5}}}`。answers每问最多12000字符，必须为真实小问ID；scores必须是有限数，0到相应points，不能是布尔值。操作逐条接受/拒绝，opId去重，沿用事件日志及serverSeq。相应state.statuses保存writtenAnswers及selfScores。
- 自评分不是客观判题，不增加correctCount/wrongCount。无分草稿不算自评活动，反复保存相同评分不重复统计；自评不自动改变待刷/掌握状态。
- `PracticeGeneration`生产默认legacy_enabled=False。上传返回practiceGeneration.status=deferred、target=100，只做解析；catalog不展示旧批次。启动取消旧生成活跃队列，watch/callback/enqueue/resume/execute/provider/publish均阻止旧200题续发。resume返回PRACTICE_GENERATION_RETIRED。受控兼容测试可显式开启旧实现，不代表生产仍自动调用。
- 浏览器workspace-v1缓存按账号隔离，必须含algorithm100与exam408300才可接收。旧后台忽略source返回旧题库时显示WORKSPACE_BANK_OUTDATED，不静默缓存空408。有效完整缓存支持离线；旧课程缓存不覆盖新来源。


### 2026-10-31 连贯正文输出

网页资料问答的最终正文保留模型生成的完整 `answer`，不再用 `claims` 条目拼接替代。发布前将正文及其证据笔记在同一次来源核对中检查；正文不通过时不会用已通过的零散摘录冒充完整回答。SSE 在核对完成前仅报告工作进度，通过后沿用原 content/done 格式发布正文。`verification=reviewed-narrative` 表示整篇正文经过模型来源核对，不表示绝对正确；完全逐字的正文仍为 verbatim-only。

自主兜底仍是一次独立、无课程证据包的请求，使用独立HTTP连接，避免承接异常的池内连接；不会重发原请求或循环调用。连接异常与超时分别记录错误类别，仅记录类别及异常类型，不记录密钥或请求正文。没有新付费在线验收。

### 2026-11-05 计划生成连接检查与回执恢复补充

- GET `/api/learning/space/plan/connectivity`：沿用本地Host/Origin、账号与X-Xueya-Token鉴权，向服务端配置的模型站点根路径发无密钥、无资料、非推理GET；`connected=true,inference=false,httpStatus`仅说明传输连接，不证明鉴权或生成质量。失败返回`AI_CONNECTION_FAILED`，不写模型调用账本。
- POST `/api/learning/space/plan/generate`：相同账号与operationId已存在时先核验输入一致并返回原job；真正新作业先连接预检，失败零入队、零推理。worker也预检，连接变化时不重试未知调用。客户端丢回执应保留并复用原operationId，不用新编号重发同一次操作。
- GET `/api/learning/space/plan/list`：失败/未知作业可扩展只读`diagnosticCode=AI_CONNECTION_FAILED`，来自同账号账本异常类名或作业错误码；旧status/error不改写，不公开异常正文或密钥，未知计费语义保留。

### 2026-11-05 计划超时与输入上限

计划作业服务端总限时270秒、单次规划请求120秒，仍取全局执行预算剩余值的较小者；仅服务端handler可配置作业时限，客户端Job DTO不接受timeout。其他作业默认90秒与其他学习生成默认60秒不扩大。新增只读诊断AI_PLAN_RESPONSE_TIMEOUT（兼容历史JOB_TIMEOUT），保留unknown计费、单次尝试与不自动重放语义。

规划输入只发送有界题目代表元信息和所选科目的课程元信息；资源上限64知识点/12,000字符并标partial，完整题目仍保留原Question/题库。按输出预算给出maxTasks（4096token最多20项），不要求模型逐日展开。模型响应经过既有依赖、来源、日期、休息日和每日预算检查后才保存草稿；不以固定模板冒充成功的AI计划。

### 2026-11-05 资料关联框架覆盖标记

material-plan框架新增coverage：kind=material-linked、representedPhases/totalPhases、representedTasks/totalTasks、partial。任务数以sourceTaskId去重，跨日拆分不虚增；该覆盖只指当前计划的资源关联，不代表教材学术完整性。plan完成草稿保存frameworkCoverage副本供展示，旧记录缺失时仍可读。模型生成的标题/阶段/说明不得把当前原创/改编候选称为站内逐字真题；程序规范化展示表述，用户目标与原题引用不改写。

### 2026-11-05 计划采用与导图失败隔离

计划GET/list增加派生canAdopt、可选frameworkStatus=failed/frameworkError。framework-pending草稿仅在同账号生成作业已终止并释放租约，且检查点stage=framework、planId及输入account匹配时可采用；GET不修写数据、不再付费生成。运行中的未完成草稿仍拒绝采用。

POST /plan/adopt继续要求confirmed=true、业务expectedRevision及operationId，保留事务、存储CAS、adoptionBase及单活跃计划规则。已保存有效计划的附属导图失败不再硬阻止采用；明确采用后持久化generationStatus=plan-ready-framework-failed，不修改原作业/账本或虚构frameworkId。再次提交同operationId返回原回执，不重复采用。业务revision与Repository version保持各自语义。


### 2026-11-06 知识点练习、确定性演示与阶段路线（增量契约）

既有 HTTP/SSE 入口和返回字段保留。下列接口继续使用本站 token、账号边界及学习空间存储。

- `GET /api/learning/space/materials/concept/{conceptId}?courseId=course-default`：返回已保存 `concept`、`sourceRevision`、`groups`（简单/中等/困难/待分级）及本知识点补题作业 `jobs`。知识点必须属于当前可访问、可信解析且版本有效的资料；题目仅公开题干、选项、难度、分级理由和来源字段，不返回答案。
- `POST /api/learning/space/materials/supplement`：输入 `conceptId`、`difficulty`、可选 `courseId`、`confirmedExternal:true`。复用 material-learning 作业；知识点/来源版本/难度构成幂等身份，一次最多4题，maxAttempts=1；相同身份的成功、失败和 unknown 均返回原作业，不自动重试。原题与记录保留，新题追加至原知识点。
- `GET /api/learning/space/algorithm-demo/{questionId}?sample=0`：仅支持 h100-63、h100-53，返回原题样例、教学代码及确定性 `steps`。不存在的题目/样例显式拒绝，不使用模型；DFS保持二维四邻域。
- 计划增加 `learningRoute`：完整计划 → phases → stages → nodes；节点保存题目 id/revision/sourceRevision、难度、日期、预算、缺题数和资源状态。新草稿创建时保存，GET只投影当前完成情况，不重新选题或调用模型。`POST /api/learning/space/plan/{planId}/route` 仅为无路线的历史计划整理一次现有资源，重复调用不替换题组。
- `POST /api/learning/space/quiz/attempts` 增加可选 `planId`、`nodeId`。服务端校验当前计划、节点、题目版本及资料可访问性；客户端不得将其他节点或计划的作答记到本节点。公开 attempt 增加 planId/nodeId 用于恢复同一上下文。
- 路线完成以节点中全部固定题的有效提交为依据，缺题节点不能完成；重复作答不增加完成题数，错题不阻止完成。每天学习完成事件按计划/日期幂等保存为 study-completion，与旧 attendance 到访记录分离。
- 阶段报告按 planId/nodeId/questionRevision 限定作答，首次正确率以首次作答的原始评阅为依据；争议、待评分和无法判定单独计数。重评不新增作答，其他阶段记录不混入；没有判定依据时 firstAccuracy=null。
# 知识图谱固定练习链接（2026-11-09）

`GET /api/learning/space/course-graph` 的 concept 节点新增 `fixedQuestions: [{id,title,url}]`，链接指向现有 `#space/practice/legacy/{id}`，复用课程固定题及原有作答记录。候选与当前账号 workspace 题库一致，不创建新 Question 或 Attempt。

已就绪的栈与队列章节可附加 `sourceType: fixed-practice` 节点，由可见题库的 topic/subtopic 分组。此类节点不计入 AI 提取批次或生成题统计；`questionIds` 仍仅供现有资料题练习接口使用。无匹配题时 `fixedQuestions` 为空，不伪造题量或重试模型。
