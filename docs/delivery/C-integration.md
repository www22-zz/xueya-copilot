> **2026-10-17 main 合并更新**：本文保留 C 分支交付时的设计和测试记录。当前统一入口、Python 路径、MCP 2.3 依赖、B/C 数据适配和实际开放范围以 [main-C-integration.md](main-C-integration.md) 为准。下文旧 JS/Zod/ts-fsrs 命令及“未提交”描述属于历史记录，不作为当前执行指令。

# C 模块接线与验收说明

本说明对应 `feat/large-C-agent-learning`，供 A/B/D/E/F 审查与接线。目前不宣称已经接入生产持久层、全新学习页面或真实付费模型。API 凭据未配置，所有模型内容测试均为受控测试；FSRS 使用实际锁定库，浏览器回归使用真实本机浏览器和真实本地 MCP。

## 入口与职责

| 入口 | 职责 |
| --- | --- |
| `backend/agent/learning-service.js` | 章节学习包、作答、订正、笔记/计划预览和版本化采纳 |
| `backend/agent/http-handler.js` | 可选 HTTP 接入层，供 E 装配；默认主应用未挂载新路由 |
| `backend/agent/answer-policy.js` | 现有 `/api/ai` 和 `/api/agent` 共用的最终回答证据检查 |
| `backend/agent/question-service.js` | 有来源候选题、审核/编辑、变式题和有探索配额的练习选择 |
| `backend/agent/concept-service.js` | 有来源概念候选、稳定 ID、别名复用和关系人工纠正 |
| `backend/agent/review-service.js` | 记忆卡预览、版本化复习事件、FSRS 到期队列和历史导出 |
| `backend/agent/diagnosis-service.js` | 候选错因、学习者订正和明确输入误操作的掌握证据排除 |
| `backend/agent/study-session.js` | 不调用模型的作答—诊断—选题—路径—每日推荐闭环 |
| `backend/agent/package-composer.js` | 摘录/摘要、概念、已审核测验、诊断和计划的学习包组合 |
| `backend/agent/planning.js` / `learning-path.js` | 逐日空闲、漏学重排、先修依赖、明确的剩余工作量 |
| `backend/agent/recommendation-feedback.js` | 跳过、暂不推荐、恢复推荐的版本化反馈，不制造作答/完成证据 |
| `backend/agent/local-experiments.js` | 已有固定策略与新本地规则的可复现实验 |
| `backend/agent/media-service.js` | 受控媒体、识别确认、候选步骤诊断、音频转写、视频抽帧结果、TTS |
| `backend/providers/router.js` | 显式模型路由、版本化缓存、预算账本端口 |

生产接入时由 E 提供课程授权、数据和队列。`tests/fixtures/agent-repository.js` 与 `agent-restart-worker.js` 是测试替身，不是生产数据库方案。

## 仓库与作业端口

ArtifactRepository：

```js
get(courseId, id) // → 当前记录或 null
getOperation(courseId, operationId) // → { requestHash, value } 或 null
commit({courseId, id, operationId, requestHash, expectedRevision, value})
```

`commit` 必须在一个数据库事务中：核对 operation 是否已经存在；相同 hash 返回原结果，不同 hash 抛 `IDEMPOTENCY_CONFLICT`；核对当前 revision；保存历史版本、当前版本和 operation 原始结果。不存在的记录 revision 为 0。操作键包含 course，不能跨课程复用。对旧网络重试，不能只返回最新记录：题库可能已更新，作答可能已人工订正，必须能取回该 operation 当时的结果。

RunRepository：

```js
get(courseId, id)
compareAndSet(courseId, id, expectedRevision, newValue) // → boolean
```

CAS 必须原子执行。`verifySnapshot(courseId, snapshot)` 是必需端口，根据 B 当前资料版本核对内容快照。创建运行时带不可变输入、步骤和快照；客户端不能自报 handler/type/effect。步骤输出写检查点后继续。`recover` 的 `leaseExpired:true` 只能由 E 在租约过期确认后传入，不能来自浏览器。

