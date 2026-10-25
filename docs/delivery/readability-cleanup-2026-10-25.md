# 可读性整理：缩进、长行与嵌套

本轮基线：`9715626`，工作分支 `feat/large-C-agent-learning`。远程 main 仍为 `01c98fd`，本地已有三批行为保持重构，没有未提交用户工作。

用户要求继续改善代码可读性和维护性。沿用此前红线：不改外部行为、接口、数据结构、配置格式和原测试；不新增框架、依赖或业务抽象层，不夹带修复审计待办。

## 范围与顺序

1. 前端搜索／资料库／工作台纯排版：`frontend/js/search-workspace.js`、`library-workspace.js`、`workbench-ui.js`。统一两空格缩进，拆开连写语句、对象字段、异常处理和回调；保留全部字符串、模板、正则和表达式。基线分别仅 28、30、17 行，多个业务函数挤在一行。
2. C 学习模块纯排版：优先学习服务、计划和运行状态机。Python 使用四空格缩进，展开长参数、校验、字典和嵌套条件表达式，纯排版须保持 Python AST 完全一致。
3. 对已覆盖行为的延期与恢复分支使用提前返回／跳过，减少嵌套。先在旧实现运行特征测试，再改控制流，验证输出、异常、持久化和异步顺序。

每批单独验证、提交。生产格式化依赖未增加；一次性本地排版辅助仅在 Git 忽略的 test-results 下，不进入后端或发布内容。JS 通过当前 Node 自带解析器比较 AST（忽略位置），模板原始文本、字面量与运算结构仍须相同。Python 用标准库 AST 比较。

## 验证与限制

- 基线完整严格 pytest：547 passed；前端 42 passed；前轮检索质量为固定 43/46、结构化 40/46，存在已记录的随机 UUID 同分排序差异。
- 三套浏览器检查仍缺 Playwright；本轮不新增依赖。前端排版只能报告语法树等价与自动回归，不能声称完成实际浏览器验收。
- 独立 lint／类型检查／构建入口未配置，不将语法检查当作这些检查。
- 纯排版不补镜像实现测试；复用既有行为与契约保护网，并以 AST 等价证明仅排版。控制流改动补充有实际业务断言的测试。

## 执行记录

- 第一批改前：前端契约／搜索／工作台／资料库专项 37 passed；前端 42 passed。三模块排版后分别为 262、474、169 行，均保持 AST 完全一致；前端 42 passed。完整严格 Python 回归 **547 passed / 88.31 秒，无警告**；git diff --check 通过。包含 HTML 的长模板保留原文字节，不通过插入空白改变页面文本／DOM；控制代码已拆开。
- 第二批：学习服务、计划、运行状态机、概念图与 Agent 编排五模块统一四空格缩进，展开长参数／校验／字典／条件表达式；构造函数参数和多项初始化独立成行。五文件 AST 与 `9715626` 完全相同；改前学习专项 85 passed，改后完整严格 pytest **547 passed / 90.38 秒，无警告**、前端 42 passed、diff --check 通过。现有两处关键取消／快照注释改为中文，内容语义保留。
- 第三批改前：新增 20 项计划动作、运行恢复、Agent HTTP/SSE 完成分支特征测试全部通过；没有修改旧测试。改后相关专项 88 passed。
- 第三批改动：完成／跳过计划后提前返回，延期处理不再包在 else 中；查找任务时跳过不匹配项；运行恢复跳过已完成步骤和非等待步骤；学习路径理由采用 if/elif 顺序分支；Agent 成功终止路径返回后再顺序处理尚未满足的完成条件。保留原检查点保存、错误与取消处理、共同轮次收尾和结果事件顺序。
- 可核对的嵌套变化：按函数 AST 中 if 的嵌套深度统计（不计循环层数），`planning.revise_plan` 为 **2 → 1**，`RunService.resume` 为 **3 → 1**。Agent 的拒绝完成处理少一层缩进；不宣称整个 Agent 已拆成短函数。
- 从 `git show 9715626:...` 装载旧函数，随机种子 20261025，计划动作与运行恢复分别 250 组输入比较全部通过，比较完整结果／异常、输入不变性、仓库存储和快照验证顺序。除此四个函数外，四模块其他函数和签名 AST 仍与本轮基线一致；学习服务整模块 AST 一致。
- 最终完整严格 Python 回归 **567 passed / 90.15 秒，无警告**（原 547＋新增 20）；前端 42 passed，pip check、MCP（4 工具／2 命中）、Python 224／JS 56 文件语法检查、diff --check 通过。离线检索仍为固定 43/46、结构化 40/46；没有修改检索或模型行为，没有调用付费 API。

## 可复核命令

```powershell
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider -W error::pytest.PytestUnraisableExceptionWarning
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests_python/test_readability_branches.py tests/python/test_agent_finish_readability.py
node scripts/test.js --frontend
.venv/Scripts/python.exe -B -m pip check
.venv/Scripts/python.exe -B -m backend.xueya.mcp_server --check
.venv/Scripts/python.exe -B -m scripts.check_quality --repeats 1 --output test-results/readability/f-quality
git diff --check
```

前端三个文件的 AST 比较保留字面量 raw、模板 raw/cooked、运算符和表达式顺序，只忽略解析器的位置字段；不是仅对比去空白后的字符串。后端第二批采用 `ast.dump(ast.parse(source))` 全模块比较，原注释保留或就地翻译为中文。一次性随机对照不将旧生产实现复制进永久测试。

本轮三个计划批次全部完成：`9f75ae2`（前端排版）、`ccfb37f`（Python 排版），第三批为本节所在提交（减少嵌套与 20 项特征测试），可用 `git log --oneline 9715626..HEAD` 核对。一次性本地排版辅助文件已删除，未进入交付。未推送、未合并 main。前轮审计的业务错误处理、兼容平台、检索排序、资源警告等待办没有夹带修改；长 HTML 模板原文和部分复杂业务函数仍保留，不能把本轮整理称为整个项目所有维护问题已消除。
