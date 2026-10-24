# 行为保持重构审计与执行记录

日期：2026-10-25。审计基线：`01c98fd3eb2926bcc84bc94c143a2a031cc88347`。
范围：默认副本的生产 Python、C 兼容实现、浏览器代码、测试与工程配置；不读取真实 `.env` 内容，不处理旧副本。
阶段 1 仅搜索、读取、内存分析及受控复现，完成报告后才进入阶段 2。下表行号均指审计基线，重构后请结合 Git 原始版本核对。

## 阶段 0 基线

- 远程 `main` 与本地同为 `01c98fd`，工作区干净；Python 3.12.7、Node 24.19.0。
- `python -B -m pytest -q -p no:cacheprovider`：495 passed，89.25 秒。首次沙箱运行在临时目录创建阶段失败，正常权限重跑通过，非产品失败。
- `node scripts/test.js --frontend`：42 passed；`python -B -m pip check` 通过。
- `python -B -m backend.xueya.mcp_server --check`：4 工具，检索命中 2 条。
- `python -B -m scripts.check_quality --repeats 1`：退出 0，fixed-lexical 43/46，structured-lexical 40/46；质量未全部达标。
- 内存 `ast.parse` 检查 Python 219 文件，`node --check` 检查 JavaScript 56 文件，通过。
- `node tests/e2e/browser.js`、`workspace.js`、`platform.js` 均报 `MODULE_NOT_FOUND: playwright`，未进入浏览器场景。
- `npm` 不在 PATH，直接运行 package.json 对应脚本；未安装或修改依赖。
- `package.json:6-26`、`pyproject.toml:1-25`、`.github/workflows/quality.yml:31-36` 未定义独立 lint、类型检查和构建入口，语法检查不等于这些检查。

## 审计方法与证据边界

1. `git ls-remote origin refs/heads/main refs/heads/feat/large-C-agent-learning` 核实远程；`git merge-base main feat/large-C-agent-learning` 返回 `015b3d5`，C 分支是 main 的祖先，无独有提交。
2. 对 `backend/`、`scripts/` 的 Python AST 统计函数长度、分支节点、导入名称使用、相同函数体。分支节点数是静态粗指标，包含嵌套定义，**不是正式圈复杂度**；未发现不少于 6 行的完全相同函数体，不等于没有语义重复。
3. 对顶层静态导入建图，未发现环；不覆盖延迟导入、动态插件或反射。全局搜索 `getattr`、`globals`、`locals`、`import_module`、`__import__` 后，对不能排除的兼容导出不删除。
4. 只扫描 Git 跟踪的文本，密钥候选仅输出路径与行号，不输出值；命中项核对为受控测试配置，未确认真实硬编码凭据。此项不等于完整安全审计。
5. 所有问题按下表列证据；没有引用证据的代码不判为死代码，业务 bug 不混入行为保持重构。

## 问题清单

