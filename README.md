# 学涯 Copilot

基于课程资料的本地学习助手，提供知识库、有据问答、资料阅读、练习与错题，以及学习计划和复习服务。

前端使用 HTML/CSS/JavaScript，后端使用 Python/FastAPI。所有 AI 推理只调用外部 API，不安装本地模型或 GPU/CUDA 环境。

学习空间主入口为 **AI 助手 / 学习中心**。学习中心左侧依次为 **课程学习、练习、复习、学习分析**；执行计划在 **学习分析 → 我的学习计划**，知识框架历史在 **AI 助手工具** 中。学习中心内的学科、专题是各模块的筛选层级。当前修复范围和尚未完成的新方案要求见[交付说明](docs/delivery/FINAL-DELIVERY.md)，不能将已有界面入口视为整份新方案已经验收。

练习提供原版力扣算法 **Hot100**（100道代码题、17专题、三语言题解、跳转力扣作答）、**我的小测与作答**和固定 **408题库300题**（240单选＋60综合应用，四科分章）。408原有综合题仍按小问保存过程、对照评分点自评，不把自评改称 AI 评分。

可在聊天主动请求小测，直接提交答案，并从练习打开同一题与同一次作答。新题卡客观题由服务端判定，主观题保存原答案后入后台评阅；有评分标准才给参考分，复核与人工修正保留版本，不新增作答次数。Hot100和408的主观文字作答可进入同一参考评阅链，原自评独立保留；不执行代码，也不声称已读嵌入PDF的图。AI生成题尚未独立审校，旧缺完整快照记录保留只读。

聊天提出学习规划时先补齐缺项；分析内也可输入目标与时间。两个入口都生成后台作业、草稿与独立知识框架，明确采用后才成为当前计划。任务依赖由程序校验，跨学科共用每日预算；可打开实际固定题/课程章节、补用户链接，并预览调整时间；已完成记录保留，竞争采用会明确冲突。框架支持持久AI细化、撤销及历史筛选，修改知识图不改变计划。

本人课程、手动完成与真实HTML5续播位置保存在本账号服务端，可刷新恢复并与课程任务双向同步；匿名旧缓存不自动归属，当前账号的本机旧记录可显式导入。原站嵌入播放器没有本站可读进度，完成与掌握分开。旧视频目录仍未完成真实分集/播放验收，详见[课程核验记录](docs/resources/course-source-verification.md)。

408现有151道历年考点改编、149道项目原创，全部题干及解答可在站内阅读；不是逐字原卷题库，原卷链接仅用于追溯考点，不应拿原卷答案判改编题。逐题来源与构建方法见[408题库说明](materials/exam408/README.md)。本地加载和作答不产生模型费用。

旧“每份上传资料自动生成Hot100＋基础100”流程已默认停用。上传继续解析和进入资料库，既有题目、错题、笔记和学习记录保留在历史来源中。此前[数据结构精选题库](materials/data-structures-practice/README.md)属于旧教材混合题，不覆盖新的固定算法或408入口。其他问答与AI分析仍按各自设置使用外部API。

## 启动

