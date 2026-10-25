# 学习服务接入契约

统一生产入口为 `backend/xueya/server.py`，由 `backend/xueya/learning_integration.py` 将学习领域接到主平台；领域代码位于 `backend/agent/`。本文件保留仍适用的学习路由说明，取代旧阶段接线草稿，不引入另一套存储或启动入口。

## 作用域、证据与保存

请求同源、本机 Host，并附 `/api/platform/bootstrap` 返回的 `X-Xueya-Token`；课程由 `?courseId=...` 绑定，默认 `course-default`，请求体不能跨课程。来源由服务端解析，`selection` 可含 documentIds、section、sourceIds，不接受客户端伪造原文、题目和学习事件。

证据至少包含 courseId、documentId、version、id、quote。章节处理读取完整所选来源，不能只取 top-k 片段冒充全章。资料版本变化使旧快照失效；引用存在不等于语义审核通过。

预览保存在服务端，客户端传 draftId。只有明确 confirmed 与操作 ID 才采纳；revision 条件和操作回执在主平台事务中核对。相同请求重放原回执，不同请求复用操作 ID 时冲突；历史作答依据当时题目快照订正。

## HTTP 路由

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

返回字段及错误保持现有实现，详细规则以 `backend/agent/http_handler.py`、`backend/xueya/learning_ui_api.py` 和 [公共 HTTP/SSE 契约](../api-contracts.md) 为准。高级接口可用不代表所有页面都展示对应入口。

## 复习、计划与运行

FSRS 以实际事件重放并保留算法版本。日期采用 Asia/Shanghai；到期队列同时检查实际 dueAt／eligibleAt，延期不伪造复习事件。无充分作答证据时掌握状态为 unknown，不输出虚假精确分数。

计划考虑先修、每日时间和完成／跳过记录；超预算保留 remaining，漏学重排提供差异。学习包保存不自动覆盖用户计划，包内计划需另行预览和采纳。

运行保存检查点、快照和 CAS revision，等待确认不持有模型或 MCP 连接。远程步骤中断可能为 unknown，核对结果后才能显式重试；本地操作 ID 不能保证供应商不重复扣费。后台作业与模型调用统一复用主平台资源和账本。

媒体仅通过课程内已保存 ID 与版本解析。图像、音频、视频结果保留真实页码或时间位置，先核对再保存；没有服务配置时明确不可用，不产生假转写。
