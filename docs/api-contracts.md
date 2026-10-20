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

未启用持久数据时使用官方SDK真实stdio四工具；启用后工具读取SQLite中可信宿主选择的课程。模型不能覆盖userId/courseId。宿主确认路由不注册为工具。公共平台HTTP接口与错误/CAS/迁移语义见[平台指南](platform-guide.md)及[统一契约](contracts/phase1.md)。

模块装配统一在`backend/xueya/app.py`、`platform.py`；不再保留Node后端或Python到Node桥接。客户端JSON字段仍为camelCase，Python内部方法使用snake_case，不要求前端随语言迁移改名。
# G1/G2 增量接口

新增工作台能力/任务投影与课程资料导入/阅读接口，旧 HTTP/SSE 保持。兼容定义、鉴权、字段、调用关联和操作流程见 [工作台与资料接线](contracts/workbench-library.md)。

G5 复用同一学习主平台，新增分段媒体任务与有出处复习音频，旧媒体路由保留；见 [G5 媒体与音频契约](contracts/G5-media-audio.md)。

### 提问附件与麦克风输入（2026-10-20）

加号选择图片/文档；直接录音停止后，客户端转换为16kHz单声道PCM WAV，复用现有 `media/upload`、`media/transcribe`。ASR 使用 `mimo-v2.5-asr`，识别文字回填草稿，用户发送后才调用配置的 LLM（默认 `mimo-v2.6-flash`）。文档复用原上传/解析接口，并加入该次问答的 `documentIds` 及有效来源范围；无新增HTTP/SSE接口。详见[交付与使用说明](delivery/composer-input.md)。
