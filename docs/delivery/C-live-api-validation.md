# C 真实 MiMo API 验证

实际调用时间：2026-10-15 23:58–23:59（Asia/Shanghai）；记录于 2026-10-16。用户授权累计不超过 10 元。

最新 origin/main 已核对为 `0a16b0e5f72954e2871d16869f8f3b5a8261cc52`。继续保留 C 分支未提交改动，没有上传。

| 实测项目 | 模型 | 结果 |
| --- | --- | --- |
| 中文结构化 JSON | mimo-v2.6-flash | 通过；answer=5，finish_reason=stop |
| SSE 流式中文输出与 usage | mimo-v2.6-flash | 通过；收到“学习测试成功” |
| 结构化工具调用 | mimo-v2.6-flash | 通过；course_lookup，courseId=math，finish_reason=tool_calls；未执行外部工具 |
| Base64 图片输入 | mimo-v2.6-flash | 通过；程序绘制 3 红块/2 蓝块，均识别正确 |
| 中文文字转语音 | mimo-v2.5-tts | 通过；冰糖音色，返回 69164 字节 RIFF/WAVE 音频 |
| 中文语音转文字 | mimo-v2.5-asr | 通过；上一项合成音频转写为“三加二等于五。” |

## 用量与费用

6 次真实 HTTP 请求成功，没有自动重试付费请求。首次沙箱内 5 次尝试均为 ENOTFOUND，域名解析失败、未发送到供应商；获得联网权限后完成上述验证。

主模型合计输入 218 tokens、输出 53 tokens。ASR 返回计费音频时长 2 秒。按[官方国内价格](https://mimo.mi.com/docs/en-US/price/pay-as-you-go)：Flash 输入 1 元/百万 tokens、输出 2 元/百万 tokens，ASR 0.5 元/小时，TTS 当前限时免费。估算文字/图片 0.000324 元，ASR 约 0.000278 元，合计约 **0.000602 元**。未读取账户账单，最终扣费以平台为准。

脚本每个请求保守预留 1 元，跨运行记账；本轮预留 6 元，这是预算控制额度，不是实际费用。不能删除预算账本绕过累计上限。

## 复现与限制

显式付费命令：`node scripts/check-c-live-api.js --live --budget-cny=10`。普通单元测试不会运行。后续新增付费测试仍须遵守累计预算。

本地被 Git 忽略的 `test-results/c-live-api/` 保存 report.json（含 usage、finish reason）、budget.json、合成 PNG/WAV；`.env` 也被 Git 忽略。报告不保存密钥、授权请求头或原始供应商错误正文。

本次使用现有 createMimoProvider/createMimoSpeech，没有上传真实课程、私人资料或个人声音。工具仅验证模型返回的结构化调用；语音是合成短句往返测试，没有主观听感评测。不能据此宣称复杂图片、真人录音、长课程、完整学习业务端到端质量通过。

E 持久化/鉴权/队列、B 课程证据/媒体定位、A 前端接线及 F 独立评测仍有待完成。默认应用装配未改。
