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

当前由浏览器检索后提交原文；`sources: []` 明确表示没有资料，不会自动替换成示例来源。历史只用于理解追问，不能作为引用依据。请求非流式，响应一次返回完整答案。

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

限制：问题 4000 字符；来源只处理前 6 条、每条原文最多 3000 字符；历史先取最后 8 条再保留 user/assistant 文本，每条最多 5000 字符；回答最多 16000 字符。模型请求上限 25 秒，前端请求上限 30 秒。

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
```

这些方法为异步接口，B 可替换为真正的解析或检索实现。当前 `ingest` 不持久化，HTTP Agent 使用 `prepareSources` 校验前端已选资料。前端资料读取在 `frontend/js/services/library-service.js`：

```js
await prepareDocument(file) // → {id,name,bytes,status,meta,chunks?}
```

TXT/MD 读取文本，限制 1 MiB、12 万字符；PDF/DOCX 限 10 MiB，仅记录。校验失败抛出 `error.code === 'INVALID_DOCUMENT'`，`error.message` 为可展示文案。读取失败由页面统一提示；保存与去重由控制器处理。

## 4. Agent 与模型（C）

```js
const agent = createAgent({ rag, model, tools });
await agent.run(chatRequest);       // → HTTP 成功响应形状，失败抛 Error
await agent.listTools();            // → ToolDefinition[]
await agent.callTool(name, args, { signal }); // → ToolResult
```

`run` 当前固定为“规范化请求 → 准备来源 → 构造提示词 → 模型请求 → 校验答案和引用”。工具调用是显式入口，不会执行资料或模型文本中的命令。C 后续设计工具决策流程时调用 `callTool`，无需修改 MCP 内部代码。

模型适配器：

```js
await model.generate({ messages }) // → {content: string, model: string}
```

模型返回的是原始文本，JSON 解析、知识点与引用过滤由 Agent 负责。MiMo 密钥、URL、模型名称沿用 `.env`。`createMimoProvider(config, fetchImpl?)` 支持替换请求实现，测试不使用真实密钥。

前端问答服务 `createChatService(options?)`：

```js
await chat.ask({ question, mode, sources, history, previousSources? })
// → {answer, sources: Source[], engine, online, knowledgePoints, model?}
```

这里的 `sources` 是浏览器候选来源集合，服务先检索再发 HTTP。没有直接命中且问题包含追问词时，可使用 `previousSources`。网络、超时、服务失败或响应格式异常时返回本地摘录；`file:` 页面不请求 HTTP。不要在 UI 模板中重复实现这套逻辑。

## 5. MCP 工具网关（C/D）

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

装配发生在 `backend/app.js`。当前没有外部连接、没有公开的任意工具执行 HTTP 接口；需要接入真实客户端时，由 C/D 与联调负责人共同接入。