Windows 双击根目录的 **启动学涯.cmd**，或安装 Python 3.11+ 后在项目根目录运行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
.venv/Scripts/python.exe -m backend.xueya.cli doctor
.venv/Scripts/python.exe -m backend.xueya.server
```

打开 [本机学习空间](http://127.0.0.1:4173/)。也可用 `scripts/start.ps1` 自动准备环境；macOS/Linux 的解释器路径为 `.venv/bin/python`。已有 npm 时，`npm start` 同样启动 Python 服务，后端不需要 Node.js。

界面布局样式和图标字体由本地提供，打开页面无需访问 Tailwind CDN 或 Google Fonts。浅色、深色及跟随系统沿用「系统设置 → 通用设置」。开发时修改前端 utility 类后，运行 `npm ci`，再用 `.venv/Scripts/python.exe -m scripts.build_frontend_styles` 更新随应用提供的 `frontend/css/utilities.css`；此编译步骤需要 Node.js，Python 服务运行时不需要。图标字体许可证及来源见 `frontend/assets/material-symbols-LICENSE.txt` 与最终交付说明。

配置模板为 `.env.example`，真实密钥写入本机 `.env`。停止服务运行 `.venv/Scripts/python.exe -m backend.xueya.cli stop`，或 `scripts/stop.ps1`。更新时保留 `.env`、原数据目录和访问地址；数据库升级与恢复见 [平台指南](docs/platform-guide.md)。

## 使用

学习平台现在有三个并列入口：**课程资料学习、算法学习、408考研学习**，默认从全部可访问资料学科中选择。问答课程选择器仅表示当前问答上下文，不要求先锁定学习科目。

课程资料学习中，私人资料可信解析并完成必要校正后沿用上传处理流程；已有资料进入和刷新页面不再自动发起出题。知识点目录与图谱共享三档难度练习，旧题未分级时单独标识，补题需明确确认外部模型费用。图谱节点可打开关联的单选、多选、判断与填空，支持缩放、拖动画布与搜索。未匹配标准形式的填空进入待复核。相同内容修订不会因刷新或重复上传反复生成，失败/unknown不自动付费重试。首批题量受输出预算限制，大资料会明确标记部分覆盖，不能理解为整本教材已出完题。视频目录展示全部已核验课程总览，不再按当前已就绪资料的学科范围过滤。上传与管理页展示资料索引状态、知识库规模，并可对当前资料库做关键词/向量检索调试；未配置的能力明确显示未配置。个性化学习工作台按目标、学科、难度与时间调用外部模型生成阶段路线，可先看程序估算再生成草稿，并导出 XMind/FreeMind 思维导图；XMind 文件为 Zen 兼容格式，本机尚未用真实 XMind 客户端验证，导出同时提供 .mm 兜底与站内路线树预览。

个性化计划可选择学科/专题、难度、起止日期、每日时长与休息日；先查看草稿，再采用。资料题目可关联同一知识点的阶段导图和练习；有匹配资源时提供课程总览链接，没有精确分集时如实标注。个性化学习页可只填目标文字生成草稿，无本地题目绑定时任务明确标注“未绑定本地题目”；右侧估算与导出路线均来自程序真实计算和已保存计划。个性化学习默认展示阶段路线，保存节点题组及版本，按该节点的有效作答计算完成情况；阶段分析可追溯原题与原作答。每日签到独立于学习完成和掌握度。

算法学习入口直接打开 Hot100 精选题库工作台（旧 `#space/algorithms` 自动重定向）；#35《搜索插入位置》和 #200《岛屿数量》仍提供独立交互演示，读取原题示例，展示二分区间或三维网格DFS的深入与回溯。演示支持播放/暂停、前后步、重置及调速，不执行用户代码。Hot100 代码台会对 Python、C++、Java 解法做真实本地运行：Python 用后端同款解释器，C++/Java 在检测到 g++/JDK 时本地编译执行，按题库示例逐用例比对并在页面显示编译或运行错误；未检测到编译器的语言会明确提示原因、不影响 Python 与其他功能。C++/Java 暂不支持 4 道设计类题和环/随机指针等特殊结构，会返回“暂不支持”。也可按需调用外部模型做复杂度诊断，未配置模型时明确报错。执行器是本机单用户功能，不是强安全沙箱。

408入口保留分科练习，并提供历年原卷/整理解析的原站链接，以及程序选编和AI选题模拟卷。页面为双卡片工作台：**自主练习**进入分科练习；**模拟考试**在弹窗中选择科目、题量、时长与组卷方式，确认后进入全屏计时考试（服务端截止时间、逐题保存、右上角退出、底部交卷）。站内计时卷首版为固定单选题，逐题保存、刷新恢复、服务器截止时间、交卷评分与逐题解析；已答题交卷后进入统一作答记录。原卷尚未结构化接入自动阅卷，不能把固定改编题或模拟卷称为对应年份真题。详见[新方案边界](docs/architecture/material-learning-update.md)。

**学习分析**可选最近7天、30天或全部历史、题库、随手记，以及对话/课程/小测/计划依据；可排除会话，非学习会话需手动纳入。报告使用固定截止快照，后续订正不改写旧报告；无练习但有其他记录也可做限定分析。程序统计区分客观题、AI参考分、人工修正及自评，不能把AI回答、课程确认或重复复核当作掌握或新作答。生成和追问使用外部模型，历史阅读不调用。

首次打开分析会初始化每周一09:00（Asia/Shanghai）的本地回顾检查。设置可改周期或关闭。外部自动分析默认关闭，账号本人勾选并确认数据外发和付费后才启用；未启用时只准备本地候选。停机错过多个周期合并一份，无新记录跳过，多worker去重，未知作业不自动重放。更完整的验收与剩余限制见[交付说明](docs/delivery/FINAL-DELIVERY.md)。

1. 从首页进入AI问答或学习平台；学习平台按全部可学科目选择，问答可另选课程上下文。
2. 在“知识库”导入或查看资料、处理状态和原文；选定问答使用的资料范围。
3. 在资料问答中输入问题，可附图片或语音，核对回答的原文引用。模型未配置或生成失败时明确提示未完成，原文保留在引用区供核对。
4. 使用练习与错题页完成题目、查看解析并记录复习；服务端高级学习能力按实际入口和配置开放。
5. 在设置中查看本机账号、任务、用量和服务数据。账号共用本机服务，但私人资料、工作区和任务按登录账号隔离，不跨电脑自动同步。旧共享空间中归属未知的资料不会自动分配给新账号。

新数据目录首次启动会自动准备仓库内 17 份数据结构课件；进入知识库查看进度。已有资料历史的目录不会重复导入，可用 `XUEYA_AUTO_IMPORT_DEMO=0` 关闭。课件、图片补录及手动导入见 [共享资料包](materials/data-structures-algorithms/README.md)。私人数据库不随 Git 同步。

知识库支持最大64MiB的PDF；扫描教材须先完成文字识别，之后才能预览并确认替换旧PPT资料。OCR每次仅处理显式选择的一批，不会自动调用整本教材；未配置服务时显示待识别。接口、当前扫描教材准备状态及限制见 [PDF教材换库](docs/contracts/pdf-knowledge.md)。

