# 项目语言约定

用户已明确要求后端全部使用 Python。新增或修改的后端、后端测试、CLI 与验证脚本使用 Python，不再增加 Node.js 服务端实现或 JavaScript 运行桥接。浏览器前端继续使用 HTML/CSS/JavaScript。

默认工作分支仍为 feat/large-C-agent-learning。迁移需兼容 docs/api-contracts.md 的 HTTP/SSE 和既有学习业务，维护 docs/delivery/python-migration.md 与 C 交付记录。真实密钥仅保存在 .env，不得输出或提交；本轮真实 API 测试累计授权上限 10 元，无自动付费重试。不得擅自合并、强推或联系队友。
