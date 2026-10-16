# 本地平台运行、迁移和恢复

当前AI架构为**永久只调用外部API**，见[当前产品约束](requirements.md)。需要Python 3.11+，不需要GPU、CUDA或本地模型。普通TXT/MD/PDF/DOCX解析在有界、可终止的Python子进程中进行；扫描件OCR等新能力需由B/C接入实际API，当前不会伪造解析成功。

## 启动

安装Python **3.11或更新版本**，进入项目根目录：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
.venv/Scripts/python.exe -m backend.xueya.cli doctor
.venv/Scripts/python.exe -m backend.xueya.server
```

也可运行`scripts/start.ps1`。后端运行不需要Node；安装了npm仍可用`npm start`调用Python。访问`http://127.0.0.1:4173`，只监听本机。原JS后端已移除，不能再运行旧命令。macOS/Linux用`.venv/bin/python`。

从旧版本切换前先安全停止旧服务、备份；保留原数据目录、.env和访问地址。Python直接兼容SQLite v3和workspace v3，不清空浏览器存储；详见[迁移记录](delivery/python-backend-migration.md)。

`.env.example`列出MiMo、工具超时、API并发和数据目录选项。真实`.env`不提交。`API_MAX_CONCURRENT=2`是所有模型调用共用的默认并发许可；普通解析CPU并发2。API忙时明确失败/回退，不建立无界等待队列。

默认`.xueya-data/`（Git忽略）包含：

```text
workspace.sqlite        # SQLite WAL数据库，迁移版本当前3
workspace.sqlite-wal    # 运行期间的WAL，不能随意删
workspace.sqlite-shm
files/ab/<sha256>       # 原件，内容寻址，显示名称单独存数据库
server.json            # 当前实例/PID/停止凭据，禁止分享
```

可用`XUEYA_DATA_DIR`指向其他绝对目录。一个数据目录只运行一个服务器；PID存活则拒绝重复启动。端口占用时关闭原实例或修改PORT，不要强杀未知程序。

停止：

```powershell
.venv/Scripts/python.exe -m backend.xueya.cli stop
```

或`scripts/stop.ps1`。停止命令校验实例ID及本地停止凭据，停止接单、取消活动作业、关闭数据库，不按模糊进程名称杀其他程序。

## 迁移已有浏览器数据

1. 在原来使用项目的浏览器/地址打开学习空间，点击右上角**本地数据**。
2. 先点**导出浏览器备份**，保留下载的JSON。
3. 点**预览迁移到本地服务**，核对课程、资料、完整对话、作答、笔记数量。服务已有数据时会提示替换并保留旧版本备份。
4. 点**确认迁移并启用同步**。服务端保存原始输入、旧服务快照和导入hash；原浏览器localStorage不清空。当前IndexedDB中找得到的原件会复制到本机文件库，找不到的明确提示重新上传。
5. 后续修改先保留浏览器副本及待同步数据，约400ms后CAS写入服务端。刷新/重启仍保留；版本冲突不会自动覆盖。

当前支持workspace v3及经A存储适配器读入的旧v2/v1。保留完整现存数据，不再为持久化截成24条消息/300条记录；**已经被旧版本删除且没有备份的历史不能恢复**。模型请求的有界上下文不等于数据库删除历史。

直接双击HTML时没有API调用，仍保留浏览器模式；另一个浏览器或另一个端口是不同localStorage来源。新浏览器连接同一本机服务时，可点**使用服务端版本**，该操作先下载当前浏览器备份，再采用服务快照。恢复流程不会被旧页面beforeunload写回旧数据覆盖。

如有冲突，先导出浏览器备份，再明确选择服务端版本，或重新预览迁移浏览器版本。不要手动删除localStorage“解决冲突”。

## 资料和后台作业

新上传TXT/MD（1MiB）和PDF/DOCX（10MiB）通过A适配器进入E文件仓库，调用现有B解析/分段服务。原件和解析作业、进度、检查点、正文引用都持久化；同一个幂等键不能用于不同内容。新版本保留独立ID，旧版不参与检索，引用快照仍可核对。

在本地数据面板查看作业、取消或重试。扫描件未接OCR时会保留原件并明确处理失败；不生成虚假正文。删除资料采用可恢复软删除，移出活动资料和索引，原件/修订暂留恢复用；不是物理销毁承诺。

队列状态：queued/running/cancelling/succeeded/failed/cancelled/unknown。CPU失败按上限重试；租约到期能从检查点重新排队。业务写入必须使用`commit(fn)`验证当前租约/取消状态，过期Worker不能提交。默认作业90秒超时；不合作的处理器仍占许可，停止时报告WORKERS_NOT_STOPPED，不假装清理成功。

资源只有`cpu`和`api`。外部API结果不明会进入unknown，**不自动重试，也不允许普通手动重试按钮重放**；先核对服务商请求/计费记录。E不提供本地模型Worker，B/C注入服务端API适配器即可。

## MCP与现有业务接线

启用浏览器数据同步前保留原四工具流程。同步后，现有Python Agent从SQLite读取当前课程资料/题目/作答，经过D真实SDK工具验证引用，并保存Run/Checkpoint和模型调用状态。旧`/api/ai`、流式接口、出题、知识点、解析接口仍在；公共模型适配器统一取得API许可和调用日志。

