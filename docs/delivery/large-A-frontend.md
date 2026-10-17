> 当前状态补充（2026-10-17）：默认 Python 宿主的 A～E 接线、修复与剩余工作以 [整体验收记录](AE-integration-audit.md) 为准。下文保留原阶段证据。

> 历史记录：本文件保留当时的实现与验收证据。当前后端已迁移Python/FastAPI，启动和派工以[README](../../README.md)、[当前需求](../requirements.md)及[Python迁移记录](../delivery/python-backend-migration.md)为准；旧Node命令不再作为开发要求。

# 大任务A：前端与完整学习空间

分支：`feat/large-A-frontend`。起始代码：`0a16b0e`。开始日期：2026-10-16。

状态：前端实现与本地/受控适配验收完成，待B/C/E真实能力接线与F独立验收。未合并main，不将受控适配测试写成真实模型效果。

## 设计与执行约定

沿用首页原创知识球体、浅蓝/靛蓝与液态玻璃界面。学习区以“课程→资料→问题→证据→笔记→练习→复习”为主线，增加真实学习图谱与多模态工作区。保持原生脚本与本地文件预览，不迁移框架。

配色沿用`#fafbfe`纸面、`#172036`正文、`#4058d8`交互、`#747d91`说明、`#dee3ee`分隔。中文沿用系统字体，知识图谱与公式使用适合阅读的数学/等宽字体。视觉特征保留首页知识球，学习区强调原文与学习产物之间的联系。

采用渐进拆分：课程/会话存储、内容渲染、能力适配、页面扩展和交互控制分别成文件；既有问答/出题接口复用。跨模块后端由B/C/E负责，前端未接通能力明确显示状态，不模拟在线成功。

## 内部进度

| 阶段 | 范围 | 状态 |
| --- | --- | --- |
| 现状与基线 | 阅读任务、代码/接口、切A分支、现有62项检查 | 已完成：62/62通过 |
| 存储与结构 | 旧数据迁移、多会话/课程、长历史、存储/渲染/控制/服务拆分 | 已完成，覆盖超24条消息/300条作答、配额失败与中断恢复 |
| 资料与问答 | 批量上传/重试、标签/版本、原件/全文片段、范围、旧回答追问与反馈 | 本地已完成；服务端资料CRUD端口经受控适配验证 |
| 内容与笔记 | 安全Markdown/MathML/表格/代码、编辑/历史恢复/分类 | 已完成，不执行原始HTML或加载远程图片 |
| 练习与学习 | 题目审核、多题型/测验、作答恢复、错因订正、图谱、回忆与计划 | 前端已完成；语义图谱/算法与多题型后端待C接通 |
| 多模态 | 图片预览问答、音视频预览/片段、TTS缓存、编辑为笔记、停止处理 | 完整交互与受控端口已验证；真实模型待C/E配置 |
| 验证与交接 | 原回归、新场景、375/768/1440、键盘、file预览、接口记录 | 已完成，见下方命令与结果 |

## 已交付代码

- `frontend/js/state/workspace-store.js`：版本化浏览器状态、多课程/归档、多会话与每会话资料范围、草稿、记录/版本和JSON导出。v3为权威状态，成功后兼容镜像v2；读取旧数据不先清空或截断。容量不足明确提示未保存，提供导出。
- `frontend/js/ui/rich-content.js`：转义原始HTML、限制链接协议、Markdown段落/标题/列表/表格/代码，常用公式用原生MathML；支持分式、根式、上下标和常见符号，不声称完整TeX兼容，不加载外部CDN。
- `frontend/js/ui/workspace-views.js`与`frontend/css/workspace.css`：九个学习页面、多会话、独立滚动对话区、资料范围、弹窗、媒体、图谱、移动导航和状态反馈。
- `frontend/js/workspace-controller.js`：原文阅读与查找、文件版本、笔记/题目审核与恢复、作答/自评、测验、错因订正、复习回忆、计划预览/采纳/延期/排序/历史、显式先修关系和多模态结果。
- `frontend/js/practice-controller.js`：从app分离知识点与候选题流程，支持停止等待、失败重试和课程切换保护。候选题展示待核对状态；保留原AI题库操作路径。
- `frontend/js/services/file-cache.js`：当前浏览器IndexedDB原件与生成语音缓存；缓存失败不会伪装为原件已保存。
- `frontend/js/services/workspace-service.js`：独立可注入后端能力端口，输入/结果约束、取消、超时和资料规范化。`file:`预览不调用这些端口。
- 既有`app.js`、`views.js`和问答/出题服务渐进接入；服务请求携带可选`courseId`，不修改后端或公共schema。

