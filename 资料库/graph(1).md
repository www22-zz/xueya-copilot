# 图知识库：从基础到进阶

版本：1.0.0；编写日期：2026-11-04。路线：图的术语 → 存储与遍历 → 拓扑与关键路径 → 最短路 → 最小生成树 → 连通性、网络流与建模。

适用：数据结构课程学习、C++17示例、RAG问答。内容为独立编写的教学材料，仿照栈与队列知识库的组织风格，不是课程PPT或扫描教材的转录，不附原教材页码。

通用约定：0基下标，区间默认左闭右开；n为元素数，V/E为图顶点/边数；空间复杂度默认辅助空间并另行说明输出。每个cpp代码块均为独立完整C++17程序，须分别编译，保留assert。输入规模及数值范围须满足各块前提，示例并非工业泛型库。

参考导航：[MIT算法课程主题目录](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/pages/lecture-notes/)；[C++字符串接口规范（持续更新的工作草案）](https://eel.is/c++draft/string.classes)。核对日期：2026-11-04。课程目录用于主题覆盖导航；本文推导、代码和练习为原创。只使用C++17已有接口，不把草案新增接口当作C++17。

## GR01 有向图、无向图、度与路径

<!-- kb-meta: {"id": "GR01", "aliases": ["digraph", "degree", "path", "cycle", "连通图"], "questions": ["有向图、无向图、度与路径的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

图G=(V,E)由顶点集合与边集合组成。无向边无方向，有向边为有序对；简单图不含自环和重边，多重图允许重边。边可带权，权可能表示距离、费用、容量，其语义不能互换。本文顶点编号0到V-1，图可不连通。

无向图各顶点度数和为2E，自环若允许则对度贡献2；有向图入度和与出度和均为E。简单无向图最多V(V-1)/2条边，简单有向图无自环最多V(V-1)。路径是相邻顶点序列，简单路径不重复顶点；环首尾相同。路径长度可能指边数或权和，必须说明。

无向图连通指任意两点可达；有向图强连通指任意两点互相可达，弱连通指忽略方向后连通。树是连通无环无向图，n结点恰n-1边；仅有n-1条边不能保证任意图是树，还须连通或无环条件。

## GR02 邻接矩阵、邻接表、边集与十字链表

<!-- kb-meta: {"id": "GR02", "aliases": ["adjacency matrix", "adjacency list", "边集数组", "十字链表", "邻接多重表"], "questions": ["邻接矩阵、邻接表、边集与十字链表的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

邻接矩阵用V×V格表示边，空间O(V²)，查两点是否相邻O(1)，枚举某点邻居O(V)。带权图必须用单独标志或INF区分无边与权重0；对角线0常表示零长度路径，不等于存在自环。重边需按问题合并或保留。

邻接表空间O(V+E)，枚举u的出边O(outdegree(u))。无向边通常存两条邻接记录，逻辑边数仍为E。若只需排序所有边（Kruskal）或反复扫描边（Bellman-Ford），边集数组更直接。

有向图十字链表让一条边同时进入起点出边链和终点入边链，适合同时遍历入边与出边；无向邻接多重表让同一边记录与两端关联。结构复杂度换来了操作便利，普通只读遍历常用vector邻接表即可。

## GR03 BFS、DFS、访问标记和连通分量

<!-- kb-meta: {"id": "GR03", "aliases": ["广度优先", "深度优先", "BFS", "DFS", "三色标记"], "questions": ["BFS、DFS、访问标记和连通分量的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

BFS用队列按距源边数分层，发现邻居时立即标记并入队，避免重复入队。无权或等正权图中，首次发现的层数给出最少边数；任意边权图不能直接用普通BFS求最小权和。

DFS递归或显式栈深入分支，可计算DFS序、检测环、拓扑排序及连通分量。单源遍历只覆盖可达区域；完整遍历须对所有未访问顶点再次启动。邻接表下完整BFS/DFS时间O(V+E)，辅助O(V)；矩阵实现要扫描每行，最坏O(V²)。

无向图环检测要跳过父边；存在平行边时应按边ID跳过同一条父边，而非跳过所有连向父顶点的边。有向图DFS用未访问、递归中、已完成三色，指向递归中结点才是返祖环证据，不能把所有已访问边都判成环。

## GR04 BFS最短边数与路径恢复完整程序

<!-- kb-meta: {"id": "GR04", "aliases": [], "questions": ["BFS最短边数与路径恢复完整程序的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "code", "prerequisites": []} -->

图采用邻接表，调用者保证顶点与邻居编号有效。dist=-1表示不可达，parent保存首次发现的前驱。路径从目标逆向回溯后反转；源到自身为单点路径。时间O(V+E)，辅助O(V)。测试包含不可达点、自身路径和存在环的无向图。

```cpp
#include <algorithm>
#include <cassert>
#include <queue>
#include <utility>
#include <vector>
using Graph=std::vector<std::vector<int>>;
std::pair<std::vector<int>,std::vector<int>> bfs(const Graph& g,int s) {
    std::vector<int> d(g.size(),-1),p(g.size(),-1); std::queue<int> q;
    d.at(s)=0; q.push(s);
    while(!q.empty()) {
        int u=q.front(); q.pop();
        for(int v:g[u]) if(d[v]==-1) {d[v]=d[u]+1;p[v]=u;q.push(v);}
    }
    return {d,p};
}
std::vector<int> path(int t,const std::vector<int>& d,const std::vector<int>& p) {
    if(d.at(t)==-1) return {};
    std::vector<int> out;
    for(int u=t;u!=-1;u=p[u]) out.push_back(u);
    std::reverse(out.begin(),out.end()); return out;
}
int main() {
    Graph g{{1,2},{0,2,3},{0,1},{1},{}};
    auto [d,p]=bfs(g,0);
    assert((d==std::vector<int>{0,1,1,2,-1}));
    assert((path(3,d,p)==std::vector<int>{0,1,3}));
    assert(path(4,d,p).empty() && path(0,d,p)==std::vector<int>{0});
}
```

## GR05 拓扑排序与DAG动态规划

<!-- kb-meta: {"id": "GR05", "aliases": ["topological sort", "Kahn", "DAG", "AOV"], "questions": ["拓扑排序与DAG动态规划的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

DAG是有向无环图。拓扑序要求每条u→v都使u在v之前。Kahn算法将入度0顶点入队，取出后删除其出边并降低邻居入度；若最终输出少于V个顶点，则存在有向环。多重边计数必须在初始入度及删除时各处理一次。

拓扑序可能不唯一；若每步可选入度0顶点均唯一，才有唯一拓扑序。普通队列不保证字典序最小，需要最小堆时复杂度通常变为O((V+E)log V)上界。邻接表加队列版本O(V+E)。

DAG上可按拓扑序做最短路、最长路、路径计数，边权允许为负，因为无环保证依赖可按顺序结算。最长路初值不可达应为负无穷，不能全置0后误把任意顶点当起点；路径计数可能指数大，应使用足够整数或规定取模。

## GR06 Kahn拓扑排序完整程序

<!-- kb-meta: {"id": "GR06", "aliases": [], "questions": ["Kahn拓扑排序完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

返回optional序列；有环返回nullopt，空图返回有效空序列，两者可区分。测试验证每条边的拓扑次序约束，而非假设只有一个正确序列，并验证不连通图和有环图。邻接表时间O(V+E)，辅助O(V)。

```cpp
#include <cassert>
#include <optional>
#include <queue>
#include <vector>
std::optional<std::vector<int>> topo(const std::vector<std::vector<int>>& g) {
    std::vector<int> in(g.size()),out; std::queue<int> q;
    for(const auto& row:g) for(int v:row) ++in[v];
    for(int i=0;i<static_cast<int>(g.size());++i) if(!in[i]) q.push(i);
    while(!q.empty()) {
        int u=q.front();q.pop();out.push_back(u);
        for(int v:g[u]) if(--in[v]==0) q.push(v);
    }
    if(out.size()!=g.size()) return std::nullopt;
    return out;
}
int main() {
    std::vector<std::vector<int>> g{{1,2},{3},{3},{},{}};
    auto out=topo(g); assert(out);
    std::vector<int> pos(g.size());
    for(int i=0;i<static_cast<int>(out->size());++i) pos[(*out)[i]]=i;
    for(int u=0;u<static_cast<int>(g.size());++u) for(int v:g[u]) assert(pos[u]<pos[v]);
    assert(!topo({{1},{0}})); assert(topo({})->empty());
}
```

## GR07 AOE关键路径、最早与最迟时间

<!-- kb-meta: {"id": "GR07", "aliases": ["AOE", "关键路径", "critical path", "ve", "vl"], "questions": ["AOE关键路径、最早与最迟时间的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

AOE网用顶点表示事件、带权边表示持续时间非负的活动，必须是DAG。先按拓扑序算事件最早时间ve[v]=max(ve[u]+w(u,v))。项目工期为所有终点ve的最大值；多个起终点可引入零权虚拟源和汇。

令汇点vl等于总工期，逆拓扑序算vl[u]=min(vl[v]-w(u,v))。活动u→v的最早开始e=ve[u]，最迟开始l=vl[v]-w，松弛时间l-e，e=l为关键活动。关键路径是决定工期的最长持续时间路径，不是最短路径，也可能有多条。

例：S→A为3，S→B为2，A→T为2，B→T为4，工期max(5,6)=6，S-B-T关键。缩短非关键活动可能不减总工期；即使缩短一条关键路径，多条关键路径也可能继续限制完工。假设依赖满足且资源无限，资源冲突调度需要额外模型。

## GR08 最短路算法选择与松弛

<!-- kb-meta: {"id": "GR08", "aliases": ["relaxation", "松弛", "0-1 BFS", "最短路径"], "questions": ["BFS、Dijkstra、Bellman-Ford和Floyd怎么选择？", "有负权边为什么不能直接用Dijkstra？"], "level": "基础", "kind": "concept", "prerequisites": []} -->

松弛u→v指若dist[u]+w<dist[v]则更新v距离与前驱，只能从已可达u发起。单源无权用BFS；0/1边权用双端队列0-1 BFS（0权入前、1权入后）可O(V+E)；非负权用Dijkstra；允许负边用Bellman-Ford；DAG可拓扑处理；全源小规模稠密图常用Floyd。

Dijkstra每次确定最小未定距离依赖非负权。反例：S→A=2、S→B=5、B→A=-4，若先确定A就可能错。负边不等于负环；可达负环且能到达目标时，目标最短路没有有限下界。

数值实现使用INF时要避免INF+w溢出，要求路径长度在约定范围内。不可达、距离0、负无穷是三种不同语义。多源可把各源dist置0，或加零权超级源。

## GR09 Dijkstra最小堆完整程序

<!-- kb-meta: {"id": "GR09", "aliases": [], "questions": ["Dijkstra最小堆完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

邻接表存有向非负权边，所有编号有效且源存在；INF=2^60，输入保证有限最短路小于INF。惰性堆允许同点多记录，弹出时距离不等即跳过。一般多重图复杂度O(V+E log(E+1))，空间O(V+E)；简单图常记O((V+E)log V)。测试包含0权、重复候选、重边、不可达及负边拒绝。

```cpp
#include <cassert>
#include <functional>
#include <queue>
#include <stdexcept>
#include <utility>
#include <vector>
using LL=long long; constexpr LL INF=1LL<<60;
using Graph=std::vector<std::vector<std::pair<int,LL>>>;
std::vector<LL> dijkstra(const Graph& g,int s) {
    for(const auto& row:g) for(auto [v,w]:row) {
        (void)v; if(w<0 || w>=INF) throw std::invalid_argument("weight range");
    }
    std::vector<LL> d(g.size(),INF); d.at(s)=0;
    std::priority_queue<std::pair<LL,int>,std::vector<std::pair<LL,int>>,std::greater<std::pair<LL,int>>> q;
    q.push({0,s});
    while(!q.empty()) {
        auto [du,u]=q.top();q.pop(); if(du!=d[u]) continue;
        for(auto [v,w]:g[u]) if(du<=INF-w && du+w<d[v]) {
            d[v]=du+w; q.push({d[v],v});
        }
    }
    return d;
}
int main() {
    Graph g{{{1,10},{2,1},{2,3}},{{3,0}},{{1,2},{3,8}},{},{}};
    assert((dijkstra(g,0)==std::vector<LL>{0,3,1,3,INF}));
    bool bad=false; try {dijkstra({{{0,-1}}},0);} catch(const std::invalid_argument&){bad=true;}
    assert(bad);
}
```

## GR10 Bellman-Ford、负环与Floyd-Warshall

<!-- kb-meta: {"id": "GR10", "aliases": ["Bellman-Ford", "Floyd", "SPFA", "负环"], "questions": ["Bellman-Ford、负环与Floyd-Warshall的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

Bellman-Ford最多V-1轮扫描全部边；第k轮后至少已得到所有不超过k条边路径的最优候选，可提前停止于无更新。再一轮仍可松弛表示源可达负环影响，时间O(VE)，辅助O(V)。若问某目标，须从额外可更新顶点沿边传播，只有被传播到的目标才无有限最短路。不可达负环不影响该源；检测任意负环可用超级源。

Floyd令dist[i][j]为仅允许中间顶点来自已处理集合的最短距离，k必须作为最外循环，更新d[i][j]=min(d[i][j],d[i][k]+d[k][j])。初始化对角线0、无边INF、平行边取最小；允许负自环时对角线取min(0,w)。时间O(V³)，空间O(V²)。

Floyd完成后d[k][k]<0说明负环；若i可达k且k可达j，则i到j没有有限最短值，普通表中那个数字不能当最终答案。SPFA是队列化松弛的实现策略，最坏仍可O(VE)，不能承诺线性。

## GR11 Bellman-Ford距离与源可达负环检测完整程序

<!-- kb-meta: {"id": "GR11", "aliases": [], "questions": ["Bellman-Ford距离与源可达负环检测完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

返回距离及是否存在源可达负环；若标志为真，dist不是完整的负无穷分类结果，调用者不可直接把所有值当有限最短路。输入顶点合法，V≥1，权重和中间累加在long long范围内且有限距离小于INF。测试有负边无负环、可达负环及不可达负环。

```cpp
#include <cassert>
#include <utility>
#include <vector>
using LL=long long; constexpr LL INF=1LL<<60;
struct Edge {int u,v;LL w;};
std::pair<std::vector<LL>,bool> bellman(int n,const std::vector<Edge>& edges,int s) {
    std::vector<LL> d(n,INF); d.at(s)=0;
    for(int k=1;k<n;++k) {
        bool changed=false;
        for(auto [u,v,w]:edges) if(d[u]!=INF && d[u]+w<d[v]) {
            d[v]=d[u]+w; changed=true;
        }
        if(!changed) break;
    }
    for(auto [u,v,w]:edges) if(d[u]!=INF && d[u]+w<d[v]) return {d,true};
    return {d,false};
}
int main() {
    auto [d,bad]=bellman(4,{{0,1,4},{0,2,5},{1,2,-2}},0);
    assert(!bad && d[2]==2 && d[3]==INF);
    assert(bellman(3,{{0,1,0},{1,2,-2},{2,1,1}},0).second);
    assert(!bellman(3,{{1,2,-2},{2,1,1}},0).second);
}
```

## GR12 最小生成树、割性质、Prim与Kruskal

<!-- kb-meta: {"id": "GR12", "aliases": ["MST", "Prim", "Kruskal", "cut property", "最小生成森林"], "questions": ["最小生成树、割性质、Prim与Kruskal的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

连通带权无向图的生成树包含所有顶点且无环，恰V-1条边；最小生成树MST使总边权最小，不保证任意两点路径最短。边权可负、可为0、可相同。非连通图只能得到最小生成森林。全不同权重足以保证MST唯一，但存在同权边不必然不唯一。

割性质：跨越某割的最轻边至少属于某棵MST；唯一最轻时属于所有MST。Kruskal按边权递增，若两端不在同一并查集则加入；排序O(E log E)，并查集合并近线性。Prim从一个点逐步选连接当前树与外部的最轻边；矩阵O(V²)，堆邻接表常O((V+E)log V)或按具体惰性堆给出log E界。

例三角形AB=2、AC=3、BC=2，MST取AB和BC总4，但A到C沿树为4，比原图直边3更长。把MST当最短路径树会答错。

## GR13 并查集与Kruskal完整程序

<!-- kb-meta: {"id": "GR13", "aliases": [], "questions": ["并查集与Kruskal完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

并查集采用路径压缩和按集合大小合并，连续m次操作总O((V+m)α(V))常用摊还界；单次不应直接声称最坏O(1)。Kruskal返回森林总权及剩余连通分量数，分量数为1时才是非空图MST。总权不溢出long long。测试涵盖负边、平行边、自环和断连。

```cpp
#include <algorithm>
#include <cassert>
#include <numeric>
#include <tuple>
#include <utility>
#include <vector>
struct DSU {
    std::vector<int> p,sz;
    explicit DSU(int n):p(n),sz(n,1){std::iota(p.begin(),p.end(),0);}
    int find(int x){return p[x]==x?x:p[x]=find(p[x]);}
    bool unite(int a,int b){a=find(a);b=find(b);if(a==b)return false;
      if(sz[a]<sz[b])std::swap(a,b);
      p[b]=a;sz[a]+=sz[b];return true;}
};
std::pair<long long,int> kruskal(int n,std::vector<std::tuple<long long,int,int>> e) {
    std::sort(e.begin(),e.end()); DSU d(n); long long sum=0; int components=n;
    for(auto [w,u,v]:e) if(d.unite(u,v)){sum+=w;--components;}
    return {sum,components};
}
int main(){
    assert((kruskal(3,{{2,0,1},{3,0,2},{2,1,2}})==std::pair<long long,int>{4,1}));
    assert((kruskal(4,{{-2,0,1},{5,0,1},{-9,1,1}})==std::pair<long long,int>{-2,3}));
    assert((kruskal(0,{})==std::pair<long long,int>{0,0}));
}
```

## GR14 强连通分量、桥与割点

<!-- kb-meta: {"id": "GR14", "aliases": ["SCC", "Tarjan", "Kosaraju", "lowlink", "割点", "桥"], "questions": ["强连通分量、桥与割点的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

有向图的强连通分量SCC是最大互相可达顶点集合。缩点后必为DAG。Kosaraju先在原图按DFS完成次序记录，再按逆完成次序在反图搜索分量；Tarjan用dfn、low和活跃栈单趟完成，两者邻接表均O(V+E)。Tarjan遇到栈内返边更新low时通常使用目标dfn，不能把已出栈顶点也当活跃祖先。

无向图桥是删去后增加连通分量数的边，割点是删去后增加分量数的点。DFS树边u→v若low[v]>dfn[u]为桥；非根u若有孩子v满足low[v]≥dfn[u]为割点，根则需至少两个DFS孩子。桥用严格大于、割点用大于等于，含义不同。

多重图必须按边ID跳过反向父边，否则两点间的平行边可能被误判桥。SCC的low更新与无向桥算法形式相似但语义不同，不能混抄代码。

## GR15 二分图、最大匹配、欧拉路与网络流

<!-- kb-meta: {"id": "GR15", "aliases": ["二分图", "增广路", "Hopcroft-Karp", "Hierholzer", "最大流", "残量图"], "questions": ["二分图、最大匹配、欧拉路与网络流的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "concept", "prerequisites": []} -->

无向二分图可将顶点分两色使每条边两端异色，等价于不含奇环；BFS/DFS对所有分量染色即可O(V+E)判定，自环立即失败。二分图最大匹配可反复找增广路；Hopcroft-Karp利用分层增广，在标准模型下O(E√V)。匹配不允许两条所选边共享端点。

欧拉路每条边恰使用一次，与哈密顿路每顶点恰访问一次不同。无向图忽略孤立点后连通，奇度点为0个有欧拉回路、2个有开欧拉路。有向欧拉回路需所有非零度顶点强连通且入度=出度。Hierholzer用边ID标记可O(V+E)构造。

网络流在有向容量网络上满足0≤f≤c和中间顶点流量守恒；残量图反向边表示撤销已有流的能力，不能省略。最大流最小割定理把最大流值与最小割容量相连。适合分配、匹配、容量瓶颈；费用优化另需最小费用流。此节给出建模与前提，未提供这些算法的完整实现。

## GR16 图建模与自测反例

<!-- kb-meta: {"id": "GR16", "aliases": [], "questions": ["图建模与自测反例的含义、适用条件和注意事项是什么？"], "level": "基础", "kind": "exercise", "prerequisites": []} -->

建模先决定什么是状态顶点、什么是合法转移、边权表示什么。迷宫可把可走格建点，公交换乘可把站点与线路状态结合；仅用站点可能遗漏“当前线路”这一影响后续费用的状态。边数可能随状态扩展显著增长。

题1：含0权边能用BFS求最小权和吗？答：普通按边数BFS不行，可用0-1 BFS（全权仅0/1）或Dijkstra。

题2：Kahn只输出部分点证明什么？答：图有环，不代表所有未输出点都在环上，它们也可能只是环的下游。

题3：某源到不了负环，最短路是否仍无意义？答：该负环不影响此源；源可达负环也只影响能从其到达的目标。

题4：无向图有V-1边就必为树吗？答：否，例如三点环加一个孤立点共4点3边。

检索问答应先补齐有向性、权重范围、连通性及目标类型，再选算法；不能只看到“路径”就一律推荐Dijkstra。

## GR17 Floyd全源最短路与负环影响完整程序

<!-- kb-meta: {"id": "GR17", "aliases": [], "questions": ["Floyd全源最短路与负环影响完整程序的含义、适用条件和注意事项是什么？"], "level": "进阶", "kind": "code", "prerequisites": []} -->

d[i][j]初始化为INF，无边不等于权0；对角线0、重边取小。k外层保证中间点集合递推正确。另返回bad[i][j]表示可经某负环到达，若为true则该点对无有限最短路。O(V³)时间、O(V²)空间。输入V≥0、顶点合法，所有迭代中间加法必须不溢出且有限值与INF区分。测试重边、0边、不可达及局部负环。

```cpp
#include <algorithm>
#include <cassert>
#include <tuple>
#include <vector>
using LL=long long;constexpr LL INF=1LL<<60;
struct Result{std::vector<std::vector<LL>> d;std::vector<std::vector<bool>> bad;};
Result floyd(int n,const std::vector<std::tuple<int,int,LL>>& edges){
    Result r{std::vector<std::vector<LL>>(n,std::vector<LL>(n,INF)),
             std::vector<std::vector<bool>>(n,std::vector<bool>(n))};
    auto& d=r.d;for(int i=0;i<n;++i)d[i][i]=0;
    for(auto [u,v,w]:edges)d[u][v]=std::min(d[u][v],w);
    for(int k=0;k<n;++k)for(int i=0;i<n;++i)for(int j=0;j<n;++j)
        if(d[i][k]!=INF && d[k][j]!=INF)d[i][j]=std::min(d[i][j],d[i][k]+d[k][j]);
    for(int k=0;k<n;++k)if(d[k][k]<0)
        for(int i=0;i<n;++i)for(int j=0;j<n;++j)
            if(d[i][k]!=INF && d[k][j]!=INF)r.bad[i][j]=true;
    return r;
}
int main(){
    auto r=floyd(4,{{0,1,5},{0,1,2},{1,2,0}});
    assert(r.d[0][2]==2 && r.d[2][0]==INF && !r.bad[0][2]);
    r=floyd(4,{{0,1,1},{1,2,-2},{2,1,1}});
    assert(r.bad[0][2] && !r.bad[3][2] && !r.bad[0][0]);
}
```

## GR18 DFS二分图染色完整程序

<!-- kb-meta: {"id": "GR18", "aliases": [], "questions": ["DFS二分图染色完整程序的含义、适用条件和注意事项是什么？"], "level": "应用", "kind": "code", "prerequisites": []} -->

对所有分量迭代DFS，两色用0/1、未染为-1。输入是无向图邻接表，所有编号有效，调用者保证双向表示；发现同色相邻立即false。O(V+E)时间、O(V)额外空间。测试偶环、奇环、不连通和自环；空图约定二分图。

```cpp
#include <cassert>
#include <stack>
#include <vector>
bool bipartite(const std::vector<std::vector<int>>& g){
    std::vector<int> color(g.size(),-1);
    for(int s=0;s<static_cast<int>(g.size());++s)if(color[s]==-1){
        std::stack<int> q;color[s]=0;q.push(s);
        while(!q.empty()){
            int u=q.top();q.pop();
            for(int v:g[u]){
                if(color[v]==-1){color[v]=color[u]^1;q.push(v);}
                else if(color[v]==color[u])return false;
            }
        }
    }
    return true;
}
int main(){
    assert(bipartite({{1,3},{0,2},{1,3},{0,2},{}}));
    assert(!bipartite({{1,2},{0,2},{0,1}}));
    assert(!bipartite({{0}}));assert(bipartite({}));
}
```