运行状态：queued → running → completed / failed / cancelled / unknown / awaiting_user / awaiting_confirmation。等待确认不持有 MCP 或模型连接。远程步骤超时/中断可能是 unknown，必须人工确认结果后才可重试；不能承诺供应商不会重复扣费。同一进程可通过 `workflow.cancel(courseId,id)` 中断正在运行的 handler；跨进程由 E 把取消请求传给执行 worker 的 AbortSignal。

队列消费 `learning.workflow.execute(courseId,runId,{signal})`。`enqueue({courseId,runId})` 应幂等；若入队失败而 run 已 queued，E 应重投同一 runId，不能另建付费任务。

## 证据与审查端口

B 的来源对象最少包含：`courseId/documentId/version/id/quote`；可附 `title/heading/section/location`。ID 稳定，version 跟随资料版本。完整章节必须提供全部选中块，不能只提供 top-k 命中。C 逐块处理、记录 offset/length、保留章节来源，并用完整内容指纹使旧缓存失效。

- `review({text,evidence},{signal})` 返回 `{supported:boolean,method,...}`，负责断言语义支持；原文片段存在仅证明出处，没有证明推断正确。
- `questionReview({question,source},{signal})` 是独立端口，核对题干/答案/解析。不要把断言 reviewer 不加适配直接用作题目 reviewer。
- 无 reviewer：逐字原文可以返回；自由改写仍标记 unverified，兼容问答回退到标注的原文摘录。题目即使通过自动检查，仍是 candidate，需要明确人工审核。
- 模型生成的 `answer` 不能夹带 claims 外的文字；现有问答最终正文重建自已检查 claims。流式增量只是暂态，只有最终 done 可保存。
- 章节检查点可注入 `{get(courseId,key),put(courseId,key,value)}`。使用模型时需要稳定 modelId；使用 reviewer 时需要 reviewVersion。未明确身份时不复用旧模型检查点。

## 可选 HTTP 装配

E 传入真实端口后，可按以下形式组合，无需重写既有主应用：

```js
const learning = createLearningService({
  artifacts, runs, model, modelId, review, reviewVersion, questionReview,
  checkpoint, verifySnapshot
});
const handleLearning = createLearningHandler({
  learning, resolveContext, resolveEvidence, resolveQuestions, previewStore, enqueue
});
const app = (req, res) => {
  if (!handleLearning(req, res)) handleExistingApp(req, res);
};
```

`resolveContext(req,{signal})` 完成授权后返回 `{courseId,loadStudyContext?}`。日期与学习事件从服务端读取；浏览器自报 baseDate、events、graph、sources 不作为可信学习记录。

`resolveEvidence({courseId,selection},{signal})` 由 B/E 返回该课程的真实版本化来源；章节任务返回全量选中来源。`resolveQuestions({courseId,ids})` 返回服务端保存的题目。`previewStore.put(courseId,draftId,draft)` 与 `get(courseId,draftId)` 保存服务端预览；浏览器只传 draftId，不传可自行重算 hash 的 draft/content。预览摘要不能视为签名。由 E 设置草稿保留/过期策略与授权范围。