## 后端交接需求

当前服务实际提供`/api/parse`、文本问答/Agent、知识点/单选题生成和健康检查。尚未提供资料原件持久化、OCR纠错、图片/音视频、学习图谱或跨设备存储API。

新增前端能力通过`window.XueyaWorkspaceBackend`可注入适配，不擅自冻结不存在的HTTP端点。E按实际API绑定，B/C提供领域结果。在`app.js`初始化之前加载适配器；每个方法形状为`async method(input, {signal, onProgress})`，未提供的方法不会伪装可用。默认等待上限90秒，适配层需要与真实长任务/作业查询协调；取消等待不保证远程已执行动作被撤回。

### E/B：资料与原文端口

| 方法 | 输入 | 输出 |
| --- | --- | --- |
| `uploadDocument` | `courseId, file:File, previousDocumentId?` | 兼容文档对象；进度可回调字符串或`{label,percent}` |
| `listDocuments` | `courseId` | `Document[]`或`{documents:Document[]}`，为该课程服务端资料的有效快照 |
| `updateDocument` | `courseId, documentId, version, metadata:{name,chapter,tags}` | 成功结果；异常必须抛出，不能返回假成功 |
| `removeDocument` | `courseId, documentId, version` | `{removed:true}`确认后才移除前端记录 |
| `original` | `courseId, documentId, version` | `{blob:Blob}`，优先使用当前浏览器原件缓存 |
| `correctOCR` | `courseId, documentId, version, correction` | 确认已接收的结果；服务端仍负责纠错校验、版本和重索引 |

兼容文档至少为`{id,name,status,meta?,version?,tags?,chapter?,chunks?}`。片段至少为`{id,documentId,title,location,quote,keywords?}`，位置必须真实。前端仅规范化结构，不判断OCR/检索效果；服务端检索、读取、缓存和删除都需执行课程隔离。

**版本身份约束**：本界面的文档`id`唯一标识一份版本记录，`familyId`联系同一资料的不同版本；不得让两个原件版本共用同一前端ID。后端使用稳定documentId＋versionId时，由适配器映射到独立前端ID，调用服务时再反向转换。前端拒绝重复ID的新上传或列表，防止新原件覆盖旧版本缓存。已有来源ID也不得用于不同文本。

本地原件以文档ID作缓存键，JSON导出只含学习数据和文本，不含原文件或媒体Blob。服务端资料没有删除适配器时拒绝假删除。未接通元信息更新时，仅保存浏览器侧整理并明确提示；同步列表保留这部分本地整理。

### C/E：图文与学习端口

| 方法 | 输入 | 输出 |
| --- | --- | --- |
| `imageChat` | 现有问答请求、`courseId, images:File[]` | `{answer,sources:[id或来源对象],engine?,workflow?}`；引用只接受所选资料范围内已知ID |
| `graph` | `courseId` | `{nodes,edges,paths?}`；节点`{id,label,sourceId?,records?,mastery?:{score,confidence}}`，边`{from,to,type}`，路径`{title,nodeIds}` |
| `variant` | `courseId, question` | `{questions:[...]}`，必须有有效选项、答案和当前课程原文来源 |

图谱`score/confidence`采用0～1数值，UI标明“服务端估计”，不从连线数量生成掌握度。未接通图谱服务时，只显示本地实际资料/笔记/关键词来源关联，以及用户手工维护的先修关系；不称为自动语义抽取或经验证的学习路径。

