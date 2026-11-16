# 字符串与多维数组知识库：从基础到进阶

版本：1.0.0；编写日期：2026-11-04。路线：字符与串 → 基本操作 → KMP与进阶匹配 → 多维地址 → 特殊矩阵、稀疏矩阵 → 前缀和与应用。

适用：数据结构课程学习、C++17示例、RAG问答。内容为独立编写的教学材料，仿照栈与队列知识库的组织风格，不是课程PPT或扫描教材的转录，不附原教材页码。

通用约定：0基下标，区间默认左闭右开；n为元素数，V/E为图顶点/边数；空间复杂度默认辅助空间并另行说明输出。每个cpp代码块均为独立完整C++17程序，须分别编译，保留assert。输入规模及数值范围须满足各块前提，示例并非工业泛型库。

参考导航：[MIT算法课程主题目录](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/pages/lecture-notes/)；[C++字符串接口规范（持续更新的工作草案）](https://eel.is/c++draft/string.classes)。核对日期：2026-11-04。课程目录用于主题覆盖导航；本文推导、代码和练习为原创。只使用C++17已有接口，不把草案新增接口当作C++17。

## SA01 字符串、字符、子串与子序列

<!-- kb-meta: {"id": "SA01", "aliases": ["string", "substring", "subsequence", "空串"], "questions": ["子串和子序列有什么区别？", "空串与空格串相同吗？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

字符串是有限字符序列，长度为零的是空串。空格串包含真实字符，不等于空串。子串要求连续；子序列只要求相对顺序。例如“abc”是“axbyc”的子序列，但不是其子串。前缀从首字符开始，后缀到末字符结束；真前缀/真后缀不等于整个串。

本文统一从0下标开始，区间写成左闭右开[l,r)，长度r-l；空区间满足l=r。求匹配位置时返回起始下标，而不是第几个字符；未找到用-1或npos，必须说明接口约定。字符串相等要求长度及对应字符都相等。

例：“ababa”的长度为5，“aba”在下标0、2出现，两次可以重叠。常见误区是把非连续匹配当子串，或把位置0误判为失败。

## SA02 C风格字符串、std::string与Unicode

<!-- kb-meta: {"id": "SA02", "aliases": ["C字符串", "零终止", "UTF-8", "Unicode"], "questions": ["strlen、sizeof、string.size有何区别？", "为什么中文字符串长度不是汉字数量？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

C风格字符串以首个\0字节作为结束标志，字符数组必须为终止符预留空间。char a[3]={'a','b','c'}不是合法的以零结尾字符串，不能交给要求终止符的strlen。strlen需要扫描，通常O(n)；sizeof数组得到的是数组字节数，两者含义不同。

C++17的std::string管理长度和存储，可以包含内嵌零字节。size()为O(1)，不靠扫描终止符求长度。读取普通字符使用0≤i<size()；at(i)在越界时抛异常。c_str()提供零结尾视图，不能在对象失效或修改导致地址失效后继续使用。

std::string按char存储，UTF-8中文的size()通常是字节数，不是汉字数。按字节反转会破坏多字节编码；即使按Unicode码点处理，组合字符和表情仍可能由多个码点构成。本文匹配例程针对字节序列/ASCII；人类语言检索应另做编码、规范化和分词。

## SA03 C++17字符串基本操作完整程序

<!-- kb-meta: {"id": "SA03", "aliases": [], "questions": ["C++17字符串基本操作完整程序的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "code", "prerequisites": []} -->

std::string的substr(pos,count)第二参数是长度；find返回size_type，无结果为npos，不能先窄化为int再判断。插入、删除会移动后缀，最坏线性；substr复制的时间与结果长度线性相关。本例断言覆盖内嵌零字节及未找到情形。

```cpp
#include <cassert>
#include <string>
int main() {
    std::string s = "abc";
    s.insert(1, "XY");
    assert(s == "aXYbc");
    s.erase(1, 2);
    assert(s.substr(1, 2) == "bc");
    assert(s.find("z") == std::string::npos);
    std::string binary("a\0b", 3);
    assert(binary.size() == 3 && binary[1] == '\0');
    assert(s.substr(s.size()).empty());
}
```

## SA04 朴素模式匹配与边界

<!-- kb-meta: {"id": "SA04", "aliases": ["BF匹配", "暴力匹配"], "questions": ["朴素字符串匹配为什么最坏O(nm)？", "空模式应返回什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

在长度n的文本T中找长度m的模式P，朴素算法依次尝试每个起点i，比较T[i+j]与P[j]；失配后起点右移一格。最坏O((n-m+1)m)，通常写O(nm)，额外空间O(1)。当m>n时直接无匹配，避免无符号n-m下溢。

本知识库规定空模式首次出现在0；若要列出所有空模式位置，则为0到n的n+1个边界。这是接口选择，使用外部系统时必须核对其约定。例：T=aaaaab、P=aaab，多次长前缀比较导致重复工作，KMP通过保留已匹配信息避免回退文本指针。

## SA05 KMP前缀函数与失配回退

<!-- kb-meta: {"id": "SA05", "aliases": ["KMP", "prefix function", "next数组", "前缀函数"], "questions": ["KMP的pi与next数组能直接混用吗？", "KMP如何找到重叠匹配？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

前缀函数pi[i]是P[0..i]的最长相等真前缀和真后缀的长度；pi[0]=0。它存长度，不是下一个字符的下标；部分教材next使用-1起始约定，不能直接混用公式。

计算pi时令j=pi[i-1]；若P[i]与P[j]失配，反复令j=pi[j-1]，直到可扩展或j=0。若相等再j++。扫描文本时同样回退j，文本下标始终向前。匹配长度达到m说明在i-m+1处找到，随后j=pi[m-1]可保留重叠候选。

例：模式ababaca的pi为[0,0,1,2,3,0,1]。不能失配就j--，那样既不保证候选合法，也失去线性保证。前缀构建O(m)，搜索O(n)，总额外空间O(m)。线性原因是j的累计增加和回退次数都受扫描长度约束。

## SA06 KMP全部匹配完整程序

<!-- kb-meta: {"id": "SA06", "aliases": [], "questions": ["KMP全部匹配完整程序的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "code", "prerequisites": []} -->

输入按字节比较，返回所有匹配的0基起点。空模式返回所有边界，模式长于文本返回空集合。代码用匹配后回退保留重叠；测试将短二进制字母表中的所有文本和模式与朴素实现交叉比较。复杂度O(n+m+输出数)，辅助空间O(m)，不含输出。为教学简洁，长度要求可由int表示。

```cpp
#include <cassert>
#include <string>
#include <vector>
std::vector<int> match(const std::string& t, const std::string& p) {
    int n = static_cast<int>(t.size()), m = static_cast<int>(p.size());
    std::vector<int> out;
    if (!m) { for (int i=0;i<=n;++i) out.push_back(i); return out; }
    std::vector<int> pi(m);
    for (int i=1,j=0;i<m;++i) {
        while (j && p[i]!=p[j]) j=pi[j-1];
        if (p[i]==p[j]) ++j;
        pi[i]=j;
    }
    for (int i=0,j=0;i<n;++i) {
        while (j && t[i]!=p[j]) j=pi[j-1];
        if (t[i]==p[j]) ++j;
        if (j==m) { out.push_back(i-m+1); j=pi[j-1]; }
    }
    return out;
}
std::string word(int mask, int n) {
    std::string s(n, 'a');
    for(int i=0;i<n;++i) if(mask & (1<<i)) s[i]='b';
    return s;
}
int main() {
    assert((match("ababa","aba")==std::vector<int>{0,2}));
    for(int n=0;n<=6;++n) for(int x=0;x<(1<<n);++x)
      for(int m=0;m<=4;++m) for(int y=0;y<(1<<m);++y) {
        auto t=word(x,n), p=word(y,m);
        std::vector<int> expected;
        for(int i=0;i+m<=n;++i) if(t.substr(i,m)==p) expected.push_back(i);
        assert(match(t,p)==expected);
      }
}
```

## SA07 进阶字符串索引：Trie、AC自动机、哈希与后缀结构

<!-- kb-meta: {"id": "SA07", "aliases": ["Trie", "AC自动机", "Rabin-Karp", "suffix array", "LCP"], "questions": ["进阶字符串索引：Trie、AC自动机、哈希与后缀结构的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

Trie把键的公共前缀共享成路径，长度L的单词查询通常需O(L)次字符转移；固定字母表数组转移占空间大，映射转移增加查找成本。AC自动机在Trie上添加失败指针，适合多个模式同时扫描文本；固定有限字母表且完整转移预处理后，扫描可做到O(n+输出数)，不等于忽略全部输出。

滚动哈希把子串映射为数值，预处理前缀哈希后可O(1)计算某区间哈希；必须保持相同模数、底数及长度约定。哈希相同不保证原串相同；双哈希降低碰撞概率但不是确定性证明，需要时回查原文。

后缀数组按字典序排列所有非空后缀起点，配合LCP支持重复子串等问题；常见倍增实现O(n log²n)，使用计数/基数排序可O(n log n)，不可不看实现就标同一复杂度。后缀自动机可表示所有子串，概念与完整实现超出本节代码范围。选择：单模式KMP、多模式AC、前缀词典Trie、静态全文子串索引考虑后缀结构。

## SA08 多维数组、行优先与地址公式

<!-- kb-meta: {"id": "SA08", "aliases": ["row-major", "column-major", "stride", "多维地址计算"], "questions": ["二维数组按行优先存储的地址如何计算？", "vector<vector<int>>是否整体连续？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

多维数组的逻辑元素由多个下标确定。设二维数组A有R行C列，元素宽w字节，首元素地址B，下界分别为lr、lc。行优先地址为B+((i-lr)C+(j-lc))w；列优先为B+((j-lc)R+(i-lr))w，前提是存储连续且下标合法。

三维连续行优先数组维长d0,d1,d2，偏移为((i*d1)+j)*d2+k。一般维数用各维步长stride描述。地址计算前需防止乘法溢出。C++原生int a[R][C]按行连续，但vector<vector<int>>各行分别分配，不能把跨行元素当作一整段连续内存。

例：3×4数组每元素4字节、B=1000、0基下标，A[2][1]偏移(2×4+1)×4=36，地址1036。问地址必须先知道维长、下界、元素宽和布局，不能仅凭下标猜测。

## SA09 对称矩阵、三角矩阵和带状矩阵压缩

<!-- kb-meta: {"id": "SA09", "aliases": ["特殊矩阵", "三角矩阵", "三对角矩阵", "对称矩阵压缩"], "questions": ["对称矩阵、三角矩阵和带状矩阵压缩的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

n×n对称矩阵满足A[i][j]=A[j][i]，可只存下三角含主对角线，共n(n+1)/2项。0基按行压缩时先令r=max(i,j)、c=min(i,j)，索引k=r(r+1)/2+c。公式只适用于此布局；1基教材公式需转换。

下三角矩阵的上半区可能是统一常数，压缩时下三角数据与常数要分开；对称矩阵是镜像相等，两者性质不同。三对角矩阵只允许|i-j|≤1处可能非零，n≥1时有效位置数为3n-2；第0行2项（n=1时仅1项），中间行3项，末行2项。带宽固定时可O(n)存储。

压缩节省空间但改变访问公式；若只看非零值却未记录下标，就无法恢复矩阵。计算n(n+1)/2需要足够宽整数，并检查容量。

## SA10 稀疏矩阵COO、CSR与快速转置

<!-- kb-meta: {"id": "SA10", "aliases": ["COO", "CSR", "CSC", "三元组", "快速转置"], "questions": ["稀疏矩阵COO、CSR与快速转置的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

稀疏矩阵有大量零元素，按非零项存储可节省空间。COO三元组(row,col,value)便于追加；同坐标可能重复，应先规定合并（常见求和）及合并为0后是否移除。仅记录非零值而没有坐标无法恢复原矩阵。

CSR包含values、col_index、row_ptr；row_ptr长R+1，第r行非零项位于[row_ptr[r],row_ptr[r+1])。末项row_ptr[R]=nnz，各行可为空。若列下标有序，行内查找更方便。总空间O(R+nnz)，矩阵向量乘法O(R+nnz)。CSC相当于按列组织。

COO快速转置先按原列计数，再做前缀和算出目标每行起点，最后把(r,c,v)写成(c,r,v)，O(C+nnz)时间和O(C+nnz)结果及辅助空间。普通逐列扫描COO可达O(C·nnz)。当矩阵较密时压缩索引开销可能超过收益。

## SA11 连续矩阵与二维前缀和完整程序

<!-- kb-meta: {"id": "SA11", "aliases": [], "questions": ["连续矩阵与二维前缀和完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

前缀和P[i][j]表示原矩阵[0,i)×[0,j)的和，额外补零行零列。矩形[r1,r2)×[c1,c2)用容斥P[r2][c2]-P[r1][c2]-P[r2][c1]+P[r1][c1]。预处理O(RC)，每次查询O(1)，空间O(RC)。示例验证所有矩形（含空矩形）与逐项求和一致。long long仍有范围限制，输入须保证所有中间和不溢出。

```cpp
#include <cassert>
#include <vector>
int main() {
    int R=3,C=4;
    std::vector<long long> a{1,2,3,4,5,-6,7,8,9,10,11,12};
    std::vector<std::vector<long long>> p(R+1,std::vector<long long>(C+1));
    for(int i=0;i<R;++i) for(int j=0;j<C;++j)
      p[i+1][j+1]=a[i*C+j]+p[i][j+1]+p[i+1][j]-p[i][j];
    for(int r1=0;r1<=R;++r1) for(int r2=r1;r2<=R;++r2)
      for(int c1=0;c1<=C;++c1) for(int c2=c1;c2<=C;++c2) {
        long long direct=0;
        for(int i=r1;i<r2;++i) for(int j=c1;j<c2;++j) direct+=a[i*C+j];
        assert(p[r2][c2]-p[r1][c2]-p[r2][c1]+p[r1][c1]==direct);
      }
}
```

## SA12 二维差分、矩阵乘法与缓存局部性

<!-- kb-meta: {"id": "SA12", "aliases": ["二维差分", "矩阵乘法", "缓存局部性"], "questions": ["二维差分、矩阵乘法与缓存局部性的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

若需多次给矩形整体加v、最后统一恢复，二维差分在[r1,r2)×[c1,c2)的四角分别加v、减v、减v、加v，再沿两维前缀累加。每次更新O(1)，最终恢复O(RC)。若更新查询交错且要求在线，应考虑二维树状数组等结构，不能每次完整恢复仍宣称O(1)。

矩阵乘法A为R×K、B为K×C，结果为R×C，C[i][j]=ΣA[i][k]B[k][j]。普通算法O(RKC)，不能用对应元素相乘代替。行优先情况下i-k-j循环常更便于连续访问B的行；分块乘法通过复用缓存提高实际速度，但普通固定分块不改变立方阶。

图像积分图、地图区域统计适合二维前缀和；稀疏线性系统适合CSR；密集数值计算优先考虑成熟矩阵库。选择存储时同时考虑非零比例、访问模式和修改频率。

## SA13 自测、反例与解题检查

<!-- kb-meta: {"id": "SA13", "aliases": [], "questions": ["字符串和多维数组有哪些典型易错题？"], "level": "基础", "kind": "exercise", "prerequisites": []} -->

题1：ab是acb的子串吗？答：不是，缺少连续性，但它是子序列。

题2：aaaa中aa有几次重叠匹配？答：3次，起点0、1、2；找到后直接把模式游标清零会漏掉重叠。

题3：0基、5列、行优先、元素8字节，A[2][3]离首元素多远？答：(2×5+3)×8=104字节。

题4：4阶对称矩阵下三角按行压缩，A[1][3]在哪？答：映射到(3,1)，索引3×4/2+1=7。

题5：CSR的row_ptr=[0,2,2,5]说明什么？答：3行，第二行空，总非零项5。具体值与列位置仍需其他数组。

解题依次确认字符单位、区间与下标、空输入规则、矩阵布局和数值范围；字符串哈希的等值结论还要考虑碰撞。

## SA14 COO快速转置完整程序

<!-- kb-meta: {"id": "SA14", "aliases": [], "questions": ["COO快速转置完整程序的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "code", "prerequisites": []} -->

输入COO可乱序、可有重复坐标；本例只转置，保留每条记录且不合并重复，矩阵数值语义按重复项求和解释。先统计原各列记录数，再用前缀起点定位；输出按新行分组。时间O(C+nnz)，额外O(C+nnz)含输出。测试双次转置按坐标排序后恢复全部原记录，并验证空列。

```cpp
#include <algorithm>
#include <cassert>
#include <stdexcept>
#include <tuple>
#include <vector>
struct Entry {int r,c,v;};
std::vector<Entry> transpose(int R,int C,const std::vector<Entry>& a) {
    if(R<0 || C<0) throw std::invalid_argument("shape");
    std::vector<int> next(C+1);
    for(auto e:a) {
        if(e.r<0 || e.r>=R || e.c<0 || e.c>=C) throw std::invalid_argument("coordinate");
        ++next[e.c+1];
    }
    for(int j=1;j<=C;++j) next[j]+=next[j-1];
    std::vector<Entry> b(a.size());
    for(auto e:a) b[next[e.c]++]={e.c,e.r,e.v};
    return b;
}
int main() {
    std::vector<Entry> a{{2,3,7},{0,1,4},{0,1,5}};
    auto b=transpose(3,5,a); auto c=transpose(5,3,b);
    auto less=[](Entry x,Entry y){return std::tie(x.r,x.c,x.v)<std::tie(y.r,y.c,y.v);};
    std::sort(a.begin(),a.end(),less); std::sort(c.begin(),c.end(),less);
    assert(a.size()==c.size());
    for(unsigned i=0;i<a.size();++i) assert(a[i].r==c[i].r && a[i].c==c[i].c && a[i].v==c[i].v);
    assert(transpose(0,4,{}).empty());
}
```