| 方法与路由（前缀 `/api/learning/`） | 请求主要字段 | 结果 |
| --- | --- | --- |
| POST `answers` | question、selection、history | 核验回答或原文摘录 |
| POST `questions/generate` | selection、count、types、conceptIds | candidate 题，未自动批准 |
| POST `quiz/preview` | id、questionIds、selection、count、expectedRevision | 服务端 draftId 与审核预览 |
| POST `draft/adopt` | draftId、confirmed:true、operationId | 事务提交的版本 |
| GET `quiz/:id` | — | 白名单作答视图，不带答案、rubric 或任意扩展字段 |
| POST `attempts` | id、quizId、quizRevision、responses | 当时题目快照、作答和评分 |
| POST `attempts/review` | attemptId、expectedRevision、questionId、review、operationId | 按当时 rubric 人工订正 |
| POST `diagnosis/analyze` | attemptId | 保留不确定性的候选错因 |
| POST `diagnosis/correct` | attemptId、eventId、expectedRevision、operationId、cause、reason | 明确订正；不改写原始答案和评分 |
| POST `plan/preview` | id、selection、examDate、minutes、expectedRevision | 用服务端学习上下文生成的预览 |
| POST `plan/change` | id、expectedRevision、change | 完成、跳过、延期后的预览 |
| POST `plan/replan` | id、expectedRevision、examDate、minutes、availability | 保留完成/跳过记录，重排漏学任务 |
| POST `study/session` | selection、examDate、minutes、availability、practiceCount | 服务器学习记录下的诊断、练习、路径和今日推荐 |
| POST `package/preview` | id、selection、expectedRevision、practiceCount | 完整学习包草稿，仅使用现有证据和题目 |
| POST `package/plan` | packageId、id、expectedRevision | 将已保存包的计划单独预览，待明确采纳 |
| POST `recommendation/feedback` | itemId、action、until、reason、operationId、expectedRevision | skip/dismiss/completed/restore 推荐反馈 |
| POST `note/edit` | id、expectedRevision、text | 保留来源的人工编辑预览 |
| POST `card/preview` | id、prompt、answer、evidence、selection、expectedRevision | 有原文出处的记忆卡预览 |
| POST `reviews/rate` | id、rating（1–4）、expectedRevision、operationId | 版本化复习事件和实际 FSRS 调度 |
| POST `reviews/queue` | cardIds | 服务端上海时区日期下的新卡/到期队列 |
| POST `reviews/defer` | id、expectedRevision、operationId、until、reason | 延期且保留真实原到期时间与复习历史 |
| POST `chapter` | id、artifactId、selection、expectedRevision | 入 E 队列后的 202 queued run |
| GET `runs/:id` | — | 状态、步骤、产物和等待确认信息 |
| POST `runs/resume` | id、revision、confirmation / userInput / acknowledgeUnknown | 验证快照后重新入队 |
| POST `runs/cancel` | id | 取消；跨 worker 需 E 传递信号 |

返回 `{ok:true,result}`；无效输入 400、课程不匹配 403、不存在 404、旧 revision/草稿变更 409、缺模型或队列 503。`POST /draft/adopt` 不接受客户端提供 draft/content。

## 模型、媒体与配置

模型能力与 schema 依据在 2026-10-15 查阅的小米官方文档：[JSON 输出](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/text-generation/structured-output)、[图像](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/multimodal-understanding/image-understanding)、[ASR](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/audio/Speech-Recognition)、[TTS](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/audio/speech-synthesis-v2.5)。文档能力声明不等于账号实际权限验证；上线前重新核对。

Provider 可配置输出预算、最大总请求数、分钟频率和并发。usage 缺失时保留 null，不估造费用；E 注入持久化账本，将供应商实际 token 与明确价格版本计费。模型/提示词/资料版本改变使缓存失效，缓存命中标记 `execution:cache`。

媒体仅接受 E/B 授权解析的 ID/版本。视频解码、音轨/切片、OCR/缩放与 GPU 作业由 B/E 提供；C 不重复实现文件仓库。图像识别先返回 awaiting_user，允许用户订正题干，再作候选步骤诊断。诊断不给未经审核的精确掌握分。音频只使用实际切片时间，不伪造逐字对齐；视频仅声称观察采样帧。A 实现语音播放/暂停/倍速与文本对照。

`ts-fsrs@5.4.2` 固定版本的冷启动算法回放已运行；使用默认参数并关闭随机 fuzz。没有个体训练或学习收益结论。研究比较代码提供按文档分组切分与 paired 回放，真实黄金集和最终统计交 F 联合完成。

