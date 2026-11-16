# AGENT_FINAL_REPORT — 学涯 Copilot 无人值守系统优化最终报告

> 执行时间：2026-11-15 ～ 2026-11-16（Asia/Shanghai）
> 分支：`codex/unattended-overhaul-20261115`
> 实现检查点：`dab491a feat(overhaul): complete unattended system upgrade for T1-T4`
> 文档/验收提交：`docs(agent): record progress, issues, test evidence and final report`（分支最新提交）
> 详细测试证据：`AGENT_TEST_REPORT.md`；过程与决策：`AGENT_PLAN.md` / `AGENT_PROGRESS.md`；问题记录：`AGENT_ISSUES.md`

## 1. 结论摘要

四项需求**全部落地并通过可执行验收**，没有「只改文案/只写文档/只生成空壳」的虚假完成：

| 总览 | 数值 |
| --- | --- |
| 端到端验收 | **25 项检查全部 PASS，0 FAIL，0 SKIP**（隔离服务 + 真实 Chromium 交互，238.9s） |
| 后端全量回归 | 28 failed（**与开工基线逐条一致**）/ **1130 passed** / 6 skipped（492.69s） |
| 前端回归 | **77 pass / 0 fail** |
| 本轮新增测试 | 6 个测试文件、58 个测试：**56 通过 + 2 条件跳过**（跳过项为显式开关的穷举扫描/浏览器实验室，等价校验分别由 coverage 全量 213 样例与端到端 t3 检查完成） |
| 算法交互演示 | Hot100 **100/100 题**、**213/213 个官方样例**真实执行校验通过 |
| 桌宠知识库 | 17 篇系统百科、**131 chunks × 4096 维**真实向量（Qwen3-VL-Embedding-8B） |
| 修改规模 | 52 个文件、+14,405 / −162 行（实现检查点） |

## 2. 需求完成状态矩阵

状态定义：DONE = 已实际开发并通过可执行验收；PARTIAL = 部分完成；BLOCKED = 外部条件阻塞；NOT_APPLICABLE = 数据条件不满足、不做才诚实。

