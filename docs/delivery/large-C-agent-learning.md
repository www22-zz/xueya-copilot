# C：Agent 与个性化学习交付进度

## 当前交付说明（2026-10-16，上传准备）

本次为阶段性交付，C 整包仍在进行中。当前后端使用 Python；下方早期 Node.js 路径、无凭据及缺少整个 E 存储的说明属于历史记录，以末尾 Python 更新和本文当前说明为准。

- 已有：模型适配、证据校验、分块总结、学习包、五题型/审核/评分、诊断、FSRS/计划、概念与路径、运行恢复、媒体业务服务及专项测试。真实 API 短样例通过，不等于真实课程质量验收。
- 尚未完成：高级 `/api/learning/*` 的默认装配与前端全流程、多模态页面的上传/处理/展示接线、长音视频处理整条流程、真实课程与学习效果及独立验收。不能将这些内容统一归因为等待队友。
- 上传前重新执行 Python 回归：85 项通过，基础与平台两套浏览器回归通过；本次回归不调用付费 API。暂存内容已检查，未发现真实本地密钥或被排除的运行数据。
- 上传准备时远程 main 已更新到 `58c7805`，包含另一套 `backend/xueya/` Python 迁移。当前 C 工作基于 `f149b5d`，本次不覆盖远程 main 或强推；两套运行入口、依赖（尤其 MCP SDK）和公共文件需要 E 在 PR 集成时统一，不能声称已经兼容最新迁移。代码审查应同时参考 `docs/delivery/python-migration.md` 与 main 的迁移说明。
- 本地真实 `.env`、数据库、运行日志、测试输出、虚拟环境和迁移备份均排除。仅提交代码、配置模板、合成测试数据及交付说明。
- 用户已提供提交署名，配置仅限本仓库。本次按阶段性交付提交并推送 C 任务分支，提供 PR 审查，不合并 main；实际提交与上传结果以 Git 和 PR 记录为准。

状态：进行中，整包未完成。本轮已继续扩展无密钥业务、兼容接入与验证，具体成果如下；测试数量不代表整包验收完成度。起始基线 `0a16b0e`；当前分支 `feat/large-C-agent-learning`，跟踪远程同名分支。实现和依赖变更均未提交、未推送。

## 接续指令

继续前阅读此文件、`C-integration.md`、`docs/tasks/大任务/C-Agent与个性化学习.md`、`docs/tasks/README.md` 和工作区 diff。用户明确以 `D:\web\xueya-copilot-github` 最新代码为准，旧副本不处理；用户负责 C，已要求按整份 C 任务单完成。用户目前要求优先做不依赖密钥的实现与验证；没有任何 API 凭据，不能执行真实模型/ASR/TTS调用，也不要让用户在聊天里发密钥。用户已在暂停后明确要求继续。Git 尚无提交姓名/邮箱，已询问用户并解释署名不等于登录账号；用户尚未提供，不能擅自用他人身份提交。

绝不覆盖或丢弃当前未提交工作。共享 schema、HTTP 装配和存储由 E 提供；面向 C 的服务以注入的仓库、模型、检索、媒体和 reviewer 为边界。不能把 test fixture 宣称为生产持久化实现。真实模型、语音和 GPU 结果与受控本地结果分开报告。任务单验收后才更新为完成。

## 已实现