“栈与队列”可直接使用新编写的 [Markdown知识库](materials/stack-queue/栈与队列知识库.md)，包含基础概念补课、核心实现、进阶算法和13个可分别编译的C++17完整程序，无需OCR。使用、验证与RAG接入方式见 [教材说明](materials/stack-queue/README.md)。

演示可使用 [提问清单](materials/stack-queue/演示提问清单.md) 或 [直接复制的问题](materials/stack-queue/演示问题.txt)，分别注明历史真实问答与本地规则验证。本机已启用`AI_RAG_GENERAL_FALLBACK=1`：资料不足或回答未完成时，最多切换一次不带课程引用的MiMo自主回答；不会重放原超时请求，界面明确区分资料回答与自主回答。

## 验证

```powershell
.venv/Scripts/python.exe -m pytest -q
node scripts/test.js --frontend
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -m backend.xueya.mcp_server --check
.venv/Scripts/python.exe -m scripts.check_quality --repeats 1
# 本机评测能力自检（Python / C++ / Java 是否可用、版本与路径）
.venv/Scripts/python.exe -m backend.xueya.judge_toolchain --probe
# 用题库官方参考解自测某语言的判题覆盖率（可按需加 cpp / java）
.venv/Scripts/python.exe -m backend.xueya.code_runner --self-check --languages python
# 学习工作台专项（代码运行/思维导图/静态资源；需先以 XUEYA_DATA_DIR 指向临时目录启动隔离服务）
.venv/Scripts/python.exe -m scripts.check_workbench_http --base http://127.0.0.1:4199
# 408/个性化学习/资料库/Hot100 页面截图与控制台、横向溢出检查（需 Playwright 与浏览器）
.venv/Scripts/python.exe -m scripts.check_redesign_browser --base http://127.0.0.1:4199 --out test-results/redesign-shots
```

Node.js 20+ 用于前端回归。可选浏览器检查为 `node tests/e2e/browser.js`、`workspace.js`、`platform.js`，需要 Playwright 和浏览器，可设置 `CHROME_PATH`。测试使用临时数据库及受控上游，不等于真实模型质量验收。生成文件统一位于被 Git 忽略的 `test-results/`。

## 目录

| 目录 | 最终交付用途 |
| --- | --- |
| `frontend/`、`shared/` | 页面、浏览器状态、客户端、离线规则与静态资源 |
| `backend/xueya/` | 统一宿主、HTTP/SSE、SQLite、作业、RAG、MCP、模型账本与接入层 |
| `backend/agent/`、`backend/providers/` | 学习领域、证据校验、复习计划、多模态与外部 API 适配 |
| 其他 `backend/` 模块 | 仍被专项测试使用的兼容实现，不是第二个生产入口 |
| `scripts/` | 启动、导入、维护和可复用验收工具 |
| `tests/`、`tests_python/`、`evals/` | 回归测试、测试夹具、固定评测集及研究基线结果 |
| `materials/`、`demo/` | 共享课程和演示资料 |
| `docs/` | 最终操作指南、接口契约、技术报告与交付说明 |

## 文档

- [MinerU / Qwen 教材解析、校正与向量检索](docs/contracts/mineru-qwen.md)（含已核验的服务协议、样本验证和Markdown替代方案）

- [最终交付说明与已知限制](docs/delivery/FINAL-DELIVERY.md)
- [技术报告](docs/reports/学涯Copilot技术报告.md) · [演示与验收指南](docs/demo/演示与验收指南.md)
- [HTTP/SSE 契约](docs/api-contracts.md) · [学习服务契约](docs/contracts/learning-services.md)
- [平台运维](docs/platform-guide.md) · [账号契约](docs/contracts/local-account.md)
- [资料与工作台](docs/contracts/workbench-library.md) · [知识库](docs/contracts/knowledge-base.md)
- [Agent 使用](docs/agent-mcp-guide.md) · [MCP 开发](docs/mcp-platform.md) · [RAG 接入](docs/rag-integration.md)
- [高级学习说明](docs/C-learning-user-guide.md) · [录音与复习音频](docs/G5-media-user-guide.md)
- [产品约束](docs/requirements.md) · [原创验收集](evals/acceptance/README.md)

## 数据与能力边界

服务默认只监听本机，持久数据位于 `.xueya-data/`。密钥仅由后端读取；选定资料和近期上下文可能发送至配置的外部服务。付费请求结果未知时不自动重放，Token 用量不是实际账单。

资料不足不伪造证据；流式增量不是正式完成结果，只有通过最终校验的 `done` 可保存。OCR、向量、重排、图像和语音能力按配置开放。视频分析只覆盖实际采样帧。受控测试、合成实验和共享课件补录不代表真实模型质量或学习收益已经验收。

教材PDF已整理为[逐页OCR资料包](materials/data-structures-textbook/README.md)，可导入已有课程并显式替换旧PPT；实际能力、私人历史保护与验证见[PDF换库说明](docs/contracts/pdf-knowledge.md)。