| 编号 | 需求 | 状态 | 实现要点 | 验收证据（实跑） |
| --- | --- | --- | --- | --- |
| T1 | 修复「去提问」无法跳转 | **DONE** | 新增 `window.XueyaOpenAsk()`：保留草稿 → 路由到 `#space/ask` → 等视图就绪 → 发送；`ask()` 增加单槽排队（上一条生成中不再静默丢弃）；概览「提问」按钮、快捷 chips、知识框架「答疑」三类入口统一 | `t1.overview-ask`：hash=`#space/ask`、问题进入线程、payload 含 question/courseId/sources(4)/documentIds(1)/mode=ask/webSearch=false、空输入不跳转；`t1.overview-chips`；`t1.real-answer`（真实模型回答 26 字带引用） |
| T2A | 全面理解系统 | **DONE** | 逐项核对路由注册（`frontend/js/app.js`）、页面组件、后端 API 与题库/向量配置，不靠文件名猜测 | 17 篇文档中的 35 个 `#space` 路由全部经 `KNOWN_VIEWS` 校验存在（`audit.docs-guide`） |
| T2B | 系统百科全书 | **DONE** | `docs/guide/` 17 篇：总览、功能总览、页面路由目录、课程学习、课程资料、算法学习、408、练习错题、个人资料库、AI 助手、学习计划与学情、知识框架、账号设置、桌宠说明、FAQ、功能位置索引、功能限制；每篇含功能名/作用/模块/进入路径/步骤/路由/FAQ/代码依据 | `audit.docs-guide`：17 docs / 45,239 字 / 35 真实路由 |
| T2C | 桌宠专属 RAG 知识库 | **DONE** | 复用既有 Embedding 基础设施（不新建重复服务）；`scripts/build_system_guide_vectors.py` 按标题层级切分、内容哈希去重、`--check` 校验、增量重建；`materials/system-guide/{manifest,vectors}.json`；与课程 RAG 逻辑隔离（独立目录、独立加载器、不写用户向量表）；检索=向量余弦+关键词/标题/元数据混合打分，返回功能名、页面路径、步骤 | `audit.system-vectors`：131 × 4096 维、哈希唯一、含「算法练习」chunk；`build_system_guide_vectors.py --check`：`manifest/identity/dimension/vectors/content hashes/docs coverage all match` |
| T2D | 桌宠对话集成 | **DONE** | 新增 `POST /api/learning/space/companion/chat`；系统类问题走百科 RAG 并返回可点击 `links`（仅白名单真实路由），普通问题走通用问答，资料不足返回 not_found，模型不可用时降级为本地指南答案；桌宠 UI 渲染 links 并支持点击跳转 | `t2.companion-api`（system/general/not_found 三路）、`t2.companion-browser`（回答含真实路径，点击 links 实际跳到 `#space/practice/hot100`）、`t2.companion-unavailable`（无模型降级仍给出正确入口） |
| T2E | RAG 测试 | **DONE** | 覆盖功能介绍、位置查询、步骤查询、多轮追问、普通聊天、不存在功能、检索失败、API 不可用 | `t2.companion-multiturn`（带 history 的追问仍 `route=system`、sources=5、links 合法）+ 18 个单元测试 |
| T3 | AI 助手检索机制 | **DONE** | 文案改「联网搜索」；`state.webSearch` 首次进入强制 false；课程资料默认参与（UI 旁注说明）；后端课程会话工具白名单改为 `COURSE_READ_TOOLS`（不含 `search_web`），`/api/platform/tools/call` 对 `search_web` 要求显式 `allowWebSearch=true`；UI 状态与请求参数一致 | `t3.toggle-ui`（文案/aria/title/默认值/toast）、`t3.payloads`（关闭 `webSearch=false`/开启 `true` 的真实请求）、`t3.search-events`（SSE：关闭 9 事件无 `search_web`；开启 10 事件出现 `search_web`） |
| T4.1 | 删除多余返回按钮 | **DONE** | 移除 Hot100 工具栏「返回算法学习」面包屑入口，标题行保持布局 | `t4.1.back-button`：DOM 无该元素、标题行存在、100 行列表正常 |
| T4.2 | 搜索框图标垂直居中 | **DONE** | `.hot100-search-wrap` 改为 flex + `align-items:center`、输入框 `display:block/align-self:center`，消除 inline 基线间隙 | `t4.2.icon-centering`：1440/1024/390 三种宽度 delta=**0.0px** |
| T4.3 | 知识点分类遗漏（#200） | **DONE** | 数据层审计：100/100 题 `topic ∈ tags`、官方 17 专题并集=100、无 #200 特例；UI 改为由官方专题数据生成 17 组导航（带计数），「全部知识点」按专题分组，筛选后选中题自动滚入可视区 | `audit.practice-bank`、`t4.3.knowledge-points`（100 行、17 组计数与官方一致、「图论」筛选=4 行、h100-53 滚入可视区）、`t4.3.no-hardcode`（无写死 id） |
| T4.4 | 全部算法题 3D 交互演示 | **DONE（Hot100 100/100）** | 用「真实执行追踪」替代手写动画：在隔离子进程执行官方 Python 参考解，`sys.settrace` 记录真实行号与 JSON 安全局部变量快照，断言最终返回值==样例预期（不一致报 `DEMO_RESULT_MISMATCH` 而非编造）；4 道设计类题逐操作追踪；前端 12 个数据驱动渲染器（grid/matrix/array/dp/tree/linked-list/graph/string/stack-queue/backtracking/design/scalar）+ 播放/暂停/上一步/下一步/重置/调速/拖拽旋转缩放/当前状态/关键高亮/代码行高亮/示例输入输出/文字解释；registry 由脚本从后端导出 | `audit.demo-coverage`（100/100 题、213/213 样例、0 失败）、`t4.4.registry`（100 ids、11 种 viz、`--check` 通过）、`t4.4.api-schema`（抽样 10 题逐样例校验）、`t4.4.browser`（3 题真实播放、结果正确、无 console 错误）、`t4.4.integration`（100 个入口标记与 registry 一致） |
| T4.5 | 代码编辑器初始内容 | **DONE** | `backend/xueya/data/hot100_starters.json`：100 题 × Python/C++/Java 骨架（类/签名/参数，无核心实现）；`practice_bank` 校验后挂 `starterCode`；首次打开显示骨架，用户已保存代码优先不覆盖，切语言仅在「模板态」替换，「查看完整题解」保持可用，判题逻辑不变 | `audit.startup-starters`（100/100 × 3 语言、均短于完整解）、`t4.5.starter-code`（骨架 128 字符 vs 答案 660 字符、已保存代码保留、题解可查看）、9 个单元测试（含 C++/Java 代表样例真实编译、Python 骨架可执行） |
| T5 | 回归与最终验收 | **DONE** | 一条命令跑完全部验收 + 主要页面回归；报告 JSON + 24 张截图 | 25/25 PASS；新增 58 测试（56 通过 + 2 按开关跳过，均有等价覆盖）；详见 §5 |