- Provider：文本生成和 SSE 适配、输出 token/并发/分钟和总请求上限、取消与超时、`finish_reason`、用量记录、图像能力门控、响应截断识别。无自动付费重试。新增固定依赖 `ts-fsrs@5.4.2`（`package.json` 与锁文件变更需 E 集成审查）。新增受控 MiMo 图像/ASR/TTS 适配器和能力/用量报告；仅受控适配测试，未调用真实 API。
- 可信证据：新增带课程、文件版本和内容指纹的 evidence package；逐项验证引用 ID 和原文片段。现有 `/api/ai`、`/api/ai/stream` 和 Agent 学习流程均接入严格 finalizer。对语义改写没有 reviewer 确认时退回明确标注的实际原文。最终正文重建自核验 claims，模型不能在 answer 外夹带未支持结论；取消不伪装为成功回退。
- 内容生产：章节服务接收完整选中来源并逐块保留证据。学习包现已串联摘录/摘要、已确认概念、已审核测验、作答诊断、练习建议和预算计划；无模型时明确标注摘录，缺题/缺概念明确显示缺口。包内测验可直接作答，计划需另行明确采纳。所有保存使用 preview/adopt 和 revision。
- Agent runs：基于 E 提供的 compare-and-set 仓库接口，含 revision 状态迁移、步骤预算、取消、等待用户/确认、快照校验、恢复及远程结果不明状态。持久层尚无 E 的生产实现；测试用 JSON 单写者 fixture 验证子进程退出/重启接续。正式接线必须注入 `verifySnapshot(courseId,snapshot)`，且检查 B 的实际课程/资料版本。
- 题目与测评：题库证据、课程和版本检查；五题型候选生成、变式来源约束、题干去重、审核/编辑和难度/概念限制；模型不能自动批准候选。客观评分、人工评分、无作答区分、去重组卷和白名单作答视图。作答持有当时题目快照；更新题库后仍能按原 rubric 订正，旧提交重试返回当时操作结果。错因候选明确不确定，支持学习者订正；明确输入误操作可排除于 mastery，原始评分不变。
- 个性化：有最低样本阈值的掌握估计；有来源概念抽取、稳定 ID/别名复用、候选关系人工纠正和先修循环校验；每日时间预算计划、部分任务完成、跳过、延期；固定规则 baseline 和真实 FSRS；弱项练习保留探索配额。新增记忆卡预览、自评事务、版本化复习历史、到期队列和导出；卡片内容变化重启调度但保留旧记录。没有学习效果提升结论。
- 多模态：媒体仅由课程媒体 ID/版本解析；图像识别先等用户核对，不更新 mastery；音频按实际切片起止转写并标记未逐词对齐；视频标注只观察已采样帧；TTS只对已确认文本生成并留正文。模型和媒体都为可替换注入适配器，实际服务能力待凭据验证。
- 研究：已实际执行合成课程下的预算、选题与复习规则对照，原始结果和报告保存在 `c-local-experiments/`，可由脚本重现。另保留按 groupId 分割与 paired 回放入口。没有真实用户/课程黄金集、模型效果和学习收益结论。
- 可选 HTTP：新增 `backend/agent/http-handler.js`，实际本机 HTTP 往返测试覆盖预览/确认/采纳/答题/重复请求/隔离。来源、学习上下文、题目和草稿由 E/B 服务端解析，浏览器不能提交伪造 draft 或改写已审核内容。独立服务层尚待 E 在正式 app 中挂载。

## 基线与验证

- 上轮完整回归 100 项通过。本轮追加验证记录见文末；测试均不调用付费 AI，模型为受控替身，MCP/FSRS/本机 HTTP 与子进程重启为实际执行。
- 近期命令：`node --test --test-timeout=30000`（必须使用 Node.js >=20，需 npm ci）。测试运行需要本机临时服务/文件改名权限；沙箱受限时用允许的本地测试方式，不删减测试。
- `git diff --check` 已通过，EOF 空行已修复；仅有 Git 的 LF/CRLF 提示。
- 浏览器 E2E 已在本机 Edge 完整通过：真实 MCP、追问依据、停止取消/重试、TXT/MD/PDF/DOCX、引用/卡片、题库/错题/复习、离线/直接文件预览、搜索与响应式。使用受控模型。新 C HTTP 服务尚未挂到默认 app，生产持久化和 A 新功能页面未接线。

## 当前工作区

修改：`backend/agent/practice.js`、`backend/agent/index.js`、`backend/agent/prompts.js`、`backend/agent/learning-workflow.js`、`backend/providers/mimo.js`、`package.json`、`package-lock.json`、兼容问答/工作流测试和浏览器受控模型 fixture。
本轮还扩展 study.js、learning-service.js、content-service.js、review-service.js、artifact-service.js、run-service.js、http-handler.js。
新增：

