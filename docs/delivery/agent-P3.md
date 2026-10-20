# P3 单章节学习闭环

动态运行 scenario=chapter 在只读准备完成后复用 LearningService.study_session 计算真实学习状态、选择当前来源下已审核题目。先展示来源讲解、诊断和无答案的练习预览，用户确认摘要后才采纳试卷。实际答案由 answer 操作提交，调用原 submit_quiz 和确定性评分；主观题停在 awaiting_review，使用现有人工评分后 refresh。

依据实际事件重新计算 study_session、排除近期相同题目，再生成复习安排预览。确认后保存，未经确认不写计划，不自动作答、不推断完全掌握。无已审核题目停在 missing_questions，可补题后 refresh。

增量操作：POST /api/learning/agent-runs/{id}/confirm（revision,confirmed,digest）、answer（revision,responses）、refresh（revision）。均使用既有课程鉴权，来源更新及摘要篡改拒绝执行。返回 interaction 描述下一项真实用户操作。

验证：P3 三项闭环、题库不足、篡改/来源失效验收与 P2 四项，共 7 项通过。无真实付费调用。
