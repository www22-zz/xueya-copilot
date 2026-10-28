# 数据结构：经典 Hot 100 与基础 100

版本：`data-structures-curated-20261028-v1`。共200道实际题目，180道新编练习及20道从项目已有Hot100中选入的经典代码题。Hot指经典重点、易错辨析和经典算法选编，不表示实时互联网热度排行。基础题着重定义、基本操作、直接计算和短小实现。

| 题型 | Hot 100 | 基础 100 |
| --- | ---: | ---: |
| 单选 | 30 | 40 |
| 多选 | 20 | 30 |
| 填空 | 30 | 20 |
| 代码 | 20 | 10 |
| 合计 | 100 | 100 |

两套题各按以下10个单元分组，每单元10题：算法基础与复杂度、线性表与链表、栈与队列、串与数组、树与二叉树、堆与哈夫曼树、图、查找与散列表、排序、综合应用与算法设计。每题还有更细的subtopic与tags，可叠加知识点和题型筛选。基础代码题提供C与Python参考实现；选编代码题保留已有语言题解和原题链接。代码不在生产服务中执行或自动判分。

## 题目和来源

- 正式题库：[data_structures_practice.json](../../backend/xueya/data/data_structures_practice.json)。包含全部题干、选项、答案、解析、知识点、参考代码、样例和来源。
- 新编文字内容：[data_structure_curriculum.py](../../backend/agent/data_structure_curriculum.py)；10道新编代码内容：[data_structure_code.py](../../backend/agent/data_structure_code.py)。题目为逐题编写内容，不是用题号替换同一模板凑数。
- 选编题来自原有 `practice_bank.json`，通过 `origin.originalQuestionId` 和原题链接保留出处；原有官方题单和旧进度不删除。
- 每道题的 `references` 保存实际教材PDF页及OCR摘录，标明是相关知识点背景，不能将其冒充该题原始出处或完整题解。安装时重新绑定当前本地教材的文档ID、原文片段ID和内容修订。
- 教材为用户已有《数据结构——从概念到C++实现（第3版）》，原件hash由教材资料包固定。OCR不是独立人工校订本，公式与图示仍应对照原件。新编与选编题已做结构、引用、去重及代码样例检查，不宣称全部答案经过独立人工审题。

## 生成和安装

在仓库根目录：

```powershell
.venv/Scripts/python.exe -X utf8 -m backend.agent.data_structure_bank
.venv/Scripts/python.exe -X utf8 -m scripts.install_data_structure_practice --course-id course-default
.venv/Scripts/python.exe -X utf8 -m scripts.install_data_structure_practice --course-id course-default --apply
```

不带 `--apply` 只预览。安装必须找到当前课程内已解析的同一教材原件，不自动导入或替换资料。应用前创建SQLite一致性备份，只写入课程题库快照和选择指针，检查旧笔记、作答事件等记录数不变。多个版本快照可保留，当前页面读取被选中的题库；其他科目不受影响。服务已加载新代码时刷新即可读取选择变化；首次部署新代码需要启动或重启服务。

## 验证

`tests/python/test_curated_data_structures.py` 检查两套题计数、题型、10单元覆盖、题干去重、引用真实页文、安装幂等、旧记录保留、课程边界及资料修订失效。10道新编C题分别用GCC的C11模式、`-Wall -Wextra -Werror` 编译并运行边界样例；对应Python参考也执行实际样例。

`scripts/check_curated_practice_browser.py` 用实际200题及隔离教材绑定验收页面：知识单元导航、知识点和题型组合筛选、多选/填空作答、原题链接、C参考代码、深浅色、手机布局及刷新。无模型调用或API费用；截图与报告输出到被忽略的 `test-results/curated-data-structures/`。
