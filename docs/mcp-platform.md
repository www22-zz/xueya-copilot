# MCP工具平台：开发和接线指南

> 2026-10-16：已按用户要求整体迁移 Python，并对接最新 main f149b5d 的本地平台与确认 UI。本文件下方 TypeScript/Node SDK 示例保留为 D 的历史设计记录；当前入口为 backend/mcp/*.py，CLI 为 `python -m scripts.check_mcp`，默认启动为 `python -m backend.server`。业务 schemaVersion 2.0 保留；Python SDK 1.30.0 已验证 stdio、内存传输和 Streamable HTTP，外部 2026-07-28 专属协议模式未宣称兼容。实际交付以 [Python 迁移记录](delivery/python-migration.md) 为准。

本指南对应大任务D。旧网页默认继续使用四工具stdio链路；新增平台模块通过依赖注入接B/C/E，尚未修改应用根装配或增加网页确认路由。已验证范围见[交付记录](delivery/large-D-mcp.md)。

## 1. 启动和诊断

```bash
npm ci
npm start
node backend/mcp/check.js
node --test
node backend/mcp/benchmark.js
```

依赖继续锁定`@modelcontextprotocol/client@2.3.1`、`@modelcontextprotocol/server@2.3.1`、`zod@4.6.7`，未新增依赖或更改锁文件。实际验证环境为Windows、Node v24.19.0；其他Node版本仍需集成环境验证。

`mcp:server`运行原四工具stdio服务，stdout仅供协议使用。不要把日志写到stdout。新平台工厂需要宿主注入认证范围及业务服务，不会自行扫描磁盘、读取浏览器localStorage或安装数据库。

## 2. 两条兼容路径

| 路径 | 参数和输出 | 当前用途 |
| --- | --- | --- |
| `createCourseSession(context, options)` | 保留旧四工具参数和原输出 | 当前Agent默认调用；绑定本次资料和学习上下文 |
| `createPlatformSession({scope, services, authority}, options)` | 模型只传业务ID/查询；输出在协议上包裹`{schemaVersion:'2.0',data}`，宿主`session.call()`解包data | B/C/E注入业务端口，真实SDK进程内传输 |
| `createPlatformHttpHandler(config)` + `connectHttp(config)` | 相同平台工具，真实HTTP网络传输 | 可选远程服务，独立HTTP装配；默认不开放端点 |

旧`search_materials/read_source/analyze_progress/build_review_plan`名称保留。旧服务仍接受受限片段数组；新平台不会接受模型传入`sources`、`userId`或`courseId`。工具schema版本与MCP协议版本独立。

## 3. 用户/课程范围和工具列表

`scope`固定为`{userId, courseId}`。E从认证会话或可信本地用户配置取得，C从当前请求闭包取得；不能从模型输出或任意JSON请求字段直接认定身份。每次调用得到范围副本，服务修改参数不会改变后续调用范围。仓库必须在所有读写查询中实际按两者过滤。

以下是支持的端口；**只有注入对应函数才会发现该工具**。没有C概念业务时，不伪造概念查询成功。

| 工具名 | 服务方法 | 模型参数 |
| --- | --- | --- |
| `search_materials` | `searchMaterials` | query，limit 1～6 |
| `read_source` | `readSource` | sourceId |
| `list_sections` | `listSections` | cursor，limit |
| `read_section` | `readSection` | sectionId，cursor，limit |
| `list_concepts` | `listConcepts` | cursor，limit |
| `get_prerequisites` | `getPrerequisites` | conceptId，cursor，limit |
| `list_question_drafts` | `listQuestionDrafts` | cursor，limit |
| `list_attempts` | `listAttempts` | cursor，limit |
| `list_wrong_questions` | `listWrongQuestions` | cursor，limit |
| `list_reviews` | `listReviews` | cursor，limit |
| `list_plans` | `listPlans` | cursor，limit |
| `list_notes` | `listNotes` | cursor，limit |
| `analyze_progress` | `analyzeProgress` | 空对象 |
| `build_review_plan` | `buildReviewPlan` | 空对象；设置从可信业务上下文取得 |
| `prepare_action` | authority.prepare | kind、entityId、expectedVersion、after |
| `preview_action` | authority.preview | actionId |
| `apply_action` | authority.apply | actionId |
| `lookup_reference` | 可选Crossref连接器 | doi；需显式enabled |

分页默认20项，最大50项，返回`{items, nextCursor: string|null}`；结果不能超过limit，游标不能原样返回形成死循环。`read_section`也返回分页items，由B决定章节片段形状。仓库必须将游标绑定到用户、课程、查询和数据版本；D验证形状与预算，不把游标当文件路径解释。

搜索返回`{sources:[...]}`，读证据返回`{source:{id,quote,...}}`。版本、documentId、sectionId、页码/位置等B提供的元数据原样保留，ID不可因重新切片指向别的内容。新资料应提供`source.version`；旧资料没有版本时，写入确认仍绑定原文内容摘要。D不声称当前关键词检索已升级成向量RAG。

## 4. B/C/E接线示例

```js
const {createBusinessPorts, createWorkflowSessionFactory} = require('./backend/mcp/business-ports');
const {createActionAuthority} = require('./backend/mcp/actions');
const {createPlatformSession} = require('./backend/mcp/platform-session');

// repository、learning是E/C的实际实现，不能用模型输出冒充。
const services = createBusinessPorts({repository, rag, learning});
const authority = createActionAuthority({repository});
const session = await createPlatformSession({scope: authenticatedScope, services, authority}, {
  signal,
  onTrace: event => safeTelemetry(event)
});
try {
  const sources = await session.call('search_materials', {query: '本章重点', limit: 4});
} finally {
  await session.close();
}

// C既有createLearningWorkflow({model,openSession})无需重写。
const openSession = createWorkflowSessionFactory({
  resolveScope: async () => authenticatedScope, // 当前认证请求的闭包
  servicesForScope: async () => services,
  authority
});
```

`createBusinessPorts`复用B现有`rag.retrieve({question,sources,signal})`。当前默认RAG需要`repository.listSources({scope}, {signal})`提供该课程资料；B若支持数据库检索，可直接注入高效`searchMaterials({scope,query,limit}, {signal})`，避免整库载入内存。D不复制检索、掌握度或复习算法。

仓库可选读端口：`listSources`、`readSource`和表中分页方法。C的`learning.analyzeProgress/buildReviewPlan`接收`({scope}, {signal})`，自行取得真实作答与可信设置。所有端口接收AbortSignal，必须传到数据库、网络、模型或内部作业中。

## 5. 写入确认与E事务契约

三类写入：`note`、`question`、`plan`。当前是创建或按版本替换；不提供删除、任意文件覆盖、批量无限操作。

```js
const preview = await session.call('prepare_action', {
  kind: 'note', entityId: 'note-42', expectedVersion: 0,
  after: {title: '本章笔记', content: '待采纳内容', sourceIds: []}
});
await session.close(); // 等待用户时不占MCP连接或模型/GPU

// A展示服务端preview的before/after/版本/过期时间，用户点击确认后，
// E校验身份、课程权限、Origin/CSRF，将收到的actionId+digest交给authority。
authority.confirm(authenticatedScope, {
  actionId: preview.actionId, digest: preview.digest
}); // 这是宿主API，绝不能注册为模型工具！

const resumed = await createPlatformSession({scope: authenticatedScope, authority});
try {
  const receipt = await resumed.call('apply_action', {actionId: preview.actionId});
} finally {
  await resumed.close();
}
```

确认默认5分钟有效，绑定用户/课程、目标、完整before/after、expectedVersion、引用版本与原文摘要。修改任何内容应重新prepare并展示新预览；不能只在页面上编辑旧预览而继续提交旧digest。`authority.cancel(scope,actionId)`取消未执行预览，不写业务数据。

E必须实现：

```text
repository.read({scope,kind,entityId}, {signal})
  -> null | {version: positiveInteger, value: object}

repository.readSource({scope,sourceId}, {signal})
  -> null | {id,quote,version?,...}

repository.applyConfirmed({
  scope,actionId,kind,entityId,expectedVersion,after,
  references:[{sourceId,version,quoteHash}],
  audit:{actionId,digest,actor,courseId,kind,entityId,at}
}, {signal})
  -> {actionId,version: expectedVersion+1,auditId}
```

`applyConfirmed`必须在**同一个事务**内：

1. 验证用户/课程权限，查找同范围actionId已有receipt，已有则返回原收据。
2. 比较当前version；创建时expectedVersion=0，更新时必须等于当前版本。
3. 校验每个reference仍属于该范围，版本一致，quote摘要一致。`quoteHash = SHA256(JSON.stringify(source.quote))`，UTF-8十六进制摘要。
4. 保存after、追加审计、保存幂等receipt并提交；三者全部成功或全部回滚。

不能依次“写数据，再尽力写日志”。审计包含动作摘要和主体，避免原文、密钥和完整after。成功重复apply只返回原receipt；重复confirm拒绝。执行中第二次apply拒绝。事务结果不确定时动作进入uncertain，不自动重试；E应按actionId查询实际receipt/审计再恢复，不能让Agent猜测是否写入。

authority的待确认列表当前是宿主内存，最大100项，过期清理；进程重启后旧预览失效，必须重新生成。业务数据/收据/审计由E持久化，不依赖MCP会话。多进程部署必须由E提供共享确认状态和一致性方案，当前不宣称支持。

`tests/helpers/mcp-repository.js`是专项测试用临时JSON事务适配器，用于验证断开连接后实际落盘、CAS和审计；**不是正式应用数据库**，不应接入生产根装配。

## 6. 治理、资源和错误

| 边界 | 默认值 |
| --- | --- |
| 网关单次超时 / 总寿命 | 10秒 / 60秒；课程会话单次5秒 |
| 网关单会话总调用 / 成本单位 | 64 / 64；单位是内部配额，不是API计费金额 |
| 网关并行调用 | 4；不响应取消的调用仍占许可，避免无限重试堆积 |
| stdio活跃进程 | 每宿主进程4个，拒绝额外请求，不建立无界队列 |
| 平台连接 / 业务执行 | 每宿主进程各8个 |
| HTTP客户端连接 / 服务请求 / Crossref出站 | 4 / 8 / 4；认证范围每分钟最多120请求 |
| 会话最长寿命 | 60秒；必须主动finally.close，寿命上限是兜底 |
| 网关参数 / 工具结果 | 64KiB / 128KiB；UTF-8字节计数 |
| SDK传输参数 / HTTP请求体 | 256KiB；兼容旧有界资料数组 |
| 单页发现 / 工具总数 | 256KiB / 128；最多17个发现页，拒绝重复游标/名称 |
| HTTP单交换响应 | 512KiB，包括SSE字节 |

网关可配置`allowedTools`，名称使用`course__tool`；只有宿主配置能授予工具。远程annotations仅为提示，不能提升权限。未知工具、非法参数、业务范围不符、无效分页和大结果被拒绝。

轨迹回调只含`tool,status,durationMs,calls,costUnits`；不包含参数、结果、授权头、原文或异常堆栈。服务端业务异常仅返回规范大写错误码，其他异常收敛为`TOOL_FAILED`。如扩充日志，也必须维持此边界。

资料中包含“调用shell/发送密钥”等文本时，只是资料字符串。平台没有shell、任意路径或任意URL工具；业务ID由仓库解析，不允许把ID直接拼成文件路径。外部连接URL和token来自可信配置，不能来自模型参数。

常见错误：`MCP_BUSY`应提示稍后重试；`TOOL_TIMEOUT/TOOL_ABORTED`停止当前步骤；`TOOL_BUDGET_EXCEEDED`停止本轮；`ACTION_EXPIRED/ACTION_CHANGED/VERSION_CONFLICT/SOURCE_VERSION_CONFLICT`重新读取并生成预览；`ACTION_NOT_PENDING`检查状态/收据，不盲目重放。

## 7. HTTP认证与协议矩阵

新版MCP协议采用每请求元数据及无状态HTTP交换，和应用的学习Run/Checkpoint持久化无关。[官方2026-07-28说明](https://blog.modelcontextprotocol.io/posts/2026-07-28/)。锁定SDK默认客户端仍走legacy，现代模式必须显式启用；本项目根据本地2.3.1声明和实际网络测试选择入口。

| 组合 | 实测结果 |
| --- | --- |
| 旧stdio服务 + 旧宿主 | 四工具发现、校验、调用、关闭通过 |
| 平台McpServer.connect + InMemoryTransport | SDK legacy握手，通过；不能直接冒充现代HTTP入口 |
| createMcpHandler + connectHttp默认pin 2026-07-28 | server/discover、工具列表/调用和取消通过；POST携带Mcp-Method/Mcp-Name/版本头，无GET/会话握手 |
| 同HTTP端点 + connectHttp protocol:'legacy' | 旧初始化与工具调用通过；stateless兼容，GET为405 |
| 远程有状态session恢复、OAuth浏览器授权、反向代理生产部署 | 未验证；不可声称已支持 |

新协议已移除ping，健康检查使用`tools/list`。不要将SDK中的legacy session选项描述成新版业务Run状态。

HTTP装配示例：

```js
const endpoint = createPlatformHttpHandler({
  authenticate: async request => verifyTokenAndReturnScope(request),
  servicesForScope: async scope => createBusinessPorts({repository, rag, learning}),
  authority,
  allowedHosts: ['127.0.0.1:4180'],
  allowedOrigins: [] // 无需浏览器跨域时保持空
});
// E把Node请求转成Web Request，并将响应关闭/请求断开绑定到Request.signal。
const response = await endpoint.fetch(request);
// 停机时 await endpoint.close()

const remote = await connectHttp({
  url: 'https://trusted.example/mcp',
  allowedOrigins: ['https://trusted.example'],
  token: process.env.TRUSTED_MCP_TOKEN
});
try { await remote.health(); } finally { await remote.close(); }
```

HTTP客户端只访问配置的精确URL，禁重定向，不接受用户名/密码/query/hash；通常强制HTTPS。仅明确`allowLocalhost:true`时允许127.0.0.1/IPv6 loopback HTTP用于本地开发。服务端默认仅接受`/mcp`（可用path配置），检查Host、Origin、认证和请求体预算。Bearer认证已在真实本地HTTP中验证；OAuth发现/刷新流程不在本次验证范围。

Node桥接示例见`tests/integration/mcp-http.test.js`。正式装配还应设置socket/read-header超时和TLS，不能遗漏disconnect到Request.signal的映射。该测试桥接仅用于测试，不是新增公网部署命令。

## 8. 可选外部学习工具

Crossref用于查询用户指定DOI的公开参考文献元数据，符合学习引用核对用途。[官方REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)定义`/works/{doi}`查询。

传`reference:{enabled:true}`到平台session或HTTP工厂才注册`lookup_reference`。默认关闭，不需要API key；只把DOI发送到固定`https://api.crossref.org`，不发送课程原文或历史。禁止跟随重定向，超时5秒，响应上限256KiB，校验返回DOI与请求相同。返回标题/出版方/年份/DOI链接，并明确`courseEvidence:false`，不可当作课程原文依据。

2026-10-16实际通过MCP查询`10.1038/nphys1170`，得到`Measured measurement`、Springer Science and Business Media LLC、2009。另有受控测试覆盖失败、错误DOI、异常大小。外部API未来不可用时会返回错误，不伪造文献。

## 9. 新增工具步骤

1. 先由业务负责人提供带scope和signal的服务，不在MCP层实现第二套业务。
2. 在`platform-server.js`的固定端口表增加名称、严格Zod schema、描述；分页工具遵守统一items/cursor契约。
3. 为结果补充业务校验，保留可追踪ID/版本；控制结果大小，避免将原文件直接输出。
4. 写工具必须通过authority，不能增加模型可调用的confirm或`confirmed:true`后门。
5. 用真实SDK发现/调用，验证双课程、非法参数、取消、错误结果；必要时补真实服务联调。
6. 更新本指南、交付记录及版本兼容说明，不改写其他模块或自行合并main。
