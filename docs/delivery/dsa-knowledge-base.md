# 数据结构与算法知识库

2026-10-22，从最新 main `76c41c2` 建立 `codex/dsa-knowledge-base`；原工作区干净。目标：复用已合并 B/G2/G3/G4，建立真实课件知识库及简洁前端入口，提交 PR 待负责人审核。

## 进度

- 已核查 AGENTS、README、派工说明、AE 历史审计和现有代码；实际 main 已包含 G1～G5、导航/历史调整。
- 材料：指定目录 17 份 PPTX、5 份 Office 临时锁文件，原始文件不修改。
- 已发布[兼容接口定义](../contracts/knowledge-base.md)。无新数据库、模型、依赖或迁移；未联系队友。
- 已实现独立接口、知识库入口、目录/章节筛选、处理进度/取消/CPU 重试、原文/原件、检索/真实引用、选定资料转现有问答。外部 API 逐次确认，不自动付费重试；PPT 图示与 PDF OCR 的能力边界明确。
- 新导入工具支持不同客户端重复导入去重、跳过锁文件、输出本机 manifest。PPT 同页段落合并保留精确偏移、页码和表格边界。
- 已安全停止旧服务并用当前任务代码重启，原数据预先一致性备份至本机忽略目录 `.xueya-backups/before-dsa-knowledge-20261022`。原默认课程与私人数据保留。
- 已在实际主服务的现有数据库中创建“数据结构与算法”，courseId `kb-0423d84c6cf4f7e2c0a51d77a11d2b26`。导入原目录全部 17 份正式 PPTX，跳过 5 个锁文件；原件总计 44,433,210 字节，1112 页、204,194 个正文字符、1210 个片段。原件没有进入 Git。
- 9 个主题词法冒烟查询各返回 8 条依据，72 条引用全部通过原 RAG validate（课程、内容版本、hash、偏移及原文摘录）。属于作者冒烟验收，不能作为独立相关性准确率或真实模型质量评测。
- 3 份课件标记 OCR_REQUIRED，合计 7 个空文本页；268 页包含图片，仅文本框内容被提取，图示/图片/动画的含义没有自动理解。图示请下载原件核对，必要时先转 PDF 再另行 OCR；本轮无付费预算，不调用外部 OCR。

## 验证与未完成

最终 `python -m pytest -q`：**343 passed，114.79 秒，无失败/警告/跳过**，包含 9 项知识库专项。前端原有 `npm run test:frontend`：**41 passed**；B/知识库中期专项 36 项通过，随后新 PPT 上下文测试也已纳入最终全量。

实际 Chrome 最终 **18 项流程检查通过**，使用临时数据库和真实 17 份课件；覆盖创建/上传/去重/检索/实际页码阅读/刷新/课程隔离/问答范围完整文档列表/桌面/390px/手机检索跳转/深色主题，期间 invocations 表为空。MCP 官方 stdio（tools=4，matched=2）、pip check、compileall 和 git diff --check 通过。

旧三套 Node 浏览器脚本仍保留，并实际尝试运行。初次缺少本仓库 Playwright，随后通过桌面自带 NODE_PATH/CHROME_PATH 执行，无安装依赖：

| 脚本 | 当前分支 | 未修改 main `76c41c2` 快照 |
| --- | --- | --- |
| test:browser | browser.js:55，已折叠 `#documentList` 的 innerText 为空 | 相同位置和断言失败 |
| test:workspace | workspace.js:33，已折叠旧资料行不可见 | 相同位置和可见性等待失败 |
| test:platform | platform.js:11，设置中 `#platformData` 尚未展开 | 相同位置和可见性等待失败 |

以上是主线现有导航调整后的旧脚本适配问题，本任务不通过展开所有产品界面或删除旧检查掩盖它们。独立主线快照保存在忽略目录 `test-results/knowledge-base/main-baseline`，所有复现使用临时数据库。本 PR 的 Python Chrome 脚本按实际当前界面完成验收，但不能宣称三套旧浏览器全通过。

本机原始证据：`test-results/knowledge-base/import.json`，隔离 Chrome 的 `test-results/knowledge-base/browser/report.json`、`real-import.json` 和截图。真实课件与库只在本机；PR 不会让其他电脑自动获得课件。负责人可运行导入工具导入其有权使用的材料。

重复导入再次验证：相同 courseId、17 个 documentId 和 jobId 均保持不变，仍是 17 份/1210 片段，没有追加解析修订；见本机 `repeat-import.json`。实际主服务检查：OCR/Embedding/Rerank 均未配置，课程真实 API 调用 0，词法检索可用。

已分阶段提交并推送 `codex/dsa-knowledge-base`：`e316981` 后端/导入/PPT 上下文，`93daafb` 前端/实际课程验收。PR：[#13](https://github.com/www22-zz/xueya-copilot/pull/13)，目标 main，等待负责人审核，未自行合并。

主服务已用最终代码重启并再次读取实际库：17 份/1210 片段/0 处理中/3 份需核对，最短路径查询返回 8 条，课程 invocations 仍为 0。当前任务没有剩余实现阻塞；上述模型配置、图示核对与主线旧脚本适配限制保留给负责人评估。
不进行未授权付费 API 测试；不能用软件适配测试冒充真实向量/OCR 效果。PPT 图示/图片中的文字需核对原件，普通文本解析不承诺理解图示。

## 使用

1. 运行根目录 `启动学涯.cmd`，打开 `http://127.0.0.1:4173/#space/knowledge`。
2. 在知识库下拉选择“数据结构与算法”；也可新建独立课程知识库。上方可批量上传课件，留空章节会按文件名中的章/周标识整理。
3. 查看资料处理状态，按章节筛选；右侧输入问题检索免费原文，再点击“核对原文”查看实际页码/上下文。手机顶部“检索原文”直达搜索区。
4. “用于问答”带着该资料范围进入既有问答；笔记/练习/模板/统一搜索仍使用同一课程与来源版本。阅读历史/纠错/归档由原“资料”页面管理。
5. 本机重新导入：`python -m scripts.import_knowledge_base --directory <自己的课件目录> --name 数据结构与算法`。先启动主服务；既有课程可指定 `--existing-course-id`。不会请求任意服务器路径，浏览器只能上传显式选择的文件。
