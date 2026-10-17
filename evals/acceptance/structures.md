# 结构验收

| 结构 | 次序 |
| --- | --- |
| 栈 | 后进先出 |
| 队列 | 先进先出 |

```python
stack = []
stack.append(3)
assert stack.pop() == 3
```

$$T(n)=T(n/2)+1$$
