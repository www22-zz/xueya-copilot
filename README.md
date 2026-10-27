# 学涯 Copilot

基于课程资料的本地学习助手，提供知识库、有据问答、资料阅读、练习与错题，以及学习计划和复习服务。

前端使用 HTML/CSS/JavaScript，后端使用 Python/FastAPI。所有 AI 推理只调用外部 API，不安装本地模型或 GPU/CUDA 环境。

## 启动

Windows 双击根目录的 **启动学涯.cmd**，或安装 Python 3.11+ 后在项目根目录运行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
.venv/Scripts/python.exe -m backend.xueya.cli doctor
.venv/Scripts/python.exe -m backend.xueya.server
```

打开 [本机学习空间](http://127.0.0.1:4173/)。也可用 `scripts/start.ps1` 自动准备环境；macOS/Linux 的解释器路径为 `.venv/bin/python`。已有 npm 时，`npm start` 同样启动 Python 服务，后端不需要 Node.js。

配置模板为 `.env.example`，真实密钥写入本机 `.env`。停止服务运行 `.venv/Scripts/python.exe -m backend.xueya.cli stop`，或 `scripts/stop.ps1`。更新时保留 `.env`、原数据目录和访问地址；数据库升级与恢复见 [平台指南](docs/platform-guide.md)。

## 使用

1. 从首页进入学习空间，选择课程。
2. 在“知识库”导入或查看资料、处理状态和原文；选定问答使用的资料范围。
3. 在资料问答中输入问题，可附图片或语音，核对回答的原文引用。模型未配置或生成失败时，按实际能力提示或回退原文摘录。
4. 使用练习与错题页完成题目、查看解析并记录复习；服务端高级学习能力按实际入口和配置开放。
5. 在设置中查看本机团队账号、任务、用量和服务数据。团队账号共享同一本机服务，不跨电脑自动同步。

新数据目录首次启动会自动准备仓库内 17 份数据结构课件；进入知识库查看进度。已有资料历史的目录不会重复导入，可用 `XUEYA_AUTO_IMPORT_DEMO=0` 关闭。课件、图片补录及手动导入见 [共享资料包](materials/data-structures-algorithms/README.md)。私人数据库不随 Git 同步。

知识库支持最大64MiB的PDF；扫描教材须先完成文字识别，之后才能预览并确认替换旧PPT资料。OCR每次仅处理显式选择的一批，不会自动调用整本教材；未配置服务时显示待识别。接口、当前扫描教材准备状态及限制见 [PDF教材换库](docs/contracts/pdf-knowledge.md)。

## 验证

```powershell
.venv/Scripts/python.exe -m pytest -q
node scripts/test.js --frontend
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -m backend.xueya.mcp_server --check
.venv/Scripts/python.exe -m scripts.check_quality --repeats 1
```

Node.js 20+ 用于前端回归。可选浏览器检查为 `node tests/e2e/browser.js`、`workspace.js`、`platform.js`，需要 Playwright 和浏览器，可设置 `CHROME_PATH`。测试使用临时数据库及受控上游，不等于真实模型质量验收。生成文件统一位于被 Git 忽略的 `test-results/`。

## 目录

| 目录 | 最终交付用途 |
| --- | --- |
| `frontend/`、`shared/` | 页面、浏览器状态、客户端、离线规则与静态资源 |
| `backend/xueya/` | 统一宿主、HTTP/SSE、SQLite、作业、RAG、MCP、模型账本与接入层 |
| `backend/agent/`、`backend/providers/` | 学习领域、证据校验、复习计划、多模态与外部 API 适配 |
| 其他 `backend/` 模块 | 仍被专项测试使用的兼容实现，不是第二个生产入口 |
| `scripts/` | 启动、导入、维护和可复用验收工具 |
| `tests/`、`tests_python/`、`evals/` | 回归测试、测试夹具、固定评测集及研究基线结果 |
| `materials/`、`demo/` | 共享课程和演示资料 |
| `docs/` | 最终操作指南、接口契约、技术报告与交付说明 |

## 文档

- [最终交付说明与已知限制](docs/delivery/FINAL-DELIVERY.md)
- [技术报告](docs/reports/学涯Copilot技术报告.md) · [演示与验收指南](docs/demo/演示与验收指南.md)
- [HTTP/SSE 契约](docs/api-contracts.md) · [学习服务契约](docs/contracts/learning-services.md)
- [平台运维](docs/platform-guide.md) · [账号契约](docs/contracts/local-account.md)
- [资料与工作台](docs/contracts/workbench-library.md) · [知识库](docs/contracts/knowledge-base.md)
- [Agent 使用](docs/agent-mcp-guide.md) · [MCP 开发](docs/mcp-platform.md) · [RAG 接入](docs/rag-integration.md)
- [高级学习说明](docs/C-learning-user-guide.md) · [录音与复习音频](docs/G5-media-user-guide.md)
- [产品约束](docs/requirements.md) · [原创验收集](evals/acceptance/README.md)

## 数据与能力边界

服务默认只监听本机，持久数据位于 `.xueya-data/`。密钥仅由后端读取；选定资料和近期上下文可能发送至配置的外部服务。付费请求结果未知时不自动重放，Token 用量不是实际账单。

资料不足不伪造证据；流式增量不是正式完成结果，只有通过最终校验的 `done` 可保存。OCR、向量、重排、图像和语音能力按配置开放。视频分析只覆盖实际采样帧。受控测试、合成实验和共享课件补录不代表真实模型质量或学习收益已经验收。

教材PDF已整理为[逐页OCR资料包](materials/data-structures-textbook/README.md)，可导入已有课程并显式替换旧PPT；实际能力、私人历史保护与验证见[PDF换库说明](docs/contracts/pdf-knowledge.md)。