| ID／维度 | 基线位置与证据 | 问题／风险 | 建议与预估范围 |
| --- | --- | --- | --- |
| R01 死代码候选 | `backend/agent/learning_service.py:6` 的 `select_practice`、`recommendation_feedback.py:1` 的 `clone`、`review_service.py:1` 的 `SHANGHAI`；AST 中未出现对应 Load；`rg -n 'select_practice\|SHANGHAI\|clone' backend tests tests_python scripts -g '*.py'` 核对调用来源 | 低。存在未使用导入，但模块属性可能作为隐式导出，静态搜索不能排除仓库外使用 | 不删除。后续明确导出边界再处理，约 3 个文件；`study.py:4` 的计划函数同样保留 |
| R02 历史契约候选 | `shared/contracts/platform.js:2` require Zod；`package.json:26` 无依赖；`rg -n 'contracts/platform\|shared/contracts/platform' frontend shared backend tests tests_python docs scripts README.md` 只发现历史说明、迁移脚本和静态访问拒绝测试；主页面 `frontend/index.html:15-53` 未加载它 | 低。当前无生产装载引用，单独执行需旧依赖，但属于历史契约，不能只据无调用删除 | 待确认文档归档政策；代码和文档约 2-4 文件，本轮保留，不新增 Zod |
| R03 重复平台 | `backend/app.py:22` 与 `backend/xueya/app.py:90`；`tests_python/test_http.py:5`、`test_platform.py:10` 直接导入前者；`docs/delivery/main-C-integration.md:22` 明确保留兼容工厂 | 中。两套 HTTP/数据库/MCP 适配增加维护成本，但仍有真实调用 | 不合并平台。后续先清点兼容消费者再设计，跨约 20 文件，高风险，不列入本轮 |
| R04 重复扫描／性能 | `backend/agent/concepts.py:70-75` 在每个输出节点内 `next` 扫描全部概念、筛选全部边，并再次扫描边；调用方为 `study_session.py:38`、`learning_ui_api.py:249` | 低。输出阶段约 O(V²+VE)，无需数据库查询也有重复工作 | 批次 2：仅用函数局部索引替代查找，保留输入、拓扑顺序、边顺序、重复边、返回引用和错误码；1 源文件＋专项测试 |
| R05 重复扫描／性能 | `backend/agent/learning_service.py:74` 对每个提交 ID 重建题目 ID 列表，`:78` 对每题 `next` 查作答；`http_handler.py:153` 和 `agent_interactions.py:135` 调用 `submit_quiz` | 低。题目与作答交叉扫描；幂等请求不能因优化被重新评分 | 批次 3：只索引通过验证的作答，错误检查在索引前保持原顺序；1 源文件＋专项测试 |
| R06 过长／职责混杂 | `backend/xueya/agent.py:264-471` `_learning_stream` 208 行；`learning_ui_api.py:113-333` dispatch 221 行，内部 execute 195 行；`app.py:90-365` 装配及路由 276 行 | 中。单函数串联路由、IO、预算、生成、取消、降级和持久化，拆分容易改变 await／清理时序 | 待办。先补断开、重启、错误事件轨迹，再讨论拆分，约 3-8 文件；本轮不整体重写 |
| R07 命名／可读性 | `backend/agent/assessment.py:7-21,49-52,60,88` 多条件长行；`:21` 单条评分要点验证难以核对短路顺序 | 中。错误优先级、bool 与 int 区分不易读，直接改写判断可能改变行为 | 批次 1：仅展开原表达式，不提取新抽象、不更名外部函数；通过 AST 等价检查；1 源文件＋专项测试 |
| R08 浏览器可读性 | `frontend/js/search-workspace.js:13` 单行 5634 字符，`library-workspace.js:22-23` 单行 3311／3653 字符；按逐行字符数统计 | 中。业务分派与 HTML 字符串密集，定位和审查困难 | 待办。浏览器保护网可运行后按单个函数整理；约 2-4 文件，不能以格式化代替 XSS 证明 |
| R09 魔法常量／重复格式 | `backend/agent/question_service.py:82` 的探索比例 `.7`；`answer_policy.py:33` 与 `answer_service.py:31` 均生成引用编号，空格、推理标签和省略行为不同 | 低。配置意图不明显；相近生成逻辑不能直接合并 | 保留既定比例和两种格式。未来补算法依据与协议快照，约 2-3 文件，不改配置格式 |
| R10 错误处理可观察性 | `backend/xueya/gateway.py:101-102` 忽略取消钩子 Exception；`rag_service.py:208-209,333-334` 捕获 AppError 后跳过来源；后者附近向量与重排失败另有 warnings | 中。清理／坏来源原因对诊断不可见；不能把所有空 except 都认定 bug，`run_service.py:93` 是取消清理 | 待办。需确定日志渠道与用户警告是否属于接口变化，约 2 源文件＋故障测试 |
| R11 模型错误形状 bug | `backend/agent/answer_service.py:23-24` parse 后立即 `.get`；受控模型返回 JSON `[]`，实测 `AttributeError: 'list' object has no attribute 'get'` | 中。合法 JSON 但错误结构绕过 DomainError；`http_handler.py:83-85` 未捕获 AttributeError | 待办。增加对象校验会把现有异常／可能的 HTTP 500 改成领域错误，属于 bug 修复，不能混入本轮；约 1-3 文件 |
| R12 评分要点结构 bug | `backend/agent/assessment.py:21` 对 rubric 每项直接 `.get`；传入 `rubric=['bad']`，实测 `AttributeError: 'str' object has no attribute 'get'` | 中。字段结构校验不完整，可能绕过领域错误返回 | 待办。补对象校验及 HTTP 错误映射会改变当前错误行为，约 1-3 文件；批次 1 不修复它 |
| R13 工程配置 | `pytest.ini:2-5` 与 `pyproject.toml:15-19` 重复测试配置；`package.json:26` 未声明浏览器依赖，而三套 e2e 第 1-2 行均 require Playwright；`.github/workflows/quality.yml:31-36` 无独立 lint／类型检查 | 中（浏览器环境）／低（配置重复）。浏览器基线无法运行，测试配置可能漂移 | 待办。安装／声明依赖和选择配置入口均需单独工程变更；约 3-5 文件，本轮不新增依赖 |
| R14 测试缺口 | `tests_python/test_domain.py:91-107` 仅对路径顺序／拒绝先修局部断言；`:144-146` 只验证典型提交和幂等 | 中。没有锁定完整路径输出、边重复顺序、缺答、乱序响应、错误优先级与旧评分快照 | 本轮三批分别增加行为测试，保留原测试不改；新增 Python 测试文件，不增加框架 |
| R15 评测复现性（执行中追加） | `rag_service.py:87` 每次上传生成随机文档 UUID；`rag_parse.py:247-248` 将文档 ID 纳入片段 ID；`rag_search.py:46,64,73` 同分按片段 ID 排序。同一未修改实现独立重跑，structured-lexical 46 问中 16 问 returned 不同 | 中。不同临时导入的同分尾部证据不完全一致；不能对两次独立导入直接断言片段逐字等价 | 单列 B/F 待办，不修改检索顺序／测试。固定输入的新旧 C 实现精确比较负责验证本轮行为等价；检索评测保留原指标和返回片段记录 |
| R16 异步资源警告（执行中追加） | 最后一批首次完整 pytest 在 `tests/python/test_mcp_trace.py::test_dynamic_stream_exposes_arguments_before_observation_and_correlates_round` 报两条 PytestUnraisableExceptionWarning，涉及 ProactorSocketTransport／socket 的 ResourceWarning | 中。警告在垃圾回收时出现，报告所在测试／栈帧不能直接当作资源创建点，尚未确定来源或是否稳定复现 | 保留观察记录，不夹带清理代码修改。启用 `-W error::pytest.PytestUnraisableExceptionWarning` 后 MCP 专项 4 项与完整 547 项均通过，无警告；根因尚未定位，不宣称已修复 |

