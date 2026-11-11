# 可分发的栈与队列向量资料包

仅对应上一层的《栈与队列知识库.md》，不接入其他教材或课件。

- `vectors.json.gz`：已有真实 Qwen3-VL-Embedding-2B 向量缓存，178 条、2048 维，gzip 压缩约 3.2 MB；不包含账号、密钥、会话、私人数据库或本机文档 ID。
- `manifest.json`：原文、压缩包及展开后缓存的 SHA256，以及完整模型身份。

普通 `git clone` / `git pull` 会取得本目录，不需要 Git LFS。新电脑复制根目录 `.env.example` 为 `.env` 后启动项目、注册本机账号，首次打开会通过现有 CPU 解析和 FileStore/SQLite 自动接入这一个文件并导入已有向量。不会重新调用模型计算 178 个片段的向量；重复启动不重复导入，用户归档后的资料不会自动恢复。已有其他资料历史的课程不会被本资料包覆盖。`XUEYA_AUTO_IMPORT_STACK=0` 可关闭自动接入。

语义查询仍需配置外部向量服务密钥。后端优先读取本机 `.env` 的非空 `RAG_EMBEDDING_API_KEY`，否则可读取单独安全配置的本机 `.env.team-embedding`；设置 `XUEYA_SHARED_EMBEDDING=0` 可禁用后者。真实密钥不随仓库分发，仓库只提供 `.env.team-embedding.example` 空密钥模板。没有密钥时仍可用关键词检索，已有文档向量保留。模型设置与缓存匹配如下：

```dotenv
RAG_EMBEDDING_PROVIDER=moark-qwen
RAG_EMBEDDING_BASE_URL=https://api.moark.com/v1
RAG_EMBEDDING_MODEL=Qwen3-VL-Embedding-2B
RAG_EMBEDDING_DIMENSION=2048
RAG_EMBEDDING_REVISION=1
```

问答生成还需配置自己的 `MIMO_API_KEY`。语义检索仍需调用外部服务生成“问题”的向量，可能产生调用费用；本包只免去对文档片段重复向量化。换用不同模型或维度时不会误用当前缓存；页面显示模型不匹配，仍可关键词检索。

文字被修改、压缩包损坏、片段哈希或模型身份不匹配时停止接入并记录错误，不自动付费修复。首次安装前务必保留原文件的 LF 换行；仓库 `.gitattributes` 已指定换行规则。修改正文后需要显式重新生成并发布与之匹配的资料包。
