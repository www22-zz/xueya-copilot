> 当前状态补充（2026-10-17）：默认 Python 宿主的 A～E 接线、修复与剩余工作以 [整体验收记录](AE-integration-audit.md) 为准。下文保留原阶段证据。

> 历史记录：本文件保留当时的实现与验收证据。当前后端已迁移Python/FastAPI，启动和派工以[README](../../README.md)、[当前需求](../requirements.md)及[Python迁移记录](../delivery/python-backend-migration.md)为准；旧Node命令不再作为开发要求。

# 大任务E交付记录：本地工程底座与集成

日期2026-10-16，分支`feat/large-E-platform`；起点main `0a16b0e`。已合入A `466893a`、D `008847c`，不合并main，不覆盖其他任务分支。状态：**E底座与现有模块集成完成，待负责人/F验收；B/C后续新增业务继续按契约接入。**

## 已确认的产品决定

用户明确要求永久仅调用AI API。因此本次移除了GPU探测、模型常驻/显存调度和Python推理Worker方案；保留普通Node文件解析、SQLite和业务规则。向六份任务单、长计划及README发布[当前产品约束](../requirements.md)，旧本地模型候选不再是开发要求。

默认存储冻结为Node24.4+内置SQLite，WAL/FULL同步，内容寻址原件库。本机实际Node24.19.0/SQLite3.53.3可用，PostgreSQL/psql/Docker未安装。未同时造两套数据库；后续PostgreSQL迁移保持同一仓库接口并核对ID、版本和数据hash，不默默切换运行产品。向量检索由B选用API并实现索引服务，E不伪称已有pgvector或向量效果。

使用/迁移/恢复见[本地平台指南](../platform-guide.md)，接口见[公共契约v1.0](../contracts/phase1.md)。数据库迁移版本当前3，接口版本与数据库版本不同。

## 内部里程碑

| 部分 | 实现与实际接线 |
| --- | --- |
| 公共契约 | scope、稳定ID、实体/版本/UTC时间、错误、分页、workspace、作业schema；校验重复课程及有效活动课程 |
| SQLite仓库 | 课程隔离、实体/修订、快照、导入备份、作业/事件、Run/Checkpoint、API调用、确认/审计/receipt；同步事务和嵌套savepoint，CAS更新 |
| 文件生命周期 | SHA256内容寻址、原子写入/fsync、hash核对、类型/体积/路径限制；新版本独立ID，软删除退出检索，修订及原件留恢复用；孤立文件GC默认dry-run |
| 浏览器迁移 | 预览统计、显式确认、原始数据/旧服务快照备份、hash幂等、40条对话/400条作答保留验证；可用IndexedDB原件复制，缺失原件明确提示 |
| 前端同步 | A接口接真实HTTP；上传、资料状态、整理/删除、原件下载；400ms同步、持久待发送副本、CAS冲突停止覆盖、明确恢复选择 |
| 持久化作业 | 队列、进度、检查点、幂等、租约/heartbeat、重试、取消、SSE序号恢复、超时与重启恢复；ctx.commit校验租约与取消 |
| 普通CPU解析 | 有界Node Worker线程调用现有B解析/分段，避免阻塞HTTP；128MiB线程堆限制，取消后terminate；不属于本地AI推理 |
| 外部API治理 | 默认2个API并发许可，旧/新模型路径统一适配；请求摘要、状态、usage及billing状态记录；未知付费结果不自动重试，重启不自动重放 |
| D真实写入 | 实际D SDK prepare/confirm/apply连接E事务库和A确认面板；笔记可见，题目/计划也有同一事务及A快照适配；D Map端口注入SQLite确认store |
| 确认恢复 | 预览/确认跨重启保留且原TTL不延长；执行中断先查receipt，有收据恢复applied，无收据保持uncertain，不猜测成功、不重放 |
| Agent接线 | 迁移前兼容原四工具；迁移后使用SQLite资料/作答和D真实SDK，保存Run/阶段checkpoint/结果；调用现有C工作流，不重写学习算法 |
| 本地交付 | doctor、init、原启动命令、Windows脚本、实例锁/身份校验停止、健康检查、只读一致性备份、校验恢复到新目录、快照导出、环境模板 |

## 代码入口

- `shared/contracts/platform.js`、`docs/contracts/phase1.md`：模块可共同使用的schema和冻结接口。
- `backend/platform/database.js/repository.js`：SQLite迁移、事务、课程及实体仓库、快照投影、D确认事务。
- `files.js/file-worker.js/parse-worker.js`：原件和普通文件解析；支持注入B的parseArtifact实现。
- `jobs.js/resources.js`：持久队列与cpu/api许可；不含GPU或本地模型加载。
- `migration.js/action-store.js`：迁移预览/备份与持久确认状态恢复。
- `api-provider.js/workflow.js`：统一模型许可/调用用量记录、存储驱动的既有Agent装配和运行追踪。
- `index.js`：平台装配，当前B解析/RAG及C规则服务注入。
- `backup.js/cli.js`、`scripts/start.ps1/stop.ps1`：操作与交付入口。
- `backend/http/platform.js`、`app.js/config.js/server.js`：同源本机HTTP、nonce、跨源限制、运行配置与关闭。
- `frontend/js/services/platform-client.js`：A正式适配、迁移/恢复/后台任务/MCP写入面板；beforeunload恢复保护。
- `backend/mcp/actions.js`：最小兼容修改，新增可选Map形状store并持久化状态转换，默认Map行为和D原测试不变。
- `backend/providers/mimo.js`：保留原模型调用，仅把服务商usage交给E记录，不猜价格或暴露密钥。

