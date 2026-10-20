# 加号附件与直接录音输入

日期：2026-10-20。基于最新 main `6ad28ef`，分支 `codex/composer-upload-recording`。

## 怎么使用

- 学习概览、问答的输入框：点击“＋”，选择图片或 PDF、DOCX、TXT、Markdown。可预览、移除，最多四个附件；图片每份6MB、文档每份10MB。发送后文档由现有 Python 接口解析，原件与版本保存在当前课程，可在资料页查阅；本次问答会包含这些文档的范围与真实原文引用。无法解析的文档明确报错，不伪装成已读。
- 点击麦克风图标，允许浏览器使用麦克风。再次点击停止并识别，或点击取消丢弃。最长一分钟；录音与识别期间禁用发送、添加附件和切换课程。
- 停止后浏览器把录音转换为 16kHz、单声道、16位 PCM WAV，经原媒体接口交给 `mimo-v2.5-asr`。文字追加到现有草稿，可继续修改；只有点击发送才交由 `mimo-v2.6-flash` 回答。
- 取消或离开输入页面时释放麦克风，不提交被丢弃的录音。等待权限时取消，即使之后才授权也会关闭麦克风。识别失败保留本次内存录音供显式重试，不自动重试；已上传的音频原件沿用现有本地媒体存储。切课、切会话、离页或刷新不保留待重试的内存录音。
- 兼容旧音频附件适配，但麦克风按钮不再打开音频文件选择器。旧语音转写确认对话框只用于历史音频附件流程，直接录音使用输入框核对。

## 接口和配置

复用 `media/upload`、`media/transcribe`、原文档上传与后台解析、普通问答流和图文问答。没有新增后端、数据库、任务队列或 HTTP/SSE 契约；权限、并发及模型用量账本保持原平台管理。

ASR 通过现有 `NativeSpeech` 固定调用 `mimo-v2.5-asr`；LLM 使用现有 `MIMO_MODEL=mimo-v2.6-flash`。已核对 [MiMo 官方语音识别文档](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/Speech-Recognition) 中的 `input_audio`、WAV data URL 和 `asr_options` 格式。密钥继续只在本机 `.env`，没有写入前端或 Git。

## 验证与边界

- 全量 Python：250 项通过；原有前端规则：41 项通过。
- `python -m scripts.check_chat_experience`：原有图片、语音附件、导航、主题、登录、资料和章节学习流程通过。
- `python -m scripts.check_composer_browser`：实际浏览器验证加号文件选择、Markdown 解析及真实引用、图片预览移除、真实 MediaRecorder 测试音频流、PCM 格式、请求模型、ASR 回填后不自动调用 LLM、编辑后发送、拒绝权限、取消、离页停止、延迟授权后取消、失败后显式重试、390px明暗主题。测试音频由浏览器振荡器生成，不使用用户麦克风；上游为受控服务，真实API费用为0。报告及截图在忽略的 `test-results/composer-input/`。
- 真实麦克风硬件、口音/噪音识别质量及真实付费 API 可用性未作本次验收。浏览器须支持 MediaRecorder、Web Audio，且通过 localhost/127.0.0.1 或 HTTPS 使用；file:// 无法调用本地后端。
- 新前端模块为 `frontend/js/services/composer-input.js`，样式在 `frontend/css/composer-input.css`，保持其他页面布局。
