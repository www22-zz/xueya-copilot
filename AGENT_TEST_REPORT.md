# AGENT_TEST_REPORT

> 只记录**实际运行过**的命令与结果，禁止虚构。测试环境默认隔离（`.tmp/agent-lab-data/*`）。
> 最后更新：2026-11-16 15:30（Asia/Shanghai）。

## 0. 环境与命令

| 项目 | 值 |
| --- | --- |
| Python | `.venv\Scripts\python.exe`（Python 3.13.9，Anaconda 基础环境） |
| Node | `C:\Users\12638\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe`（v24.21.0） |
| 浏览器 | Playwright Chromium（profile 在 `.tmp/playwright`，绕开被策略拒绝的系统 Temp） |
| 后端测试 | `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` |
| 前端回归 | `node scripts/test.js --frontend` |
| 端到端验收 | `.venv\Scripts\python.exe scripts/check_agent_overhaul_browser.py --data-dir overhaul-final` |
| 生产服务 | 4173 全程只读，未重启；所有测试用隔离数据目录 + 测试账号 |

## 1. 基线（开工时，2026-11-15）

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 后端 pytest | `python -m pytest -q` | **29 failed, 1073 passed, 4 skipped**，508.04s（工作区当时无源码改动） |
| 前端回归 | `node scripts/test.js --frontend` | **77 pass / 0 fail / 0 skip**（486ms） |

既有失败清单（供最终对比，非本次需求引入）：
- `tests/python/test_cross_course_presets.py::test_cross_course_citations_and_snapshots_fail_after_origin_changes[remove-document]`
- `tests/python/test_curated_data_structures.py::test_authored_c_references_compile_and_run[complexity|linear|stack|strings|trees|heap|graphs|search|sorting|design]`（10 项，本机 C 工具链）
- `tests/python/test_document_practice.py::{test_upload_generates_100_hot_and_100_basic_and_can_answer, test_programming_material_can_generate_code_in_both_categories, test_failed_batch_is_not_replayed_and_explicit_resume_keeps_completed_work, test_server_restart_resumes_queued_batches_without_replaying_completed_batches}`
- `tests/python/test_plan_adoption_current.py::test_http_adoption_optional_current_is_forwarded_and_validated`
- `tests/python/test_platform.py::test_node_v3_snapshot_and_confirmations_are_compatible`
- `tests/python/test_portable_corpus.py::test_fresh_account_installs_existing_vectors_without_calls_and_preserves_history`
- `tests/python/test_portable_knowledge.py::{test_fresh_clone_accounts_get_cache_without_model_calls_and_restart_is_idempotent, test_archived_material_is_not_automatically_restored_on_restart, test_existing_bundle_subject_repair_preserves_content_and_custom_names[栈与队列知识库], test_existing_bundle_subject_repair_preserves_content_and_custom_names[自定义科目]}`
- `tests/python/test_queue_calculation.py::test_actual_chapter_evidence_can_answer_without_a_model_or_embedding`（5 个参数化）
- `tests/python/test_space_quiz_versions.py::test_hot100_text_review_does_not_execute_code_or_invent_numeric_rubric`
- `tests/python/test_study_space.py::test_study_plan_lifecycle_and_constraints`

## 2. 实验记录

### E-001 Hot100 知识点完整性（2026-11-15）
- 脚本：`.tmp/probe7.py` + `backend/xueya/practice_bank.py`。
- 结果：Hot100=100 题；官方专题 17 个；`topic ∉ tags` 的题 = 0；官方编号/专题与 bank 完全一致；各专题数量与官方一致。
- 隔离浏览器：`#space/practice/hot100` 初始 100 行，h100-53（#200 岛屿数量）存在；点胶囊「图论」=4 行；清除为「全部知识点」=100 行且含 h100-53；关键词「岛屿」「200」均能定位。
- 结论：数据层无遗漏；"找不到"来自切换筛选后选中项不在可视区 + 知识点导航不完整 → T4.3 按"官方 17 知识点导航 + 分组 + 选中定位"修复。

### E-002 算法演示现状（2026-11-15）
- 修复前 `algorithm_trace.trace()` 仅接受 h100-63/h100-53；前端 practice-view 写死 `['h100-63','h100-53']`。
- 修复后：通用引擎 100 题、registry 驱动、前端 12 个渲染器。

