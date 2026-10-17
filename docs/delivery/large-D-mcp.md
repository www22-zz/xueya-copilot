> 当前状态补充（2026-10-17）：默认 Python 宿主的 A～E 接线、修复与剩余工作以 [整体验收记录](AE-integration-audit.md) 为准。下文保留原阶段证据。

> 历史记录：本文件保留当时的实现与验收证据。当前后端已迁移Python/FastAPI，启动和派工以[README](../../README.md)、[当前需求](../requirements.md)及[Python迁移记录](../delivery/python-backend-migration.md)为准；旧Node命令不再作为开发要求。

# 大任务D交付记录：MCP工具平台

日期：2026-10-16。分支：`feat/large-D-mcp`，基于最新main `0a16b0e`。状态：**D平台实现与专项验证完成，待跨任务联调验收**。未合并main，未合入A分支代码，没有替B/C/E实现另一套业务/数据库。

## 范围和实现决策

按已批准的D完整任务执行，先核对已有官方SDK四工具，再扩展为严格schema网关、范围固定的业务工具、写入确认和远程扩展。保留默认stdio以兼容现有网页；服务端注入采用官方SDK进程内传输，远程采用官方createMcpHandler，分别验证，避免把普通函数调用声称为MCP。

不选择全局上下文进程池：测试表明复用降低启动延迟，但当前浏览器资料/记录每次请求变化，跨用户缓存需要B/E稳定版本与失效机制。保留每个Agent运行独立stdio进程，在同一运行中复用并关闭；新注入路径减少新进程启动成本，同时维持独立范围。

详细契约、代码示例和扩展方法：[MCP平台指南](../mcp-platform.md)。

## 内部工作进度

| 工作项 | 本次成果 | 尚需集成 |
| --- | --- | --- |
| W-040 本地工具 | 旧四工具回归；RAG调用B服务；新增14个资料/章节/学习端口；不可用端口不展示 | B/C/E提供正式仓库、概念/复习等业务实现 |
| W-041 写入预览 | 笔记/题目/计划prepare、preview、宿主confirm、apply、cancel；范围/版本/TTL/原文摘要绑定；审计事务契约 | A确认界面、E认证确认路由与正式事务存储 |
| W-042 工具治理 | allowlist、schema方言、输入/输出/发现预算、调用配额、取消/超时、并发上限、轨迹脱敏、进程清理、HTTP兼容 | C真实Run/Checkpoint配额及E根装配，生产代理/多进程认证 |
| 外部工具 | 可选Crossref DOI文献核对；固定域名和DOI-only出站；实际公开API连通 | 如需OAuth或其他收费服务，另提供对应服务与凭据 |

## 文件与导出

- `backend/mcp/index.js`：createToolGateway；JSON Schema验证、namespace、allowlist、预算、执行统计。
- `policy.js`：scope/page/result/字节预算和有界许可。
- `sdk-adapter.js`：真实SDK分页发现/调用/健康检查，拒绝无限游标/重复工具/大结果。
- `stdio-client.js`：connectStdio、processStats，最多4个进程、生命周期与取消清理。
- `course-session.js`：保持旧工具上下文接口，增加stats/onTrace。
- `course-server.js`：四工具保留，检索调用现有createRagService，不复制算法。
- `business-ports.js`：createBusinessPorts、createWorkflowSessionFactory；B/C/E依赖注入。
- `platform-server.js`：createPlatformServer、executionStats，14个按能力发现的读工具和3个写入工具。
- `platform-session.js`：createPlatformSession、connectionStats，官方SDK进程内往返，宿主确认与模型工具分离。
- `actions.js`：createActionAuthority，精确变更预览/确认、TTL、CAS和原文版本要求；事务由E实现。
- `http-client.js`：connectHttp、httpConnectionStats，HTTPS/URL allowlist、Bearer、响应预算。
- `http-server.js`：createPlatformHttpHandler，认证范围、Host/Origin校验、有界请求、限频、现代和legacy路径。
- `reference-tool.js`：registerReferenceTool，可选Crossref公开参考文献查询。
- `benchmark.js`：可重复运行的连接策略比较，不是生产池。
- 新增5份专项测试、1份测试仓库适配器；未修改package、lockfile、backend/app.js、前端或C核心工作流。

## 实际验证

基线62项通过；最终完整`node --test`通过86项（新增24项），无跳过/失败。MCP目录JavaScript语法检查和`git diff --check`通过。

```bash
node --test
node backend/mcp/check.js
node backend/mcp/benchmark.js
```

