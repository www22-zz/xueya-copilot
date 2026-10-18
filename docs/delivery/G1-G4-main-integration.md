# G1～G4 集成验收与主线合并

日期：2026-10-18；起始 main `bc3a36b`。集成分支 `codex/g1-g4-integration`，按 G1→G2→G3→G4 正常合并，保留各工作包原有提交与历史，不整目录覆盖、不强推。

## 合入范围

| 工作包 / 原 PR | 本次核对的头提交 | 交付与入口 |
| --- | --- | --- |
| [G1 / #5](https://github.com/www22-zz/xueya-copilot/pull/5) | `ff56339` | 统一学习主区；顶栏服务设置、免费配置检查、任务与实际用量；旧记录仍可展开 |
| [G2 / #6](https://github.com/www22-zz/xueya-copilot/pull/6) | `eeead30` | 资料页文字/文件/公开网页导入、阅读、版本、归档恢复、显式复用及原件位置；依赖 G1 |
| [G3 / #7](https://github.com/www22-zz/xueya-copilot/pull/7) | `8dcb0ff` | 顶栏模板与笔记；模板试运行、确认采纳、产物转换及来源依赖检查 |
| [G4 / #8](https://github.com/www22-zz/xueya-copilot/pull/8) | `6cc230e` | 放大镜或 Ctrl/Cmd+K；资料/学习内容搜索、会话上下文、预算内综合回答及 G3 转换 |

统一使用既有 Python 主服务、SQLite、队列与调用账本；没有新增依赖或数据库迁移。前端继续使用 HTML/CSS/JS。各专项实现和限制见 G1～G4 各自交付文档，不能由“已合入”推断真实供应商质量也已验收。

## 合并时修正的兼容问题

1. 仅在平台 bootstrap 可用时装配 G1～G4 服务组件。关闭平台服务或直接文件预览时，保留原浏览器功能与旧搜索，避免新搜索拦截后显示不可用页面。
2. C 切换页面时，在当前页面资料加载完成前显示连接状态，不用上一页面数据先画可操作表单。否则刚选的图片可能被随后到达的刷新清空；原图像/音频浏览器流程已用于重验。
3. 保留现有 A/E 浏览器断言；其历史记录专项测试显式展开历史区域，新 G1 浏览器检查仍独立验证默认折叠、主学习区与移动布局。没有删除原测试来获得通过。

## 本次实际验证

- 完整 Python：**227 passed，99.67 秒**，同时收集 tests/python 与 tests_python。
- 原前端单元：**41 passed**。
- 原浏览器：主流程 browser.js、A workspace.js、E platform.js，以及 C check_learning_browser；包含上传/引用、追问、停止/重试、迁移与持久化、题目审核、订正、FSRS、计划、受控图像/音频。
- 新浏览器：check_workbench_browser、check_library_browser、check_content_browser、check_search_browser --with-content；核对真实页面、刷新、390px 布局与 G4 回答→G3 预览→确认采纳。
- MCP stdio：发现 4 个实际工具并检索成功；pip check 无依赖冲突。
- F 离线 46 题重新运行：固定/结构分块全部证据召回仍为 100%/92.5%；位置错误和预算超出均为 0。原三条短问法缺陷未在本轮声称修复。
- 原始输出在忽略目录 test-results/；临时数据库及受控上游用于验证，没有新增付费模型调用，没有操作私人数据库。

GitHub 自动检查结果以集成 PR 的 Actions 为准；本文件记录的是实际本机验证，不能冒充远端执行结果。

## 更新和后续

队友更新最新 main 后，再把 main 合入仍在开发的任务分支；不重置队友提交、不上传完整旧目录。G2～G4 实际使用用户指定的 `codex/g2-workspace`、`codex/g3-workspace`、`codex/g4-workspace`，覆盖原派工表的示例分支名。

G5 尚未纳入本次合并。真实公网抓取受本机 DNS 条件限制，真实模型/OCR/向量/重排/音视频质量、人工课程标注、无障碍人工审计及最终比赛交付仍按既有待办单独验收。整体备份不等同于下一轮课程包导入导出。
