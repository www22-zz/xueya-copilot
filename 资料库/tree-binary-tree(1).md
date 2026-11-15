# 树和二叉树知识库：从基础到进阶

版本：1.0.0；编写日期：2026-11-04。路线：术语与性质 → 表示与遍历 → 构造与线索 → 搜索树、平衡树 → 堆、哈夫曼 → 祖先与区间结构。

适用：数据结构课程学习、C++17示例、RAG问答。内容为独立编写的教学材料，仿照栈与队列知识库的组织风格，不是课程PPT或扫描教材的转录，不附原教材页码。

通用约定：0基下标，区间默认左闭右开；n为元素数，V/E为图顶点/边数；空间复杂度默认辅助空间并另行说明输出。每个cpp代码块均为独立完整C++17程序，须分别编译，保留assert。输入规模及数值范围须满足各块前提，示例并非工业泛型库。

参考导航：[MIT算法课程主题目录](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/pages/lecture-notes/)；[C++字符串接口规范（持续更新的工作草案）](https://eel.is/c++draft/string.classes)。核对日期：2026-11-04。课程目录用于主题覆盖导航；本文推导、代码和练习为原创。只使用C++17已有接口，不把草案新增接口当作C++17。

## TB01 树、森林、深度与高度的统一约定

<!-- kb-meta: {"id": "TB01", "aliases": ["root", "leaf", "forest", "树高", "结点层次"], "questions": ["树的深度、高度和层次如何区分？", "二叉树与度为2的树相同吗？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

非空有根树由一个根及若干互不相交的子树组成。结点的度为孩子数，树的度为最大结点度；叶子度为0。祖先位于到根的路径上，兄弟有相同父结点。森林是若干互不相交树的集合，删除树根会得到其子树森林。

本文根深度为0，高度按最长根到叶路径的边数计，单结点树高度0，空树高度-1。某些教材根为第1层、高度按结点数计，引用公式前先转换。n个结点的非空树边数n-1；拥有c个非空树的森林共n-c条边。

一般树的孩子可以有顺序或无顺序。二叉树有明确左右位置，即使仅一个孩子也区分左与右，所以二叉树不只是“每个结点度≤2的无序树”。

## TB02 二叉树性质、满二叉树与完全二叉树

<!-- kb-meta: {"id": "TB02", "aliases": ["perfect", "complete", "full", "n0=n2+1", "完全二叉树"], "questions": ["二叉树性质、满二叉树与完全二叉树的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

二叉树第d层（根深度0）最多2^d个结点，高度h最多2^(h+1)-1个。非空二叉树若叶子数n0、度为2的结点数n2，则n0=n2+1：由边数n-1=n1+2n2与n=n0+n1+n2相减得到，与树是否平衡无关。

本文“满二叉树”专指每层都满的perfect binary tree；英语full/proper有时只要求每个内部结点恰有两个孩子，未必各层满。完全二叉树除最后一层外都满，最后一层从左到右连续，适合数组存储。非空完全二叉树n结点高度floor(log2 n)，但普通二叉树可能退化为高度n-1的链。

完全树0基数组中，i的孩子为2i+1、2i+2，合法前提是结果<n；非根父结点为(i-1)/2。数组位置不是键值。

## TB03 二叉链表、顺序表示与所有权

<!-- kb-meta: {"id": "TB03", "aliases": ["二叉链表", "顺序二叉树", "空指针数量"], "questions": ["二叉链表、顺序表示与所有权的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

二叉链表每结点保存值及左右孩子；可选parent指针支持向上访问。n结点二叉链表有2n个孩子指针槽，实际边n-1，所以空孩子指针共n+1个。这个计数不包含额外parent指针和头结点。

顺序表示按完全树位置编号，访问父子O(1)，但偏斜树可能产生大量空槽；链式表示空间O(n)，更适合形态任意的树。竞赛常用vector<Node>和整数下标，-1表示空；vector扩容可能使裸指针/引用失效，整数下标则可在未删除重排元素时保持含义。

教学代码用唯一拥有的unique_ptr自动释放，或采用索引数组。不共享子树，不形成环；若结构可能有环或多个父结点，就要按图处理，不能套用普通树递归。

## TB04 先序、中序、后序与层序遍历

<!-- kb-meta: {"id": "TB04", "aliases": ["preorder", "inorder", "postorder", "level order", "DFS", "BFS"], "questions": ["先序、中序、后序与层序遍历的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

先序根左右适合复制和序列化；中序左根右对BST产生有序键；后序左右根适合释放子树、计算高度与表达式值；层序用队列按深度处理。每个结点常数次访问时均O(n)。递归额外调用栈O(h)，最坏链形为O(n)，不是固定O(log n)。

迭代中序：不断压入当前结点并向左，左空则弹出访问，再转右。层序队列最坏O(w)，w为最大层宽，可能O(n)。先序用栈时先压右孩子再压左孩子，才会先处理左。

例：根1，左2，右3，2的右孩子4。先序1,2,4,3；中序2,4,1,3；后序4,2,3,1；层序1,2,3,4。遍历序列由树和左右顺序共同决定。

## TB05 迭代中序与层序完整程序

<!-- kb-meta: {"id": "TB05", "aliases": [], "questions": ["迭代中序与层序完整程序的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "code", "prerequisites": []} -->

索引-1表示空，输入必须是无环、无共享孩子的合法二叉树。中序栈保存尚未访问的祖先；层序队列保存待处理结点。空树返回空序列，测试非对称树以避免左右次序错误被对称例子掩盖。时间O(n)，中序额外O(h)，层序O(w)。

```cpp
#include <cassert>
#include <queue>
#include <stack>
#include <vector>
struct Node { int value,left,right; };
std::vector<int> inorder(const std::vector<Node>& a,int root) {
    std::vector<int> out; std::stack<int> s; int u=root;
    while(u!=-1 || !s.empty()) {
        while(u!=-1) { s.push(u); u=a[u].left; }
        u=s.top(); s.pop(); out.push_back(a[u].value); u=a[u].right;
    }
    return out;
}
std::vector<int> level(const std::vector<Node>& a,int root) {
    std::vector<int> out; if(root==-1) return out;
    std::queue<int> q; q.push(root);
    while(!q.empty()) {
        int u=q.front(); q.pop(); out.push_back(a[u].value);
        if(a[u].left!=-1) q.push(a[u].left);
        if(a[u].right!=-1) q.push(a[u].right);
    }
    return out;
}
int main() {
    std::vector<Node> a{{1,1,2},{2,-1,3},{3,-1,-1},{4,-1,-1}};
    assert((inorder(a,0)==std::vector<int>{2,4,1,3}));
    assert((level(a,0)==std::vector<int>{1,2,3,4}));
    assert(inorder(a,-1).empty() && level(a,-1).empty());
}
```

## TB06 遍历重建、序列化与线索二叉树

<!-- kb-meta: {"id": "TB06", "aliases": ["树重建", "序列化", "threaded binary tree", "线索化"], "questions": ["遍历重建、序列化与线索二叉树的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

键值互异时，先序+中序或后序+中序可唯一重建二叉树：先序首项或后序末项确定根，中序根位置划分左右范围。中序位置哈希表可使期望时间O(n)，空间O(n)；每层线性找根最坏O(n²)。序列不一致必须报错，不能越界拼树。重复值会破坏仅靠值定位的唯一性。

仅先序+后序通常不唯一，例：根1的单孩子2放左或放右均同序列；附加“每个内部结点恰有两个孩子”等条件才可能恢复唯一性。先序序列化若显式保存空标记，如1,2,#,#,3,#,#，可以恢复形态；值本身若可能等于标记必须转义或结构化编码。

线索二叉树利用空孩子指针指向某遍历次序的前驱/后继，并用标签区分孩子与线索；遍历时若把线索当孩子递归会成环。线索化改变表示，并未改变逻辑树的父子关系。

## TB07 树与森林的孩子兄弟表示

<!-- kb-meta: {"id": "TB07", "aliases": ["左孩子右兄弟", "森林转换", "多叉树"], "questions": ["树与森林的孩子兄弟表示的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

孩子兄弟表示令left指向第一个孩子，right指向下一个兄弟，可以用两个指针表示任意多叉树。将森林各根用兄弟指针串起即可统一表示。这里right不表示原树的右孩子，解释程序必须先识别表示法。

原树先根遍历对应转换后二叉表示的先序；原树后根遍历对应转换后二叉表示的中序。例：根A的孩子B,C，B有孩子D；原树先根A,B,D,C，后根D,B,C,A。转换后二叉树的边有两种语义，不能拿其高度直接当原树高度。

文件目录、组织层级和语法树常用多叉树；若频繁按第k个孩子访问，vector孩子表比链式兄弟更直接，若频繁局部接链则要考虑兄弟指针。

## TB08 二叉搜索树BST及删除的三种情况

<!-- kb-meta: {"id": "TB08", "aliases": ["BST", "二叉排序树", "binary search tree"], "questions": ["BST删除有两个孩子的结点怎么做？", "普通BST查询一定O(log n)吗？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

BST采用严格键规则：左子树所有键小于当前，右子树所有键大于当前。重复键可忽略、计数或引入复合键，但必须统一。中序有序是整体子树约束的结果，仅检查左右孩子大小不够：根10左孩子5的右孩子12已经违规。

查找与插入沿比较路径下降，时间O(h)，最坏O(n)。删除叶子直接摘除；仅一个孩子则父链接绕过当前结点；两个孩子可用右子树最小键（中序后继）替换，再删除后继原结点。若结点还带业务值或计数，应移动完整记录，不能只替换键。

随机插入在相应概率假设下可有期望对数高度，但按递增键插入必退化。工程需要最坏保证时用平衡树，不能把普通BST的查找一概写成O(log n)。

## TB09 BST插入、查找和删除完整程序

<!-- kb-meta: {"id": "TB09", "aliases": [], "questions": ["BST插入、查找和删除完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

采用unique_ptr唯一拥有子树，重复键忽略。删除双孩子结点时用后继替换；测试删除叶子、单孩子、双孩子、根和不存在键，并用有序集合状态验证中序结果。时间O(h)，递归栈O(h)，大量退化输入宜改迭代或平衡结构。

```cpp
#include <cassert>
#include <memory>
#include <vector>
struct Node {
    int key; std::unique_ptr<Node> left,right;
    explicit Node(int k):key(k){}
};
using Ptr=std::unique_ptr<Node>;
void insert(Ptr& p,int k) {
    if(!p) p=std::make_unique<Node>(k);
    else if(k<p->key) insert(p->left,k);
    else if(k>p->key) insert(p->right,k);
}
bool has(const Ptr& p,int k) {
    const Node* u=p.get();
    while(u && u->key!=k) u=k<u->key?u->left.get():u->right.get();
    return u!=nullptr;
}
void erase(Ptr& p,int k) {
    if(!p) return;
    if(k<p->key) erase(p->left,k);
    else if(k>p->key) erase(p->right,k);
    else if(!p->left) { auto q=std::move(p->right); p=std::move(q); }
    else if(!p->right) { auto q=std::move(p->left); p=std::move(q); }
    else {
        Node* s=p->right.get(); while(s->left) s=s->left.get();
        p->key=s->key; erase(p->right,s->key);
    }
}
void walk(const Ptr& p,std::vector<int>& out) {
    if(!p) return;
    walk(p->left,out); out.push_back(p->key); walk(p->right,out);
}
int main() {
    Ptr root; for(int k:{5,3,7,2,4,6,8}) insert(root,k);
    insert(root,5); assert(has(root,6) && !has(root,9));
    for(int k:{2,3,5,99}) erase(root,k);
    std::vector<int> out; walk(root,out);
    assert((out==std::vector<int>{4,6,7,8}));
    for(int k:{4,6,7,8}) erase(root,k);
    assert(!root);
}
```

## TB10 AVL与红黑树：平衡不变量与旋转

<!-- kb-meta: {"id": "TB10", "aliases": ["AVL", "红黑树", "LL", "LR", "旋转"], "questions": ["AVL与红黑树：平衡不变量与旋转的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

AVL要求任意结点左右子树高度差绝对值≤1。插入后沿祖先更新高度，LL失衡右旋，RR左旋，LR先左旋左孩子再右旋，RL反之。旋转保持中序次序，因此保留BST性质，但必须正确更新父链接和高度；删除可能导致多个祖先继续失衡。

红黑树通过结点颜色、根与空叶为黑、红结点无红孩子、各到空叶路径黑高相同等约束限制高度为O(log n)。它允许比AVL更松的高度平衡，以旋转和重新着色维护。查找、插入、删除最坏O(log n)。

C++有序关联容器提供对数级操作保证，常见实现使用红黑树；标准接口保证不应等同于强制某种具体树实现。需要顺序遍历、前驱后继和范围查询考虑有序树；只求等值查找可比较哈希表。完整AVL/红黑插删实现不在本版代码范围。

## TB11 堆与优先队列：上浮、下沉和线性建堆

<!-- kb-meta: {"id": "TB11", "aliases": ["heap", "priority_queue", "建堆", "优先队列"], "questions": ["堆与优先队列：上浮、下沉和线性建堆的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

二叉堆是完全二叉树，最大堆满足父键≥孩子键，最小堆相反。堆仅保证父子局部偏序，并不保证中序或数组整体有序。插入把元素放末尾再上浮，弹出堆顶用末尾填根再下沉，两者O(log n)，取顶O(1)。

自底向上对所有内部结点下沉可O(n)建堆，因为靠近底部的结点多但可下降高度小，Σn/2^(h+1)·h=O(n)。逐个插入的建堆上界O(n log n)，不能混为同一构建过程。

std::priority_queue<int>默认最大堆，配greater<int>为最小堆；同优先级不保证FIFO，可附加递增序号。Dijkstra惰性删除方案可重复入堆并丢弃过期距离；需要按句柄减少键时则须额外索引。

## TB12 哈夫曼树、带权路径长度与前缀编码

<!-- kb-meta: {"id": "TB12", "aliases": ["Huffman", "WPL", "前缀码", "最优二叉树"], "questions": ["哈夫曼树、带权路径长度与前缀编码的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

带权路径长度WPL=Σ叶权×根到该叶的边数。哈夫曼算法反复合并权重最小的两个子树，最终得到WPL最小的二叉前缀编码树。每次合并代价相加恰等于最终WPL，因为该子树每片叶的深度增加1。

最小堆实现建堆O(n)，随后n-1次取两项并插入，共O(n log n)，空间O(n)。例权重1,2,3,4：先合并1+2=3，再3+3=6，再4+6=10，WPL=3+6+10=19。并列权重不同选择可能得到不同码字，但最优WPL相同。

树边标0/1，叶路径构成前缀码，任何叶码不是另一码的前缀。仅一个符号时理论树深0，可约定空码，但实际文件格式常规定码0并记录符号数；编码器和解码器必须一致。哈夫曼是给定符号频率下的前缀码最优，不等于所有压缩方法的全局最优。

## TB13 哈夫曼合并代价完整程序

<!-- kb-meta: {"id": "TB13", "aliases": [], "questions": ["哈夫曼合并代价完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

只计算最小WPL，不生成码表；输入为非负频率，总和及全部合并代价必须可由long long表示。0或1项时返回0，这是按边计路径长的理论定义。时间O(n log n)，空间O(n)。测试包含空输入、单符号、并列权重与经典样例。

```cpp
#include <cassert>
#include <functional>
#include <queue>
#include <stdexcept>
#include <vector>
long long cost(const std::vector<long long>& weights) {
    for(auto w:weights) if(w<0) throw std::invalid_argument("negative weight");
    std::priority_queue<long long,std::vector<long long>,std::greater<long long>> q(
      std::greater<long long>{}, weights);
    long long total=0;
    while(q.size()>1) {
        auto a=q.top(); q.pop(); auto b=q.top(); q.pop();
        total+=a+b; q.push(a+b);
    }
    return total;
}
int main() {
    assert(cost({1,2,3,4})==19);
    assert(cost({})==0 && cost({7})==0 && cost({1,1,1,1})==8);
    assert(cost({5,9,12,13,16,45})==224);
}
```

## TB14 LCA、树形动态规划与子树区间

<!-- kb-meta: {"id": "TB14", "aliases": ["LCA", "倍增", "Euler tour", "树形DP"], "questions": ["LCA、树形动态规划与子树区间的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

最近公共祖先LCA是两个结点共同祖先中深度最大的结点，允许结点是自身祖先。单次查询可沿parent上跳或递归；大量查询可预处理up[v][k]为v的2^k级祖先，先拉平深度，再从大到小同步上跳。倍增预处理O(n log n)，每次O(log n)，空间O(n log n)。森林中不同树的结点没有共同祖先，除非约定虚拟根。

DFS进入编号tin配合子树大小，可让一棵子树对应连续区间[tin,tin+size)，便于接树状数组或线段树。用进入/退出时间判祖先时必须统一时钟规则。树形DP先求孩子状态再合并，例如子树大小=1+Σ孩子大小、最大独立集维护“选当前/不选当前”两种状态。

例：树上路径距离（按边）为depth[u]+depth[v]-2depth[LCA(u,v)]；带权树可用到根距离替代深度。路径公式依赖唯一简单路径，不能直接套到一般有环图。

## TB15 线段树、树状数组、B树与B+树的选择

<!-- kb-meta: {"id": "TB15", "aliases": ["segment tree", "Fenwick", "BIT", "B树", "B+树"], "questions": ["线段树、树状数组、B树与B+树的选择的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

线段树将区间递归二分，结点保存可合并摘要，如和、最值；点修改和区间查询O(log n)，常见数组表示O(n)空间。区间加法配懒标记时，结点和增加delta×区间长度，标记延迟下传；区间赋值与加法组合有顺序，不能只维护一个相加标记。

树状数组Fenwick利用lowbit分解前缀，点增量/前缀和O(log n)、空间O(n)；范围和由两个前缀相减得到。最小值等非可逆操作不能随意套用相减。坐标压缩保持顺序，不保留实际距离。

B树每结点有多个有序键和孩子，所有叶子同层，借较高扇出减少外存访问。B+树通常把数据记录或记录指针放叶层，叶子顺序链接便于范围扫描，内部结点用于导航。阶数m到底表示最大孩子数还是最小度数，教材约定不一，推导占用率和分裂位置前须说明。

## TB16 自测与易错纠正

<!-- kb-meta: {"id": "TB16", "aliases": [], "questions": ["自测与易错纠正的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "exercise", "prerequisites": []} -->

题1：非空二叉树有8个度为2结点，叶子多少？答：9，与度为1结点数无关。

题2：完全二叉树有10结点，按边高度多少？答：floor(log2 10)=3；按结点层数则4。

题3：BST的中序是严格递增吗？答：在本库忽略重复键规则下是；若允许重复，需按其规则解释非降或复合键次序。

题4：堆顶最小是否说明数组已排序？答：否，兄弟及不同分支未被全序排列。

题5：先序1,2、后序2,1可唯一确定吗？答：不能，2既可为左孩子也可为右孩子。

检查树题先写根层次、高度单位、重复键策略和空树返回值。递归算法还要说明最坏树高及栈深；深链输入可能导致运行栈耗尽。

## TB17 先序中序重建与后序验证完整程序

<!-- kb-meta: {"id": "TB17", "aliases": [], "questions": ["先序中序重建与后序验证完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

输入键必须互异，两序列必须表示同一棵树。中序用map定位，构造时校验根是否落在当前子树范围，并拒绝重复和缺失。为确定性复杂度选map：O(n log n)时间、O(n)存储及最坏O(n)递归栈；使用unordered_map可改为期望O(n)。unique_ptr自动清理错误时已构造部分。

```cpp
#include <cassert>
#include <map>
#include <memory>
#include <stdexcept>
#include <vector>
struct Node{int x;std::unique_ptr<Node> left,right;explicit Node(int v):x(v){}};
using Ptr=std::unique_ptr<Node>;
Ptr build(const std::vector<int>& pre,const std::vector<int>& in) {
    if(pre.size()!=in.size()) throw std::invalid_argument("length");
    std::map<int,int> pos;
    for(int i=0;i<static_cast<int>(in.size());++i)
        if(!pos.emplace(in[i],i).second) throw std::invalid_argument("duplicate");
    int next=0;
    auto rec=[&](auto&& self,int l,int r)->Ptr {
        if(l==r) return nullptr;
        if(next==static_cast<int>(pre.size())) throw std::invalid_argument("missing root");
        int x=pre[next++];auto it=pos.find(x);
        if(it==pos.end() || it->second<l || it->second>=r) throw std::invalid_argument("inconsistent");
        int m=it->second;auto p=std::make_unique<Node>(x);
        p->left=self(self,l,m);p->right=self(self,m+1,r);return p;
    };
    return rec(rec,0,static_cast<int>(in.size()));
}
void post(const Ptr& p,std::vector<int>& out){
    if(!p) return;
    post(p->left,out);post(p->right,out);out.push_back(p->x);
}
int main(){
    auto p=build({1,2,4,3},{2,4,1,3});std::vector<int> out;post(p,out);
    assert((out==std::vector<int>{4,2,3,1}));assert(!build({},{}));
    bool bad=false;try{build({1,3,2},{2,1,3});}catch(const std::invalid_argument&){bad=true;}assert(bad);
}
```

## TB18 树状数组点增量与区间和完整程序

<!-- kb-meta: {"id": "TB18", "aliases": [], "questions": ["树状数组点增量与区间和完整程序的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "code", "prerequisites": []} -->

外部下标0基，内部i=index+1。lowbit=i&-i给出当前结点覆盖长度，更新沿i+=lowbit走向祖先，查询沿i-=lowbit拆分前缀。prefix(r)表示[0,r)；range(l,r)=prefix(r)-prefix(l)。单次O(log n)，空间O(n)。n及增量累加需在类型范围内，示例使用小规模。测试每次更新后所有区间与普通数组核对。

```cpp
#include <cassert>
#include <stdexcept>
#include <vector>
class Fenwick {
    int n;std::vector<long long> bit;
public:
    explicit Fenwick(int size):n(size),bit(checked(size)+1){}
    static int checked(int size){if(size<0 || size>10000000)throw std::invalid_argument("size");return size;}
    void add(int p,long long delta){
        if(p<0 || p>=n)throw std::out_of_range("index");
        for(int i=p+1;i<=n;i+=i&-i)bit[i]+=delta;
    }
    long long prefix(int r)const{
        if(r<0 || r>n)throw std::out_of_range("prefix");
        long long total=0;for(int i=r;i>0;i-=i&-i)total+=bit[i];return total;
    }
    long long range(int l,int r)const{
        if(l<0 || l>r || r>n)throw std::out_of_range("range");
        return prefix(r)-prefix(l);
    }
};
int main(){
    Fenwick f(8);std::vector<long long>a(8);
    for(int p=0;p<8;++p){a[p]+=p-3;f.add(p,p-3);
        for(int l=0;l<=8;++l)for(int r=l;r<=8;++r){long long sum=0;
            for(int i=l;i<r;++i)sum+=a[i];
            assert(f.range(l,r)==sum);}}
    assert(Fenwick(0).prefix(0)==0);
}
```