### E-003 任务一（overview「提问」入口）修复与验证（Lead）
- 复现：主问答生成中回到 `#space/overview` 点「提问」——hash 变为 `#space/ask`，但问题被静默丢弃（`ask()` 中 `state.pending` 直接 return）。这就是"点击后没有正常进入提问"的真实原因。
- 修复：`app.js` 新增 `window.XueyaOpenAsk(question)`（保留草稿→导航→等待 ask 视图→发送）+ `ask()` 排队；`overview-view.js` 按钮/chips 与 `framework-view.js` 答疑入口统一走该 helper。
- 验证：正常按钮、空输入、pending 场景、快捷 chip 均按预期（含排队自动发送）。

### E-004 独立验证脚本（T5）
`scripts/check_agent_overhaul_browser.py`：一条命令跑完 T1/T2/T3/T4 的浏览器与数据验收；隔离服务（带模型 / 无模型两套）；每项独立 PASS/FAIL/SKIP；输出 `test-results/agent-lab/overhaul-report.json` 与 24 张截图。

### E-005 本轮（2026-11-16）修复验收脚本编码崩溃
- 现象：GBK 控制台打印 `🌐` → `UnicodeEncodeError`，`t3.toggle-ui` 之后 8 项检查中断（首轮：PASS 5 + FAIL 1，其余未执行）。
- 修复：启动时 `sys.stdout/stderr.reconfigure(encoding='utf-8', errors='replace')`。
- 验证：同一命令重跑**25 项全部执行**；`t3.toggle-ui` 正常输出 `text='🌐\n联网搜索'`。

### E-006 桌宠 not-found 门禁收紧（I-005）
- 现象：问「怎么开启全息投影学习模式？这个功能在哪里？」返回 `status=ok` 并把入口指向 `#space/ask`。
- 根因：`_phrase_covered` 只要 CJK 连续段中**任一**二元组命中语料即算覆盖；「开启全息投影学习模式」因含「学习」「模式」被误判为已收录。
- 修复：每段要求 **≥3/5 二元组命中且至少 2 个**（整数上取整）；`PHRASE_STOP` 增补口语胶水词。
- 语料探针（54 条真实问法）：真实功能问法 33/34 覆盖（唯一例外「视频课程支持倍速播放吗」该能力系统确实没有，返回未收录是正确的）；不存在功能 19/20 被拦截（剩「如何开启后台自动播放」由模型依据片段兜底）。
- 端到端：`t2.companion-api` 的 not-found 分支由 `status=ok` 变为 `status=not_found`；新增回归测试 `test_compound_unknown_feature_is_not_treated_as_covered`；新增 `t2.companion-multiturn` 多轮检查。

## 3. 最终验收（2026-11-16，全部实跑）

### 3.1 端到端验收（隔离服务 + Chromium 真实交互）

命令：`.venv\Scripts\python.exe scripts/check_agent_overhaul_browser.py --data-dir overhaul-final`
结果：**PASS 25 | FAIL 0 | SKIP 0 | 238.9s**，报告 `test-results/agent-lab/overhaul-report.json`。