- `backend/agent/answer-service.js`
- `backend/agent/answer-policy.js`
- `backend/agent/artifact-service.js`
- `backend/agent/assessment.js`
- `backend/agent/concepts.js`
- `backend/agent/concept-service.js`
- `backend/agent/content-service.js`
- `backend/agent/evidence.js`
- `backend/agent/experiments.js`
- `backend/agent/learning-service.js`
- `backend/agent/http-handler.js`
- `backend/agent/review-service.js`
- `backend/agent/diagnosis-service.js`
- `backend/agent/media-service.js`
- `backend/agent/run-service.js`
- `backend/agent/study.js`
- `backend/providers/router.js`
- `backend/providers/speech.js`
- `tests/fixtures/agent-repository.js`
- `tests/fixtures/agent-restart-worker.js`
- `tests/integration/agent-restart.test.js`
- `tests/integration/learning-domain.test.js`
- `tests/integration/learning-http.test.js`
- `tests/integration/agent-review.test.js`
- `tests/integration/agent-diagnosis.test.js`
- `tests/unit/agent-core.test.js`
- `tests/unit/agent-fsrs.test.js`
- `tests/unit/agent-media.test.js`
- `tests/unit/agent-study.test.js`
- `tests/unit/answer-policy.test.js`
- `tests/unit/agent-questions.test.js`
- `tests/unit/agent-chapters.test.js`
- `tests/unit/agent-concepts.test.js`
- `docs/delivery/C-integration.md`

不要在 `.env`、日志、fixture 或 diff 中引入密钥、真实课程、音频和图片。

## 尚未完成及顺序

用户本轮指定的“不依赖 API 和队友的 C 内部工作”已按下方 6 项实现和验证，不再把这些内容写成等待 API。正式产品接线与真实模型/课程质量仍在后续范围。

1. 按 `C-integration.md` 接上 E 的实际 store/schema/API/worker/授权与 B 全章证据、媒体定位；挂载新 handler。当前 repository、queue、previewStore 和快照验证器还没有生产实现，不能用测试替身冒称完成联调。
2. 与 A 接通作答、候选题审核、笔记/计划/学习包预览及明确采纳、图谱/掌握展示、音频播放和照片识别确认；F 做独立验收。
3. 在真实课程上核对全章总结的覆盖/正确性、题目质量、语义 reviewer、概念/先修关系；当前合成来源和受控模型只验证业务逻辑。
4. 验证 E 数据库下的历史、复习事件、用户改分/错因、计划版本、复习调度、备份/恢复和跨 worker 租约/取消。
5. 真实模型能力探测、图文/工具/结构输出和预算账本与实际用量验证，需用户配置凭据后开展。
6. 与 B/E 确认上传和媒体异步作业/取消/存储/删除策略，再联上图片、音频、抽帧、TTS；凭据可用后最多按任务单先做少量短真实样例、严格预算，并记录模型 ID、usage、stop reason 和结果。当前所有这些是真实 API 未验证。
7. 研究实验需要 F 黄金集、样本标注、拆分和评价脚手架，采用锁定数据/算法版本与 baseline，报告统计及局限，不编造效果。
8. 等用户提供提交署名后分阶段提交本地任务分支；本轮没有提交和推送。用户说上传前不推送，也不自行合并 main。

## 接口交接

- B 输入：`evidencePackage({courseId,sources})` 要求每来源有 `courseId/documentId/version/id/quote`；B 为完整章节和有效定位、版本负责。
- E 输入：run 的 `{get, compareAndSet}` 和 artifact 的 `{get, getOperation, commit}` 仓库端口必须原子 compare revision、写 history 和幂等 operation 原始结果；run 验证器根据最新资料版本核对 snapshot。新 HTTP 需要 resolveContext、resolveEvidence、resolveQuestions、previewStore 和 enqueue。详见 `C-integration.md`，不接受客户端自报工具/效果或原始草稿。
- D 工具：只注入已有白名单只读工具；改变状态类工具仍需明确预览、确认、幂等 key，不自建 MCP 第二套服务。
- A 输入：`createLearningService` 的摘要/题库/计划 draft 只是预览；A 显示 draft 的差异与来源后由用户明确采纳，再调用 adopt/submit。
- F：cross-workflow 和独立效果评测；Mock、文档能力声明和真实付费 API 结果分别记录。

## 本轮收尾检查点（2026-10-15）

- 完整回归 `node --test --test-timeout=30000`：**123 项通过，0 失败，0 跳过**。实际日志在忽略提交的 `test-results/c-regression.log`。
- `git diff --check`：通过；没有将 LF/CRLF 提示误记成业务失败。
- `node tests/e2e/browser.js`：本机 Edge 浏览器通过，使用 bundled Playwright 和受控模型；截图在 `test-results/browser/`。
- 本机 Node.js v24.21.0 位于 `C:\Users\571\AppData\Local\OpenAI\Codex\runtimes\cua_node\a9ba6825a525118c\bin\node.exe`。当前 PATH 无 node/npm；npm 10.9.2 位于 `D:\web\.tools\npm-10.9.2\package\bin\npm-cli.js`。这些本地工具路径不进入产品代码。
- 浏览器回归时 NODE_PATH 指向上述 runtime 的 `bin/node_modules`，CHROME_PATH 为 `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`。
- 本轮改动已保存，未提交/未推送。等待提交署名不影响继续实现；缺少 API、真实课程和其他模块生产端口时，继续维护明确交接，不使用旧副本代码凑实现。