## 真实验收

合并A/D后97项基线通过；最终`node --test` **107项通过，0失败/跳过**。E新增10项集成验证，原97项保留。JavaScript语法、Git差异空白及新增文档链接检查通过。

| 流程 | 证据 |
| --- | --- |
| 迁移/持久化 | 专项测试40消息/400作答，raw备份、重复导入、CAS、SQLite关闭重开后数量完整 |
| 范围和事务 | 双课程隔离、游标范围拒绝、归档写入拒绝、事务回滚；文件ID不能作为任意路径 |
| 资料作业 | 真实Node线程调用现有解析和分段，原件、chunks、进度/事件、完成结果重启保留；重复上传键不重复创建 |
| CPU/API任务 | CPU失败重试/检查点恢复，租约恢复、取消阻止业务提交；API失败及崩溃结果unknown，不自动重试；并发上限与usage记录 |
| MCP事务 | SQLite真实数据、引用版本校验、audit/receipt一次提交；已确认笔记写入后更新兼容workspace，旧快照不能覆盖 |
| 确认重启 | 新authority从SQLite恢复预览；故障模拟executing但已有receipt时只恢复原收据，审计仍1条 |
| Agent HTTP | 当前C流程→D官方SDK→SQLite资料→真实RAG→受控模型；引用通过、无degraded，Run及API ledger成功 |
| 恢复 | SQLite backup及原件复制，新目录恢复后完整读取；篡改hash、已存在目标均拒绝；修复Windows临时文件占用时的有界改名重试 |
| 普通解析取消 | 真Node Worker异常编码和取消/terminate验证，不需要Python/模型运行时 |
| 安全与兼容 | 既有接口回归；缺nonce、跨源请求、私有数据库路径拒绝；原件只走授权下载端点 |

三套真实Chrome脚本均通过：

```text
node tests/e2e/browser.js      # 原应用：问答、引用、停止/重试、解析、题库、复习、file预览
node tests/e2e/workspace.js    # A完整学习空间；可选多模态端口明确使用受控适配器
node tests/e2e/platform.js     # E真实SQLite/MCP/原件/作业/同步/恢复
```

E浏览器实测：35条对话/350条作答迁移；点击确认前笔记数为0，确认后真实MCP写入、审计1条、刷新后A笔记恢复；上传MD→Node解析作业→文件hash/检索正文→自动同步→刷新；1440和375宽无横向溢出，0运行时异常，截图已检查。

还实际执行了Windows干净测试目录启动（临时端口50406）、`npm run stop`等价CLI停止，实例PID文件清理且进程正常结束；实际CLI backup/restore输出成功。所有恢复测试仅操作临时目录或Git忽略的test-results副本，没有给用户真实浏览器执行自动迁移，也没有覆盖用户数据库。

doctor实际报告：Node24.19.0、SQLite3.53.3、inference=external-api-only、pythonRequired=false、gpuRequired=false。MiMo配置存在仅核对boolean，未打印密钥；**本次没有调用付费MiMo/OCR/向量/语音API，生成结果用受控模型验证**，不把配置存在当成模型效果验收。

## 给B/C/F的接线

1. B复用E repository/files/job端口，普通解析可替换parseArtifact，OCR/Embedding/Rerank只接外部API；提供真正源位置/版本和索引生命周期，不在E复制检索算法。
2. C复用createStoredWorkflow所调用的现有工作流及repository/Run接口，增强学习业务；新的模型/多模态API通过统一API许可和usage/未知结果语义接入。API调用不是数据库事务，不能声称外部扣费至多一次。
3. D已在E分支完成正式SQLite确认和A界面接线，独立D分支仍可保持默认内存Map；后续改共享工具schema先更新公共契约及测试。
4. F按同样命令独立验收与报告，区分真实SQLite/SDK/文件解析、受控模型、尚未接入的付费能力。当前没有本地模型/GPU实验要求。

## 限制和后续

- B/C新分支尚未提交增强业务，本次真实接通的是已有RAG、解析、学习规则和Agent；向量/混合检索、OCR、多模态、FSRS等仍是B/C任务，不因E完成而声称已上线。
- 当前个人本机用户，scope为未来账号隔离保留。没有多人登录、云同步、远程公网部署和分布式配额；不要将本机nonce当成公网认证系统。
- 软删除与修订保留利于恢复，不承诺物理销毁。GC只清未被任何资料修订引用的孤立文件，默认dry-run。
- API token usage若服务商未返回则未知；实际账单金额未报告，不自动填估算金额。结果unknown需核对服务商后由业务恢复，不提供一键盲目重放。
- 快照是原UI兼容格式，关系实体是同库投影；大课程检索应由B注入数据库检索端口，不能把目前读取课程候选片段的适配当成大规模向量方案。
- 现存浏览器原件缺失、早期版本已截断且无备份的数据无法凭空恢复。正式迁移需用户在原浏览器预览并确认。
- 跨版本回退采用已校验备份恢复到新目录，当前不提供破坏式SQL降级；不会自动合并main。

## 提交

- `b6ce42e`：E分支集成A/D已验证成果。
- `1f0d760`：纯API持久化、任务、迁移、HTTP与MCP实际装配。
- `2ccaaad`：有界可取消Node文件解析线程。
- `b48be34`：确认状态持久化、收据恢复及Windows恢复健壮性。
- 文档单独提交；以`git log origin/main..feat/large-E-platform --oneline`查看完整历史。普通推送E分支，main及其他任务分支不变。
