# G3 兼容接线定义（供 G1/G4 集成）

基线 main bc3a36b。用户指定分支 codex/g3-workspace，进度 docs/delivery/G3-workspace.md。
范围 ON-06/09/10：复用 LearningHost、LearningRepository、ArtifactService、ContentService、ReviewService，
只在现有 artifact 命名空间增加 learning-template/template-result；笔记、候选题和复习卡仍使用既有 kind。
没有数据库迁移、第二套队列或模型账本。来源依赖绑定原文 ID/正文版本/hash，而非向量索引或配置。

新增独立 ContentWorkspace(host)，在已鉴权 LearningHost.handle 通过一个委派入口 dispatch。
路径 /api/learning/content/*，courseId 及 token/同源规则沿用现有宿主。
模板/产物/笔记写入全部先生成服务器预览，再用既有 draft/adopt 明确确认/CAS/幂等保存。
后台试运行每份资料独立作业，复用 E JobQueue；一次失败不覆盖其他结果。未知远端调用不自动重试。
运行结果在 host.previews 及现有 run 仓库，只有明确采纳才进入笔记/题库/卡片。

前端独立组件 content-workspace.js，最小挂载：index 加脚本，app 初始化 create({state,store,toast})
并在既有 learningUI.mount 后调用；不修改G1的render装配行。G1 可将 mount 放入统一内容区。
G4结果可发 xueya:content-convert {courseId,parent} 事件打开转换预览；后端重读search-run的实际结果与来源，
不信任事件传入的正文，继续走同一preview/adopt确认及版本校验。
G4 通过 host.repo.all(course) 读取 note/template-result/question-draft/memory-card，并按 kind 标明非教材证据。
依赖检查为显式免费查询，不自动生成/重跑付费任务。历史内容不删除，旧产物未知出处标 unknown。