现有单选知识点/题库API继续使用。新增本地多选、判断、简答的`type/options/answer/answerText`、作答`questionVersion/selfAssessed`、回忆`reviewLog`、错因`corrections`需C/E纳入领域契约与持久化。目前后台诊断只识别原单选结构，UI明确提示；接入支持后可在适配对象声明`questionTypes:['single','multiple','short']`。自评统计明确区别于客观正确率，不实现第二套FSRS/掌握度算法。

### C/E：媒体端口

| 方法 | 输入 | 输出 |
| --- | --- | --- |
| `transcribe` | `courseId, file:File` | `{text?,segments?:[{start,end,text}]}` |
| `video` | `courseId, file:File` | `{summary或text,segments?:[...]}` |
| `speak` | `courseId,text` | `{audio:Blob,text?}` |

时间以真实秒值提供；无时间时标“未提供”，不推断逐词对齐。选中的音视频支持当前页预览，返回片段可定位同一原件；刷新后原音视频需重新选择，转写/摘要结果保留。生成语音在容量允许时缓存并可刷新后播放。结果可编辑为笔记，取消/超时和迟到结果不会标为成功。

### 尚待真实联调

1. B/E：资料原件服务端持久化、上传作业/OCR与真实页码定位、版本删除/重索引、存储迁移。当前本地PDF/DOCX仍沿用基础解析器，不声称已具备OCR。
2. C/E：MiMo真实图片、ASR、视频与TTS；题目/作答多类型、诊断、语义图谱/路径、FSRS等领域能力。受控适配的UI通过不等于模型质量或学习收益已验证。
3. E：将浏览器课程ID映射到服务端课程/权限与仓库；输入的`courseId`只是客户端上下文，不是权限证明。服务器必须重新校验。JSON导出不是数据库和原件的完整备份，恢复迁移由E对接。
4. F：使用真实样本、真实模型/硬件独立验收；引用ID存在不等于内容支持，候选题仍需审核与独立评测。

## 验证记录

- 起始基线：`node --test`，62项通过；未调用付费模型。
- 最终自动检查：`node --test`，73/73通过。新增11项覆盖长历史迁移、会话/课程/范围隔离、配额失败、刷新草稿、内容安全/公式、资料结果规范化、取消/超时与迟到结果。
- 原有浏览器回归：`node tests/e2e/browser.js`通过。真实官方SDK的MCP链路与受控模型配合；保留文本/PDF/DOCX、引用、题库、错题/记忆、取消、离线计划、响应式和file预览。
- A专项浏览器：`node tests/e2e/workspace.js`通过。覆盖资料版本/缓存原件/纠错草稿、笔记安全渲染与恢复、会话与指定旧回答追问、检索范围、反馈、多选/简答/草稿、计划预览/采纳/延期、图谱循环、课程归档/恢复、配额提示，以及受控资料CRUD、图谱/路径/掌握数据和图像/ASR/视频/TTS端口。
- 九个学习页面分别检查1440、768、375宽度，无页面横向溢出；检查Ctrl+K、Esc、原生弹窗、可聚焦对话滚动与文件预览不请求HTTP API。
- Playwright与Chrome为可选测试环境，使用方式与原浏览器脚本相同；本次使用已安装Chrome和工作区提供的Playwright，未修改package/lockfile。
- 截图：`test-results/workspace/chat-1440.png`、`chat-768.png`、`chat-375.png`和`graph-desktop.png`。已实际查看桌面/手机截图，修复输入框遮挡正文与图谱侧栏过长；截图目录被Git忽略。
- 本次未调用付费模型，未测试真实MiMo多模态、OCR、GPU或跨设备数据库，不把这些列为完成效果。

## 下一步

将本分支交E接入真实端口、交F独立验收。后续只需读取本文件、对应任务单和当前代码，按“尚待真实联调”继续；不重做已通过的前端流程。合并main由负责人审查决定。
