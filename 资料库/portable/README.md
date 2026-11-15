# 七份数据结构资料及预计算向量

本目录和上一层七份 MD 是可通过 Git 分发的 RAG 数据包。包含518个资料片段对应的 **500条去重向量**，模型为 **Qwen3-VL-Embedding-8B，4096维**，压缩约16 MB。无需 Git LFS；不包含密钥、账号、会话、作答、私人数据库或本机文档ID。

队友拉取此版本后按根目录 README 启动并登录。`XUEYA_AUTO_IMPORT_CORPUS=1`（默认开启）会通过原有 CPU 解析、后台作业、FileStore 与 SQLite 将原文及现成向量加入当前账号的默认课程。**安装不调用 embedding、OCR 或问答模型，也不生成练习。** 重复启动不重复导入；已有资料和学习记录保留；归档或删除过的同内容资料不会自动恢复。`XUEYA_AUTO_IMPORT_CORPUS=0` 可关闭安装。

无密钥可以进行关键词检索。语义检索仍需要把每次“问题”转换成向量；本包免去的是重复计算文档向量，不免除问题向量和回答生成的API调用。复制根目录 `.env.example` 为自己的 `.env` 并填入自己的密钥；已有配置请核对以下项目。不同模型/维度不会混用缓存。

```dotenv
RAG_EMBEDDING_PROVIDER=moark-qwen
RAG_EMBEDDING_BASE_URL=https://api.moark.com/v1
RAG_EMBEDDING_MODEL=Qwen3-VL-Embedding-8B
RAG_EMBEDDING_DIMENSION=4096
RAG_EMBEDDING_REVISION=1
```

`manifest.json` 绑定七份原文SHA256、模型身份、片段数量、向量ID、压缩及展开文件哈希；`vectors.json.gz` 只保存模型身份、教材清单、内容哈希和规范化向量。导入时重新校验当前解析结果、文档修订及出处，损坏或不匹配时停止，不自动付费重建。MD保留原始CRLF字节，`.gitattributes` 禁止Git转换换行，避免克隆后哈希变化。

维护者仅在显式重新计算、确认新资料后，使用 `python -m scripts.export_md_vector_bundle --owner <本机数据所有者ID>` 导出。导出工具本身不调用API，只允许上层七个指定文件，不导出其他资料或私人状态。
