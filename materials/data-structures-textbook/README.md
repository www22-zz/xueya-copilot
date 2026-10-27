# 数据结构与算法：扫描教材资料包

本资料由用户提供并授权用于本项目课程知识库。保留原扫描 PDF，不改变版面或页序。

- `textbook.pdf`：《数据结构——从概念到C++实现（第3版）》，324页，54,355,583字节。
- `prepared-ocr.json`：绑定原件SHA-256的逐页OCR文本，`prepared-pdf-ocr-v1`兼容格式。
- `textbook-ocr.md`：按PDF实际页码整理的可阅读文本；不是人工校订版。

原件SHA-256：`536aca02ecdab9352293b3cdcc1ac760e2e6dcdf5a581f03f0b71eeda1047757`。

本次经用户授权，仅在构建此资料包时使用已安装的 Windows 中文 OCR，无额外OCR API费用、模型安装或GPU依赖。项目运行时不调用系统OCR；后续图片识别仍使用项目配置的外部服务。原始识别445,147字符；只清理相邻中文/中文标点间的OCR空格、保留行序后为296,358字符。PDF第81、111、183、301页经原图核对为空白，保留页码但不生成证据。其余320页不等于逐字独立人工审核。

公式、代码、表格与图示存在识别误差，不能将整理文本直接当作可编译代码或公式真值。不要猜测替换难辨字形；通过页面的“查看原文/下载原件”核对扫描图。PDF页码含封面目录，可能与书上印刷页码不同。

## 导入已有课程

先备份并停止本机主服务。在本机 `.env` 设置 `XUEYA_PRESERVE_LEGACY_DATA=1`、`XUEYA_AUTO_IMPORT_DEMO=0`，以保留私人旧学习记录并避免再次准备PPT演示包。然后：

```powershell
python -m scripts.import_prepared_pdf --pdf materials/data-structures-textbook/textbook.pdf --prepared materials/data-structures-textbook/prepared-ocr.json --course-id <已有课程ID> --name "数据结构—从概念到C++实现（第3版）.pdf" --apply
```

需要将本课程旧PPT退出当前检索时，再明确附加 `--replace-ppt`。它只在新PDF通过9组检索和引用校验后生成预览并原子确认，旧原件与版本、其他课程及私人学习记录保留。未传`--apply`只核对原件绑定，不修改数据库。不同电脑不复制本机数据库、账号、令牌、密钥或文档ID。

导入复用平台FileStore、CPU作业、版本化资料和取消/提交机制；不调用模型，不新增数据库、HTTP根路由或本地推理运行时。相同原件/文本幂等，换页、hash不符、未解决空页、版本过期或取消时不发布部分文本。重新解析原扫描PDF会重新得到待OCR状态；保留本资料包，可再次显式采纳预处理文字。

本机实际导入为821个片段，检索及引用校验通过。代码本身不把用户私有课程ID写成通用默认值。
