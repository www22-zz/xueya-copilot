# 模块接口约定

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

加号选择图片/文档；直接录音停止后，客户端转换为16kHz单声道PCM WAV，复用现有 `media/upload`、`media/transcribe`。ASR 使用 `mimo-v2.5-asr`，识别文字回填草稿，用户发送后才调用配置的 LLM（默认 `mimo-v2.6-flash`）。文档复用原上传/解析接口，并加入该次问答的 `documentIds` 及有效来源范围；无新增HTTP/SSE接口。详见[交付与使用说明](delivery/composer-input.md)。

### Agent P0 可信执行（2026-10-20）

原路径、基础字段和 SSE 类型保持。资料问答的正文在逐条证据核验后以 `content/done` 发布，核验期间仍发送 `workflow` 进度；通用问答继续流式。未审核改写退回原文，额外返回 `verification/reason`；生成期间资料修订会阻止发布失效来源。

主服务通用聊天直接接收模型回答正文，不向上游强制 JSON 格式；宿主将每个正文增量做 JSON 字符串转义，继续以既有 `content` JSON 增量和最终 `done.answer` 发布。因此普通文字、Markdown 和用户要求的代码/JSON 示例不会因为不是 `{"answer":...}` 而丢弃。结构化课程任务和旧兼容调用仍执行原有格式/证据校验。工作流失败沿用 `general-chat-unavailable`、降级 `workflow` 和最终 `done`：空正文提示没有返回回答，截断/缺失结束帧提示回答不完整；仅确认本机未配置密钥时提示配置密钥，其他服务故障提示稍后重试。不透出上游原始错误或自动重试付费请求。

主服务通用聊天请求显式设置 `thinking: {type: "disabled"}`，并引导简单问题简短作答以减少等待；仍调用同一外部模型并由宿主保证 JSON 接口、流式事件和调用账本。课程资料问答及学习规划不自动套用此设置，继续使用原有推理模式。该优化不承诺固定响应时间，网络和服务端排队仍影响延迟。

聊天工作流的浏览器上下文通过同进程 MCP 会话调用原有课程工具，不再逐条消息启动 stdio 子进程；独立 stdio MCP 入口仍保留。工具参数校验、只读白名单、预算及课程隔离不变。主模型 HTTP 连接池随应用启动和关闭，逐请求超时仍独立生效，SSE 在 `[DONE]` 后消费 HTTP 收尾以允许安全复用连接，不再转发收尾后的内容，不自动重发失败请求。

聊天请求可选 `previousAnswerKind: "general"`：浏览器仅在所选历史范围的上一条助手回答为通用问答时提供此提示，契约层只保留该枚举值。`ask` 模式的指代/编辑追问可据此继续通用聊天；旧会话中针对已存在代码块的编辑也可直接续答。此提示不能绕过明确的课程依据要求或有效的上轮课程引用，不能改变用户、课程或权限。它不对其他新话题强制通用路由，也不会新增模型意图判定调用。

主模型调用增加输出上限与结束状态检查；原 `error` 字段可返回 `AI_TRUNCATED`、`AI_INCOMPLETE`、`AI_UNEXPECTED_TOOL_CALL`、`STALE_EVIDENCE`、`AI_RUN_TIMEOUT`、`AI_MODEL_BUDGET_EXCEEDED`、`AI_TOOL_BUDGET_EXCEEDED`、`AI_OUTPUT_BUDGET_EXCEEDED`、`AI_COST_BUDGET_EXCEEDED`、`AI_PRICING_REQUIRED`。工作流可继续采用已存在的原文/规则回退，但不发布被拒绝的模型正文，也不额外重试收费请求。

预算仅由服务器 `.env` 配置；请求体不能提高限额或工具权限。主聊天 MCP 仅能使用四个兼容只读工具；原宿主鉴权和具体预览确认写入路径保留。默认限额、费用计价边界及验收见 [P0 交付说明](delivery/agent-P0.md)。

### Agent P1 动态只读流程（2026-10-20）

保留原 `/api/agent` 与 `/api/agent/stream` 请求、基础响应字段和SSE类型。已配置模型的文本课程学习请求默认进入动态规划，服务器决定是否启用；`/api/ai`、问候/通用聊天、图片聊天、无模型规则与原学习业务接口保留。

动态流程额外返回 `agent`：`status`（completed/partial/awaiting_user）、`plan`、`planHistory`、`planRevision`、`completedStepIds`、`observations`、`decisions`、`decisionCount`、`replans`和`stopReason`。中间进度仍为workflow，经过证据校验的正文仍为content/done。前端继续使用原处理进度区，持久化可选agent元数据。

完成指本轮只读准备，不是学习掌握或保存确认。缺少条件时显示补充问题；用户下条消息仍走原接口，不新增或承诺P2恢复协议。现有run/checkpoint保存审计状态；partial/awaiting_user不会伪装为整个任务成功。

动态工具白名单在P0基础上增加现有平台的错题、到期复习卡和课程图谱只读查询；仅暴露实际可用项。`build_review_plan`兼容增加可选examDate/minutes，生成只读预览，不修改设置或采纳计划。原固定流程四工具、宿主鉴权与人工确认写入路径保持。开关与限额见 [P1交付说明](delivery/agent-P1.md)。
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