| # | 检查项 | 结果与关键证据 |
| --- | --- | --- |
| 1 | audit.practice-bank | PASS — Hot100=100、官方专题 17、并集=100 `{哈希3,双指针4,滑动窗口2,子串3,普通数组5,矩阵4,链表14,二叉树15,图论4,回溯8,二分查找6,栈5,堆3,贪心算法4,动态规划10,多维动态规划5,技巧5}` |
| 2 | audit.startup-starters | PASS — 100/100 题 × 3 语言骨架，均短于官方完整解 |
| 3 | audit.docs-guide | PASS — 17 篇／45,239 字／35 个 `#space` 路由全部真实存在 |
| 4 | audit.system-vectors | PASS — `vectors.json` 131 × 4096 维、内容哈希唯一、含「算法练习」chunk |
| 5 | audit.demo-coverage | PASS — 100/100 题、213/213 样例、0 失败、schema=demo-2 |
| 6 | t4.4.registry | PASS — registry 100 ids、11 种 viz；`export_algorithm_demos.py --check` 退出码 0 |
| 7 | t4.4.api-schema | PASS — 抽样 10 题（含全部 samples）schema/行号/state/`result==sample.output` 一致 |
| 8 | t2.companion-api | PASS — system→`route=system`（sources 5, links 1）；general→`route=general`；不存在功能→`status=not_found` |
| 9 | t2.companion-multiturn | PASS — 首轮系统问题；带 history 的追问仍 `route=system`、sources=5、links 合法 |
| 10 | t3.search-events | PASS — 关闭：9 个事件、工具全为 `search_materials`（无 `search_web`）；开启：10 个事件、出现 `search_web` |
| 11 | t2.companion-unavailable | PASS — 无模型服务下系统问答降级为本地指南答案（含真实路径与步骤） |
| 12 | t1.overview-ask | PASS — hash=`#space/ask`、问题进入线程、payload 含 question/courseId/sources(4)/documentIds(1)/mode=ask/webSearch=false；空输入不跳转 |
| 13 | t1.overview-chips | PASS — 快捷 chip 触发跳转并把问题送入请求 |
| 14 | t1.real-answer | PASS — 真实模型链路返回回答（26 字，带引用标记） |
| 15 | t3.toggle-ui | PASS — 文案「🌐 联网搜索」、`aria-label/title` 一致、默认 `false`、toast 正确 |
| 16 | t3.payloads | PASS — 关闭时 `webSearch=false/absent`；开启时真实请求 `webSearch=true` |
| 17 | t4.1.back-button | PASS — DOM 无「返回算法学习」按钮、标题行存在、100 行列表正常 |
| 18 | t4.2.icon-centering | PASS — 1440/1024/390 宽度下图标与输入框中心差值均为 **0.0px** |
| 19 | t4.3.knowledge-points | PASS — 100 行、17 组计数与官方数据一致、「图论」筛选=4 行、h100-53 滚入可视区（row 488-566 落在 484-848） |
| 20 | t4.3.no-hardcode | PASS — 演示入口由 registry 驱动、无写死 #200 特例、读取 starterCode |
| 21 | t4.5.starter-code | PASS — 骨架 128 字符 < 答案 660 字符；切换语言后已保存代码保留；查看完整题解可用 |
| 22 | t4.4.browser | PASS — h100-63(6 步, result=2)、h100-53(21 步, result=1)、h100-01(8 步, result=[0,1])；上一步/播放/下一步/重置/样例选择齐全；无 console 错误 |
| 23 | t4.4.integration | PASS — 100 个「交互演示」标记与 registry 一致；详情链接 `/algorithm-demo.html?question=…` 正确 |
| 24 | t2.companion-browser | PASS — 桌宠回答含真实路径，links 可点击并真实跳转到 `#space/practice/hot100` |
| 25 | regression.pages | PASS — overview/ask/courses/practice/exams/knowledge/analysis 桌面+移动均无 JS 错误、无横向溢出 |

### 3.2 后端全量回归

| 运行 | 结果 | 说明 |
| --- | --- | --- |
| 基线（11-15） | 29 failed, 1073 passed, 4 skipped | 既有失败 |
| 中途（11-16，含全部改动） | 28 failed, 1129 passed, 6 skipped | 新增测试全部通过；1 项基线失败转为通过 |
| **最终（11-16，独立重跑）** | **28 failed, 1130 passed, 6 skipped, 492.69s** | 28 项失败与基线逐条对应，**无新增回归**；58 个新测试 56 通过 + 2 条件跳过 |

对比基线：**本轮新增 58 个测试：56 通过 + 2 条件跳过**（`--collect-only` 实测 58 collected；运行 `-rs`：`test_algorithm_demo.py::test_all_samples_trace_verifies` 需 `XUEYA_ALGO_DEMO_FULL=1` 的穷举开关，其等价校验已由 `test-results/algorithm-demo-coverage.json` 全量 213 样例完成；`test_web_search_toggle.py::test_browser_default_off_then_explicit_web_search_payload` 需 `XUEYA_RUN_BROWSER_LAB=1`，其等价浏览器校验已由端到端 `t3.toggle-ui`/`t3.payloads` 覆盖）。失败集合与基线逐条对应，无新增回归。