## 后续无 API 内部逻辑交付（2026-10-15）

用户要求先说明内容再工作，本轮明确并完成了以下 6 项：

1. 学习包串联：使用现有完整来源、图谱和已审核题目，加入诊断、建议和计划；包内测验可直接作答，计划单独采纳，不生成假题/假概念。
2. 诊断到练习：根据实际评分/学习者确认的错因安排动作；默认避免 7 天内已评分题重复推荐；旧资料版本和不可用题目单列，不静默当作当前证据。
3. 逐日与漏学重排：支持 availability、0 分钟日、部分任务完成、跳过历史、考试日期变化和原计划差异；按先修依赖安排，不足容量返回剩余工作。
4. 复习闭环：卡片延期、真实 FSRS 反馈、下一次推荐和可恢复推荐反馈；保留 deferrals，恢复推荐不改成绩。修复“今天稍后到期”被立即重复推荐的问题，使用精确 eligibleAt。
5. 图谱路径：只使用已确认先修边，明确目标、前置知识、证据和推荐理由；拒绝已否决前置节点与循环，候选边不成为执行依据。
6. 可复现实验：4 个预算场景、固定/自适应选题、5 次复习事件固定规则/FSRS 对照，生成实际合成数据报告，不宣称学习收益。

新增核心文件：learning-path.js、planning.js、study-session.js、recommendation-feedback.js、package-composer.js、local-experiments.js（均在 backend/agent/）；脚本 scripts/run-c-local-experiments.js；合成课程 fixture 与 calendar-planning、local-study-loop、local-study-http、local-experiments 测试。

最终执行 `node --test --test-timeout=30000`：**138 项通过，0 失败，0 跳过**。`git diff --check` 通过。本轮没有使用任何外部模型 API。既有浏览器流程未修改，没有无理由重复上一轮已通过的浏览器回归。

实验复现：`node scripts/run-c-local-experiments.js --output docs/delivery/c-local-experiments`。文件 `c-local-experiments/results.json` 和 `report.md` 为实际执行结果，来源是标注的合成课程。4 个候选规划均无超预算；不代表真实学习效果提升。

新 HTTP 路由：study/session、package/preview、package/plan、plan/replan、recommendation/feedback、reviews/defer，均位于 /api/learning/。已用本机真实 HTTP 与测试仓库执行学习包保存/作答、计划独立采纳/重排、复习/推荐反馈测试。生产数据库和默认 app/前端挂载依然需要团队接线，不能把测试仓库说成生产实现。

代码全部保留在原 C 分支，尚未提交或上传。没有配置提交作者姓名/邮箱；这是提交事项，不是这些内部逻辑实现的阻塞。

## 真实 API 验证更新（2026-10-16 记录）

用户已配置本地密钥并授权本次累计不超过 10 元，随后明确要求开始测试。2026-10-15 23:58–23:59（Asia/Shanghai）真实执行 6 次调用：mimo-v2.6-flash 的 JSON、SSE、工具调用、合成图片理解，以及 mimo-v2.5-tts 生成短中文 WAV、mimo-v2.5-asr 转写该 WAV，全部通过。主模型输入 218/output 53 tokens，ASR 2 秒；按官方国内价估算约 0.000602 元，未核对账户账单。详见 [C-live-api-validation.md](C-live-api-validation.md)。

新增显式付费脚本 scripts/check-c-live-api.js；无自动付费重试，按请求保守预留预算并跨运行记录。原始本地报告和合成媒体位于被忽略的 test-results/c-live-api/，密钥仅在被忽略的 .env。联网沙箱首次 DNS 失败未到达供应商，后获联网权限验证成功。

此前“所有真实 API 未验证”的记录是历史检查点，现以本段为准：上述 6 项小样例已真实通过；真实课程质量、真人录音、长音视频处理、生产持久化和 A/B/E/F 联调仍未完成，不据此标记完整 C 验收通过。没有再运行付费请求，没有提交或上传。

## 日常问答更新（2026-10-16）