## 3. 实际修改的主要文件

### 3.1 新增（核心能力）

| 文件 | 规模 | 作用 |
| --- | --- | --- |
| `backend/xueya/algorithm_demo.py` | 1,314 行 | 算法执行追踪引擎（demo-2 schema、样例结果校验、缓存、设计类题、错误码） |
| `backend/xueya/companion_knowledge.py` | 450 行 | 系统百科索引加载 + 混合检索 + 路由/链接白名单 + not-found 门禁 |
| `backend/xueya/companion_api.py` | 323 行 | 桌宠 `/companion/chat` 端点（系统/普通/降级/多轮） |
| `backend/xueya/data/hot100_starters.json` | 50.5 KB | 100 题 × 3 语言初始骨架 |
| `docs/guide/*.md` | 17 文件 / 45,239 字 | 系统百科（RAG 知识源） |
| `materials/system-guide/manifest.json` `vectors.json` | 11.75 MB | 4096 维向量索引 + 身份/哈希/增量清单 |
| `frontend/js/algorithm-lab.js` | 2,827 行 | 数据驱动 3D 演示（12 渲染器 + 播放控制 + 交互） |
| `frontend/js/algorithm-demo-registry.js` | 生成文件 | 100 个可演示题目注册表 |
| `scripts/check_agent_overhaul_browser.py` | 1,904 行 | 25 项端到端验收（隔离服务 + Chromium） |
| `scripts/build_system_guide_vectors.py` | 619 行 | 文档切分/向量化/去重/增量/`--check` |
| `scripts/build_practice_starters.py` | 565 行 | 从官方题解生成骨架目录 |
| `scripts/export_algorithm_demos.py` | — | 导出演示注册表 + `--check` |
| `scripts/agent_lab.py` | 160 行 | 隔离测试环境（数据目录/账号/浏览器/预热） |
| 测试 6 个文件 | 58 测试 | 演示引擎、桌宠 API/知识、题库分类、初始骨架、联网开关 |

### 3.2 修改（既有文件）

- `backend/xueya/agent.py`：新增 `COURSE_READ_TOOLS`（默认不含 `search_web`），课程会话与工具会话使用该白名单。
- `backend/xueya/app.py`：注册桌宠端点；`/api/platform/tools/call` 增加联网显式守卫。
- `backend/xueya/config.py`、`frontend/index.html`：`UI_BUILD` 升级为 `2026-11-15-unattended-overhaul-1`（并引入 registry 脚本）。
- `backend/xueya/practice_bank.py`：校验并注入 `starterCode`。
- `backend/xueya/algorithm_trace.py`：保留旧接口兼容 shim，内部转发通用引擎。
- `frontend/js/app.js`：`XueyaOpenAsk`、问答排队、`XueyaAskCompanion`（桌宠对话适配）。
- `frontend/js/overview-view.js`、`frontend/js/framework-view.js`：统一「提问/答疑」入口。
- `frontend/js/practice-view.js`：T4.1/T4.3/T4.5（专题导航、分组、滚动定位、骨架、registry 演示入口）。
- `frontend/css/stitch-theme.css`：搜索图标居中 + 知识点导航/分组样式。
- `frontend/js/ui/workspace-views.js`、`frontend/js/workspace-controller.js`：联网搜索文案/默认值/toast。
- `frontend/js/study-companion.js`：百科 sources/links 渲染、route 标识、降级与错误处理。
- `frontend/algorithm-demo.html`、`frontend/css/algorithm-lab.css`：演示页外壳与 3D 视觉样式。
- `.gitignore`：忽略 pytest/Playwright 回退到仓库根目录时产生的临时目录。

## 4. 算法题数量与演示覆盖（真实统计）