| 验证 | 实际证据 |
| --- | --- |
| 旧应用兼容 | 原62项全部保留；Agent HTTP仍经真实stdio检索、读原文和计划预览 |
| 双范围并行 | 两个用户/课程各自实际临时持久化资料，通过SDK同时查询，互相ID无法读取；模型不能覆盖scope |
| B业务接通 | 现有RAG服务读取临时仓库真实资料；现有Agent注入session后检索、读证据、受控模型回答，无degraded回退 |
| 写入闭环 | SDK生成笔记预览，宿主确认，SDK执行，重新打开磁盘数据确认内容、版本、auditId与一条审计；题目/计划同链通过 |
| 写入异常 | 未确认、重复确认、过期、取消、参数变更、越权、实体版本冲突、证据变更拒绝；重复apply返回原收据；并发/不确定提交不自动重放 |
| 等待确认 | prepare后关闭所有MCP连接，再宿主确认并用新session执行成功 |
| 生命周期 | 真实kill子进程、失败命令、活跃连接取消、寿命上限和并发上限；检查进程已消失、许可归零 |
| 工具治理 | schema、非法结果、UTF-8预算、分页、重复游标/工具、次数/成本、超时、不响应取消的处理器隔离，轨迹无私密输入 |
| HTTP现代协议 | 实际本地TCP连接，官方SDK发现/调用；2026-07-28版本及Mcp-Method/Mcp-Name头；取消达到真实业务AbortSignal |
| HTTP旧兼容 | 同端点legacy握手与调用；stateless GET=405 |
| HTTP边界 | 缺token、未批准URL、Origin、过大请求和禁重定向拒绝 |
| 公开API | 实际MCP查询Crossref DOI 10.1038/nphys1170，得到公开文献标题/出版方/年份；不是Mock成功 |

模型问答测试使用受控模型；**未调用付费MiMo模型、未做GPU实验**。临时磁盘仓库是验证适配器，**没有声称正式E数据库已联调**。概念/题库/复习等端口仅验证协议、范围和可注入性，实际算法由C负责。

## 性能记录

Windows、Node v24.19.0、官方SDK2.3.1，每组8次，本地内置示例，未调用模型。小样本诊断数据不是严谨性能结论，F可按相同命令扩大实验。

| 路径 | P50 | P95 | 补充 |
| --- | --- | --- | --- |
| 每请求stdio建连+检索+关闭 | 232.16ms | 275.52ms | 包含进程启动 |
| 两个固定上下文连接复用 | 0.83ms | 4.87ms | 不含213.98ms池启动，实验比较用 |
| 独立进程内SDK建连+检索+关闭 | 3.64ms | 22.45ms | 通过官方SDK消息传输 |

实验stdio进程累计10、峰值2、结束0，上限4；进程内连接累计8、峰值1、结束0，上限8。复用与独立方案输入规模相同，实验池交替包含示例/空上下文，不是并发压力试验；结论只支持启动开销比较，不支持跨用户全局池上线。

## 给其他任务的明确接线事项

1. **E**：实现指南中的read/readSource/applyConfirmed仓库契约；数据、CAS、引用版本校验、audit、幂等receipt同事务；提供当前用户/课程认证闭包。确认服务端不能信任模型传来的身份。挂载HTTP/确认路由并传播断开信号；正式数据库持久化与多进程恢复由E负责。
2. **B**：注入searchMaterials/readSource/listSections/readSection，提供稳定引用、版本和位置。当前默认适配器复用已有RAG，数据库大资料库应使用B的直接检索端口。
3. **C**：注入概念、先修、题目/作答/错题/进度/复习业务；通过openSession接入现有工作流；Run恢复、学习算法和模型预算仍由C管理。
4. **A**：显示服务端before/after/版本/过期时间，用户点击后调用E宿主确认路由。编辑预览需重新prepare。不要把confirm暴露给模型；等待确认释放流和计算资源。
5. **F**：复用专项测试和benchmark，扩大错误/恢复/性能实验；报告区分SDK真实传输、临时持久化适配器、正式业务库、真实公开API和受控模型。

## 已知限制与下一步

- 未动根装配，网页默认仍是旧四工具；新平台写入/新学习工具不会凭空出现在当前网页。待B/C/E/A交付后按上述接口接通，不应把此状态标成整站业务验收通过。
- 待确认动作在宿主内存，重启需重新预览；不确定写入须由E查事务收据，禁止自动重试。MCP会话不是业务Checkpoint。
- HTTP完成Bearer和无状态新/旧协议测试；未验证远程OAuth、旧有状态session恢复、公网TLS代理和多机部署。
- 每宿主限额不是分布式配额；外部API费用和模型Token预算由相应业务/运行层管理。
- 外部Crossref是公开元数据，不能充当课程原文，默认不联网。未来外部服务不可用时保留明确失败。
- 下一步是B/C/E/A实际模块交付后的联调和F独立验收；D目前可独立验证的实现已完成，不需要负责人再次拆成小任务。

## 提交记录

代码与专项测试：`b9025d0 feat(mcp): add scoped learning tools and confirmed write execution`。

交付与接线文档单独提交。具体提交SHA可用`git log origin/main..feat/large-D-mcp --oneline`获取；本分支普通推送远端，不自行合并main。
