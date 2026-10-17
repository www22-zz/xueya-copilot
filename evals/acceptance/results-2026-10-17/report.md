# F 离线验收实测

数据版本：F-acceptance-v1；SHA256：`24f7815d71d5ca6f6eeeb0f85803785a7dacd0cc84408aafc6d2bb94e6a06815`。

分组：test；本次 46 问；每次重复 3 轮；预算 2000 UTF-8 bytes，top-k=6。

| 方法 | 通过 | 全部证据召回 | 摘录召回 | MRR | 不可答无检索证据 | P50/P95 ms |
| --- | --- | --- | --- | --- | --- | --- |
| fixed-lexical | 43/46 | 1.000 | 1.000 | 0.975 | 0.500 | 0.97/1.68 |
| structured-lexical | 40/46 | 0.925 | 0.932 | 0.875 | 0.500 | 6.97/10.39 |

这是原创验收集的实际结果，不代表真实模型质量或真实学习收益；没有新增付费调用。

## 失败条目

- fixed-lexical / negative-5：课程指定的栈容量上限是多少？（命中 0/0，返回 4 段）
- fixed-lexical / negative-6：这门课二叉树考试在哪一天？（命中 0/0，返回 1 段）
- fixed-lexical / negative-8：这份讲义要求的队列作业截止时间是什么？（命中 0/0，返回 3 段）
- structured-lexical / trees-2-2：根左右是哪种遍历？（命中 0/1，返回 6 段）
- structured-lexical / trees-3-2：左根右是哪种遍历？（命中 0/1，返回 6 段）
- structured-lexical / trees-4-2：左右根是哪种遍历？（命中 0/1，返回 6 段）
- structured-lexical / negative-5：课程指定的栈容量上限是多少？（命中 0/0，返回 5 段）
- structured-lexical / negative-6：这门课二叉树考试在哪一天？（命中 0/0，返回 6 段）
- structured-lexical / negative-8：这份讲义要求的队列作业截止时间是什么？（命中 0/0，返回 5 段）