### 3.3 前端回归

`node scripts/test.js --frontend` → **77 pass / 0 fail / 0 skip**（456.8ms），与基线一致。

### 3.4 定向复核

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 系统百科向量与文档一致性 | `python scripts/build_system_guide_vectors.py --check` | `check ok: manifest, identity, dimension, vectors, content hashes and docs coverage all match`（17 篇 / 131 chunks / 4096 维 / 11,754,997 bytes） |
| 演示注册表新鲜度 | `python scripts/export_algorithm_demos.py --check` | `hot100 questions: 100, verified demos: 100, failed: 0`；`REGISTRY CURRENT (100 ids)` |
| 演示覆盖真实校验 | `test-results/algorithm-demo-coverage.json` | 100 题 / 213 样例 / 0 失败 / 42.2s（引擎内真实执行官方参考解并比对样例输出） |
| 构建/语法检查 | `node --check` 9 个改动的 JS 文件；`python -m compileall backend/xueya`；pytest 内 C++/Java 代表样例真实编译 | PASS（9/9 JS 解析通过；compileall OK） |
| 演示页渲染 | 24 张截图（`test-results/agent-lab/demo-frontend-*.png`，含 12 种 viz 的真实数据与 mock 兜底） | 人工抽查 grid/graph/dp 等，均为对应算法的真实状态可视化 |

### 3.5 最终全量回归与残余失败

最终独立重跑（`python -m pytest -q -p no:cacheprovider`）：
**28 failed, 1130 passed, 6 skipped, 492.69s**。

- **28 项失败与开工基线逐条一致**（见 §1 清单），属于本机工具链/既有功能的历史问题，与本次改动无调用关系。
- 新增的 58 个测试：**56 通过 + 2 条件跳过**（跳过项为显式开关的穷举扫描与浏览器实验室，其等价校验分别由 coverage 全量 213 样例与端到端 t3 检查完成）；通过数 1129 → 1130 即本轮新增的 not-found 门禁回归测试。
- 过程记录：在其中一次并发运行的整轮测试中，`test_cross_course_presets.py::test_two_accounts_search_and_read_public_metadata_at_actual_origin` 曾偶发失败一次，报错为 `sqlite3.OperationalError: unable to open database file`（资源型）；单独运行通过（8.04s），该文件连续两次重跑也只复现既有的 `[remove-document]` 失败，随后的独立整轮重跑不再出现。判定为环境偶发，与本次改动无关。
- 结论：**本轮改动未引入任何可复现的新失败**。

## 4. 未通过的项与原因

| 项目 | 状态 | 原因 |
| --- | --- | --- |
| basic/interview 题库的 3D 演示 | 未实现（不适用） | 这两类题库没有官方样例输出与参考解，演示引擎坚持「结果必须等于样例预期，否则报错」不能伪造，故无法生成可信演示；它们也不在 Hot100 模块的交互演示入口内 |
| 后端 28 项存量失败 | 维持原状 | 历史问题（C 工具链、portable/queue 等），超出本次四项需求范围；未删改测试掩盖 |
| 生产服务 4173 的 UI 交互 | 未测 | 生产账号已配置且未登录，不能猜测密码；全部 UI 验证在隔离服务 + 测试账号完成 |

## 5. 复现方式

```powershell
# 1) 端到端验收（25 项，约 4 分钟；会启动多个隔离服务与 Chromium）
.venv\Scripts\python.exe scripts/check_agent_overhaul_browser.py --data-dir overhaul-final
# 只跑部分
.venv\Scripts\python.exe scripts/check_agent_overhaul_browser.py --only t1,t3,t4.5 --data-dir overhaul-final
# 不花钱（跳过真实模型调用）
.venv\Scripts\python.exe scripts/check_agent_overhaul_browser.py --skip-model
# 2) 后端全量
.venv\Scripts\python.exe -m pytest -q
# 3) 前端回归
node scripts/test.js --frontend
# 4) 知识与注册表一致性
.venv\Scripts\python.exe scripts/build_system_guide_vectors.py --check
.venv\Scripts\python.exe scripts/export_algorithm_demos.py --check
```
