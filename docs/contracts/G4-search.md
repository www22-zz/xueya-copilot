# G4 可控检索与综合问答兼容定义

基线 bc3a36b；用户分支 codex/g4-workspace，进度 G4-workspace.md。
复用 LearningHost/B RagService/C AnswerService、单一 SQLite/队列/API账本；不迁移 schema。
新增独立 SearchWorkspace(host)，鉴权后委派 /api/learning/search/*。
当前课程/浏览器 sessionId 绑定 context-policy，资料可 excluded/background/original，
模式 relevant/chapter/general；笔记为非权威背景。UTF-8字节估计明确非精确token/账单。
全文搜索首先免费；语义/混合只用已配置B适配器，笔记/题目等仍明确词法检索。
复杂回答在现有JobQueue分步记录query/evidence/result，最多4查询、显式API调用数上限，
不输出隐藏推理，不自动重试未知付费请求。所有来源在发布/读取时复核有效版本。
G3产物通过同一学习repo按kind查询，不复制笔记数据库、不将笔记当教材原文。
前端独立 search-workspace.js，app只初始化组件，组件自行维护可关闭对话框，不改旧聊天契约。
G1共享接线仅审查鉴权后委派/脚本初始化和API许可复用的小diff，不替换主路由/状态。