复习事件带内容版本，卡片题干/答案/依据变化后保留旧历史，并按新内容开始冷启动调度；旧内容的记忆状态不直接套到新内容。到期日期统一按 Asia/Shanghai，重复自评按 operationId 幂等。诊断默认不能知道真实思考过程；只有学习者明确确认输入误操作时，才把该次事件从掌握估计中排除，同时保留原始评分和订正理由。

FSRS 的分钟级复习不能只比较日期。catalog 保留 dueAt/eligibleAt；当前到期队列按服务器实际时间筛选，今日稍后到期卡出现在 study/session 的 waitingCards，不会刚作答就立即再推荐。延期改变可推荐时间，不篡改原始调度，也不生成虚假复习事件。

## 无 API 的完整本地业务

`learning.studySession(input)` 只运行本地规则。输入来自 E 服务端学习上下文：版本化 sources、已确认 graph、题库、events、diagnoses、cardIds。cards 可通过 C 的 reviews.catalog 自动读取；推荐反馈通过 C 的 feedback 仓库自动读取。输出包含 estimates、diagnosticActions、practice、path、plan、daily、waitingCards、feedbackRevision 和被明确排除的过期证据。无记录时掌握度为 unknown，不编造概念或新题。

`availability` 为 `{"2026-10-15":0,"2026-10-16":45}`：0 表示当天不安排，未指定日期使用 minutes。单日上限 480 分钟。规划按已确认的先修边保证阅读/练习顺序，支持分段任务，时间不足返回 remaining 和 INSUFFICIENT_CAPACITY；最多规划 maxDays（默认 90，可配置至 366），范围不足时明确给 HORIZON_LIMIT。完成和跳过分别保留，跳过不算掌握。`previewReplan` 保留两类记录，重排漏学任务并提供 moved/added/removed 差异，草稿采纳前不改原计划。

每日推荐遵循同一先修顺序与当天预算，不把尚未排到的后继知识练习提前。近期已评分题默认 7 天内不反复推荐；已确认审题/计算/方法/符号等错因会改变后续动作和推荐理由，候选错因仍标明未知。题库不足时报告缺口，不生成固定假题。

`previewLearningPackage` 将内容、路径、已审核测验、诊断、建议和计划组成一个版本化 artifact。无模型时内容部分明确标注原文摘录。包保存后，GET quiz/:packageId 和 submitQuiz 可以直接使用包内题目，仍隐藏作答前答案。保存学习包不替换用户的当前计划；通过 package/plan 单独预览后再采纳。

`recommendation/feedback` 只影响建议展示，不写成绩、掌握度或已完成计划。expectedRevision 使用 study/session 的 feedbackRevision。until 是包含结束日的暂缓日期，默认当天；restore 可提前恢复。重复请求跨日仍返回原操作结果，不能追加第二次事件。

## 本地实验与可复现证据

运行 `node scripts/run-c-local-experiments.js --output docs/delivery/c-local-experiments`。输入是自行编写的合成课程，代码位于 `tests/fixtures/local-study-course.js`。版本固定，无随机过程。报告和原始结果已保存为 [report.md](c-local-experiments/report.md) 与 [results.json](c-local-experiments/results.json)。

实际运行了 4 个逐日预算场景、固定与自适应选题对比、5 次固定间隔与真实 FSRS 的同序列回放。新规划的 4 个场景均无预算违规；这些指标验证规则行为，不证明记忆保持率、成绩提升、真实用户收益或模型质量。真实课程黄金集与独立效果评测仍需后续进行。

## 验证入口与待完成联调

`npm ci` 后运行 `node --test --test-timeout=30000`。浏览器运行 `node tests/e2e/browser.js`，需 Playwright 和 Chrome/Edge，可用 CHROME_PATH 指定浏览器；测试使用受控模型并运行真实本地 MCP。截图输出在忽略提交的 `test-results/browser/`。

新 HTTP 接口通过实际本机 HTTP 测试，但使用测试仓库；尚未接 E 生产数据库/队列或 A 新页面。真实模型、图像、ASR/TTS、GPU和真实课程质量仍未验证，不能用这些测试替代整包验收。
