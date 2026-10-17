# G1 学习体验与公共接线

基线：main `bc3a36b`；分支 `codex/g1-workspace`。状态：进行中。

## 范围和兼容定义

复用 backend/xueya 主程序、SQLite、JobQueue、invocations、B/C 服务。新增 `/api/platform/workbench/{operation}`，沿用同源与 X-Xueya-Token；GET capabilities 返回逐项配置/验证边界和用途，GET tasks 返回有界安全任务投影与实际 usage，POST check 仅执行免费本地配置检查，POST task-action 仅取消或安全 CPU 重试。不接受供应商密钥或任意 URL，不新建配置库/账本，不把配置当成真实连接成功。

主学习区沿用 C 页面服务；旧浏览器记录保留在可展开区域；资料和聊天仍沿用既有主入口。资料范围与会话选择通过既有 store 共享。设置通过 .env 更换/移除密钥并重启，页面不保存凭据，环境优先级不变。

本次同时承担 G2，公共装配由本包统一，G2 在独立模块中接入 `/api/platform/library/{operation}`；无必要迁移，不联系其他队友。G3/G4/G5 可沿用同一鉴权、任务 ID、courseId、版本和 preview/confirm 语义；禁止通过新入口绕过旧确认保存。

## 检查点

- 已阅读当前 AGENTS/README/派工说明、ON-01/02/13 和 AE 审计，确认当前 B/C 已接通，未采用旧 C 未接线记录。
- 现有工作区干净；已从最新 main 创建 G1 和用户指定的 codex/g2-workspace。
- 尚未完成：服务端安全投影、工作台入口、状态中心、专项与浏览器验证。
- 不进行付费 API 测试，不操作私人数据库。

## 下一步

完成逐能力状态与任务服务、统一页面入口，再验证并提交阶段成果；G2 随后在同一公共约定上实现。
