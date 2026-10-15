# 模块接口约定

本文件与 `shared/contracts/index.js` 一起维护。公共格式变更应由相关负责人共同检查，不能只改发送端或接收端。

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

解析正文最多保留 120 万字符；服务器不保存上传原文件。不支持的类型返回 HTTP 400 / `UNSUPPORTED_DOCUMENT_TYPE`，超限返回 HTTP 413 / `FILE_TOO_LARGE`。空正文不伪造内容，前端显示未识别到文字。内置 PDF 解析器覆盖部分文本 PDF、CMap 与压缩流，不提供 OCR，也不承诺支持全部 PDF 编码或布局。

## 3. RAG（B）

`shared/rag/index.js` 可由 Node 引用，也可用浏览器全局 `XueyaRag`：

```js
extractChunks(text, { id, name }) // → Source[]；600 字符窗口，520 字符步长
retrieve(question, sources)      // → Source[]；当前关键词检索，最多 4 条
```

`backend/rag/index.js` 导出 `createRagService({catalog?})`：

```js
await rag.ingest({ text, document })   // → { document, sources: Source[] }
await rag.retrieve({ question, sources? }) // → Source[]；缺省用内置示例
await rag.prepareSources(sources)     // → 规范化后的 Source[]；不重新排序
await rag.parseDocument({buffer,kind}) // → 上述解析响应；kind 为 pdf 或 docx
```

这些方法为异步接口，B 可替换为真正的解析或检索实现。当前 `ingest` 不持久化，HTTP Agent 使用 `prepareSources` 校验前端已选资料。前端资料读取在 `frontend/js/services/library-service.js`：

```js
await prepareDocument(file) // → {id,name,bytes,status,meta,chunks?}
```

TXT/MD 在浏览器读取文本，限制 1 MiB、12 万字符；PDF/DOCX 限 10 MiB，调用服务端解析后加入相同分段检索。解析失败或 `file:` 预览时保存待解析记录；空正文显示未识别到文字。校验失败抛出 `error.code === 'INVALID_DOCUMENT'`，`error.message` 为可展示文案。读取失败由页面统一提示；保存与去重由控制器处理。

## 4. Agent 与模型（C）

```js
const agent = createAgent({ rag, model, tools });
await agent.run(chatRequest);       // → HTTP 成功响应形状，失败抛 Error
for await (const event of agent.stream(chatRequest, {signal})) { /* 上述 SSE 事件对象 */ }
await agent.topics({sources});      // → 知识点响应
await agent.questions({sources,focus,count}); // → 题目响应
await agent.listTools();            // → ToolDefinition[]
await agent.callTool(name, args, { signal }); // → ToolResult
```

`run` 当前固定为“规范化请求 → 准备来源 → 构造提示词 → 模型请求 → 校验答案和引用”。`stream` 在最终 `done` 前执行同样校验；`topics/questions` 在 `backend/agent/practice.js` 中维护。工具调用是显式入口，不会执行资料或模型文本中的命令。C 后续设计工具决策流程时调用 `callTool`，无需修改 MCP 内部代码。

模型适配器：

```js
await model.generate({ messages, temperature?, timeoutMs?, signal? }) // → {content: string, model: string}
for await (const event of model.stream({messages,timeoutMs?,signal?})) { /* {type,text,model} */ }
```

模型返回的是原始文本，JSON 解析、知识点与引用过滤由 Agent 负责。MiMo 密钥、URL、模型名称沿用 `.env`。`createMimoProvider(config, fetchImpl?)` 支持替换请求实现，测试不使用真实密钥。

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

实现入口为 `createLearningWorkflow({model,openSession?,toolTimeoutMs?})`，公开 `run(input,{signal?})` 与异步生成器 `stream(input,{signal?})`。旧的 `createAgent` 保留原问答和出题兼容接口。

追问可提供 `context.previousSourceIds`，最多三个，仅保留当前 `context.library` 内的 ID。泛指追问结合近期用户问题生成检索词；没有命中时读取这些有效来源并核对原文，不把历史回答作为原文。常规新问题不会自动使用上一轮来源。

前端 `createChatService().stream(input,{workflow:true,onUpdate,signal})` 接受调用方的 AbortSignal。主动取消向外抛出取消原因，不返回本地摘录；页面清除未校验的片段，保留重试输入。网络失败或超时可本地回退，学习任务使用与服务端相同的 `shared/agent/tasks.js`，返回 `workflow` 和 `artifacts`，不写入已保存计划。SSE 单事件最多 1 Mi 字符，累计模型正文和推理最多 200,000 字符。

## 6. MCP 工具网关（C/D）

```js
const tools = createToolGateway({ timeoutMs: 10000 });
tools.registerTool({ name, description, inputSchema }, async (args, {signal}) => result);
await tools.listTools();                     // → ToolDefinition[]，默认 []
await tools.callTool(name, args, {signal});   // → ToolResult
```

结果沿用 MCP 内容结构：

```js
{ content: [{ type: 'text', text: '结果' }], isError: false }
```

支持 `structuredContent` 和其他 MCP 内容项，网关保留结果。业务错误可返回 `isError:true`，由工作流处理。网关只检查参数是对象、结果包含 `content` 数组；具体 JSON Schema 校验由工具实现或 MCP 适配器完成。

对接真实服务：

```js
await tools.registerServer('course', {
  async listTools() { /* 返回规范化后的 ToolDefinition[] */ },
  async callTool(name, args, {signal}) { /* 返回 ToolResult */ }
});
```

上面展示的是适配器形状，实际实现由 D 提供。真实 SDK 的 `{tools:[...]}` 响应应在适配器中取出 `tools` 数组。服务工具自动命名为 `course__原工具名`，避免不同服务同名。网关不负责握手、连接认证、翻页发现或关闭 SDK 客户端，这些由 D 的适配器负责。

调用超时或取消会终止等待并传递 AbortSignal；适配器也应响应 signal。远端操作是否真正停止取决于远端和传输支持，网关不保证撤销已执行的动作。

网关错误：`TOOL_NOT_FOUND`、`INVALID_TOOL_ARGUMENTS`、`TOOL_TIMEOUT`、`TOOL_ABORTED`、`INVALID_TOOL_RESULT`。注册错误：`INVALID_TOOL`、`INVALID_MCP_ADAPTER`、`DUPLICATE_TOOL`。适配器自身的异常继续抛出，由调用方处理。

装配发生在 `backend/app.js`。现在已通过 `stdio-client.js` 和 `course-session.js` 接入真实的课程 MCP 服务。每次学习流程创建独立连接、绑定上下文，并在工具阶段结束后关闭。四个课程工具及使用方法见 [Agent 与 MCP 指南](agent-mcp-guide.md)。没有公开的任意工具执行 HTTP 接口；接入额外服务时仍需由 C/D 与联调负责人共同确认工具白名单和数据范围。