模型调用日志只存范围、请求摘要、状态、时间和服务商返回的usage，不存密钥或完整Prompt。成功/未知状态和billing_status不同；**Token用量不是实际账单金额**，服务商未报告费用时显示未报告，不猜价格。重启时未完成调用标记unknown，未完成Run标记interrupted，不自动重新扣费请求。

本地数据面板提供笔记“生成写入预览→确认保存”流程，真实调用D的prepare/confirm/apply并以SQLite事务保存实体、审计、幂等receipt，采用服务端版本后可在A笔记页看到结果。题目/计划使用同一D/E事务端口，C/A后续可增加对应交互。

概念/先修、OCR、向量/重排、音视频等新业务未因E底座接通而自动实现，仍由B/C完成实际API适配及算法。E不重复实现另一套学习算法。

## API入口

同源`GET /api/platform/bootstrap`返回本地会话nonce、workspace版本、课程、作业和资源状态。后续平台请求带`X-Xueya-Token`；Host与Origin受限本机。这里只是个人本机宿主，不是多人账号系统，不应反代为公网服务。

| 入口 | 用途 |
| --- | --- |
| GET/PUT `/workspace` | 完整快照读取/CAS保存 |
| POST `/migration/preview`、`/migration/apply` | 预览并确认导入；保留raw和旧快照 |
| GET `/migration/backup?id=...` | 获取当次导入备份用于核对/回退 |
| POST `/courses` | 本地用户课程创建、名称与归档 |
| POST `/documents/upload` | 二进制上传，Idempotency-Key必填 |
| POST `/documents/import-original` | 为已迁移资料绑定原件，不更换来源ID |
| GET `/documents`、`/documents/original` | 资料列表、原件下载 |
| POST `/documents/update`、`/documents/remove` | 元数据CAS更新、软删除及索引失效 |
| GET/POST `/jobs` | 作业列表与已注册类型提交 |
| GET `/jobs/status`、`/jobs/events` | 状态与可恢复SSE；Last-Event-ID/after |
| POST `/jobs/cancel`、`/jobs/retry` | 取消/有条件重试 |
| GET `/tools`、POST `/tools/call` | D工具发现与调用 |
| POST `/actions/confirm`、`/actions/cancel` | 宿主明确确认/取消；不属于模型工具 |
| GET `/entities`、`/audit`、`/invocations` | 按课程查询实体、审计和API调用/用量状态 |

以上路径前缀均为`/api/platform`。具体注入契约见[phase1](contracts/phase1.md)及[MCP指南](mcp-platform.md)。服务端SQLite事务仅接同步回调，异步API/解析必须在事务外执行。

## 备份、恢复和迁移回退

```powershell
.venv/Scripts/python.exe -m backend.xueya.cli backup C:/Backups/xueya-20261016
.venv/Scripts/python.exe -m backend.xueya.cli restore C:/Backups/xueya-20261016 C:/XueyaRestored
```

备份使用SQLite官方backup API生成一致数据库快照，再复制不可变原件、记录SHA256 manifest，不直接复制正在变化的sqlite主文件。[Python SQLite备份接口](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup)、[SQLite备份说明](https://www.sqlite.org/howtocorrupt.html)。

恢复先校验manifest、路径、每个文件hash及SQLite integrity_check，写入**全新目录**后原子改名，拒绝覆盖现有目标。然后停止原实例，在`.env`将XUEYA_DATA_DIR切换到新目录并启动；核对课程、资料原件和记录数量。不要同时打开旧/新服务编辑同一份学习状态。

浏览器导入备份可通过migration/backup端口下载。要回退导入，可把备份中的previous.data或原workspace交回预览/确认流程，仍使用当前CAS版本；完整灾难恢复优先用已验证的目录备份。

```powershell
.venv/Scripts/python.exe -m backend.xueya.cli export C:/Backups/xueya-workspace.json
.venv/Scripts/python.exe -m backend.xueya.cli gc
.venv/Scripts/python.exe -m backend.xueya.cli gc --apply
```

export输出快照；原件与全量数据库恢复请用backup。gc默认仅列出完全未被任何资料修订引用的孤立文件；`--apply`才物理删除这些孤立项。软删除资料仍被修订引用，因此不会被gc误删。当前没有自动销毁私人历史/原件的策略。

数据库迁移当前1→2→3，升级事务化，拒绝打开比应用更新的user_version。不做破坏式SQL降级，回退应用时从升级前备份恢复到新目录。

## 验证和已知边界

```powershell
.venv/Scripts/python.exe -m pytest -q
npm run test:frontend
node tests/e2e/browser.js
node tests/e2e/workspace.js
node tests/e2e/platform.js
```

浏览器测试需要Playwright和Chrome，可设置CHROME_PATH；专项测试使用临时目录，既不改用户数据库也不调用付费API。`python -m backend.xueya.cli doctor`只报告配置存在性，不输出密钥，也不把有配置等同于付费API成功。

SQLite是单机默认产品，不依赖PostgreSQL/pgvector。向量索引由B接入，PostgreSQL迁移方案见公共契约；多机/多人账号、云同步、远程OAuth和大规模检索不是当前已验收能力。E已为D注入SQLite确认状态：预览/确认跨重启保留，但仍受原TTL约束；执行中断先查幂等receipt，查不到即uncertain，不重放写入。正式写入确认始终依赖SQLite；独立只读Registry不需要确认仓库。持久化业务Run不代表能自动重放付费模型调用。
