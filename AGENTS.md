# 项目开发约定

- 后端、后端测试、CLI 和新增验证脚本使用 Python；浏览器前端继续使用 HTML/CSS/JavaScript。所有 AI 推理只调用外部 API，不引入本地模型、GPU/CUDA 推理或 Node 后端桥接。
- 从最新 main 建立任务分支。统一主程序为 backend/xueya/server.py；不要用 C 分支历史兼容工厂替换 main 的平台、B 检索或数据库。C 学习领域代码在 backend/agent/，接入层在 backend/xueya/learning_integration.py。
- 保持 docs/api-contracts.md 的既有 HTTP/SSE 契约。后台作业、权限、并发、数据库和模型账本复用主平台；参见 docs/delivery/main-C-integration.md。
- 后端检查：python -m pytest -q（同时包含 tests/python 与 tests_python）。前端原有回归与浏览器检查继续保留，不运行历史迁移归档脚本删除它们。
- 密钥仅存 .env，禁止输出、提交。真实付费 API 测试须在用户明确授权的预算内执行，不自动付费重试。未经用户授权不得合并、强推或联系队友。