## 未确认为问题的检查

- 未确认没有调用者的业务函数、必定不可达业务分支或可直接移除的 Python 依赖；不因 AST 未引用就删除导入／文件。
- 顶层静态导入图无环；动态与延迟调用只作为待检查边界，不声称全局无环。
- `library_fetch.py:30-34,75-79` 已校验公开地址并固定连接地址，不能仅因存在 URL 导入就报告 SSRF；`:115-116` finally 关闭连接。
- `database.py:54-67` 同步事务明确不允许 await；`learning_integration.py:46-65` 虽调用 async 方法，当前 get_operation 本体无挂起 IO，未复现跨任务事务串扰，不做无依据改造。
- 未证实 N+1 数据库查询或真实凭据泄露；上述性能项指 Python 容器重复扫描。执行中出现 R16 未关闭异步资源警告，尚未定位创建点或确定是否为永久泄漏，不把垃圾回收报告位置直接判为根因。

## 收益／风险优先级与执行计划

1. **批次 1：测评校验可读性。** 先覆盖五种题型、空答案、错误优先级、bool/int、规范化去重、答案隐藏、人工评分与输入不变性，再仅展开 assessment 表达式；AST 必须与基线一致。独立提交，单独回滚。
2. **批次 2：路径构建索引。** 先记录完整输出与异常，覆盖目标顺序、重复边、候选边、拒绝节点、默认排序、输入／返回对象语义；保留拓扑算法，只替换输出阶段容器查找。独立提交，单独回滚。
3. **批次 3：测验作答索引。** 先覆盖乱序／遗漏作答、重复／未知题目、幂等冲突、旧题目快照、版本优先级和存储结果；索引不改变评分规则和事件顺序。独立提交，单独回滚。

