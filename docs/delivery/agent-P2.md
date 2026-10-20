# P2 持久化执行

在 P1（3719c79）基础上继续，origin/main 仍为 6ad28ef。沿用已从该 main 建立的任务分支历史，新分支 codex/agent-p2-p5。

复用 LearningRepository 的 run 命名空间、主 SQLite 事务、JobQueue、模型账本和 MCP。新增动态运行以 kind 区分原有 chapter 静态运行。

每个 agent-step 作业只做一次规划决策及其工具动作。保存计划版本、观察、已完成步骤、工具结果缓存和累计预算。预算在调用前落库；运行认领、状态更新及下一作业入队在同一数据库事务中完成。API 作业 maxAttempts=1。重启后的在途运行进入 unknown，必须 acknowledgeUnknown 才能继续；不会自动重放未知付费请求。

新增 /api/learning/agent-runs（POST 创建）、/{id}（GET 查询）、/{id}/pause、resume、cancel（POST）。复用本地 Host/token 鉴权、courseId 查询参数。变更要求 revision，恢复等待输入要求 userInput。pause 在下一步边界停止；运行中取消应先暂停。现有 HTTP/SSE 不变。

验证：4 项持久化验收通过；原 P1 27 项通过。无真实付费调用。