固定内置题库的练习与复习接口。题库不依赖 AI 生成，作答判定在本地完成，本节接口不发起任何付费模型调用。
调用需同源、本机 Host，并带 `/api/platform/bootstrap` 返回的 `X-Xueya-Token`。已配置账号时还需有效的会话 cookie。

- `GET /api/practice/bank` → `{ok:true, version:'bank-2026-10-24', questions:[Question…]}`。整份 250 题随响应下发，数组顺序即题目列表的固定顺序；浏览器缓存后离线可练。题目按 `category` 区分形状：
  - `hot100`（100 题，`type:'code'`）：`samples`、`dataRange`、`hints`、`coreIdea`、`solutions{python,cpp,java}`、`complexity{time,space}`、`pitfalls`、`leetcodeUrl`。
  - `basic`（100 题 = 5 科 × 10 单选 + 10 填空）：单选 `options[4]` + `answer`（0 基下标）；填空 `answer` + `acceptedAnswers`（首项等于 `answer`）。
  - `interview`（50 题 = 5 科 × 10）：`answer`（一句话核心答案）、`keyPoints`、`followUps`。
  公共字段：`id`、`category`、`subject`、`type`、`title`、`prompt`、`difficulty`、`tags`、`explanation`。难度取值：Hot 100 为 简单/中等/困难，基础题与面试题为 基础/进阶/挑战。
- `GET /api/practice/state` → `{ok:true, serverSeq, statuses, notes}`。`statuses[qid]` 为 `{status:'pending'|'mastered'|'wrong', confidence:'unknown'|'fuzzy'|'mastered', wrongCount, correctCount, wrongEnteredAt, lastWrongAt, lastResult, masteredAt, lastOperationAt, revision}`，对应待刷/已掌握/错题本（互斥）与待巩固权重。`notes[qid]` 为 `{text, revision, updatedAt, conflicts:[{text,createdAt,deviceTag,baseRevision}]}`。
- `POST /api/practice/ops`，请求体 `{ops:[…], deviceTag?}`，单次最多 200 条、每条不超过 1MB。`op` 为 `{opId, kind, questionId, payload, clientTs, deviceTag}`，`kind` 取 `answer`（`payload.result` 为 correct/wrong）、`correct`（此答案也正确，仅填空）、`master`、`conquer`、`fuzzy`、`mark-wrong`、`reset`、`note-save`（`payload.text`/`baseRevision`）。响应 `{ok:true, accepted, duplicates, rejected, serverSeq, statuses, notes}`。
  - **幂等**：按 `opId` 去重。重放同一 `opId` 进入 `duplicates` 且不改变任何计数，断连重试必须复用原 `opId`，否则会重复累计错误次数。
  - 单条 op 的非法之处进入 `rejected`，批次内其余 op 照常生效；整个请求体不合法才返回 4xx。
  - 状态始终由有序事件日志重导，不按字段覆盖，因此多浏览器合并是确定的。作答记录按 `opId` 合并去重，掌握状态以最后一次操作为准。
  - `note-save` 的 `baseRevision` 与服务端不一致时**两份都保留**：服务端文本不变，冲突文本追加到 `conflicts[]`，由用户选择保留哪一份。
  - 规则（与 `backend/xueya/practice_rules.py` 和 `frontend/js/state/practice-store.js` 为跨语言一致性实现）：单选/填空答错自动进错题本并 `wrongCount+1`，每次重新作答答错各计一次；算法题加入错题本、面试题点忘记只记录时间不加次数；错题本内答对**仍留在错题本**，需「已攻克」才移出；「此答案也正确」只撤销本次新增次数并把题目移回待刷，保留历史与随手记；「已掌握」「已攻克」移入已掌握，「移回待刷」恢复常规练习资格且不清空历史次数；「待巩固」只提高随机抽题权重，不改变列表排序。
- `GET /api/practice/notes/{questionId}` → `{ok:true, note}`，含 `conflicts`。

账号隔离：进度、作答与随手记按登录账号分键存储（未配置账号时为隐式 `local` 账号），跨课程共享，不写入共享学习空间；其他账号读不到也写不进。本地草稿（随手记未保存文本、临时作答、面试临时草稿）仅存浏览器、按账号隔离，不作为权威数据。

前端路由：`#space/practice/hot100`、`#space/practice/foundation`、`#space/practice/interview`、`#space/review`；练习默认入口为 Hot 100。筛选、选中题目与列表位置走路由参数或本地浏览状态，不新增顶部导航项。

验证：`python -m pytest -q tests/python/test_practice_bank.py tests/python/test_practice_rules.py tests/python/test_practice_api.py`，覆盖题库计数与形状、状态迁移、错误计数、等价答案纠正、幂等重放、账号隔离、随手记冲突保留两份。

> `POST /api/topics`、`POST /api/questions` 的接口契约保持不变；AI 生成题目入口已按产品要求移除，服务端能力仍在，不影响既有契约调用方。
