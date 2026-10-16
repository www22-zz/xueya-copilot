# 本地平台统一契约 v1.0

E负责公共装配；B/C/D以注入端口接入，A使用同源HTTP适配器。默认运行配置冻结为Node 24.4+内置SQLite（WAL、FULL同步）及内容寻址文件仓库；本机没有PostgreSQL/Docker。向量数据通过vector实体保存版本/模型/维度/外部索引标识，实际Embedding/向量检索由B实现，当前不冒充已具备pgvector。

用户明确要求所有AI能力永久只调用API：不探测/调度GPU，不安装本地模型、CUDA或Python推理Worker。resource仅cpu/api；cpu用于普通文件处理，api用于外部服务并发控制。外部请求结果未知时不自动重试或声称扣费至多一次。

公共验证入口：`shared/contracts/platform.js`。实体由`userId + courseId + kind + id`隔离，版本正整数，创建expectedVersion=0，更新使用CAS；时间存UTC ISO，日期业务调用既有学习规则，不用UTC截取替代本地学习日。

统一实体kind：document/source/note/question/attempt/event/concept/plan/review/session/run/checkpoint/artifact/vector。原文件只以hash引用，业务ID不能作为路径。课程可归档，归档后保留查询和导出，不接受普通写入。

分页：`{items,nextCursor}`，limit默认20最大50，游标绑定用户/课程/实体类型；稳定ID按字典序游标，变更期间新建项可能出现在后续页面，不承诺快照分页。SSE事件携带持久化seq，可用Last-Event-ID恢复。

仓库基本方法：`read({scope,kind,entityId}) -> null|{version,value}`；`put({scope,kind,entityId,value,expectedVersion})`；`list({scope,kind,cursor,limit})`。异步业务必须在事务外执行，SQLite事务回调禁止Promise。

D确认事务端口遵循[MCP指南](../mcp-platform.md)：applyConfirmed同事务保存实体、引用版本校验、审计和幂等收据。用户身份仅来自本地宿主；courseId是已存在且属于当前本地用户的课程选择，不是授权身份。

浏览器workspace v3完整快照用于原UI兼容与恢复，关系实体是同一SQLite内的可重建投影，不另起一套数据库。快照更新同样CAS，客户端冲突不能静默覆盖。迁移保留原始输入备份与hash，禁止清空浏览器数据。

扩展：PostgreSQL迁移应新增仓库适配器及一次性版本化迁移工具，保持ID/版本/事务端口并逐课程核对count/hash；不同时维护两个默认启动产品。账号/协作/云同步是后续P2，当前固定本地用户，预留scope隔离，不宣称多人认证已上线。

E正式装配为D注入Map形状SQLite确认store；确认/执行状态与receipt恢复见platform/action-store.js。数据库迁移版本当前3（基础表、API用量、确认状态），接口契约版本仍1.0。普通文件解析使用受控Node线程，模型能力一律外部API。
