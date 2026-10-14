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

测试学习逻辑与服务端代理：

```text
node --test tests/unit/learning.test.js tests/integration/server.test.js
```

也可以使用 `npm test`。可选的浏览器回归检查为 `npm run test:browser`，需要另行准备 Playwright；生成的测试截图位于 `test-results/browser/`，不会提交到 Git。

## 目录结构

```text
web/
├── frontend/                 # 前端页面、样式、交互和静态素材
│   ├── index.html            # 网站入口
│   ├── css/styles.css        # 视觉系统与响应式布局
│   ├── js/
│   │   ├── app.js            # 学习空间交互
│   │   └── visual.js         # 知识球体、图标与动效
│   └── assets/mark.svg       # 品牌图标
├── backend/
│   └── server.js             # HTTP 服务、MiMo 代理和静态资源访问
├── shared/
│   └── learning.js           # 前后端共享的课程数据与学习规则
├── docs/
│   ├── design/               # 产品设计方案
│   ├── plans/                # 实施计划
│   ├── images/               # 文档配图与首页预览
│   └── verification.md       # 验证记录
├── tests/
│   ├── unit/                 # 学习规则单元测试
│   ├── integration/          # 服务接口和资源路径测试
│   └── e2e/browser.js        # 可选的浏览器流程测试
├── .env                      # 本地环境配置，不提交到 Git
├── .env.example              # 协作者使用的配置模板
├── .gitignore                # Git 忽略规则
├── package.json              # 项目信息、启动和测试命令
└── README.md                 # 项目说明与协作入口
```

前端请求 `/api/health` 和 `/api/ai`，由 `backend/server.js` 处理。网页通过 `/shared/learning.js` 加载共享规则，后端通过相对路径引用同一文件；不依赖前端目录中的代码。服务仅公开必要的前端资源和共享规则，不公开后端源码、文档或环境配置。

## 共同开发

- 修改页面、样式和动效：在 `frontend/` 工作。
- 修改 AI 接口或服务配置：在 `backend/` 工作。
- 修改检索、题库或复习规则：在 `shared/` 工作，并运行相应测试。
- 更新设计与功能说明：在 `docs/` 和本 README 工作。
- 新协作者根据 `.env.example` 配置自己的 `.env`；每个人使用自己的本地配置。

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

新版设计和实施文档分别位于 `docs/design/` 和 `docs/plans/`，验证记录见 `docs/verification.md`。