每批执行完整 pytest、前端 42 项、pip check、MCP check、离线质量评测、内存 Python／JS 语法与 git diff --check；没有 lint／类型／构建入口不伪造通过。浏览器因缺依赖无法进入场景，保持阶段 0 的未验证状态；不修改浏览器相关源码。任何新增回归或行为差异即撤销该批源码修改并停止该批。

## 待办清单与需权衡的设计项

- R11、R12：真实错误处理缺陷，单独 bug 修复需明确同意错误码／状态码变化；不在行为保持重构中实施。
- R03：可选 A 保留兼容工厂（兼容最稳、维护重复）；B 冻结兼容工厂只接受修复（减少漂移、重复仍在）；C 迁移调用者后收敛（长期成本低、验证与迁移范围大）。本轮保持现状，未替用户决定迁移。
- R06：可选 A 保留主流程并增加局部私有函数（范围小、主函数仍长）；B 按路由拆分现有模块（职责清晰、跨模块改动大）。需先获得完整异步事件保护网，本轮不进行此设计决策。
- R01、R02：明确隐式导出／历史契约归档边界后再清理，不删除旧备份或迁移工具。
- R08、R10、R13：分别处理浏览器可读性、诊断日志策略、验证环境／配置归属，不能夹入 C 学习算法提交。
- 离线检索固定 43/46、结构化 40/46 的缺证据／遍历同义词案例，独立交 B/F 评测，不改黄金集迎合结果，不代发队友消息。

## 阶段 2 执行检查点

- 已将现有 `feat/large-C-agent-learning` 从祖先 `015b3d5` 正常快进到最新 main `01c98fd`，没有重置、强推或覆盖独有提交。
- 批次 1：新增 25 项特征测试在旧源码上全部通过；仅展开判断表达式，`ast.dump(ast.parse(...))` 与批次前完全相同。改后完整 pytest **520 passed / 90.46 秒**，前端 42 passed、pip check、MCP 4 工具／2 命中、Python 220／JS 56 文件语法和 diff --check 通过；离线检索仍为 43/46 与 40/46，分类通过数与基线一致。浏览器保持缺 Playwright 的基线限制；未改浏览器代码。
- 批次 2：11 项新特征测试在旧源码上通过，修改后路径／领域／跨语言专项 38 项通过；400 组固定随机种子的 DAG 完整输出与 main 旧实现一致且输入不变。500 节点合成星形图 7 轮中位耗时旧实现 27.142ms、索引实现 1.117ms，仅为本机合成微测量，不宣称真实课程延迟提升。
- 批次 2 额外逐条比较两次独立导入的检索片段时断言失败，立即撤回该批源码并告知用户。旧实现两次对照也有 16 个案例返回片段不同，定位为 R15；分类通过数／召回／排名／边界指标一致。没有修改原测试或评测脚本；复现证据保存于忽略目录 `test-results/refactor-batch2/control-a/`、`control-b/`。排除此次改动导致差异后恢复同一索引补丁，重新完整 pytest **531 passed / 88.36 秒**；前端 42 passed、pip、MCP、Python 221／JS 56 文件语法、diff --check 通过，检索质量仍为 43/46 与 40/46。不采用撤回期间那次测试作为最终结果。
- 批次 3：16 项新特征测试在旧源码上全部通过；缓存题目 ID 列表、索引已校验作答，保留按题目顺序生成事件、缺答、幂等短路及历史非可哈希题目 ID 的原查找行为。没有收紧既有题目 ID 校验；提交 ID 的成员校验仍沿用列表相等语义，不宣称整段验证降为线性复杂度。修改后提交／领域／HTTP／Agent 专项 44 项通过；200 组固定输入与 main 旧实现的完整输出、异常、存储、幂等回放全部一致。首次完整 pytest 547 passed / 91.36 秒，出现 R16 的两条警告，因此未直接收尾；随后完整严格警告检查 **547 passed / 87.59 秒，无警告**。前端 42、pip、MCP、Python 222／JS 56 文件语法、diff --check 通过，检索质量仍为 43/46 与 40/46。原测试／前端／shared 均无改动。
- 本轮未调用付费模型；当前验证以确定性行为和受控上游为准，非真实模型效果验收。

