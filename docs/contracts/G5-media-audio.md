# G5 媒体学习与复习音频接口

基线 main `5699b99`，2026-10-18。主服务仍为 `python -m backend.xueya.server`。

## 接入与权限

独立业务位于 `backend/xueya/media_workspace.py`，CPU领域工具在 `backend/agent/media_audio.py`；LearningHost 鉴权后委派。前端 `media-workspace.js` 在平台 bootstrap 可用时挂接媒体页，“更多 → 章节学习 → 高级：模板加工与历史记录 → 录音与复习音频”进入。保留原 C 单文件媒体和 G1～G4 接口。

统一前缀 `/api/learning/media-workspace/`，课程在 `?courseId=`，同源、本机 Host 与 `X-Xueya-Token` 沿用主平台。JSON 请求体如含 courseId 必须相同；只能读取本课程资料。响应为 `{ok:true,result:...}`；错误为 `{ok:false,error:CODE}`。

## 免费资料与脚本

| 操作 | 方法 | 主要字段 / 结果 |
| --- | --- | --- |
| workspace | GET | 当前媒体、任务、脚本、有效文档、有出处笔记/卡片目录、音色与配置边界 |
| upload | POST | 原始 `audio/wav` 字节，query name；校验 PCM 采样数，返回既有 kind=media 记录；最多120MB/一小时 |
| upload-original | POST | 原始音频容器字节，query name；不可变保存原始文件，标记待浏览器解码，不冒充已完成识别 |
| prepare | POST | mediaId/mediaVersion、seconds=30～180、confirmed、operationId；提交普通 CPU 分段作业 |
| result | GET | id；重新读取当前媒体记录、脚本或运行及 revision |
| transcript/save | POST | id/revision、按顺序的 items[{id,text,reviewed:true}]、confirmed/operationId；保留 originalText，CAS保存校正 |
| video/save | POST | 同上，但每项还带实际 timeMs；保留原识别 observations/uncertainties/inferences |
| transcript/import | POST | id/revision、confirmed/operationId、chapter可选；仅接受完成且逐段核对的转写/视频画面说明，进入 B 文字解析队列 |
| transcript/link | POST | id/revision、documentId、confirmed；B解析完成后核对文档 origin 的 runId/runRevision，再写 G2 真实位置关联 |
| script/draft | POST | title、style=solo/dialogue、selection、parentIds、cardIds、focus=selected/due；免费原文模板，不冒充模型生成 |
| script/save | POST | id/expectedRevision、content、confirmed、operationId；每段 reviewed=true 且出处有效才保存 review-script |
| video/register | POST | mediaId/mediaVersion、frames[{id,version,timeMs}]、startMs/endMs、confirmed/operationId；核对同课程图片、唯一递增采样时间和原件范围 |

原件使用既有 C/G2 `media`、文件 hash 库和 `library/media-original`；不接受客户端文件系统路径。文件库允许最多128MB原件以容纳媒体，但文档 HTTP/解析的原有限制保持。视频仍使用既有 `media/upload`，最多50MB/30分钟；抽帧1～24张。浏览器通过实际解码/seek/canvas获取帧，时间标记为客户端采样，不是服务器鉴定的逐字时间或完整视频理解。

WAV 边界从真实采样数计算，分段最大7MB，自动缩小过大段长，最多120段。不能满足上限时明确报错，建议转换为单声道16k PCM WAV；不截掉后半段。浏览器可解码的 MP3/录音容器先用 Web Audio 转成 PCM，同时经 upload-original 保留原始字节，再通过 upload 的 originalId/originalVersion 绑定处理副本；两者同课程且版本一致才连接。原件 duration 标记为浏览器解码 PCM 的测量值，不伪造词级对齐。WAV 直接由 Python 核验。无 FFmpeg、无本地模型依赖。

转写导入保留原件、运行、修订版本、片段精度和 G2 关联；视频说明标记为采样画面笔记，不伪称完整转写。先解析后建立关联，避免发布版本变化导致位置绑定到错误版本。个别帧的关联是该实际时刻附近1ms的定位点，不代表这1ms包含完整讲解。

