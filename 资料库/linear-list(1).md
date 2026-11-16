# 线性表与链表知识库：从基础到进阶

版本：1.0.0；编写日期：2026-11-04。路线：ADT与表示 → 顺序表 → 单双循环链表 → 指针操作 → 双指针、反转、合并与工程选择。

适用：数据结构课程学习、C++17示例、RAG问答。内容为独立编写的教学材料，仿照栈与队列知识库的组织风格，不是课程PPT或扫描教材的转录，不附原教材页码。

通用约定：0基下标，区间默认左闭右开；n为元素数，V/E为图顶点/边数；空间复杂度默认辅助空间并另行说明输出。每个cpp代码块均为独立完整C++17程序，须分别编译，保留assert。输入规模及数值范围须满足各块前提，示例并非工业泛型库。

参考导航：[MIT算法课程主题目录](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/pages/lecture-notes/)；[C++字符串接口规范（持续更新的工作草案）](https://eel.is/c++draft/string.classes)。核对日期：2026-11-04。课程目录用于主题覆盖导航；本文推导、代码和练习为原创。只使用C++17已有接口，不把草案新增接口当作C++17。

## LL01 线性表ADT、逻辑次序与存储次序

<!-- kb-meta: {"id": "LL01", "aliases": ["ADT", "list", "线性关系"], "questions": ["线性表ADT、逻辑次序与存储次序的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

线性表是有先后次序的有限序列，除首末外每个元素有唯一直接前驱和后继。元素可为记录，逻辑相邻不要求物理内存相邻。ADT定义取值、定位、插入、删除等语义，顺序表与链表是其不同表示。

本文长度n、元素下标0..n-1，插入位置允许0..n，删除和读取只允许0..n-1。查找返回元素位置还是结点指针由接口决定；值可能重复，必须说明取首次、全部或任意。空表长度0但可仍有分配空间或辅助头结点。

动态数组支持O(1)按下标取值，链表通常O(n)定位；已知前驱后的局部接链O(1)，不能把“查找再插入”整体也写成O(1)。

## LL02 顺序表、动态扩容与迭代器失效

<!-- kb-meta: {"id": "LL02", "aliases": ["vector", "capacity", "reserve", "均摊复杂度"], "questions": ["顺序表、动态扩容与迭代器失效的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

顺序表元素连续存储，随机访问O(1)，在位置i插入需将[i,n)向后移动，删除i需将(i,n)向前移动，最坏O(n)。保持有序与否影响删除策略：无序场景可用末尾覆盖i再弹末尾，但会改变元素次序。

动态数组以几何倍数扩容，可使一串尾插均摊O(1)，单次扩容仍O(n)。每次只增固定容量会使大量尾插总代价O(n²)。容量capacity与有效长度size不同，reserve不创建有效元素，不能随后访问下标size以外位置。

C++ vector重分配会使指针、引用和迭代器失效；未重分配的中间插入删除也可能使操作位置及之后迭代器失效。保存下标后也要注意位置移动造成语义变化。

## LL03 单链表、头结点与删除前驱

<!-- kb-meta: {"id": "LL03", "aliases": ["头结点", "首元结点", "单链表删除", "指针接链"], "questions": ["单链表、头结点与删除前驱的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

单链表结点保存值与next。头指针是变量，头结点是可选辅助对象，首元结点是第一个有效元素。带头结点可把表头插删统一为修改前驱的next，不带头结点需更新head本身。

在已知结点p之后插入s：先s->next=p->next，再p->next=s；次序反了会丢失原后继。删除p后继时先保存q=p->next，再p->next=q->next，最后释放q；前提q存在。指针释放后不可再读取q->next。

只给待删结点且没有前驱时，普通单链表删除并不总能O(1)。把后继值复制到当前再删后继仅在非尾结点、允许改变结点身份且值可赋值等条件下适用，不能作为通用删除方案。

## LL04 双向链表、循环链表与哨兵

<!-- kb-meta: {"id": "LL04", "aliases": ["doubly linked list", "circular list", "sentinel", "LRU"], "questions": ["双向链表、循环链表与哨兵的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

双向链表有prev与next，已知有效结点时可O(1)删除，需同时修复两侧链接。额外指针增加内存，定位第k个元素仍O(n)。循环单链表尾next回到头；循环双链表可用哨兵使空表sentinel.next=sentinel.prev=&sentinel，简化边界。

循环结构遍历不能以nullptr为结束条件，要在重新到达起点或哨兵时停止。删除最后结点需恢复空环，并维护尾指针。哨兵不是有效记录，遍历不应输出它。

LRU缓存常组合哈希表和双向链表：哈希定位结点，链表将最近访问项移到前端，淘汰尾端；这是在哈希平均O(1)假设下的平均常数操作。仅用链表逐项找键仍O(n)。

## LL05 单链表反转与有序合并完整程序

<!-- kb-meta: {"id": "LL05", "aliases": [], "questions": ["单链表反转与有序合并完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

反转循环中保存next，再把当前next指向prev，最后前移；不变量是prev链已反转、cur链未处理。反转O(n)时间O(1)额外空间。合并输入两链不共享结点、各自非降，复用结点，O(n+m)时间O(1)辅助空间；重复键先取左链保证相对稳定。所有动态结点最终由destroy释放，禁止浅拷贝拥有者。

```cpp
#include <cassert>
#include <initializer_list>
#include <vector>
struct Node{int value;Node* next=nullptr;};
Node* make(std::initializer_list<int> values){
    Node dummy{0};Node* tail=&dummy;
    for(int x:values){tail->next=new Node{x};tail=tail->next;}return dummy.next;
}
Node* reverse(Node* cur){
    Node* prev=nullptr;
    while(cur){Node* next=cur->next;cur->next=prev;prev=cur;cur=next;}return prev;
}
Node* merge(Node* a,Node* b){
    Node dummy{0};Node* tail=&dummy;
    while(a&&b){Node*& src=(a->value<=b->value?a:b);
      tail->next=src;src=src->next;tail=tail->next;}
    tail->next=a?a:b;return dummy.next;
}
std::vector<int> values(Node* p){std::vector<int> v;for(;p;p=p->next)v.push_back(p->value);return v;}
void destroy(Node* p){while(p){Node* q=p->next;delete p;p=q;}}
int main(){
    Node* p=make({1,2,3});p=reverse(p);
    assert((values(p)==std::vector<int>{3,2,1}));destroy(p);
    p=merge(make({1,3,3}),make({2,3,4}));
    assert((values(p)==std::vector<int>{1,2,3,3,3,4}));destroy(p);
    assert(reverse(nullptr)==nullptr && merge(nullptr,nullptr)==nullptr);
}
```

## LL06 快慢指针、环入口与倒数第k个

<!-- kb-meta: {"id": "LL06", "aliases": ["Floyd判环", "龟兔算法", "链表中点", "倒数第k个"], "questions": ["快慢指针、环入口与倒数第k个的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

Floyd判环令慢指针每次一步、快指针两步，若相遇则有环；若fast或fast->next为空则无环。相遇后让一指针回head，两者每次一步再次相遇处为环入口。证明可把头到入口距离记μ、环长λ，相遇累计步数差为λ的整数倍，得到回头同步走μ步可在入口相遇。

寻找中点需规定偶数长度取哪个中点；常见slow=head,fast=head且循环fast&&fast->next会取后中点。倒数第k个（k从1计）先让fast走k步，不足k报错，再与slow同步直至fast空，slow即答案。

这些方法O(n)时间O(1)空间，但输入须为相应模型：倒数第k个要求无环链表；有环结构谈“末尾”无意义。相交链表判断按结点地址相同，不是值相同。

## LL07 线性表应用、选择与自测

<!-- kb-meta: {"id": "LL07", "aliases": [], "questions": ["线性表应用、选择与自测的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "exercise", "prerequisites": []} -->

频繁按下标读取、批量遍历和尾插，通常优先动态数组，局部性好且结点开销小。需要已知结点的频繁局部拼接，可考虑链表。理论复杂度相同不保证耗时相同，链表随机分配和指针追踪可能带来缓存代价。

题1：链表已知值x，插入其后O(1)吗？答：若只有值还要查结点，整体O(n)；若已知结点指针才可局部O(1)。

题2：vector reserve(100)后size仍0，能写v[3]吗？答：不能，该位置不是已构造的有效元素，应resize或push_back。

题3：两条链值序列都为1,2就相交吗？答：不一定，相交看是否共享同一结点。

题4：反转单链表先修改next再读旧next会怎样？答：丢失未处理后缀，需先保存。

解题检查空表、单结点、表头/尾删除、偶数中点、重复值、共享结点和循环输入；明确谁拥有并释放结点。

