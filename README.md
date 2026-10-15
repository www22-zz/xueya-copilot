# 学涯 Copilot · 新版

新版重新设计品牌首页和学习空间，使用原创动态知识球体、滚动内容呈现、交互演示与轻量状态反馈。没有沿用旧版的侧栏、配色或卡片布局。

[首页预览](docs/images/home-preview.jpg) · [验证记录](docs/verification.md)

## 运行

需要 Node.js 20 或更新版本，不需要安装依赖。

```text
node backend/server.js
```

访问 http://127.0.0.1:4173/ 。服务仅监听当前电脑。

已安装 npm 时，也可以在项目根目录使用 `npm start`。启动命令同时提供前端页面和后端接口，不需要分别启动两个服务。环境配置从项目根目录的 `.env` 读取，配置模板是 `.env.example`。

测试学习逻辑、模块接口、工具网关、服务端代理和资源路径：

```text
node --test
```

也可以使用 `npm test`。可选的浏览器回归检查为 `npm run test:browser` 或 `node tests/e2e/browser.js`，需要另行准备 Playwright 和浏览器。浏览器测试会自行启动临时服务，使用受控模型验证流程，不调用付费 AI；可通过 `CHROME_PATH` 指定现有 Chrome。截图位于 `test-results/browser/`，不会提交到 Git。

### 直接打开页面

也可以双击 `frontend/index.html` 预览首页和学习空间。此时使用本地检索摘录，不请求 AI 接口；需要真实 MiMo 问答时，按上面的启动方式运行服务并访问本地地址。直接打开与服务预览的浏览器存储位置不同，学习记录各自保存。

## 目录结构

```text
web/
├── frontend/
│   ├── index.html                 # 页面入口
│   ├── css/                       # A：视觉系统与响应式
│   ├── js/
│   │   ├── ui/views.js            # A：学习空间页面模板
│   │   ├── services/
│   │   │   ├── library-service.js # B：浏览器资料读取
│   │   │   └── chat-service.js    # C：问答请求、追问与回退
│   │   ├── app.js                 # 页面状态、存储、路由和事件
│   │   └── visual.js / motion.js / pointer.js # A：动效
│   └── assets/
├── backend/
│   ├── rag/index.js               # B：异步 RAG 服务边界
│   ├── agent/                     # C：工作流、提示词、回答校验
│   ├── providers/mimo.js          # C：模型 HTTP 适配器
│   ├── mcp/index.js               # D：工具注册与调用网关
│   ├── http/                      # 联调：HTTP 与静态资源
│   ├── config.js                  # 联调：环境配置
│   ├── app.js                     # 联调：模块装配
│   └── server.js                  # 服务启动，保持原命令
├── shared/
│   ├── contracts/index.js         # 公共数据格式与限制
│   ├── fixtures/course.js         # 内置课程示例
│   ├── rag/index.js               # B：前后端通用分段与关键词检索
│   ├── agent/local-answer.js      # C：本地摘录回退
│   └── learning.js                # 旧接口兼容、练习与计划规则
├── docs/
│   ├── team-development.md        # 分工、文件归属、分支与合并
│   ├── api-contracts.md           # HTTP 和模块接口约定
│   ├── design/                   # 设计与模块整理方案
│   ├── plans/                    # 实施计划
│   └── verification.md            # 验证记录
├── tests/
│   ├── unit/                     # 学习规则、模块与工具测试
│   ├── integration/              # HTTP、模型代理与静态路径
│   └── e2e/browser.js             # 可选的实际浏览器流程测试
├── .env.example                  # 本地配置模板；真实 .env 不提交
└── package.json
```

服务继续提供 `/api/health` 和 `/api/ai`。前端加载可在浏览器与 Node 共用的模块，保留 `/shared/learning.js` 兼容入口。服务不公开后端源码、文档或环境配置。

## 共同开发

先读 [四人协作指南](docs/team-development.md) 和 [模块接口约定](docs/api-contracts.md)。

- A：界面，主要修改 HTML、CSS、`frontend/js/ui/` 与动效脚本。
- B：RAG，主要修改 `backend/rag/`、`shared/rag/` 与前端资料读取服务。
- C：Agent，主要修改 `backend/agent/`、`backend/providers/` 与前端问答服务。
- D：MCP，主要修改 `backend/mcp/`，通过工具网关向 Agent 提供能力。
- 公共契约、启动配置、HTTP 路由和模块装配由联调负责人协调，避免四人一起修改入口文件。
- 各自从最新 `main` 创建任务分支，小批量提交 PR，验证后合并。不要删除其他模块目录。

当前尚未接入向量数据库或真实 MCP 服务；这次整理提供独立模块与接口，后续可分别开发。MCP 工具列表默认为空，课程问答不会自动执行外部工具。

## 使用流程

1. 首页点击“进入学习空间”。默认提供 3 份数据结构示例资料。
2. 在课程资料中添加 TXT / MD 笔记，实际读取、分段并加入检索。
3. 在资料问答中提问。点击引用查看原文，保存完整内容为知识卡片。
4. 进入示例题库练习；提交后记录正确与错误，答对的错题移出待巩固列表。
5. 在复习计划中设置考试日期和每日时长，更新计划时优先安排最近错题对应的知识点。
6. 完成任务可勾选，资料、卡片、对话、答题和计划记录刷新后恢复。

## AI 与数据

沿用 `.env` 中的 MiMo 配置，密钥只在服务端读取。服务端接收实际文本来源及最近追问上下文，返回的引用必须属于本次提供的资料。界面“MiMo 已配置”仅表示配置存在，成功生成后才显示在线。

模型不可用或响应超时时，回退到明确标识的“本地检索摘录”，仅展示相关原文；不伪装成模型生成。没有检索结果时明确说明资料不足。开放练习模式整理问题与参考内容；选择题来自内置示例题库。

资料和学习记录使用当前浏览器的本地存储，没有账号、云端同步或向量数据库。TXT / MD 限 1 MB、12 万字符；PDF / DOCX 限 10 MB，目前保存文件记录并明确显示“内容待解析”。提问时，仅相关文本片段与近期对话发送至所配置的 AI 服务。

## 设计与动效

参考 Apple、OpenAI、Linear、Stripe 的信息层级、产品叙事与交互细节，使用原创图形和产品内容。品牌页的知识球体在不可见或后台时暂停，也有手动暂停按钮；支持 `prefers-reduced-motion`。工具空间使用即时导航和清晰状态，原文与搜索使用原生对话框管理键盘焦点。布局覆盖桌面、平板和手机。

首页交互参考 Xiaomi MiMo：鼠标经过星球会引起局部粒子变化；资料、问答和知识卡片组成动态文字网络，节点可以进入相应功能，悬停或键盘聚焦时突出关联线条与说明。精细鼠标使用圆点和细圆环；输入框、可选中文本、弹窗、键盘导航、触屏和系统减少动态效果时使用适合的原生光标。

新版设计和实施文档分别位于 `docs/design/` 和 `docs/plans/`，验证记录见 `docs/verification.md`。
