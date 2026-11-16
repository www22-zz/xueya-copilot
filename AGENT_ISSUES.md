# AGENT_ISSUES

记录：问题、失败原因、尝试过的方案、最终状态。编号 I-xxx。

## 环境

- **I-001（已解决）** 本机系统 Temp 目录被策略拒绝，Playwright `mkdtemp` 报 EPERM。
  - 尝试：直接 launch → 失败；设置 `os.environ['TMP']` 但 tempfile 已缓存 → 失败。
  - 解决：`scripts/agent_lab.py` 在 import 前强制设置 `TMP/TEMP` 与 `tempfile.tempdir` 到 `.tmp/playwright`。
- **I-002（已绕开）** 隔离 server 首次 `/api/platform/bootstrap` 约 25s（安装预置语料），前端 practice-client 只等 3s → 题库显示「本机服务未连接」。
  - 解决：lab harness 注册账号后先 `warm()` 调一次 bootstrap；浏览器再访问。
- **I-003（约束处理）** 生产服务 4173 已配置账号且未登录，无法用其做交互测试；禁止猜测/重置用户密码。
  - 处理：所有 UI 测试在隔离数据目录 + 新注册测试账号进行；生产服务仅做只读健康检查，未重启、未写入。
- **I-007（已解决）** pytest / playwright 在宿主机临时目录不可用时回退到仓库根目录，产生 `xueya-*/`、`pytest-of-*/`、`probe-*/`、`pip-*/` 等临时目录（最多时 570+ 文件），污染 `git status`。
  - 解决：`.gitignore` 增加对应前缀；清理历史残渣；源码与测试数据不受影响。

## 任务相关

- **I-004（已解决，2026-11-16）** 端到端验收脚本在 GBK 控制台崩溃，导致 10 项检查未执行。
  - 现象：`scripts/check_agent_overhaul_browser.py` 在 `check_t3_ui` 打印含 `🌐` 的详情时抛 `UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f310'`，进程退出码 1；报告只记录了 5 项 audit + t4.4 + t2.companion-api，`t3.toggle-ui` 之后的 8 项全部缺失。
  - 诊断依据：脚本虽设置 `PYTHONUTF8/PYTHONIOENCODING` 环境变量，但那是给子进程用的，当前解释器的 `sys.stdout` 早已按 GBK 打开。
  - 修复：脚本启动时对 `sys.stdout/stderr` 执行 `reconfigure(encoding='utf-8', errors='replace')`，任何非 GBK 字符都不再能中断检查。
  - 验证：同一命令重跑 25 项全部执行（PASS 24 / FAIL 1 → 修复 I-005 后 PASS 25）。

- **I-005（已解决，2026-11-16）** 桌宠对「系统不存在的功能」给出了真实页面入口，违反「资料不足/功能不存在必须明确说明」。
  - 现象：问「怎么开启全息投影学习模式？这个功能在哪里？」，`companion/chat` 返回 `status=ok`、`route=system`，答案把入口指向「AI 助手与主问答 `#space/ask`」，未说明该系统功能不存在。
  - 诊断依据：检索结果本身带低相关片段，`_phrase_covered` 只要求 CJK 连续段里**任意一个**双字组在语料中出现；`开启全息投影学习模式` 因含「学习」「模式」被判为已覆盖，于是 not_found 门禁未触发，模型被误导。
  - 修复：`_phrase_covered` 改为每个 CJK 连续段要求 **≥3/5 双字组命中且至少 2 个**（整数上取整避免 0.6 浮点误差）；`PHRASE_STOP` 增补「把/被/让/给/从/向/对/到/成/着/过/也/都/还/就/才/又/并/及/以/为/会/该/几种/几道」等口语胶水词，避免自然问法被误杀。
  - 验证：54 条问法探针（34 条真实功能 + 20 条不存在功能）真实语料评估：真实问法召回 33/34（唯一例外「视频课程支持倍速播放吗」——该能力系统确实没有，返回「指南未收录」是正确行为），不存在功能拦截 19/20（剩「如何开启后台自动播放」由模型依据片段兜底）；端到端 `t2.companion-api` 返回 `status=not_found`；新增回归测试固化了正反两侧断言；companion 单测 18 项全通过。

- **I-006（记录，非本次引入）** 后端 pytest 存量失败 28 项（开工基线 29 项，本轮其中 `test_study_space::test_study_plan_lifecycle_and_constraints` 已转为通过）。
  - 分布：`test_curated_data_structures` 编译用例 11 项（本机 C 工具链）、`test_document_practice` 4 项、`test_portable_knowledge` 4 项、`test_portable_corpus` 1 项、`test_queue_calculation` 5 项、`test_cross_course_presets` 1 项、`test_plan_adoption_current` 1 项、`test_platform` 1 项、`test_space_quiz_versions` 1 项。
  - 处理：不属于本次四项需求范围，且与本轮改动无调用关系（本轮新增 58 项测试：56 通过 + 2 条件跳过）；如实记录在 `AGENT_TEST_REPORT.md` 与最终报告中，不做「删测试/改断言」式掩盖。