## 收费能力与可恢复作业

`transcribe`、`video`、`synthesize` 均为 POST，必须包含 confirmed=true、allowApi=true、maxCalls（整数0～120）和 operationId。次数限制不等于货币预算，实际供应商费用仍需用户确认。本次开发只用受控服务，未发起真实付费调用。

- transcribe：mediaId/mediaVersion、preparedId。每个真实音频片段一次 ASR 请求；输出片段级时间、originalText/text、reviewed=false，不提供词级对齐。
- video：mediaId/mediaVersion、question可选。每个实际采样帧一次图片理解请求；结果始终声明 sampled-frames-only。
- synthesize：scriptId/scriptRevision、voices={A,B}。逐段核验脚本/来源/父产物；pause 段不调用 TTS，合成音频标记 synthetic。
- cancel：POST id，取消现有主队列当前作业，传播到网络请求；已发出的请求仍可能计费，不把停止等待当作未收费。
- 恢复：对原模式再次 POST，新增 resumeId、reviewedUnknown=true，其余确认和上限仍须提供。新 operationId 创建新的恢复运行，保留已完成项，仅请求剩余项；同 operationId 只返回既有运行，不重放。

每片段独立 `media-segment-api` 作业、maxAttempts=1，复用 JobQueue 的90秒任务边界、API许可、调用账本及 G1 jobId 关联，不另建线程调度器或用量表。成功后原子保存结果和下一个作业；失败/取消/重启标 unknown，停止自动推进。配置指纹变化在发送前 NOT_SENT，旧配置的结果不混入新收费任务。

同课程/配置/段落文本/音色的音频可复用，缓存键不含整个脚本 revision，所以只修改一段只需重合成受影响段。maxCalls 在读取缓存后校验；完全缓存可用0次，改一段可限制1次。缓存不会绕过当前脚本/来源版本验证。

## 脚本、播放与学习记录

脚本包含 intro、explain、pitfall、recall、pause、answer、review；每段有 id/speaker/text/evidence/pauseSeconds/reviewed。文本每段最多800字符、总计20000字符、最多40段，留白1～30秒。来源摘录保持文档/版本/位置，个人无依据笔记不能变成教材事实；今日重点通过既有复习目录的 eligibleDate 选择，尊重延期日期。

第一版脚本是明确标注的原文模板，可人工改写并逐段核对；这不是自动语义支持度判定。G5引用按钮重新调用 G4 的免费原文读取，不只展示客户端旧快照。

播放器提供逐段播放、顺序播放与定时留白，浏览器保存段落进度；不是逐字对齐。audio GET id/part 返回已授权运行中的实际 WAV；export GET id 将完成的合成结果下载为 ZIP：review.wav、script.json、script.md、captions.srt。字幕按各实际 WAV 时长及留白排列，不推测词级时间。合并要求相同 PCM 采样格式，异常明确报错，不伪造音频；供应商当前 WAV 格式仍需真实服务验收。

播放/结束/下载都不更新掌握度。关联卡片后用户主动选择评分，才调用原 `/api/learning/reviews/rate` 写 FSRS；也可进入原题库实际作答。没有另建一套练习记录。

## 验证和参考

专项：`python -m pytest -q tests/python/test_media_workspace.py`；浏览器：`python -m scripts.check_media_browser`。浏览器需要 Chrome，全部使用临时库、真实自编 PCM/Chrome录制WebM及受控上游，不读真实密钥。

参考：[MiMo 官方 TTS 文档](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/audio/speech-synthesis-v2.5)，核对 assistant 文本、WAV 与现有音色；[MDN decodeAudioData](https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/decodeAudioData) 与 [OfflineAudioContext](https://developer.mozilla.org/en-US/docs/Web/API/OfflineAudioContext)，用于普通 CPU 音频解码/重采样。未引入声音克隆。