| 指标 | 数值 | 说明 |
| --- | --- | --- |
| 固定题库算法题总数 | **250** | `backend/xueya/data/practice_bank.json`：hot100 100 + basic 100 + interview 50 |
| 已有交互演示 | **100** | 全部 Hot100；覆盖 17 个官方专题 |
| Hot100 范围内缺演示 | **0** | — |
| 无法生成可信演示 | **150** | basic/interview 无官方样例输出与参考解；引擎要求「返回值==样例预期」才允许出演示，不能伪造 |
| 官方样例校验 | **213/213 通过** | 100 题全部样例真实执行，0 失败 |
| 演示形态 | 11 种 viz（+ scalar 兜底 = 12 渲染器） | array 26、tree 15、dp 14、linked-list 13、backtracking 8、stack-queue 6、string 6、matrix 5、design 4、grid 2、graph 1 |
| 逐题明细 | 见 `AGENT_PROGRESS.md` §T4.4 统计表 | 含题号/ID/题名/算法类型/演示形态/样例数/核心思路 |

> 严格区分：**「Hot100 的 100 道算法题」全部完成交互演示（DONE）**；**basic/interview 的 150 道题没有生成演示（NOT_APPLICABLE，非「没做」也非「假装做了」）**，原因是没有可校验的官方样例与参考解，且它们不在「算法学习 → Hot100」的交互演示入口范围内。

## 5. RAG 知识库状态与真实检索验证

**知识库状态**

| 项目 | 值 |
| --- | --- |
| 知识源 | `docs/guide/` 17 篇系统百科（45,239 字） |
| 向量库 | `materials/system-guide/vectors.json`（11,754,997 bytes）+ `manifest.json` |
| Embedding 模型 | **Qwen3-VL-Embedding-8B**（provider `api.moark.com/v1`，adapter `moark-qwen-text-v2`） |
| 维度 | **4096**（manifest `identity.dimension`，与索引逐条一致） |
| 切分 | 131 chunks（标题层级对齐，含 feature/module/routes/sectionPath 等元数据） |
| 去重 | 内容哈希唯一（`duplicateChunks: []`），重复文档不重复向量化 |
| 增量/重建 | `scripts/build_system_guide_vectors.py`：内容哈希复用（上次构建 129 复用 + 2 新增）、`--force` 重建、`--check` 校验；文档变更后 `--check` 会失败提示重建 |
| 隔离 | 独立目录 + 独立加载器（`GuideKnowledge`），不写用户课程向量表；账号级 override 仅在 `.xueya-data/system-guide` 存在时生效 |
| 敏感信息 | 已扫描新增文件与清单，无 API Key/密码/凭据；密钥只在本机 `.env` |

**真实检索验证（全部实跑，非仅代码走查）**

| 场景 | 结果 |
| --- | --- |
| 系统功能位置（算法练习在哪 / 怎么刷 Hot100） | `route=system`、`engine=guide-rag`、sources 5、links 1，答案含 `#space/practice/hot100` 与 1-2-3 步骤 |
| 浏览器桌宠真实问答 | 回答 492 字，含真实路径；点击 links 实际跳转到 `#space/practice/hot100`（`t2.companion-browser`） |
| 不存在功能（全息投影学习模式） | **`status=not_found`**，明确说明指南未收录，并列出现有功能领域，不编造入口 |
| 普通聊天（非系统问题） | `route=general`、`engine=general-chat`，不强行引用系统文档 |
| 多轮追问（带 history） | 第二轮仍 `route=system`、sources 5、links 合法 |
| 模型不可用（无模型隔离服务） | 降级为本地指南检索答案 + 「模型暂不可用」提示，入口与步骤仍正确 |
| 检索/索引失败 | 降级 lexical 并返回 warning（`SYSTEM_GUIDE_EMBEDDING_UNAVAILABLE` 等），不抛错 |
| 版本一致性 | `build_system_guide_vectors.py --check` 通过（文档、内容哈希、维度、数量全部匹配） |

## 6. 联网搜索（T3）行为验证

| 状态 | 前端 | 后端 |
| --- | --- | --- |
| 默认进入 | 按钮 `aria-pressed=false`，文案「🌐 联网搜索」，提示「课程资料默认参与检索」；请求体 `webSearch=false` | 课程会话工具白名单 `COURSE_READ_TOOLS`（无 `search_web`）；工具调用接口未显式放行时拒绝 `search_web` |
| 关闭时提问 | 课程资料照常检索（payload 带 sources/documentIds） | SSE 实测 9 个事件全部是 `search_materials`，**无** `search_web`；不存在回退联网路径 |
| 手动开启 | `aria-pressed=true`，toast「联网搜索已开启（课程知识库始终参与检索）」；请求体 `webSearch=true` | SSE 实测 10 个事件，出现 `search_web`；可与课程资料结合 |

