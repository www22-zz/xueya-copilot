# 排序知识库：从基础到进阶

版本：1.0.0；编写日期：2026-11-04。路线：排序指标 → 插入与交换 → 选择与堆 → 归并与快速 → 非比较排序 → 外部排序、Top-K和选型。

适用：数据结构课程学习、C++17示例、RAG问答。内容为独立编写的教学材料，仿照栈与队列知识库的组织风格，不是课程PPT或扫描教材的转录，不附原教材页码。

通用约定：0基下标，区间默认左闭右开；n为元素数，V/E为图顶点/边数；空间复杂度默认辅助空间并另行说明输出。每个cpp代码块均为独立完整C++17程序，须分别编译，保留assert。输入规模及数值范围须满足各块前提，示例并非工业泛型库。

参考导航：[MIT算法课程主题目录](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/pages/lecture-notes/)；[C++字符串接口规范（持续更新的工作草案）](https://eel.is/c++draft/string.classes)。核对日期：2026-11-04。课程目录用于主题覆盖导航；本文推导、代码和练习为原创。只使用C++17已有接口，不把草案新增接口当作C++17。

## SO01 稳定性、原地排序与比较下界

<!-- kb-meta: {"id": "SO01", "aliases": ["stable sort", "in-place", "比较排序下界", "严格弱序"], "questions": ["稳定性、原地排序与比较下界的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

排序按键建立非降或非升次序。稳定排序保持相等键记录原来的相对顺序；键都不重复时，单个样例无法体现稳定性。原地通常指仅常数额外数据空间，但快速排序的递归栈要另计，不同教材可能有宽松定义。

基于比较的一般排序在最坏情况下需要Ω(n log n)次比较，可由n!种排列对应决策树叶子、树高至少log2(n!)得到。计数/基数排序利用键域信息，不受“仅靠比较”的下界约束；这不表示任意对象都能线性排序。

时间应区分最好、平均、最坏；空间应注明输出、辅助数组与递归栈。比较器需满足严格弱序，使用<=作为std::sort比较器会破坏约定；浮点NaN也需专门规定排序规则。

## SO02 直接插入、折半插入与希尔排序

<!-- kb-meta: {"id": "SO02", "aliases": ["insertion sort", "Shell sort", "折半插入", "希尔排序"], "questions": ["直接插入、折半插入与希尔排序的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

直接插入维护已排序前缀，将新元素插入正确位置。只在前项严格大于当前键时右移可保持稳定；最好已排序O(n)，平均和最坏O(n²)，额外O(1)。适合小数组和近乎有序输入。

折半插入用二分找插入位置，比较次数可降至O(n log n)，但数组移动最坏仍O(n²)。为稳定应插在相等键之后，即使用upper_bound语义；使用lower_bound可能把新相等记录放到旧记录前。

希尔排序按增量分组插入并逐步缩小到1，常明显减少移动，但通常不稳定，复杂度依赖增量序列，不能统一写O(n log n)。例如朴素折半增量存在平方级最坏情形；选用特定序列需说明其已知界。

## SO03 稳定插入排序完整程序

<!-- kb-meta: {"id": "SO03", "aliases": [], "questions": ["稳定插入排序完整程序的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "code", "prerequisites": []} -->

记录含key和原位置id，测试验证相等键id顺序保持，避免只比较数值而漏掉稳定性错误。内层从j=i开始，检查j>0后才能访问j-1。时间最坏O(n²)、最好O(n)，辅助空间O(1)。

```cpp
#include <cassert>
#include <vector>
struct Item{int key,id;};
void insertion(std::vector<Item>& a){
 for(int i=1;i<static_cast<int>(a.size());++i){Item x=a[i];int j=i;
  while(j>0 && a[j-1].key>x.key){a[j]=a[j-1];--j;}a[j]=x;}
}
int main(){
 std::vector<Item>a{{2,0},{1,1},{2,2},{1,3}};insertion(a);
 assert(a[0].id==1 && a[1].id==3 && a[2].id==0 && a[3].id==2);
 std::vector<Item>b;insertion(b);assert(b.empty());
}
```

## SO04 冒泡排序与简单选择排序

<!-- kb-meta: {"id": "SO04", "aliases": ["bubble sort", "selection sort", "提前终止"], "questions": ["冒泡排序与简单选择排序的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

冒泡每轮交换相邻逆序项，使一个极值归位。只在严格逆序时交换可稳定；增加本轮无交换就终止的标志后，已排序最好O(n)，平均/最坏O(n²)，空间O(1)。没有该提前终止实现就不能声称最好线性。

简单选择排序每轮从未排区选最小值并与首项交换，比较次数始终Θ(n²)，交换仅O(n)次，空间O(1)，通常不稳定。反例记录[(2,A),(2,B),(1,C)]，首轮交换变[(1,C),(2,B),(2,A)]，相等键次序被反转。

写入代价很高时选择排序的少交换有一定意义；常规较大数据仍优先O(n log n)方法。稳定性是算法具体实现的性质，不只看算法名称和一个输出样例。

## SO05 堆排序与优先队列Top-K

<!-- kb-meta: {"id": "SO05", "aliases": ["heap sort", "Top-K", "quickselect", "nth_element"], "questions": ["堆排序与优先队列Top-K的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

升序堆排序先建最大堆，再将根与未排区末项交换，缩小堆区并从根下沉。建堆O(n)，每次调整O(log n)，总最坏O(n log n)，数组内迭代实现额外O(1)，通常不稳定。

流式保留最大的k项可维护大小k的最小堆，新项大于堆顶才替换。扫描O(n log k)，空间O(k)，最终若还要求输出有序再付O(k log k)。k=0应直接返回空；k>n的行为要规定是报错还是取全部。

求第k小可用nth_element平均线性选择后再按需处理；它只保证分区，不保证两侧内部有序。Quickselect普通实现最坏O(n²)，随机化仅改善期望；要求确定性最坏线性需另用中位数的中位数等方案。

## SO06 归并排序、稳定合并与逆序对

<!-- kb-meta: {"id": "SO06", "aliases": ["merge sort", "逆序对", "稳定归并"], "questions": ["归并排序、稳定合并与逆序对的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

归并排序将数组二分，递归排序两侧再合并。合并相等时先取左项保证稳定。递推T(n)=2T(n/2)+Θ(n)得到Θ(n log n)，数组版辅助O(n)，递归栈O(log n)被辅助数组规模覆盖。自底向上归并可避免递归。

逆序对是i<j且a[i]>a[j]。合并时若右项严格小于左项，则当前左项及剩余左侧都大于它，增加mid-i；相等不计逆序。计数最多n(n-1)/2，应使用足够宽整数。

链表归并可用接链实现合并，不需O(n)数组缓冲，但递归栈仍要计；非随机访问链表通常更适合归并而非依赖随机下标的快速排序。

## SO07 归并排序与逆序对完整程序

<!-- kb-meta: {"id": "SO07", "aliases": [], "questions": ["归并排序与逆序对完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

区间[l,r)，以r-l≤1终止。函数会排序原数组并返回原数组逆序对数。测试穷举长度≤7的三值数组，将排序结果和O(n²)逆序计数同时核对。总时间O(n log n)、额外O(n)，长度与计数须在类型范围内。

```cpp
#include <algorithm>
#include <cassert>
#include <vector>
long long rec(std::vector<int>& a,std::vector<int>& tmp,int l,int r){
 if(r-l<=1)return 0;
 int m=l+(r-l)/2;
 long long count=rec(a,tmp,l,m)+rec(a,tmp,m,r);int i=l,j=m,k=l;
 while(i<m && j<r){if(a[i]<=a[j])tmp[k++]=a[i++];
  else {tmp[k++]=a[j++];count+=m-i;}}
 while(i<m)tmp[k++]=a[i++];
 while(j<r)tmp[k++]=a[j++];
 for(int p=l;p<r;++p)a[p]=tmp[p];
 return count;
}
long long mergeSort(std::vector<int>& a){std::vector<int> tmp(a.size());return rec(a,tmp,0,static_cast<int>(a.size()));}
int main(){
 for(int n=0;n<=7;++n){int total=1;for(int i=0;i<n;++i)total*=3;
  for(int mask=0;mask<total;++mask){int x=mask;std::vector<int>a(n);
   for(int& v:a){v=x%3;x/=3;}auto expected=a;std::sort(expected.begin(),expected.end());
   long long count=0;for(int i=0;i<n;++i)for(int j=i+1;j<n;++j)count+=(a[i]>a[j]);
   assert(mergeSort(a)==count && a==expected);
  }
 }
}
```

## SO08 快速排序、三路划分与退化

<!-- kb-meta: {"id": "SO08", "aliases": ["quicksort", "三路快排", "introsort", "随机基准"], "questions": ["快速排序、三路划分与退化的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

快速排序选基准后把小项与大项分区，再递归两侧。平均/随机化期望O(n log n)，普通最坏O(n²)。若始终用首项作基准，已排序数组可产生长度n-1递归。随机基准降低特定输入导致退化的概率，不提供最坏对数保证。

大量重复值时三路划分为<pivot、=pivot、>pivot，只递归两侧，可避免全相等输入反复处理。原地交换通常不稳定。递归栈普通最坏O(n)，先递归短区间、长区间改循环可保证栈O(log n)，但运行时间最坏仍可能平方。

std::sort提供最坏O(n log n)比较数量级保证，常见实现采用内省排序：快速分区过深切换堆排序，小区间插入排序。不能把某种库实现细节当作所有C++实现强制采用的算法。

## SO09 三路快速排序完整程序

<!-- kb-meta: {"id": "SO09", "aliases": [], "questions": ["三路快速排序完整程序的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "code", "prerequisites": []} -->

使用中间位置的值作基准（复制值，交换后不随位置改变），划分不变量为[l,lt)<p、[lt,i)==p、[i,gt)未知、[gt,r)>p。交换到i的新值未检查，因此右侧交换后不增加i。短侧递归、长侧循环限制栈深O(log n)，时间最坏仍O(n²)。测试含重复和所有短三值数组。

```cpp
#include <algorithm>
#include <cassert>
#include <vector>
void quick(std::vector<int>& a,int l,int r){
 while(r-l>1){int p=a[l+(r-l)/2],lt=l,i=l,gt=r;
  while(i<gt){if(a[i]<p)std::swap(a[lt++],a[i++]);
   else if(a[i]>p)std::swap(a[i],a[--gt]);else ++i;}
  if(lt-l<r-gt){quick(a,l,lt);l=gt;}else{quick(a,gt,r);r=lt;}
 }
}
int main(){
 for(int n=0;n<=7;++n){int total=1;for(int i=0;i<n;++i)total*=3;
  for(int mask=0;mask<total;++mask){int x=mask;std::vector<int>a(n);
   for(int& v:a){v=x%3;x/=3;}auto expected=a;std::sort(expected.begin(),expected.end());
   quick(a,0,n);assert(a==expected);
  }
 }
}
```

## SO10 计数、桶和基数排序

<!-- kb-meta: {"id": "SO10", "aliases": ["counting sort", "bucket sort", "radix sort", "LSD"], "questions": ["计数、桶和基数排序的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

计数排序针对整数有限键域[min,max]，K=max-min+1。计数、前缀位置、稳定放置记录可O(n+K)时间，辅助O(n+K)；只按次数重写整数省去输出数组但不能保持带附属字段记录的原次序。K极大时不适合，计算键域宽须防溢出。

桶排序将键按范围分桶，各桶内部排序再连接。接近均匀分布及合理桶数下可获期望线性；最坏大量数据进同一桶时退化为桶内排序代价。不能把数据分布假设隐去。

LSD基数排序从最低位到最高位，每一轮必须稳定，否则之前低位次序被破坏。d轮、每位基数b，计数实现O(d(n+b))时间O(n+b)空间；负数、变长字符串和不同编码需额外规范。d和b不是永远无关输入的常数。

## SO11 外部排序与多路归并

<!-- kb-meta: {"id": "SO11", "aliases": ["external sort", "败者树", "多路归并"], "questions": ["外部排序与多路归并的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

数据大于内存时，主要成本可能是外存读写。外部归并先读入能装进内存的块，排序成初始有序段，再用k路归并逐轮合并。每路需输入缓冲，加输出缓冲，k受可用内存与文件句柄限制。初始段数r，归并轮数约ceil(log_k r)。

最小堆或败者树维护各路当前最小项，每输出一项通常O(log k)比较；顺序块读写减少随机I/O。若需稳定排序，要把相等记录原输入先后关系纳入归并规则。

文件格式、临时空间、失败恢复和原子替换也是工程问题；此处提供算法流程，不直接覆盖用户原始数据文件。流式数据只求Top-K时可避免完整外部排序，若需全序输出则仍要处理全部记录。

## SO12 常见排序复杂度与稳定性对照

<!-- kb-meta: {"id": "SO12", "aliases": [], "questions": ["常见排序的时间、空间和稳定性分别是什么？"], "level": "基础", "kind": "comparison", "prerequisites": []} -->

以下按本库所述常见数组实现，空间含递归栈、不含输入；“稳定”依赖相等项处理规则。

|算法|最好时间|平均/期望|最坏时间|辅助空间|稳定|
|---|---|---|---|---|---|
|插入|O(n)|O(n²)|O(n²)|O(1)|是|
|带提前终止冒泡|O(n)|O(n²)|O(n²)|O(1)|是|
|简单选择|O(n²)|O(n²)|O(n²)|O(1)|否|
|堆排序|O(n log n)上界|O(n log n)|O(n log n)|O(1)|否|
|归并|O(n log n)|O(n log n)|O(n log n)|O(n)|是|
|普通快排|O(n log n)|O(n log n)|O(n²)|最坏O(n)|否|
|稳定计数|O(n+K)|O(n+K)|O(n+K)|O(n+K)|是|

普通快排表指两路常见版本；三路全等输入可O(n)，短侧递归可降低栈界。希尔、桶、基数需带增量/分布/键位数前提，故不强填一个通用界。

## SO13 排序自测、比较器与选型

<!-- kb-meta: {"id": "SO13", "aliases": [], "questions": ["排序自测、比较器与选型的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "exercise", "prerequisites": []} -->

题1：稳定排序能自动按姓名再按成绩吗？答：先按次关键字稳定排序，再按主关键字稳定排序可得到组合顺序；直接比较复合键也可。

题2：折半插入是否O(n log n)总时间？答：不是，比较减少但元素移动仍可能O(n²)。

题3：三路快排全相等输入怎样？答：一次线性划分后两侧为空，不再递归。

题4：取最大的10项需要把一亿条记录全排序吗？答：通常不必，可维护大小10的最小堆。

选择时先问是否稳定、内存是否够、数据是否近有序、键域是否受限、是否只取部分结果、是否在外存。自定义比较器如a.key<b.key而非<=；要打破平局可比较(key,id)，这样得到确定次序但不等同于算法本身稳定。

## SO14 原地堆排序完整程序

<!-- kb-meta: {"id": "SO14", "aliases": [], "questions": ["原地堆排序完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

维护最大堆，依次把最大值交换到末端；down仅访问[0,n)堆区。建堆从n/2-1倒序开始，使用有符号下标避免空数组下溢。时间O(n log n)，空间O(1)，不稳定。测试所有短三值数组并与标准排序比较。输入长度可由int表示，孩子下标计算在int范围内。

```cpp
#include <algorithm>
#include <cassert>
#include <vector>
void down(std::vector<int>& a,int u,int n){
    while(u<n/2){int c=2*u+1;if(c+1<n && a[c+1]>a[c])++c;
        if(a[u]>=a[c])break;
        std::swap(a[u],a[c]);u=c;}
}
void heapSort(std::vector<int>& a){
    int n=static_cast<int>(a.size());
    for(int i=n/2-1;i>=0;--i)down(a,i,n);
    for(int end=n-1;end>0;--end){std::swap(a[0],a[end]);down(a,0,end);}
}
int main(){
    for(int n=0;n<=7;++n){int total=1;for(int i=0;i<n;++i)total*=3;
        for(int mask=0;mask<total;++mask){int x=mask;std::vector<int>a(n);
            for(int& v:a){v=x%3;x/=3;}auto expected=a;std::sort(expected.begin(),expected.end());
            heapSort(a);assert(a==expected);}}
}
```

## SO15 稳定计数排序完整程序

<!-- kb-meta: {"id": "SO15", "aliases": [], "questions": ["稳定计数排序完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

整数键0..K-1，记录含原始id。计数前缀转为每个键的写入起点，再按原输入顺序放置保证稳定。时间O(n+K)，额外O(n+K)。K须为正且可分配，键越界报错；不能直接用于范围巨大的键。测试重复键稳定性和空输入。

```cpp
#include <cassert>
#include <stdexcept>
#include <vector>
struct Item{int key,id;};
std::vector<Item> counting(const std::vector<Item>& a,int K){
    if(K<=0)throw std::invalid_argument("key range");
    std::vector<int> start(K+1);
    for(auto x:a){if(x.key<0 || x.key>=K)throw std::invalid_argument("key");++start[x.key+1];}
    for(int k=1;k<=K;++k)start[k]+=start[k-1];
    std::vector<Item> out(a.size());
    for(auto x:a)out[start[x.key]++]=x;
    return out;
}
int main(){
    auto b=counting({{2,0},{0,1},{2,2},{1,3},{0,4}},3);
    assert(b[0].id==1 && b[1].id==4 && b[2].id==3 && b[3].id==0 && b[4].id==2);
    assert(counting({},1).empty());
}
```

