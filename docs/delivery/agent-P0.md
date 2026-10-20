# Agent P0：可信执行基础

日期：2026-10-20。范围仅为 P0；动态任务规划、自主工具选择和跨作业运行预算仍属于后续阶段。

## 基线与保留功能

从最新 origin/main `6ad28ef` 建立 `codex/agent-p0`。附件/录音前置提交 `46e344c`、`f99a9b2` 以 cherry-pick 保留为 `4376f02`、`0b50f36`，未合并 main、未推送。原工作区后续未提交的前端修改未触碰。

主入口仍是 `backend/xueya/server.py`；同一 SQLite、JobQueue、资源许可、MCP 和模型调用账本。原 HTTP 路径、JSON 基础字段和 `workflow/content/reasoning/done/error` SSE 类型保持。学习业务保存仍使用现有具体预览和用户确认。

## 本次行为

- 主聊天资料回答 direct/workflow 复用 `backend/agent/answer_policy.py`。合法来源 ID 不再足以批准任意结论；逐字片段可发布，未经 reviewer 支持的改写回退原文。最终正文从有效 claims 重建，忽略模型在 answer 内夹带的其他内容。畸形 claims/source/knowledgePoints 安全处理。
- 资料正文先缓冲核验，再用原 content/done 类型发布，执行进度仍实时显示。未核验正文与推理不再进入资料问答的临时预览。通用问答仍保留无课程证据标记和流式输出。
- direct 和 workflow 发布前核对服务端来源与文档修订；相同文字但版本改变也使当前回答失效。图片聊天保留实际的 verbatim-only 回退标记，不把回退伪装为在线模型回答。
- 主 Provider 发送 max_completion_tokens；显式 length、意外工具调用、非法结束原因均拒绝；SSE 必须遇到 DONE 或正常结束原因。旧兼容服务未给 finish_reason 时，非流式完整响应或 SSE DONE 仍可用，不能声称识别了其未提供的隐藏截断状态。
- 完整但不可用响应记 failed 并保存 usage/finishReason；网络或取消导致的结果未知仍记 unknown。复用 invocation-context 元数据记录输出上限和预算，不新增账本。不自动重试。
- HTTP 全响应生命周期、后台作业分别建立服务器预算，异步子任务共享额度。MCP/通用工具网关、文本、原生媒体和 RAG 外部 API 接入同一计数。主聊天会话在服务端与客户端均限于四个只读工具；原鉴权后的人工写入工具接口保留。

## 预算设置与实际边界

见 `.env.example` 的 AI_* 设置。默认每次最多4096输出 token、每请求/作业最多10次外部模型请求（含 RAG API）、12次工具、累计32768预留输出 token、300秒。

额度在发送前同步预留，不因缺失 usage、取消、结果未知而返还。实际报告超过预留时停止接受结果或继续调用；无法撤销已产生的供应商费用。开启费用上限时，按配置文本模型的输入/输出单价及 UTF-8 字节+消息开销的保守输入估计预留。该估计是本地拦截策略，不是供应商最终账单或严格 tokenizer 上界；实际费用以供应商为准。

费用上限默认0（未启用）。只配置次数限制不等于配置费用上限。启用费用上限但缺少单价时拒绝发送；图片/ASR/TTS/OCR/向量/重排缺少独立计价，直接拒绝收费请求，不套用文本单价。已有媒体确认、maxCalls与缓存限制继续适用。

每个后台作业有独立预算；章节分块在同一作业内共享，媒体分段作业仍受原有整条任务 maxCalls 约束。跨多个请求/重启/整个动态 run 的持久化预算不在 P0，后续 P2 实施。默认新上限会限制过长生成，可在 `.env` 按授权预算调整。

## 验证

全部使用临时数据和受控上游；真实付费调用0次，不读取真实 `.env`。

- 全量 `python -m pytest -q`：287 passed，142.56秒，无失败/跳过。随后为工具任务启动前取消补充2项资源释放场景，P0专项最终39 passed；P0+MCP关联专项54 passed（该轮在最后2项补充之前）。
- 前端原有回归：41 passed，原场景保留。
- `scripts.check_chat_experience`：首页、菜单、图片/语音聊天、刷新与手机通过。
- `scripts.check_composer_browser`：文件/图片、真实录音与PCM转换、受控ASR、编辑后发送、授权失败/取消/重试、真实文档引用、手机及主题通过。受控资料回答改为真实逐字原文，不再要求未核验的测试套话出现在答案中。
- `scripts.check_media_browser`：WAV分段、受控转写、校正导入、TTS播放与ZIP/字幕、明确FSRS自评、视频采样与原件定位、刷新恢复通过。
- `scripts.check_notes_browser`：保存、编辑、草稿、课程范围、版本冲突及主题通过。
- 离线46问检索诊断：fixed-lexical 43/46、structured-lexical 40/46，与现有记录相同；已知检索不足未在P0修复，不能把诊断命令退出成功写成全部问题通过。
- `pip check` 无损坏依赖，后端编译、`git diff --check` 通过。

三套历史 `tests/e2e/*.js` 浏览器脚本保留未改动；独立工作区没有Playwright依赖，本轮未重跑。旧DOM兼容限制见 `G5-PR11-integration.md`；本轮当前界面由上述四套Python浏览器检查覆盖。

浏览器截图/报告在此工作区忽略目录 `test-results/`，交付不含私人数据库、密钥、录音或运行日志。