## 7. 失败、跳过、未完成项（严格区分）

| 项目 | 分类 | 说明 |
| --- | --- | --- |
| 四项需求 | **全部 DONE** | 无跳过、无未完成 |
| basic/interview 的 150 题演示 | NOT_APPLICABLE | 缺官方样例与参考解，无法生成「结果可校验」的演示；不伪造 |
| 后端 28 项 pytest 失败 | 既有问题（非本轮引入） | 与基线逐条一致：C 工具链 11 项、document_practice 4 项、portable_knowledge 4 项、portable_corpus 1 项、queue_calculation 5 项、cross_course 1 项、plan_adoption 1 项、platform 1 项、space_quiz_versions 1 项 |
| 生产服务 4173 的 UI 交互测试 | 未执行（约束） | 生产账号已配置但未登录，不能猜测/重置密码；全部 UI 验证在隔离服务 + 测试账号完成；生产服务仅做只读健康检查，未重启、未写入 |
| 历史任务文档 | 不做 | 按仓库约定（AGENTS.md）不在 main 重建历史任务卡；本报告与 AGENT_* 为本轮交付过程文档 |

## 8. 仍然存在的问题

1. **存量测试失败 28 项**（见上表）：属仓库历史问题，建议单独排期，不要与本轮改动混在一起。
2. **桌宠 not-found 门禁是启发式**：已完成「不存在的功能名」拦截（如全息投影/直播课/AI 画图/VR/语音克隆等），但「用真实名词组合出的能力型问题」（如「能不能自动生成视频课程」）仍会进入系统检索，最终由模型依据指南片段说明未收录——不会编造入口，但拦截不是 100% 词面级。已用 54 条问法探针量化（真实问法召回 33/34、不存在功能拦截 19/20）。
3. **`docs/guide` 与向量索引需要同步维护**：改了系统界面/入口后，必须重跑 `scripts/build_system_guide_vectors.py --write`（未重建时 `--check` 会报不一致）。已把该命令写入复现说明。
4. **端到端验收脚本依赖本机 Playwright + 外部模型 API**：CI 上需准备对应环境；`--skip-model` 可跑零成本子集。
5. **交互演示的 3D 场景为自研 Canvas/WebGL 渲染**：低端设备上元素多的题目（如 N 皇后 196 步）建议使用「步骤选择器 + 调速」而非连续播放。

## 9. 后续建议

1. 为 basic/interview 题库补官方样例与参考解，即可用同一引擎零改动扩展演示（引擎与注册表流程已就绪）。
2. 把 `scripts/check_agent_overhaul_browser.py --skip-model` 纳入提交流水线（防止 T1/T3/T4 回归），带模型的完整验收在发布前跑。
3. 桌宠侧可把「能力型问题」再收敛：对「有没有/能不能/支持…吗」句式增加功能名词白名单匹配，进一步降低误命中。
4. 清理 28 项存量失败（多数是本机 C 工具链与 portable/queue 用例），或显式标记 `skip` 并写明环境前提。
5. 文档与索引联动做成脚本钩子（改动 `docs/guide/**` 后自动 `--write`），避免知识库过期。

## 10. Git 检查点与复现

```text
dab491a  feat(overhaul): complete unattended system upgrade for T1-T4   ← 实现检查点（52 files, +14405/−162）
docs(agent)  record progress, issues, test evidence and final report      ← 本报告与过程文档
```

分支：`codex/unattended-overhaul-20261115`（main 为祖先；未合并、未强推、未联系队友，遵循 AGENTS.md）。

```powershell
# 端到端验收（25 项）
.venv\Scripts\python.exe scripts/check_agent_overhaul_browser.py --data-dir overhaul-final
# 后端 / 前端回归
.venv\Scripts\python.exe -m pytest -q
node scripts/test.js --frontend
# 知识与注册表一致性
.venv\Scripts\python.exe scripts/build_system_guide_vectors.py --check
.venv\Scripts\python.exe scripts/export_algorithm_demos.py --check
```

## 11. 启动方式（已有方式，未改动）

`一键启动学涯.cmd` 或 `node scripts/run-python.js -m backend.xueya.server`（默认 `127.0.0.1:4173`）。
生产服务在本次执行期间保持运行且未重启；`/api/health` 返回 `ok:true`，`uiBuild=2026-11-15-unattended-overhaul-1` 与 `frontend/index.html` 一致（不会触发前端版本重载循环）。