本轮三个计划批次均已完成，按顺序单独提交在 `feat/large-C-agent-learning`；批次 1 为 `e49578b`，批次 2 为 `bafc4b2`，批次 3 为本节所在提交。后续查看 `git log --oneline 01c98fd..HEAD` 获取完整列表。没有改公共接口、SQLite schema、配置格式、依赖、前端或原测试；没有合并 main 或推送远程。R01-R03、R06、R08-R13、R15-R16 作为已记录待办保留，不把本轮重构宣称为全仓库所有维护问题已消除。

## 验证命令与复核方式

解释器统一使用仓库 `.venv/Scripts/python.exe`，以下以 `python` 简写。正常本地权限执行测试；不安装依赖，不启动指向个人数据库的正式服务。

```powershell
python -B -m pytest -q -p no:cacheprovider
python -B -m pytest -q -p no:cacheprovider -W error::pytest.PytestUnraisableExceptionWarning
node scripts/test.js --frontend
python -B -m pip check
python -B -m backend.xueya.mcp_server --check
python -B -m scripts.check_quality --repeats 1 --output test-results/refactor-batch3/f-quality
git diff --check
```

新增特征测试分别为 `tests_python/test_assessment_characterization.py`（25 项）、`test_learning_path_characterization.py`（11 项）、`test_quiz_submission_characterization.py`（16 项），可单独运行；未改动原有测试。语法检查对 backend/scripts/tests/tests_python 的 Python 用内存 `ast.parse`，对 frontend/shared/scripts/tests 的 JS 用 `node --check`，不生成 pyc。批次 1 另外读取 `git show 01c98fd:backend/agent/assessment.py` 比较 AST，确认表达式和求值顺序不变。

400 组路径对照及 200 组提交对照是一次性本地诊断：从 `git show 01c98fd:...` 读取旧模块，在独立命名空间装载，随机种子 `20261025`；不将复制的旧实现加入生产代码或永久测试。路径生成 1-24 节点 DAG，混合 confirmed/candidate、prerequisite/related 边、显式／默认目标和掌握估计，比较完整返回与输入不变性。提交生成 1-59 题、乱序／遗漏答案及重复／未知 ID、版本冲突，比较返回或异常以及仓库、操作回执、历史和重放。永久特征测试保留可复核的明确行为断言，避免只复制当前实现。

浏览器交互仍未实测：三套现有 JS e2e 因缺 Playwright 无法启动。之后环境就绪应运行 README 中的三套回归；C 手动复核应覆盖学习路径的目标与先修顺序、测验跳题／乱序作答后的判分和再次提交、主观题订正使用原量规。该手动流程未执行，不以 HTTP 回归替代浏览器验收结论。当前提交仅改 C 的三个 Python 源文件，没有页面或浏览器服务改动。
