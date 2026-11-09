# 公共预置资料的跨课程范围：已批准清单

2026-10-31 用户明确批准：“批准，仅六份清单教材”。现已在现有RAG适配层接通以下六个完整SHA256标识的跨课程问答；**不迁移正式数据、不重建向量、不修改检索算法**。

仅下面六份位于可信预置 owner（既有 `local-user`）中的材料可跨课程用于问答。来源仍回原 owner/course 验证当前文档、片段、修订及索引身份；仅公开元信息，不公开原文。账号上传、旧未标记资料、私人课程与任意其他平台课程均不扩大范围。原同courseId内明确标记资料的兼容权限保留，未扩大到其他课程。

| 材料 | 完整SHA256 | 现有依据 |
| --- | --- | --- |
| 栈与队列知识库 Markdown | `7a36da9a2a222b39d22c13a720f587f7f2d21073dbfbcccc9b2769c222d0652a` | `materials/stack-queue/栈与队列知识库.md`实际字节哈希 |
| week1 第1章 绪论 | `7fbd8a0444096282daf0b2d68904aa89c70144e1525134db0979be31ed9bfd29` | `materials/data-structures-algorithms/manifest.json` |
| week2 第2章 线性表：顺序表 | `6da65496b85208708df00d7213ec3074cb535e36e9eefa03de220438ba946b42` | 同上 |
| week3 第2章 线性表：链表 | `5702f159d19a3e88a17049ff691fdaf26ca8fdd6650269d24d39d2f5a89b6504` | 同上 |
| week4 第3章 栈和队列 | `92f525d8e8f31560451023cb32bcddf43272c2900e084736a103c86abc3f0bb9` | 同上 |
| week6 第4章 数组 | `5e2521731f275e6668f2b6c3ef8cf5a8a511618ccf70922731860d6cf79f3c01` | 同上 |

跨课程读取不凭客户端isPlatform、sample、文件名或sourceFileHash声明启用。只核对实际文档fileHash和可信owner；`pub-…` ID绑定实际owner/course/source，不能用raw source ID或伪造scopeOrigin绕过。停用课程/资料、删除、哈希变化、未确认修订及原证据身份不匹配都会失效。查询等待期间变化时，最终候选重新核验；MCP旧文本回退也必须重新校验，不能复活失效来源。

同内容多个旧副本以`fileHash/textHash/page/start/end/quote`合并重复命中，原作用域各自保留；优先请求同课程，其次按原课程ID稳定排序。不同修订不合并，旧副本别名仍回其实际来源核验。公开来源兼容增加服务端originCourseId/originCourseName，浏览器展示原课程与位置，不展示正文/导出。私人账号上传即使文件内容与清单相同，也不会成为新的公共namespace。

历史审批边界：枚举所有平台课程并仅凭标记公开的补丁曾被自动审批拒绝，未应用；本次按用户后来明确批准的六份清单收窄实现，没有解除其他课程/旧资料的边界。新增回归使用临时SQLite及真实清单MD的CPU解析，五份PPT哈希与现有manifest逐项核对；不把这些受控结果宣称为正式私人资料已经迁移、所有PPT/向量已在本机重新联调或真实模型质量已验收。
