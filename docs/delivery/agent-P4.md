# P4 错题巩固与跨章节备考

wrong 场景读取有来源版本支持的真实错误事件，等待学习者明确确认错因及理由，再调用现有 DiagnosisService.correct。confirmedBy 由服务器绑定。input-error 排除掌握度统计；后续练习使用现有 study_session 的 FOLLOW_UP 规则及已审核、近期未做题目。无可核验错误记录时先进行真实练习，不编造错因。

exam 场景复用当前资料范围的知识图谱、先修约束、FSRS 卡片、实际事件与原 plan_study/replan_study。支持变更考试日期、每日时间、按日期可用时间。新成绩在每次重新规划时从数据库重读，不接收客户端自报评分。重排预览展示原计划和新安排，确认后写入；已完成/跳过任务由原重排服务保留。缺少知识图谱时暂停提示补齐。

新增运行操作 diagnose（revision,confirmed,cause,reason）、replan（revision,settings:{examDate?,minutes?,availability?}）；replan 支持已完成的 exam 运行再次更新。仍需最终摘要确认。

验证：P4 错因订正→不同练习、跨章节先修规划→缩短时长→确认、无图谱等待三项，加 P3 三项，共 6 项通过。无真实付费调用。
