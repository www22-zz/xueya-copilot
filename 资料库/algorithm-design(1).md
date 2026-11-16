# 算法设计与复杂度知识库：从基础到进阶

版本：1.0.0；编写日期：2026-11-04。路线：问题与契约 → 渐近、递推与证明 → 递归分治 → 贪心 → 动态规划 → 回溯剪枝 → 字符串DP与数论应用。

适用：数据结构课程学习、C++17示例、RAG问答。内容为独立编写的教学材料，仿照栈与队列知识库的组织风格，不是课程PPT或扫描教材的转录，不附原教材页码。

通用约定：0基下标，区间默认左闭右开；n为元素数，V/E为图顶点/边数；空间复杂度默认辅助空间并另行说明输出。每个cpp代码块均为独立完整C++17程序，须分别编译，保留assert。输入规模及数值范围须满足各块前提，示例并非工业泛型库。

参考导航：[MIT算法课程主题目录](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/pages/lecture-notes/)；[C++字符串接口规范（持续更新的工作草案）](https://eel.is/c++draft/string.classes)。核对日期：2026-11-04。课程目录用于主题覆盖导航；本文推导、代码和练习为原创。只使用C++17已有接口，不把草案新增接口当作C++17。

## AD01 算法、输入契约与正确性证明

<!-- kb-meta: {"id": "AD01", "aliases": ["算法契约", "循环不变量", "归纳证明"], "questions": ["算法、输入契约与正确性证明的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

算法是解决明确问题的有限步骤，应定义输入、输出、终止条件及有效范围。代码能跑通一个样例不证明正确；常用循环不变量、数学归纳、交换论证和反证建立对所有合法输入的保证。

循环不变量证明分初始化、保持、终止三步。例如二分找第一个≥x，始终保持l左侧全<x、r及右侧全≥x，且候选边界在[l,r]中；区间缩小至l=r即得到答案。递归证明需给出基本情形并说明子问题严格变小。

把异常和不可行也设计成输出：空集合、nullopt、不可达标志与数值0不同。输入不满足契约时可拒绝，不应编造答案。教学示例会明确范围，但生产接口通常还需系统校验。

## AD02 O、Ω、Θ及最好、平均、最坏

<!-- kb-meta: {"id": "AD02", "aliases": ["big O", "Theta", "Omega", "均摊", "期望复杂度"], "questions": ["O、Ω、Θ及最好、平均、最坏的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

O是渐近上界，Ω是下界，Θ是同阶紧界，均描述足够大输入下的增长关系，忽略常数和低阶项。O(n²)的算法也可能有更紧的O(n)界，因此比较算法时尽量说明紧界或明确所用上界。

最好/最坏按同一规模输入中代价最小/最大分析，平均需给输入概率分布，期望可来自算法自身随机选择。均摊分析针对一串操作总成本，不依赖随机输入。动态数组几何扩容均摊O(1)尾插，但某次扩容O(n)。

空间需计递归栈。嵌套循环不必然平方：双指针均只前进n次时总O(n)，而对每个i从头扫j才可能O(n²)。分析时说明n表示字符数、字节数、顶点数还是数值大小。

## AD03 递推式、主定理与伪多项式

<!-- kb-meta: {"id": "AD03", "aliases": ["Master theorem", "递归树", "伪多项式", "输入位长"], "questions": ["递推式、主定理与伪多项式的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

分治常得T(n)=aT(n/b)+f(n)，比较f(n)与n^(log_b a)。相差多项式级时，较小f给Θ(n^log_b a)，同阶附适用条件可多一层log，较大f还需正规性条件。不能仅凭“有两个递归调用”就判指数。

例归并T(n)=2T(n/2)+Θ(n)=Θ(n log n)；二分T(n)=T(n/2)+Θ(1)=Θ(log n)；不记忆化斐波那契T(n)=T(n-1)+T(n-2)+Θ(1)指数增长，不符合等比例主定理形式。递归树与代入法可处理更广情况。

0/1背包O(nW)对容量W是多项式，但W的二进制输入长度仅Θ(log W)，故称伪多项式。把大整数算术都视为O(1)也可能低估真正代价，本文基础分析通常采用定长机器字模型。

## AD04 递归、分治与快速幂

<!-- kb-meta: {"id": "AD04", "aliases": ["divide and conquer", "exponentiation by squaring", "快速幂"], "questions": ["递归、分治与快速幂的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

递归是一种实现方式，分治是一种把问题拆成较独立子问题、递归求解再合并的策略。动态规划也可递归记忆化实现，递归并不自动等于分治。需要明确基本情形和子问题收缩，深度过大会耗尽调用栈。

快速幂利用x^(2k)=(x^k)^2，指数每次减半，非负整数指数只需O(log e)次乘法。模幂在每步乘法后取模，但若乘法本身溢出，事后取模不能补救。固定小模数可用long long安全乘两个余数，大模数需宽整数或安全乘法。

当e=0时通常约定结果为1 mod m，包括x=0；负指数要求存在模逆并另定义接口，不能直接右移负数循环。

## AD05 安全范围内的模快速幂完整程序

<!-- kb-meta: {"id": "AD05", "aliases": [], "questions": ["安全范围内的模快速幂完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

契约：指数非负，模数1..10^9，底数任意long long。先对底数取余再规范到非负，两个余数之积小于10^18可由long long表示。时间O(log(e+1))，空间O(1)。测试与小指数逐乘对照，涵盖负底数、模1和0次幂。

```cpp
#include <cassert>
#include <stdexcept>
long long power(long long x,long long e,long long m){
 if(e<0 || m<1 || m>1000000000LL)throw std::invalid_argument("range");
 x%=m;if(x<0)x+=m;long long r=1%m;
 while(e){if(e&1)r=r*x%m;x=x*x%m;e/=2;}return r;
}
int main(){
 for(long long m=1;m<=30;++m)for(long long x=-12;x<=12;++x){
  long long r=1%m,b=(x%m+m)%m;
  for(int e=0;e<=15;++e){assert(power(x,e,m)==r);r=r*b%m;}
 }
 assert(power(0,0,7)==1 && power(9,0,1)==0);
}
```

## AD06 贪心选择、交换论证与反例

<!-- kb-meta: {"id": "AD06", "aliases": ["greedy", "交换论证", "区间调度", "找零反例"], "questions": ["贪心选择、交换论证与反例的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

贪心每一步作当前最优选择，需要证明局部选择可扩展为全局最优。常见交换论证：取一个最优解，若它的第一步不是贪心选项，将其替换而不变差，再归纳剩余问题。

区间调度最大化互不重叠区间数量，按结束时间最早选可行区间是正确贪心。若最优首区间结束更晚，换成贪心区间不减少后续可选空间，因此可保留最优数量。若带不同收益而目标最大收益，此策略不成立，应做加权区间DP。

找零的“每次取最大币值”也不是通用：面额1,3,4，目标6，贪心得4+1+1三枚，最优3+3两枚。写贪心前先寻找反例，不要把熟悉的现实货币规则当数学保证。

## AD07 结束时间贪心区间调度完整程序

<!-- kb-meta: {"id": "AD07", "aliases": [], "questions": ["结束时间贪心区间调度完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

输入非空长度区间[l,r)，l<r，端点相接允许兼容。结束时间升序排序，选取起点≥上次终点的区间。目标是数量而非总时长或收益。时间O(n log n)，返回结果空间O(n)，排序栈由库实现决定。测试负端点、相接及反例中长区间的取舍。

```cpp
#include <algorithm>
#include <cassert>
#include <stdexcept>
#include <utility>
#include <vector>
std::vector<std::pair<int,int>> schedule(std::vector<std::pair<int,int>> a){
 for(auto [l,r]:a)if(l>=r)throw std::invalid_argument("empty interval");
 std::sort(a.begin(),a.end(),[](auto x,auto y){return x.second<y.second;});
 std::vector<std::pair<int,int>> out;
 for(auto p:a)if(out.empty() || p.first>=out.back().second)out.push_back(p);
 return out;
}
int main(){
 auto out=schedule({{0,10},{0,2},{2,4},{4,6}});assert(out.size()==3);
 assert(schedule({{-5,-3},{-3,-1},{-4,0}}).size()==2);
 assert(schedule({}).empty());
}
```

## AD08 动态规划：状态、转移、边界与恢复

<!-- kb-meta: {"id": "AD08", "aliases": ["dynamic programming", "memoization", "最优子结构", "状态转移"], "questions": ["动态规划：状态、转移、边界与恢复的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

DP适用于可用较小子问题描述、且存在重复状态的优化或计数。先定义状态含义，再列最后一步选择形成转移，确定边界、计算顺序与答案所在位置。最优子结构并不意味着任何贪心都正确。

记忆化搜索按需递归求状态；表格DP按依赖顺序迭代。时间约为可达状态数×每状态转移数，空间取决于同时保留哪些层。滚动数组只在后续不再依赖旧层时合法，若需恢复方案则还要前驱信息或重新计算。

例网格向右/下路径计数：dp[i][j]=dp[i-1][j]+dp[i][j-1]，障碍格为0，起点无障碍时1。最短费用初始化应区分不可达与0；“恰好装满”的背包不能把所有状态初始化为0，否则不可达容量被当合法解。

## AD09 0/1背包、完全背包与遍历方向

<!-- kb-meta: {"id": "AD09", "aliases": ["knapsack", "0/1背包", "完全背包", "倒序枚举"], "questions": ["0/1背包、完全背包与遍历方向的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

0/1背包每物品最多一次，容量W，重量w>0、价值v。dp[c]表示前若干物品在容量不超过c时的最大值，处理物品时c从W递减到w，令dp[c]=max(dp[c],dp[c-w]+v)。倒序使右侧仍来自上一物品层，避免重复取当前物品。

完全背包每物品可无限次，容量正序允许右侧使用当前物品层。计数问题又要区分组合与排列：外层物品、内层容量常数无序组合，外层容量、内层物品常数有序序列，必须根据状态含义证明。

时间O(nW)，空间O(W)，是伪多项式。0重量物品需单独约定，完全背包中0重正价值会导致无界最优。负重量不在标准模型内，不能直接套循环。

## AD10 0/1背包与穷举校验完整程序

<!-- kb-meta: {"id": "AD10", "aliases": [], "questions": ["0/1背包与穷举校验完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

输入重量为正、价值非负且累加不溢出long long，容量非负；目标不要求装满。测试逐个容量与所有物品子集比较，并用单物品容量可装两份的例子确认没有被重复取。时间O(nW)、空间O(W)。

```cpp
#include <algorithm>
#include <cassert>
#include <stdexcept>
#include <vector>
struct Item{int weight;long long value;};
long long knapsack(const std::vector<Item>& a,int W){
 if(W<0)throw std::invalid_argument("capacity");
 std::vector<long long> dp(W+1);
 for(auto [w,v]:a){if(w<=0 || v<0)throw std::invalid_argument("item");
  for(int c=W;c>=w;--c)dp[c]=std::max(dp[c],dp[c-w]+v);}
 return dp[W];
}
int main(){
 std::vector<Item>a{{2,3},{3,4},{4,8},{1,1}};
 for(int W=0;W<=12;++W){long long best=0;
  for(int mask=0;mask<(1<<a.size());++mask){int weight=0;long long value=0;
   for(int i=0;i<static_cast<int>(a.size());++i)if(mask&(1<<i)){weight+=a[i].weight;value+=a[i].value;}
   if(weight<=W)best=std::max(best,value);}
  assert(knapsack(a,W)==best);
 }
 assert(knapsack({{2,3}},4)==3 && knapsack({},0)==0);
}
```

## AD11 LCS、编辑距离与最长递增子序列

<!-- kb-meta: {"id": "AD11", "aliases": ["LCS", "edit distance", "Levenshtein", "LIS", "最长公共子串"], "questions": ["LCS、编辑距离与最长递增子序列的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

最长公共子序列LCS状态dp[i][j]表示两串前i、j项的LCS长度；末字符相等取dp[i-1][j-1]+1，否则max(dp[i-1][j],dp[i][j-1])。时间O(nm)，完整表空间O(nm)，只求长度可滚动到O(min(n,m))。最长公共子串要求连续，失配应清0，且答案取所有状态最大，不能混用LCS递推。

编辑距离若插删替换代价均1，则状态取删dp[i-1][j]+1、插dp[i][j-1]+1、替换dp[i-1][j-1]+(a!=b)最小值；边界dp[i][0]=i、dp[0][j]=j。UTF-8逐字节编辑与按字符编辑不同。

LIS严格递增可维护tails[len-1]为该长度序列最小末值，每项用lower_bound替换或扩展，O(n log n)。若求非降改upper_bound。tails通常不是原数组的一条合法答案，恢复需要记录前驱与原位置。

## AD12 LCS与编辑距离完整程序

<!-- kb-meta: {"id": "AD12", "aliases": [], "questions": ["LCS与编辑距离完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

使用完整二维DP，方便解释依赖和边界。每个状态在读取之前已计算，字符按字节相等比较。时间O(nm)，空间O(nm)。测试空串、相同串及非连续LCS，明确LCS不是子串。

```cpp
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>
int lcs(const std::string& a,const std::string& b){
 int n=static_cast<int>(a.size()),m=static_cast<int>(b.size());
 std::vector<std::vector<int>>d(n+1,std::vector<int>(m+1));
 for(int i=1;i<=n;++i)for(int j=1;j<=m;++j)
  d[i][j]=a[i-1]==b[j-1]?d[i-1][j-1]+1:std::max(d[i-1][j],d[i][j-1]);
 return d[n][m];
}
int edit(const std::string& a,const std::string& b){
 int n=static_cast<int>(a.size()),m=static_cast<int>(b.size());
 std::vector<std::vector<int>>d(n+1,std::vector<int>(m+1));
 for(int i=0;i<=n;++i)d[i][0]=i;
 for(int j=0;j<=m;++j)d[0][j]=j;
 for(int i=1;i<=n;++i)for(int j=1;j<=m;++j)
  d[i][j]=std::min({d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(a[i-1]!=b[j-1])});
 return d[n][m];
}
int main(){
 assert(lcs("abcde","ace")==3 && lcs("","x")==0);
 assert(edit("kitten","sitting")==3 && edit("","abc")==3);
 assert(edit("same","same")==0 && lcs("aaaa","aa")==2);
}
```

## AD13 回溯、剪枝、分支限界与状态压缩

<!-- kb-meta: {"id": "AD13", "aliases": ["backtracking", "branch and bound", "bitmask DP", "TSP"], "questions": ["回溯、剪枝、分支限界与状态压缩的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

回溯按选择树枚举“选择—递归—撤销”，用合法性剪枝排除不可能完成的分支。排列使用used数组避免同一位置重复；输入含重复值时通常排序后跳过同层重复选择，不能把不同层也一律禁用。

分支限界在最优化中维护当前最好解，用乐观上界（最大化）或乐观下界（最小化）证明某分支不可能更好时剪掉。界必须方向正确且可靠，否则会误删最优解。最坏枚举仍可能指数，剪枝快不等于多项式保证。

状态压缩用位掩码表示小集合，如旅行商DP[mask][v]表示从固定起点访问mask后停在v的最小费用，常O(2^n n²)时间O(2^n n)空间。位移需在类型位宽内，1<<n对较大n可能溢出；状态数指数增长使其只适合小n。

## AD14 N皇后回溯完整程序

<!-- kb-meta: {"id": "AD14", "aliases": [], "questions": ["N皇后回溯完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

逐行放一个皇后，用列与两类对角线标记冲突，回溯后撤销。主对角编号r-c+n-1，副对角r+c，均在0..2n-2内。限定0≤n≤12以限制示例计算量，n=0约定有一种空摆法。忽略对角剪枝时，按不重复列枚举的部分排列数为O(n!)，每个非叶调用还要扫描n列，因此给出保守时间上界O(n·n!)；剪枝可减少实际搜索。辅助O(n)，不保存方案。测试已知计数而非仅检查能找到一个解。

```cpp
#include <cassert>
#include <stdexcept>
#include <vector>
long long dfs(int r,int n,std::vector<bool>& col,std::vector<bool>& d1,std::vector<bool>& d2){
 if(r==n)return 1;
 long long total=0;
 for(int c=0;c<n;++c){int x=r-c+n-1,y=r+c;
  if(col[c] || d1[x] || d2[y])continue;
  col[c]=d1[x]=d2[y]=true;total+=dfs(r+1,n,col,d1,d2);col[c]=d1[x]=d2[y]=false;
 }return total;
}
long long queens(int n){
 if(n<0 || n>12)throw std::invalid_argument("n range");
 if(n==0)return 1;
 std::vector<bool> col(n),d1(2*n-1),d2(2*n-1);return dfs(0,n,col,d1,d2);
}
int main(){assert(queens(0)==1 && queens(1)==1 && queens(2)==0);
 assert(queens(4)==2 && queens(8)==92);}
```

## AD15 双指针、滑动窗口与前缀和

<!-- kb-meta: {"id": "AD15", "aliases": ["two pointers", "sliding window", "前缀和哈希"], "questions": ["双指针、滑动窗口与前缀和的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "concept", "prerequisites": []} -->

同向双指针可维护连续窗口，若左右边界各只移动n次，总O(n)，即使有嵌套while也非必然平方。例正数数组求和至少S的最短窗口，右扩增加和，满足后左缩；负数会破坏和的单调性，不能继续套用同一规则。

前缀和P[i]=a[0]+…+a[i-1]，区间[l,r)和为P[r]-P[l]。要统计和为K的子数组，可扫描当前P，查询此前P-K的出现次数，再记录P；初始化频次P=0为1，避免漏掉从首项开始的子数组。哈希方案平均O(n)，适用于含负数，计数可能达到n(n+1)/2。

固定窗口极值用单调队列而非只维护一个当前最大值，过期时才能快速找到次优候选。最小覆盖字符窗口需同时维护频次与满足条件计数，不能把“种类齐全”等同于每种数量都够。

## AD16 欧几里得算法、筛法与数值边界

<!-- kb-meta: {"id": "AD16", "aliases": ["gcd", "lcm", "Euclid", "埃氏筛", "整数溢出"], "questions": ["欧几里得算法、筛法与数值边界的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "concept", "prerequisites": []} -->

欧几里得算法利用gcd(a,b)=gcd(b,a mod b)，对非负整数循环到b=0，常用算术模型下O(log min(a,b))次取模；gcd(0,0)通常约定0。lcm应先a/gcd(a,b)再乘b以减少溢出风险，但仍需检查结果范围。

埃拉托斯特尼筛初始化2..N为候选，遇素数p从p²起标记倍数，时间O(N log log N)、空间O(N)的常见界；p²计算需宽类型或用p≤N/p避免溢出。0和1不是素数，N<2应正确处理。

整数加乘溢出可能让正确递推得出错误结果；有符号C++整数溢出属于未定义行为。大数计数可使用任意精度库或明确取模，取模只能保留模意义的结果，不能拿模后的值比较原大小。

## AD17 设计方法自测与问题求解路线

<!-- kb-meta: {"id": "AD17", "aliases": [], "questions": ["设计方法自测与问题求解路线的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "exercise", "prerequisites": []} -->

题1：0/1背包容量正序会怎样？答：当前物品可被本轮多次使用，语义变成完全背包。

题2：LCS与最长公共子串的失配转移相同吗？答：不同，LCS可跳字符取相邻最优，子串连续长度失配应归0。

题3：滑动窗口求和含负数还能用正数时的收缩规则吗？答：通常不能，需其他结构或前缀方法。

题4：O(nW)背包是输入位长多项式吗？答：一般不是，W可对log W指数大，属于伪多项式。

求解路线：写清状态和目标 → 确定规模与允许代价 → 寻找结构/单调性 → 证明转移或贪心 → 设计边界 → 用小规模穷举交叉核对 → 再看性能。遇到NP困难问题应考虑输入规模、特例、近似或指数算法，不能把无法证明的启发式称精确保证。

