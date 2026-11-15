# 查找与哈希知识库：从基础到进阶

版本：1.0.0；编写日期：2026-11-04。路线：查找语义 → 顺序与折半 → 边界与答案二分 → 哈希冲突和删除 → 有序索引、Trie与布隆过滤器。

适用：数据结构课程学习、C++17示例、RAG问答。内容为独立编写的教学材料，仿照栈与队列知识库的组织风格，不是课程PPT或扫描教材的转录，不附原教材页码。

通用约定：0基下标，区间默认左闭右开；n为元素数，V/E为图顶点/边数；空间复杂度默认辅助空间并另行说明输出。每个cpp代码块均为独立完整C++17程序，须分别编译，保留assert。输入规模及数值范围须满足各块前提，示例并非工业泛型库。

参考导航：[MIT算法课程主题目录](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/pages/lecture-notes/)；[C++字符串接口规范（持续更新的工作草案）](https://eel.is/c++draft/string.classes)。核对日期：2026-11-04。课程目录用于主题覆盖导航；本文推导、代码和练习为原创。只使用C++17已有接口，不把草案新增接口当作C++17。

## SH01 静态查找、动态查找与顺序查找

<!-- kb-meta: {"id": "SH01", "aliases": ["ASL", "顺序查找", "静态查找", "动态查找"], "questions": ["静态查找、动态查找与顺序查找的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

查找按键定位记录，先规定键是否唯一、未找到返回值和重复记录处理。静态查找只查询，动态查找还需插删。顺序查找无需排序，最坏O(n)，适合很短数据或不值得建索引的单次任务。成功查找的平均比较次数依赖各位置概率，等概率时为(n+1)/2，失败通常n次。

哨兵顺序查找可减少循环边界比较，但必须有合法额外位置或允许临时改写；不能越界把键写在未分配空间。建索引的成本要计入端到端代价：只查一次时先O(n log n)排序再O(log n)二分未必划算。

查找长度ASL是按访问概率加权的比较次数，不等同于内存访问耗时，更不自动意味着每个请求代价相同。

## SH02 折半查找、lower_bound和upper_bound

<!-- kb-meta: {"id": "SH02", "aliases": ["binary search", "折半查找", "lower_bound", "upper_bound"], "questions": ["二分如何处理重复值和不存在值？", "lower_bound返回末尾是什么意思？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

折半查找要求随机访问的有序序列（更一般地对判定谓词已分区）。在左闭右开[l,r)中找第一个a[i]≥x：mid=l+(r-l)/2；若a[mid]<x，l=mid+1，否则r=mid。终止l=r，可等于n。找第一个>x只需改变比较条件。

lower_bound返回第一个不小于x，upper_bound返回第一个大于x；两者之差为有序区间中x的出现次数。查精确值还需判断位置<n且a[pos]==x。空序列返回0，这不是“在下标0找到”。

vector上比较和随机访问均使整体O(log n)；在非随机访问迭代器上标准lower_bound的比较仍对数，但迭代移动可线性。有序链表不能因此获得数组同样的随机定位性能。

## SH03 二分左右边界完整程序

<!-- kb-meta: {"id": "SH03", "aliases": [], "questions": ["二分左右边界完整程序的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "code", "prerequisites": []} -->

lo/hi均在[0,n]，空输入无需特殊访问。测试用穷举非降短数组与逐项计数比较，涵盖所有相等、目标在两端之外及空数组。单次O(log n)时间O(1)额外空间，长度须可由int表示。

```cpp
#include <algorithm>
#include <cassert>
#include <vector>
int lower(const std::vector<int>& a,int x){int l=0,r=static_cast<int>(a.size());
 while(l<r){int m=l+(r-l)/2;if(a[m]<x)l=m+1;else r=m;}return l;}
int upper(const std::vector<int>& a,int x){int l=0,r=static_cast<int>(a.size());
 while(l<r){int m=l+(r-l)/2;if(a[m]<=x)l=m+1;else r=m;}return l;}
int main(){
 for(int n=0;n<=7;++n){int total=1;for(int i=0;i<n;++i)total*=3;
  for(int mask=0;mask<total;++mask){std::vector<int>a(n);int v=mask;
   for(int& z:a){z=v%3;v/=3;}std::sort(a.begin(),a.end());
   for(int x=-1;x<=3;++x){int l=0,u=0;for(int z:a){l+=(z<x);u+=(z<=x);}
    assert(lower(a,x)==l && upper(a,x)==u);}
  }
 }
}
```

## SH04 答案二分与单调可行性

<!-- kb-meta: {"id": "SH04", "aliases": ["binary search on answer", "参数搜索", "单调判定"], "questions": ["答案二分与单调可行性的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

答案二分不是在输入数组中查键，而是在有序候选域找可行性边界。必须证明若答案x可行，则更大的候选仍可行（或反向单调）。维护[l,r)或闭区间时要相应设计不变量，避免l=mid导致无法收缩。

例如按原顺序把正整数工作量分成至多k段，最小化最大段和。给定容量C可用贪心顺扫统计所需段数；C越大所需段数不增，因此可二分C，初始下界max(a)、上界sum(a)。每次判定O(n)，总O(n log(sum-max+1))。若元素可负，贪心判定可能不再成立。

浮点二分常固定迭代次数或误差阈值，要注意舍入、区间尺度和结果精度。单调性不足时不能仅凭题目出现“最小最大”就直接二分。

## SH05 哈希函数、装载因子与冲突处理

<!-- kb-meta: {"id": "SH05", "aliases": ["hash table", "装载因子", "链地址法", "开放定址", "rehash"], "questions": ["哈希函数、装载因子与冲突处理的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

哈希把键映射到桶，冲突指不同键落同桶，不等于键相等。键比较与哈希必须一致：相等键必须有相同哈希；大小写不敏感相等规则若配大小写敏感哈希会破坏容器要求。负数取模要处理负余数，不能直接拿负值做数组下标。

链地址法每桶维护链或动态集合，装载因子α=n/m可以大于1；适当分布下查询期望O(1+α)。开放定址把全部元素放表内，α必须小于1才能保证空位，线性探测有一次聚集，二次探测及双哈希有各自表长和步长覆盖条件。

最坏所有键冲突仍可线性查找，平均O(1)不是最坏保证。扩容rehash需重算桶位置，单次O(n)，几何扩容下通常讨论均摊成本。哈希值不能当持久唯一ID或安全加密摘要，稳定文档ID应另设。

## SH06 开放定址删除、墓碑与查找终止

<!-- kb-meta: {"id": "SH06", "aliases": ["tombstone", "墓碑", "开放定址删除"], "questions": ["开放定址删除、墓碑与查找终止的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

开放定址中空槽有两类：从未使用的EMPTY和曾使用后删除的DELETED墓碑。查询遇EMPTY可终止，遇DELETED须继续；否则同一探测链后面的键会被漏掉。插入可记住首个墓碑，但仍要继续查找已有同键，避免重复插入。

例表长5，线性探测插入键1、6，落槽1、2。删除1若把槽1变EMPTY，查6从槽1立即停止而误报；用墓碑才能到槽2。探测次数必须最多m次，避免表满或全墓碑时无限循环。

墓碑多会拖慢查询，即使有效元素装载因子很低，也需清理重建。删除回移可用于特定线性探测方案，但不能不加证明地套到任意探测规则。

## SH07 哈希频次与两数和完整程序

<!-- kb-meta: {"id": "SH07", "aliases": [], "questions": ["哈希频次与两数和完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

unordered_map用于已扫描前缀中的值到下标映射。先查补数再插当前值，防止同一元素被用两次，同时可处理重复值。计算补数用long long避免int减法溢出。平均O(n)时间、O(n)空间；哈希退化时最坏O(n²)。返回nullopt表示不存在。

```cpp
#include <cassert>
#include <optional>
#include <limits>
#include <unordered_map>
#include <utility>
#include <vector>
std::optional<std::pair<int,int>> twoSum(const std::vector<int>& a,long long target){
 if(target<2LL*std::numeric_limits<int>::min() || target>2LL*std::numeric_limits<int>::max()) return std::nullopt;
 std::unordered_map<long long,int> seen;
 for(int i=0;i<static_cast<int>(a.size());++i){
  // The early check keeps subtraction inside the supported numeric range.
  auto it=seen.find(target-static_cast<long long>(a[i]));
  if(it!=seen.end())return std::pair<int,int>{it->second,i};
  seen[a[i]]=i;
 }return std::nullopt;
}
int main(){
 auto p=twoSum({3,3},6);assert(p && p->first==0 && p->second==1);
 assert(!twoSum({3},6));assert(!twoSum({},0));
 p=twoSum({2,7,11,15},9);assert(p && p->first!=p->second);
}
```

## SH08 有序树、Trie与布隆过滤器

<!-- kb-meta: {"id": "SH08", "aliases": ["Bloom filter", "布隆过滤器", "前缀索引"], "questions": ["有序树、Trie与布隆过滤器的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

等值查询平均常数需求可选哈希；范围查询、顺序遍历和前驱后继更适合平衡搜索树；按字符前缀查询适合Trie；外存范围扫描考虑B+树。索引维护有插删成本，键改变时必须同步索引。

布隆过滤器用位数组和多个哈希：插入置位，查询任一位为0则肯定未插入，全部为1则可能存在。标准只增不删模型下允许误报、不应有漏报；直接清位删除可能误伤其他键，需计数布隆过滤器等扩展。预计n键、m位、k哈希，在均匀近似独立假设下误报率约(1-e^(-kn/m))^k。

布隆过滤器不能返回原记录，也不能作为数据库真实性来源；可放在昂贵查询之前作排除过滤。向量近邻检索、精确哈希查找和字符串模式匹配目标不同，不能互相当作等价检索。

## SH09 查找自测与反例

<!-- kb-meta: {"id": "SH09", "aliases": [], "questions": ["查找自测与反例的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "exercise", "prerequisites": []} -->

题1：[1,2,2,2,4]中x=2的lower/upper？答：1与4，出现3次。

题2：数组无序但只查一个值，必须先排序吗？答：否，顺序查找O(n)可能更合适；排序会改变位置语义，还需保留原下标。

题3：哈希表删除后能把槽直接清空吗？答：开放定址通常不行，应按墓碑或正确回移规则；链地址法可从桶链直接摘结点。

题4：布隆过滤器说存在就一定存在吗？答：不一定，有误报；说不存在的保证依赖只增及实现、哈希约定一致等前提。

题5：两个键哈希值相等说明什么？答：只有同哈希值，仍需完整相等比较。

排错顺序：核查有序/分区前提、边界和返回语义，再核查比较器、哈希一致性、删除策略及并发修改。

## SH10 Trie单词与前缀查询完整程序

<!-- kb-meta: {"id": "SH10", "aliases": [], "questions": ["Trie单词与前缀查询完整程序的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "code", "prerequisites": []} -->

仅接受ASCII小写a-z，空串允许作为词。每结点26个孩子下标，-1为空，结尾标志区分“路径存在”和“整个词存在”。插入先整体校验，避免非法字符导致半途写入。单词长度L时每次操作O(L)，空间O(26×总结点数)。代码使用索引避免vector扩容后的引用失效。

```cpp
#include <array>
#include <cassert>
#include <stdexcept>
#include <string>
#include <vector>
class Trie{
    struct Node{std::array<int,26> next;bool end=false;Node(){next.fill(-1);}};
    std::vector<Node> nodes{1};
    static void validate(const std::string& s){for(char c:s)if(c<'a'||c>'z')throw std::invalid_argument("alphabet");}
    int locate(const std::string& s)const{
        validate(s);int u=0;
        for(char c:s){u=nodes[u].next[c-'a'];if(u==-1)return -1;}return u;
    }
public:
    void insert(const std::string& s){
        validate(s);int u=0;
        for(char c:s){int k=c-'a';
            if(nodes[u].next[k]==-1){int id=static_cast<int>(nodes.size());
                nodes.emplace_back();nodes[u].next[k]=id;}
            u=nodes[u].next[k];
        }nodes[u].end=true;
    }
    bool word(const std::string& s)const{int u=locate(s);return u!=-1 && nodes[u].end;}
    bool prefix(const std::string& s)const{return locate(s)!=-1;}
};
int main(){
    Trie t;t.insert("apple");assert(t.word("apple") && !t.word("app") && t.prefix("app"));
    t.insert("app");t.insert("");assert(t.word("app") && t.word(""));assert(!t.prefix("banana"));
    bool bad=false;try{t.insert("A");}catch(const std::invalid_argument&){bad=true;}assert(bad);
}
```