用户在页面发送“你好”被课程检索的无证据分支拦截，要求同时兼顾日常问答。已增加：

- 纯问候在检索前直接回应，不调用模型；混合问候与课程问题不走此捷径。
- 默认学习工作流找不到相关资料时，一般问题使用真实模型通用问答，传递对话历史；不返回课程引用，不声称已查看资料。明确要求根据课件/教材/页码回答、资料追问、总结和出题仍要求课程证据。
- 通用回答 engine=general-chat，verification=general-knowledge-not-course-verified；前端标明“MiMo 通用问答”。通用服务失败时明确提示暂不可用。
- 原 /api/ai 与 /api/ai/stream 的资料问答兼容契约保持，另支持纯问候；通用模型问答由默认 /api/agent 与 /api/agent/stream 承载。

涉及 shared/agent/tasks.js、backend/agent/general-chat.js、learning-workflow.js、index.js、frontend/js/services/chat-service.js 和专项测试。完整回归 **142 项通过，0 失败、0 跳过**；git diff --check 通过。

已重启当前项目本地服务器，HTTP 实测“你好”正常回应；另真实发送一次“怎样养成早睡习惯”，返回有效中文建议、engine=general-chat、sources=[]。该付费请求在已有 10 元预算账本中再保守预留 1 元，连同前轮共预留 7 元（非实际扣费）；应用接口未返回 usage，不将此前 0.000602 元估算冒称追加测试后的总账。实际回答保存在忽略的 test-results/c-live-api/app-general-chat.json，无自动重试。仍未提交或上传。

## 后端 Python 迁移（2026-10-16）

用户最新要求后端全部使用 Python，以后新改的后端也使用 Python。已迁移 HTTP/SSE、配置、模型/语音、RAG 解析、真实 MCP、完整现有 C 学习领域服务、可选 HTTP 端口及后端脚本。浏览器前端 JS 保留。全部新入口、模块映射、依赖与限制见 [python-migration.md](python-migration.md)，本文件上方 Node.js 命令和路径是历史检查点。

首轮 Python 回归 68/68，包含旧 JS 实际固定输出对照 7 项；Python Playwright/Edge 完整浏览器关键流程通过。Python 真实 API 6/6 通过，估算新增约 0.000696 元；累计预算账本保守预留约 7.6 元（非实际费用）未超过用户 10 元授权，无自动重试。默认 4173 服务已切换 Python，健康接口 runtime=python。备份校验后迁出旧 backend/tests/scripts 中 85 个 JS 文件，保留忽略的本地备份，未触碰密钥或旧工作副本。

Python FSRS 和 MCP SDK 已锁版本，FSRS 从事件重放并显式更新算法版本，不宣称与旧 JS 调度精确相同。原有 E/B/A/F 生产接线与课程质量待办仍然存在。未提交或上传。

Python 迁移最终收尾：pytest **72 项通过，0 失败、0 跳过**；包含真实 MCP、旧规则固定输出对照和网关/SSE 边界。Python 浏览器回归与 6 次真实 MiMo 调用均通过。compileall、pip check、git diff --check 通过。合成实验已重跑并另存 docs/delivery/c-local-experiments-python/（4 场景/5 次复习，不宣称学习收益）。最终解释器路径为项目 .venv/Scripts/python.exe，启动命令 `python -m backend.server`，以后后端新增与修改使用 Python。

### main f149b5d 接入后的更新

收尾发现新 main 含 A/D/E 功能，已同步前端/约束并将其新增 SQLite、文件/解析作业、持久化确认、MCP 作用域/HTTP/治理、CLI 备份恢复等服务一并迁移 Python。C 新增真实 SQLite LearningRepository 适配；旧有“完全缺 E 存储/队列”的阻塞不再成立，但高级 /api/learning/* 前端接线仍待完成。全部 AI 仍只用外部 API，不做 GPU/本地模型推理。

最新综合回归 **85 项通过、0 失败、0 跳过**；基础和平台两套 Python/Edge 浏览器回归通过，平台验证包含显式迁移/预览确认、原子审计回执、重启保存、原件解析作业。未新增付费测试，仍保留前述 6 次 Python 真实 API 成功证据。分支基线已安全前移 f149b5da41e94948dbd5fc267387a500fc9371c8，所有工作文件哈希验证保留，旧基线有 backup 引用。详见 python-migration.md 后续更新。未提交或上传。
