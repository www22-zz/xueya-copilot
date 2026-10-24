# 前端成员检查误报修复（2026-10-25）

基线：main `5d60628`；修复分支：`fix/ci-frontend-member-detection`。

GitHub Actions Offline quality 的 Windows 日志显示 493 passed、1 failed：
`test_practice_view_only_touches_real_store_and_client_members` 将实际导出的
`store.ready` Promise 误报为缺失。检查器只识别后接逗号的简写成员，而
`return {state, ..., ready}` 中末尾成员后接右花括号。页面实际使用
`await store.ready`，无需修改生产代码。Linux 任务亦失败，但未取得其完整日志。

修复正则识别逗号或右花括号前的简写成员，使用前瞻保留分隔符。
新增回归覆盖单成员、多成员末尾、换行、尾逗号，并确认未导出的局部变量不被认作成员。

本地 Windows 验证：

- 接口检查：9 passed。
- 完整 Python 回归：495 passed，87.81 秒（正常权限环境；沙箱受限的重复运行已停止）。
- 前端回归：42 passed。
- `python -m scripts.check_quality --repeats 1`：退出码 0；fixed-lexical 43/46，structured-lexical 40/46，未将命令成功描述为全部检索样例通过。
- `git diff --check` 通过。无付费模型调用；本地未运行 Linux 验证。

推送修复分支后需经 PR 运行双平台 CI，由负责人审查合入 main；旧提交的红叉不会因仅推送修复分支自动消失。
