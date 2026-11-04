/* Xueya Computer Video Courses Learning Workspace - Multi-Source & Local Video Enabled */
(function(root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.XueyaCourses = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

  const STORAGE_KEY = 'xueya-video-courses-v1';
  const PROGRESS_KEY = 'xueya-video-progress-v1';
  let serverData=null,serverOwner=null,serverLoading=false;
  const online=()=>typeof window!=='undefined'&&window.XueyaPlatform?.available;
  const serverCurrent=()=>serverData&&serverOwner===getAccountId();
  const operation=()=> 'course-'+(globalThis.crypto?.randomUUID?.()||Date.now()+'-'+Math.random().toString(36).slice(2));
  async function api(path,data){
    const response=await window.XueyaPlatform.spaceFetch('/api/learning/space/courses'+path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});
    const value=await response.json();if(!value.ok)throw new Error(value.error||'COURSE_NOT_SAVED');return value;
  }

  // Built-in curated Computer Science courses with Bilibili authoritative lectures & online fallback
  const BUILTIN_COURSES = [
    {
      id: 'cs-ds-algo',
      title: '数据结构与高频算法精析（清华大学公开课）',
      category: 'theory',
      categoryName: '核心理论 / 408',
      level: '进阶必修',
      badge: '408 核心 · 清华名课',
      instructor: '清华大学计算机系 · 邓俊辉团队',
      duration: '12 课时 · 约 4.5 小时',
      bvid: 'BV1b7411N798',
      coverGradient: 'linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%)',
      coverIcon: 'tree',
      description: '全网经典清华数据结构公开课：围绕线性表、树与二叉树、图论、散列表及动态规划，剖析核心底层原理与大厂面试高频算法。',
      tags: ['二叉树', '红黑树', '图算法', '动态规划', '复杂度分析'],
      episodes: [
        {
          id: 'ds-ep-1',
          title: '第 01 讲：绪论与大 O 渐近复杂度分析',
          duration: '18:30',
          bvid: 'BV1b7411N798',
          bpage: 1,
          videoUrl: '',
          summary: '深入理解时间复杂度与空间复杂度，区分最坏情况、平均情况与均摊复杂度。',
          keyPoints: ['大 O 表示法', '对数阶 O(log n)', '空间换时间权衡'],
          copilotPrompts: [
            '二叉搜索树查找的时间复杂度为什么是 O(log n)？',
            '什么是均摊时间复杂度，动态数组扩容时是如何计算的？',
            '在什么情况下算法的空间复杂度会成为主要瓶颈？'
          ]
        },
        {
          id: 'ds-ep-2',
          title: '第 02 讲：树与二叉树：遍历、AVL 平衡树与红黑树',
          duration: '24:15',
          bvid: 'BV1b7411N798',
          bpage: 4,
          videoUrl: '',
          summary: '剖析二叉搜索树的中序遍历特性，AVL 树失衡四种旋转（LL/RR/LR/RL），以及红黑树五大性质。',
          keyPoints: ['二叉搜索树', 'AVL 单双旋', '红黑树染色与旋转'],
          copilotPrompts: [
            '平衡二叉树在失衡时，LL 与 LR 旋转的具体步骤是什么？',
            '红黑树相比 AVL 树为什么在插入和删除频繁的场景更具优势？',
            '如何在不使用递归的情况下手写二叉树的前序和中序遍历？'
          ]
        },
        {
          id: 'ds-ep-3',
          title: '第 03 讲：图论实战：邻接表、BFS/DFS 与拓扑排序',
          duration: '22:40',
          bvid: 'BV1b7411N798',
          bpage: 6,
          videoUrl: '',
          summary: '图的表示方式对比，广度优先与深度优先搜索的底层队列/栈应用，有向无环图（DAG）检测与拓扑排序。',
          keyPoints: ['邻接矩阵与邻接表', 'BFS 最短路', 'DAG 环检测与拓扑排序'],
          copilotPrompts: [
            '如何利用拓扑排序判断一个有向图是否存在循环依赖？',
            'Dijkstra 最短路径算法为什么不能处理包含负权边的图？',
            '广度优先搜索（BFS）为什么能保证无权图中的最短路径？'
          ]
        },
        {
          id: 'ds-ep-4',
          title: '第 04 讲：动态规划进阶：状态定义与转移方程推导',
          duration: '26:50',
          bvid: 'BV1b7411N798',
          bpage: 11,
          videoUrl: '',
          summary: '从斐波那契到 0-1 背包、完全背包，掌握重叠子问题、最优子结构与状态压缩技巧。',
          keyPoints: ['重叠子问题', '最优子结构', '滚动数组空间压缩'],
          copilotPrompts: [
            '动态规划与贪心算法的核心区别是什么？',
            '0-1 背包问题中，为什么一维数组优化时内层循环必须逆序遍历？',
            '如何系统化推导最长公共子序列（LCS）的状态转移方程？'
          ]
        }
      ]
    },
    {
      id: 'cs-arch-sys',
      title: '计算机组成原理与体系结构深度精析（哈工大公开课）',
      category: 'theory',
      categoryName: '核心理论 / 408',
      level: '进阶必修',
      badge: '408 核心 · 硬件底座',
      instructor: '哈尔滨工业大学 · 刘宏伟团队',
      duration: '12 课时 · 约 5.0 小时',
      bvid: 'BV1WW411Q7G5',
      coverGradient: 'linear-gradient(135deg, #1e293b 0%, #475569 100%)',
      coverIcon: 'cpu',
      description: '国家级精品课程哈工大计组公开课：深入冯·诺依曼架构、机器级数据表示、主存与 Cache 映射、指令系统与寻址、CPU 流水线冒险以及总线与中断系统。',
      tags: ['冯诺依曼', '补码与浮点', 'Cache映射', '指令系统', '流水线冒险', '中断与DMA'],
      platform: true,
      episodes: [
        {
          id: 'arch-ep-1',
          title: '第 01 讲：计算机系统概述：冯·诺依曼架构与性能度量',
          duration: '22:10',
          bvid: 'BV1WW411Q7G5',
          bpage: 1,
          videoUrl: '',
          summary: '冯·诺依曼计算机五大组成部分，存储程序概念，主频、CPI、MIPS 与 FLOPS 性能度量指标。',
          keyPoints: ['冯诺依曼体系', '存储程序工作方式', 'CPI与MIPS计算'],
          copilotPrompts: [
            '冯·诺依曼体系结构的核心特点是什么，指令与数据在存储器中是如何区分的？',
            'CPI（Cycles Per Instruction）和 MIPS 指标在评估 CPU 性能时有哪些局限性？',
            '计算机中的字长（Word Length）是如何影响寻址范围和计算精度的？'
          ]
        },
        {
          id: 'arch-ep-2',
          title: '第 02 讲：数据的机器级表示：定点数、浮点数与 IEEE 754 标准',
          duration: '26:40',
          bvid: 'BV1WW411Q7G5',
          bpage: 8,
          videoUrl: '',
          summary: '原码、反码、补码与移码变换，溢出判跳逻辑（双符号位法），IEEE 754 单双精度浮点数规格化与阶码偏置。',
          keyPoints: ['补码算术加减法', '双符号位溢出判断', 'IEEE 754 浮点标准与特殊值'],
          copilotPrompts: [
            '为什么计算机底层的定点整数普遍采用补码表示而不是原码？',
            'IEEE 754 单精度浮点数中，阶码为什么采用移码（偏置常数 127）表示？',
            '浮点数的非规格化数（Subnormal Numbers）是为了解决什么计算精度问题？'
          ]
        },
        {
          id: 'arch-ep-3',
          title: '第 03 讲：存储系统与 Cache 映射：直接、全相联与组相联',
          duration: '28:15',
          bvid: 'BV1WW411Q7G5',
          bpage: 24,
          videoUrl: '',
          summary: 'SRAM 与 DRAM 原理对比，主存芯片扩展（位扩展与字扩展），Cache-主存地址映射机制与命中率计算，写直达与写回策略。',
          keyPoints: ['Cache 三种映射方式', 'Tag 标记位计算', '写分配与非写分配'],
          copilotPrompts: [
            '组相联映射相比全相联和直接映射，是如何在硬件冲突与开销间取得平衡的？',
            '已知主存容量、Cache 容量和块大小，如何准确计算主存地址中的 Tag、Index 与 Offset 位数？',
            'Cache 的写回策略（Write Back）为什么必须配合 Dirty Bit（脏位）使用？'
          ]
        },
        {
          id: 'arch-ep-4',
          title: '第 04 讲：指令系统与寻址方式：CISC 与 RISC 架构对比',
          duration: '24:30',
          bvid: 'BV1WW411Q7G5',
          bpage: 36,
          videoUrl: '',
          summary: '指令字格式与扩展操作码设计，立即寻址、直接寻址、寄存器寻址、基址与变址寻址，CISC 与 RISC 指令集哲学。',
          keyPoints: ['扩展操作码设计', '基址寻址 vs 变址寻址', 'RISC 加载/存储架构'],
          copilotPrompts: [
            '变址寻址和基址寻址在硬件实现和面向的编程场景上有何根本区别？',
            '采用扩展操作码技术时，如何设计满足短指令与长指令共存的二叉树前缀编码？',
            '为什么现代高性能 CPU（如 x86）在内部会将复杂 CISC 指令译码为微操作（uOPs）执行？'
          ]
        },
        {
          id: 'arch-ep-5',
          title: '第 05 讲：中央处理器与指令流水线：数据通路与流水线冒险',
          duration: '29:50',
          bvid: 'BV1WW411Q7G5',
          bpage: 48,
          videoUrl: '',
          summary: '单周期与多周期 CPU 数据通路设计，经典五级流水线（IF/ID/EX/MEM/WB），结构冒险、数据冒险（RAW/WAR/WAW）及分支预测处理。',
          keyPoints: ['五级指令流水线', '写后读（RAW）数据相关', '数据旁路转发与分支预测'],
          copilotPrompts: [
            '流水线中的结构冒险、数据冒险和控制冒险分别是如何产生的？',
            '旁路转发技术（Forwarding / Bypassing）是如何在无需暂停流水线的情况下解决 RAW 冒险的？',
            '为什么深入的分支预测失败会导致现代超标量 CPU 产生巨大的性能惩罚？'
          ]
        },
        {
          id: 'arch-ep-6',
          title: '第 06 讲：总线系统与 I/O 中断：程序中断与 DMA 数据传送',
          duration: '23:45',
          bvid: 'BV1WW411Q7G5',
          bpage: 60,
          videoUrl: '',
          summary: '总线仲裁方式（链式查询、计数器定时查询、独立请求），程序查询、中断请求响应与中断屏蔽字，DMA 控制器与主存直接高速数据交换。',
          keyPoints: ['中断响应周期与硬件隐指令', '多重中断与屏蔽字', 'DMA 周期挪用与总线控制权'],
          copilotPrompts: [
            'CPU 响应外部中断必须满足哪些先决条件，中断服务程序入口地址是如何获取的？',
            '多重中断系统中，中断优先级是如何通过硬件屏蔽字进行动态调整的？',
            'DMA 控制方式与中断控制方式在数据传输开销上有何本质不同？'
          ]
        }
      ]
    },
    {
      id: 'cs-os-kernel',
      title: '操作系统深度剖析：进程、内存与 Linux 内核（哈工大公开课）',
      category: 'theory',
      categoryName: '核心理论 / 408',
      level: '进阶必修',
      badge: '计算机底座 · 哈工大名课',
      instructor: '哈尔滨工业大学 · 李治军团队',
      duration: '10 课时 · 约 4.0 小时',
      bvid: 'BV1d4411v7UX',
      coverGradient: 'linear-gradient(135deg, #0f172a 0%, #334155 100%)',
      coverIcon: 'layers',
      description: '哈工大经典操作系统公开课：直击进程与线程模型、CPU 上下文切换、虚拟内存分页置换、以及 Linux 0.11 内核源码。',
      tags: ['进程线程', '虚拟内存', '死锁预防', '系统调用', 'Linux 内核'],
      episodes: [
        {
          id: 'os-ep-1',
          title: '第 01 讲：进程与线程模型：状态变迁与上下文切换',
          duration: '20:10',
          bvid: 'BV1d4411v7UX',
          bpage: 1,
          videoUrl: '',
          summary: 'PCB 进程控制块结构，用户态与内核态切换，进程调度器运作机制与时间片轮转。',
          keyPoints: ['PCB 与 TCB', '上下文切换开销', '用户态内核态转换'],
          copilotPrompts: [
            '为什么线程上下文切换的开销远小于进程上下文切换？',
            '系统调用发生时，CPU 寄存器和堆栈是如何保存与恢复的？',
            'Linux 默认的完全公平调度器（CFS）底层是基于什么数据结构实现的？'
          ]
        },
        {
          id: 'os-ep-2',
          title: '第 02 讲：虚拟内存与分页管理：TLB 与缺页中断',
          duration: '25:15',
          bvid: 'BV1d4411v7UX',
          bpage: 6,
          videoUrl: '',
          summary: '多级页表设计原理、MMU 地址翻译流程、快表（TLB）加速与 LRU 页面置换算法。',
          keyPoints: ['多级页表', 'MMU 与 TLB', '缺页异常与写时复制 (COW)'],
          copilotPrompts: [
            '为什么 64 位操作系统普遍采用多级页表而不是单级大页表？',
            'fork() 进程时写时复制（Copy-On-Write）底层是如何通过页表权限实现的？',
            'TLB 缓存未命中（TLB Miss）时硬件和内核各做了哪些工作？'
          ]
        },
        {
          id: 'os-ep-3',
          title: '第 03 讲：并发互斥、条件变量与死锁预防策略',
          duration: '21:30',
          bvid: 'BV1d4411v7UX',
          bpage: 10,
          videoUrl: '',
          summary: '互斥锁、自旋锁、读写锁性能对比，死锁产生的四大必要条件与银行家算法实测。',
          keyPoints: ['互斥锁 vs 自旋锁', '死锁四大必要条件', '锁排序与活锁检测'],
          copilotPrompts: [
            '在什么场景下应该使用自旋锁而不是互斥锁？',
            '银行家算法是如何在分配资源前判断系统是否处于安全状态的？',
            '如何通过静态锁排序彻底规避并发程序中的循环等待死锁？'
          ]
        }
      ]
    },
    {
      id: 'cs-network-http',
      title: '计算机网络原理：透视 HTTP/TCP/IP 协议栈（王道408考研微课）',
      category: 'theory',
      categoryName: '核心理论 / 408',
      level: '体系精讲',
      badge: '通信基石 · 王道精讲',
      instructor: '计算机网络教研组',
      duration: '8 课时 · 约 3.2 小时',
      bvid: 'BV1c4411d7jb',
      coverGradient: 'linear-gradient(135deg, #047857 0%, #10b981 100%)',
      coverIcon: 'link',
      description: '彻底搞懂 TCP 三次握手与四次挥手、滑动窗口拥塞控制、DNS 解析流程与 HTTP/2/3 演进。',
      tags: ['TCP/IP', '三次握手', '拥塞控制', 'HTTP/3 QUIC', 'DNS解析'],
      episodes: [
        {
          id: 'net-ep-1',
          title: '第 01 讲：TCP 核心机制：三次握手与四次挥手全解析',
          duration: '19:45',
          bvid: 'BV1c4411d7jb',
          bpage: 45,
          videoUrl: '',
          summary: 'SYN、ACK、FIN 标志位详解，为什么不是两次握手，TIME_WAIT 状态（2MSL）的必要性。',
          keyPoints: ['序号与确认号', '为什么不能两次握手', 'TIME_WAIT 与 SO_REUSEADDR'],
          copilotPrompts: [
            '为什么 TCP 建立连接需要三次握手，而关闭连接需要四次挥手？',
            'TIME_WAIT 状态为什么要等待 2MSL 时间才彻底释放？',
            '当网络上出现大量 CLOSE_WAIT 状态的连接时，通常是什么原因？'
          ]
        },
        {
          id: 'net-ep-2',
          title: '第 02 讲：TCP 可靠传输：滑动窗口、重传与拥塞控制',
          duration: '23:10',
          bvid: 'BV1c4411d7jb',
          bpage: 48,
          videoUrl: '',
          summary: '流量控制（滑动窗口）与拥塞控制（慢启动、拥塞避免、快重传、快恢复）协同运作。',
          keyPoints: ['滑动窗口机制', '慢启动门限', '快重传与 SACK'],
          copilotPrompts: [
            'TCP 流量控制与拥塞控制有什么根本区别？',
            '快重传机制触发的条件是什么，为什么收到 3 个重复 ACK 就要重传？',
            '现代 BBR 拥塞控制算法相比传统基于丢包的 Cubic 有何优势？'
          ]
        },
        {
          id: 'net-ep-3',
          title: '第 03 讲：HTTP 演进：从 HTTP/1.1、HTTP/2 到 HTTP/3 QUIC',
          duration: '24:00',
          bvid: 'BV1c4411d7jb',
          bpage: 55,
          videoUrl: '',
          summary: 'HTTP/1.1 管道化限制、HTTP/2 二进制分帧与头部压缩（HPACK）、HTTP/3 基于 UDP 的 QUIC 协议。',
          keyPoints: ['头部阻塞 (HOL)', '二进制分帧', 'QUIC 0-RTT 握手'],
          copilotPrompts: [
            'HTTP/2 解决了应用层队头阻塞，为什么依然存在 TCP 层队头阻塞？',
            'HTTP/3 的 QUIC 协议是如何在 UDP 基础上保证数据可靠传输的？',
            'HTTPS 的 TLS 1.3 握手相比 TLS 1.2 是如何减少往返时间（RTT）的？'
          ]
        }
      ]
    },
    {
      id: 'cs-prog-fullstack',
      title: '现代 TypeScript 与前端工程架构实战精讲',
      category: 'programming',
      categoryName: '编程语言与全栈',
      level: '实战进阶',
      badge: '高频全栈 · 源码精读',
      instructor: '资深全栈研发专家',
      duration: '8 课时 · 约 3.5 小时',
      bvid: 'BV14Z4y1u7vy',
      coverGradient: 'linear-gradient(135deg, #4338ca 0%, #6366f1 100%)',
      coverIcon: 'spark',
      description: '掌握 JS 引擎事件循环、闭包与原型链、TypeScript 类型体操、组件状态管理与现代化前端工程。',
      tags: ['TypeScript', '事件循环', 'Promise', '闭包', '微任务'],
      episodes: [
        {
          id: 'ts-ep-1',
          title: '第 01 讲：JS 运行时底层：事件循环、宏任务与微任务',
          duration: '19:20',
          bvid: 'BV14Z4y1u7vy',
          bpage: 1,
          videoUrl: '',
          summary: 'V8 引擎调用栈、任务队列、Promise 微任务与 DOM 渲染时机全流程追踪。',
          keyPoints: ['调用栈与执行上下文', '宏任务 vs 微任务', 'async/await 转换本质'],
          copilotPrompts: [
            '请通俗解释浏览器事件循环中宏任务与微任务的执行次序。',
            'Promise 中的 then 回调与 setImmediate/setTimeout 执行优先级是什么？',
            '为什么在微任务中执行无限循环会导致页面彻底冻结？'
          ]
        },
        {
          id: 'ts-ep-2',
          title: '第 02 讲：TypeScript 高级类型体操与泛型推导',
          duration: '25:40',
          bvid: 'BV14Z4y1u7vy',
          bpage: 8,
          videoUrl: '',
          summary: '条件类型 infer 关键字、分布式条件类型、模板字面量类型与手写 DeepPartial。',
          keyPoints: ['infer 模式匹配', '分布式条件类型', '索引访问与映射类型'],
          copilotPrompts: [
            'TypeScript 中的 infer 关键字在类型推断中是如何工作的？',
            '分布式条件类型在联合类型上的展开规则是什么？',
            '如何手写一个递归将对象所有属性变为可选的 DeepPartial 类型？'
          ]
        }
      ]
    },
    {
      id: 'cs-sys-database',
      title: 'MySQL 索引优化与底层存储引擎深度解析',
      category: 'architecture',
      categoryName: '系统架构与数据库',
      level: '核心架构',
      badge: '数据库调优 · 大厂必问',
      instructor: '知名数据库架构专家',
      duration: '8 课时 · 约 3.0 小时',
      bvid: 'BV12b411K7Zu',
      coverGradient: 'linear-gradient(135deg, #c2410c 0%, #ea580c 100%)',
      coverIcon: 'target',
      description: '深入 InnoDB 存储引擎、B+ 树索引结构、事务 ACID、MVCC 隔离机制与慢 SQL 调优方法论。',
      tags: ['MySQL', 'InnoDB', 'B+树', 'MVCC', '索引覆盖', '死锁排查'],
      episodes: [
        {
          id: 'db-ep-1',
          title: '第 01 讲：InnoDB 架构与 B+ 树索引底层设计',
          duration: '22:15',
          bvid: 'BV12b411K7Zu',
          bpage: 1,
          videoUrl: '',
          summary: '为什么 MySQL 选择 B+ 树而不是哈希表、平衡二叉树或 B 树？聚簇索引与二级索引回表。',
          keyPoints: ['B+ 树结构', '聚簇索引 vs 二级索引', '覆盖索引与最左匹配原则'],
          copilotPrompts: [
            '为什么 MySQL 索引底层选择 B+ 树而不是红黑树或普通 B 树？',
            '什么是覆盖索引，它是如何避免二级索引“回表”查询开销的？',
            '最左前缀匹配原则在联合索引中的底层原理是什么？'
          ]
        },
        {
          id: 'db-ep-2',
          title: '第 02 讲：事务隔离与 MVCC：多版本并发控制原理',
          duration: '26:00',
          bvid: 'BV12b411K7Zu',
          bpage: 14,
          videoUrl: '',
          summary: 'ReadView 生成机制、隐藏列（trx_id, roll_pointer）、Undo Log 版本链与可重复读实现。',
          keyPoints: ['ReadView 规则', 'Undo Log 版本链', '快照读 vs 当前读'],
          copilotPrompts: [
            'InnoDB 在“可重复读（RR）”隔离级别下是如何借助 MVCC 解决不可重复读的？',
            '快照读（Snapshot Read）和当前读（Current Read）有什么本质区别？',
            '间隙锁（Gap Lock）和临键锁（Next-Key Lock）是如何在当前读下避免幻读的？'
          ]
        }
      ]
    },
    {
      id: 'cs-ai-agent',
      title: '大语言模型与 Agent 智能体架构实战精析',
      category: 'ai-agent',
      categoryName: 'AI 与智能体前沿',
      level: '前沿实战',
      badge: '前沿热点 · 智能体设计',
      instructor: 'AI 平台核心研发团队',
      duration: '8 课时 · 约 3.6 小时',
      bvid: 'BV12b421p7eK',
      coverGradient: 'linear-gradient(135deg, #701a75 0%, #a21caf 100%)',
      coverIcon: 'spark',
      description: '拆解 LLM Prompt 工程、RAG 向量检索增强、ReAct 规划推理模式及 MCP 工具协议规范。',
      tags: ['LLM', 'RAG 检索', 'Agent 智能体', 'ReAct', 'MCP协议', 'Function Calling'],
      episodes: [
        {
          id: 'ai-ep-1',
          title: '第 01 讲：RAG 检索增强架构：文本切分、嵌入与重排',
          duration: '21:40',
          bvid: 'BV12b421p7eK',
          bpage: 1,
          videoUrl: '',
          summary: 'Chunking 切分策略、Embedding 向量表征、ANN 向量索引与 Rerank 重排精细化召回。',
          keyPoints: ['Chunking 策略', '向量余弦相似度', '混合检索 (Hybrid Search) 与 Rerank'],
          copilotPrompts: [
            '在构建 RAG 知识库时，如何确定最佳的文档分块大小（Chunk Size）与重叠（Overlap）？',
            '向量检索结合 BM25 关键词检索的混合检索（Hybrid Search）相比单一向量检索有何优势？',
            'RAG 中的幻觉问题（Hallucination）通常可以通过哪些校验流程进行缓解？'
          ]
        },
        {
          id: 'ai-ep-2',
          title: '第 02 讲：Agent 规划与工具调用：ReAct 模式与 MCP 协议',
          duration: '27:10',
          bvid: 'BV12b421p7eK',
          bpage: 3,
          videoUrl: '',
          summary: 'Thought-Action-Observation 闭环、结构化输出、异步工具执行与 Model Context Protocol (MCP)。',
          keyPoints: ['ReAct 循环', 'MCP 协议规范', '多 Agent 协同与任务反思'],
          copilotPrompts: [
            'ReAct 智能体循环中，Thought、Action 与 Observation 是如何交替推进任务的？',
            'Model Context Protocol（MCP）协议相较于传统的函数调用（Function Calling）解决了什么标准化痛点？',
            '当 Agent 遇到工具调用失败时，应如何设计自反思（Self-Reflection）与重试纠错机制？'
          ]
        }
      ]
    }
  ];

  function getAccountId() {
    return (typeof window !== 'undefined' && window.XueyaAccountId) || 'local';
  }
  function getCustomStorageKey() {
    return getAccountId() === 'local' ? STORAGE_KEY : STORAGE_KEY + ':' + getAccountId();
  }
  function getProgressStorageKey() {
    return getAccountId() === 'local' ? PROGRESS_KEY : PROGRESS_KEY + ':' + getAccountId();
  }

  function getCustomCourses() {
    if(serverCurrent())return serverData.courses.filter(c=>!c.platform);
    try {
      const key = getCustomStorageKey();
      let raw = localStorage.getItem(key);
      if (!raw && getAccountId() === 'local') {
        raw = localStorage.getItem(STORAGE_KEY);
        if (raw) localStorage.setItem(key, raw);
      }
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.map(c => ({ ...c, platform: false })) : [];
    } catch {
      return [];
    }
  }

  function saveCustomCourses(courses) {
    try {
      localStorage.setItem(getCustomStorageKey(), JSON.stringify(courses));
    } catch {}
  }

  function getProgress() {
    if(serverCurrent())return serverData.progress;
    try {
      const key = getProgressStorageKey();
      let raw = localStorage.getItem(key);
      if (!raw && getAccountId() === 'local') {
        raw = localStorage.getItem(PROGRESS_KEY);
        if (raw) localStorage.setItem(key, raw);
      }
      if (!raw) return {};
      return JSON.parse(raw) || {};
    } catch {
      return {};
    }
  }

  function saveProgress(courseId, epId, seconds, completed) {
    try {
      const all = getProgress();
      if (!all[courseId]) all[courseId] = { episodes: {}, lastEpisodeId: epId };
      all[courseId].episodes[epId] = {
        seconds: Math.round(seconds || 0),
        completed: Boolean(completed),
        updatedAt: new Date().toISOString()
      };
      all[courseId].lastEpisodeId = epId;
      localStorage.setItem(getProgressStorageKey(), JSON.stringify(all));

      // Synchronize with active study plan and any event listeners
      window.dispatchEvent(new CustomEvent('xueya:course-completed', {
        detail: { courseId, episodeId: epId, completed: Boolean(completed), updatedAt: new Date().toISOString() }
      }));
    } catch {}
  }

  function createCoursesWorkspace({ state, store, toast, ask, render, navigate }) {
    let activeCourseId = null;
    let activeEpisodeId = null;
    let categoryFilter = 'all';
    let searchQuery = '';
    let isAddModalOpen = false;
    let activeSource = 'bilibili'; // 'bilibili' | 'html5' | 'algo-demo'
    let mountController;
    const localVideosMap = {}; // key: "courseId:epId" -> { url, name }

    function getAllCourses() {
      if(serverCurrent())return serverData.courses;
      const custom = getCustomCourses();
      return [...BUILTIN_COURSES.map(c=>({...c,platform:true,verification:'legacy-unverified'})), ...custom];
    }

    function getFilteredCourses() {
      const list = getAllCourses();
      const q = searchQuery.trim().toLowerCase();
      return list.filter(c => {
        const matchCat = categoryFilter === 'all' || c.category === categoryFilter;
        if (!matchCat) return false;
        if (!q) return true;
        const text = (c.title + ' ' + (c.description || '') + ' ' + (c.tags || []).join(' ') + ' ' + (c.instructor || '')).toLowerCase();
        return text.includes(q);
      });
    }

    function calculateStats() {
      const courses = getAllCourses();
      const progress = getProgress();
      let completedCount = 0;
      let totalEpisodes = 0;
      let studiedEpisodes = 0;

      courses.forEach(c => {
        totalEpisodes += c.episodes.length;
        const prog = progress[c.id];
        if (prog && prog.episodes) {
          const finished = Object.values(prog.episodes).filter(e => e.completed).length;
          studiedEpisodes += Object.keys(prog.episodes).length;
          if (finished === c.episodes.length && c.episodes.length > 0) {
            completedCount++;
          }
        }
      });

      return {
        totalCourses: courses.length,
        completedCount,
        studiedEpisodes,
        totalEpisodes,
        percentage: totalEpisodes > 0 ? Math.min(100, Math.round((studiedEpisodes / totalEpisodes) * 100)) : 0
      };
    }

    function renderCatalog() {
      const stats = calculateStats();
      const courses = getFilteredCourses();
      const progress = getProgress();

      const categories = [
        { id: 'all', label: '全部体系课程' },
        { id: 'theory', label: '计算机考研 408' },
        { id: 'programming', label: '数据结构与算法' },
        { id: 'architecture', label: '操作系统与网络' },
        { id: 'ai-agent', label: 'AI 与智能体前沿' }
      ];

      return `
        <div class="courses-container flex flex-col gap-6 animate-fade-in pb-12">
          <!-- Top Metrics & Action Hero Banner (Stitch Screen 1) -->
          <section class="relative w-full rounded-2xl bg-surface-container-lowest/90 backdrop-blur-xl shadow-sm border border-outline-variant/30 p-6 lg:p-7 overflow-hidden">
            <div class="absolute -right-24 -top-24 w-80 h-80 rounded-full bg-primary/10 blur-3xl pointer-events-none"></div>
            <div class="absolute right-1/3 -bottom-28 w-72 h-72 rounded-full bg-secondary-container/10 blur-3xl pointer-events-none"></div>

            <div class="relative z-10 flex flex-col xl:flex-row xl:items-center justify-between gap-6">
              <!-- Left: Academic Mission & Progress Stream -->
              <div class="flex-1 flex flex-col gap-3 min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 text-primary font-label-md text-xs font-semibold">
                    <span class="material-symbols-outlined text-[15px]">terminal</span>
                    CS 学科知识图谱引擎
                  </span>
                  <span class="inline-flex items-center gap-1.5 text-on-surface-variant font-code-sm text-xs">
                    <span class="w-2 h-2 rounded-full bg-secondary"></span>
                    同步大纲: 2025 计算机 408 统考 & 顶尖名校体系
                  </span>
                </div>
                <div class="flex flex-col gap-1">
                  <h1 class="font-display-lg text-2xl lg:text-3xl text-on-surface tracking-tight font-bold">计算机精品课程研修台</h1>
                  <p class="font-body-md text-sm text-on-surface-variant">聚合顶级高校国家精品课程与前沿 AI 架构实践，构建严密、贯通底层的计算机认知范式。</p>
                </div>

                <!-- Integrated Progress Metrics Strip -->
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
                  <div class="flex items-center gap-3 p-3 rounded-xl bg-surface-container-low/70 border border-outline-variant/20">
                    <div class="w-10 h-10 rounded-lg bg-primary-container text-on-primary flex items-center justify-center shadow-sm">
                      <span class="material-symbols-outlined text-[20px]">school</span>
                    </div>
                    <div class="flex flex-col">
                      <span class="text-xs text-outline">已录入体系课程</span>
                      <span class="text-lg text-on-surface font-bold tracking-tight">${stats.totalCourses} <span class="text-xs font-normal text-on-surface-variant">门精选</span></span>
                    </div>
                  </div>

                  <div class="flex items-center gap-3 p-3 rounded-xl bg-surface-container-low/70 border border-outline-variant/20">
                    <div class="w-10 h-10 rounded-lg bg-secondary text-on-secondary flex items-center justify-center shadow-sm">
                      <span class="material-symbols-outlined text-[20px]">schedule</span>
                    </div>
                    <div class="flex flex-col">
                      <span class="text-xs text-outline">累计已学课时</span>
                      <span class="text-lg text-on-surface font-bold tracking-tight">${stats.studiedEpisodes} <span class="text-xs font-normal text-on-surface-variant">/ ${stats.totalEpisodes} 课时</span></span>
                    </div>
                  </div>

                  <div class="flex items-center justify-between p-3 rounded-xl bg-surface-container-low/70 border border-outline-variant/20">
                    <div class="flex flex-col">
                      <span class="text-xs text-outline">综合完成进度</span>
                      <span class="text-lg text-primary font-bold tracking-tight">${stats.percentage}%</span>
                    </div>
                    <div class="relative w-10 h-10 flex items-center justify-center">
                      <svg class="w-10 h-10 -rotate-90" viewBox="0 0 36 36">
                        <circle class="text-surface-container-high" cx="18" cy="18" fill="none" r="14" stroke="currentColor" stroke-width="3"></circle>
                        <circle class="text-primary" cx="18" cy="18" fill="none" r="14" stroke="currentColor" stroke-dasharray="87.96" stroke-dashoffset="${87.96 * (1 - stats.percentage / 100)}" stroke-linecap="round" stroke-width="3.5"></circle>
                      </svg>
                      <span class="material-symbols-outlined absolute text-[15px] text-primary">flag</span>
                    </div>
                  </div>
                </div>

                <!-- Linear Progress Bar -->
                <div class="flex flex-col gap-1 pt-1">
                  <div class="flex items-center justify-between text-xs text-on-surface-variant">
                    <span>当前学期总规划履约度</span>
                    <span class="font-code-sm text-outline font-medium">本周建议新增研习 ≥ 4.5 小时</span>
                  </div>
                  <div class="w-full h-2 rounded-full bg-surface-container-highest overflow-hidden">
                    <div class="h-full bg-gradient-to-r from-primary to-secondary rounded-full transition-all duration-700" style="width: ${Math.max(4, stats.percentage)}%;"></div>
                  </div>
                </div>
              </div>

              <!-- Right: Rapid Action Hub -->
              <div class="flex flex-col sm:flex-row xl:flex-col gap-2.5 xl:w-72 shrink-0">
                <button class="group relative flex items-center justify-between w-full px-4 py-3 rounded-xl bg-primary text-on-primary font-semibold text-sm shadow-[0_6px_20px_rgba(79,70,229,0.25)] hover:bg-primary-container transition-all" type="button" data-open-add-course>
                  <div class="flex items-center gap-2.5">
                    <div class="w-7 h-7 rounded-lg bg-surface-container-lowest/20 flex items-center justify-center">
                      <span class="material-symbols-outlined text-[18px]">add_circle</span>
                    </div>
                    <span>添加自定义视频课</span>
                  </div>
                  <span class="material-symbols-outlined text-[18px] group-hover:translate-x-1 transition-transform">arrow_forward</span>
                </button>
                <div class="p-3 rounded-xl bg-surface-container-low text-on-surface-variant flex items-center gap-2 border border-outline-variant/20">
                  <span class="material-symbols-outlined text-[18px] text-tertiary">psychology</span>
                  <span class="text-xs leading-snug">支持随堂切片标记与 AI 启发式问答</span>
                </div>
              </div>
            </div>
          </section>

          <!-- Toolbar: Categories and Search (Stitch Screen 1) -->
          <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div class="flex flex-wrap items-center gap-1.5 p-1 bg-surface-container-low rounded-xl border border-outline-variant/30" role="tablist" aria-label="课程分类">
              ${categories.map(cat => `
                <button type="button" class="px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${categoryFilter === cat.id ? 'bg-surface-container-lowest text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container'}" data-course-category="${cat.id}">
                  ${cat.label}
                </button>
              `).join('')}
            </div>
            <div class="relative flex items-center min-w-[260px]">
              <span class="material-symbols-outlined text-outline absolute left-3 text-[18px]">search</span>
              <input type="search" class="w-full pl-9 pr-4 py-2 rounded-xl bg-surface-container-lowest text-on-surface text-xs outline-none border border-outline-variant/30 focus:border-primary shadow-sm" id="courseSearchInput" placeholder="搜索课程名称、知识点或讲师…" value="${escapeHTML(searchQuery)}">
            </div>
          </div>

          <!-- Courses Grid (Stitch Screen 1) -->
          <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            ${courses.length ? courses.map(c => {
              const prog = progress[c.id];
              const finishedCount = prog?.episodes ? Object.values(prog.episodes).filter(e => e.completed).length : 0;
              const percent = c.episodes.length ? Math.round((finishedCount / c.episodes.length) * 100) : 0;
              return `
                <article class="stitch-card flex flex-col justify-between overflow-hidden group hover:-translate-y-1 transition-all" data-course-card-id="${escapeHTML(c.id)}">
                  <div>
                    <!-- Course Header Cover -->
                    <div class="relative h-40 p-4 flex flex-col justify-between overflow-hidden" style="background: ${escapeHTML(c.coverGradient || '#1e293b')};">
                      <div class="flex items-center justify-between relative z-10">
                        <span class="px-2.5 py-0.5 rounded-full bg-surface-container-lowest/85 backdrop-blur-md text-primary font-bold text-[11px]">${escapeHTML(c.badge || c.categoryName)}</span>
                        <span class="px-2.5 py-0.5 rounded-full bg-black/40 backdrop-blur-md text-white text-[11px]">${escapeHTML(c.level || '精选')}</span>
                      </div>
                      <div class="flex items-center justify-center relative z-10">
                        <div class="w-12 h-12 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center text-white shadow-lg group-hover:scale-110 transition-transform">
                          <span class="material-symbols-outlined text-[28px]">play_arrow</span>
                        </div>
                      </div>
                      <div class="flex items-center justify-between text-white/90 text-xs relative z-10">
                        <span class="flex items-center gap-1"><span class="material-symbols-outlined text-[14px]">timer</span>${escapeHTML(c.duration || (c.episodes.length + ' 课时'))}</span>
                        <span class="font-code-sm text-[11px]">${c.episodes.length} 讲全</span>
                      </div>
                    </div>

                    <!-- Course Body -->
                    <div class="p-5 flex flex-col gap-2">
                      <span class="text-xs text-primary font-semibold tracking-wider uppercase">${escapeHTML(c.categoryName)}</span>
                      <h3 class="font-headline-sm text-base text-on-surface font-bold line-clamp-1" title="${escapeHTML(c.title)}">${escapeHTML(c.title)}</h3>
                      <p class="text-xs text-on-surface-variant line-clamp-2">${escapeHTML(c.description || '深入剖析核心原理与工程实操，配套边看边问 AI 答疑。')}</p>
                      
                      <!-- Tags -->
                      <div class="flex flex-wrap gap-1.5 pt-1">
                        ${(c.tags || []).slice(0, 3).map(t => `<span class="px-2 py-0.5 rounded-md bg-surface-container text-on-surface-variant text-[11px]">${escapeHTML(t)}</span>`).join('')}
                      </div>
                    </div>
                  </div>

                  <!-- Course Footer -->
                  <div class="p-5 pt-0 flex flex-col gap-3">
                    ${percent > 0 ? `
                      <div class="flex flex-col gap-1">
                        <div class="flex items-center justify-between text-[11px] text-on-surface-variant">
                          <span>已学进度</span>
                          <span class="font-code-sm text-primary font-bold">${percent}%</span>
                        </div>
                        <div class="w-full h-1.5 rounded-full bg-surface-container overflow-hidden">
                          <div class="h-full bg-primary rounded-full transition-all" style="width: ${percent}%;"></div>
                        </div>
                      </div>
                    ` : ''}

                    <div class="flex items-center justify-between pt-2 border-t border-outline-variant/20">
                      <div class="flex items-center gap-1.5 text-xs text-on-surface-variant">
                        <span class="material-symbols-outlined text-[16px]">person</span>
                        <span class="truncate max-w-[120px]">${escapeHTML(c.instructor || '名校教研组')}</span>
                      </div>
                      <button type="button" class="px-3.5 py-1.5 rounded-lg bg-primary text-on-primary font-semibold text-xs flex items-center gap-1 hover:bg-primary-container transition-all shadow-sm" data-enter-course="${escapeHTML(c.id)}">
                        <span>${percent > 0 ? (percent === 100 ? '复习课程' : `继续学习 (${percent}%)`) : '进入伴学播放'}</span>
                        <span class="material-symbols-outlined text-[14px]">arrow_forward</span>
                      </button>
                    </div>
                  </div>
                </article>
              `;
            }).join('') : `
              <div class="col-span-full p-12 text-center flex flex-col items-center justify-center gap-3 bg-surface-container-lowest rounded-2xl border border-outline-variant/30">
                <span class="material-symbols-outlined text-4xl text-outline">search_off</span>
                <h3 class="text-base font-bold text-on-surface">未找到匹配的计算机课程</h3>
                <p class="text-xs text-on-surface-variant">尝试切换筛选分类，或换一个关键词进行搜索。</p>
              </div>
            `}
          </div>
        </div>
      `;
    }

    function renderPlayer(course) {
      const progress = getProgress();
      const courseProg = progress[course.id] || { episodes: {} };
      const currentEp = course.episodes.find(e => e.id === activeEpisodeId) || course.episodes[0];
      const isCompleted = Boolean(courseProg.episodes[currentEp?.id]?.completed);
      const localKey = course.id + ':' + currentEp?.id;
      const localVideo = localVideosMap[localKey];
      const hasLocalVideo = Boolean(localVideo?.url);
      const videoSrc = localVideo?.url || currentEp?.videoUrl || '';
      const bvid = currentEp?.bvid || course.bvid || '';
      const bpage = currentEp?.bpage || 1;

      return `
        <div class="w-full max-w-[1680px] mx-auto px-4 lg:px-6 py-4 flex flex-col gap-5 animate-fade-in">
          <!-- Meta Bar: Lecture Context & Quick Actions (Stitch Screen 3) -->
          <section class="w-full bg-surface-container-lowest/90 backdrop-blur-xl rounded-2xl p-4 lg:p-5 shadow-[0_4px_20px_-2px_rgba(15,23,42,0.04)] border border-outline-variant/30 flex flex-col xl:flex-row items-start xl:items-center justify-between gap-4">
            <div class="flex flex-col sm:flex-row items-start sm:items-center gap-4 min-w-0">
              <button type="button" class="h-10 px-3.5 rounded-xl bg-surface-container-low hover:bg-surface-container text-on-surface-variant hover:text-on-surface font-label-md text-label-md flex items-center gap-2 transition-all shadow-sm flex-shrink-0" data-back-to-catalog title="返回课程列表">
                <span class="material-symbols-outlined text-[18px]">arrow_back</span>
                <span>返回目录</span>
              </button>

              <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-primary via-primary-container to-tertiary-container flex items-center justify-center text-on-primary shadow-md flex-shrink-0">
                <span class="material-symbols-outlined text-[22px]">play_circle</span>
              </div>

              <div class="flex flex-col min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-headline-sm text-headline-sm text-on-surface font-semibold truncate max-w-[460px]">
                    ${escapeHTML(currentEp?.title || course.title)}
                  </span>
                  <span class="px-2.5 py-0.5 rounded-full bg-primary-fixed text-primary font-label-md text-label-md font-semibold">
                    ${escapeHTML(course.categoryName || '408 核心考点')}
                  </span>
                  <span class="px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm">
                    ${escapeHTML(course.instructor || '名校公开课')} · ${escapeHTML(course.title)}
                  </span>
                </div>
                <div class="flex items-center gap-3 text-on-surface-variant font-body-sm text-body-sm mt-1">
                  <span class="flex items-center gap-1 font-code-sm text-code-sm text-primary font-semibold">
                    <span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
                    ${escapeHTML(currentEp?.duration || '15:00')}
                  </span>
                  <span class="text-outline-variant">•</span>
                  <span class="truncate max-w-[600px]">${escapeHTML(currentEp?.summary || course.description)}</span>
                </div>
              </div>
            </div>

            <!-- Action Cluster -->
            <div class="flex items-center gap-2 sm:gap-2.5 flex-wrap self-end xl:self-auto">
              <button type="button" class="h-9 px-3 rounded-lg ${isCompleted ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300' : 'bg-surface-container-low hover:bg-surface-container text-on-surface-variant hover:text-on-surface'} font-label-md text-label-md flex items-center gap-1.5 transition-all shadow-sm" data-toggle-ep-complete="${escapeHTML(currentEp?.id)}">
                <span class="material-symbols-outlined text-[18px]">${isCompleted ? 'check_circle' : 'radio_button_unchecked'}</span>
                <span>${isCompleted ? '已学完' : '标记已学完'}</span>
              </button>

              <a href="#space/knowledge" class="h-9 px-3 rounded-lg bg-surface-container-low hover:bg-surface-container text-on-surface-variant hover:text-on-surface font-label-md text-label-md flex items-center gap-1.5 transition-all shadow-sm">
                <span class="material-symbols-outlined text-[18px]">picture_as_pdf</span>
                <span>讲义资料</span>
              </a>

              <a href="#space/practice" class="h-9 px-3 rounded-lg bg-primary text-on-primary hover:bg-primary-container font-label-md text-label-md flex items-center gap-1.5 shadow-sm transition-all">
                <span class="material-symbols-outlined text-[18px]">quiz</span>
                <span>随堂练习</span>
              </a>
            </div>
          </section>

          <!-- Source Switcher Bar -->
          <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 px-1">
            <div class="flex items-center gap-2 p-1 bg-surface-container-low rounded-xl border border-outline-variant/30 flex-wrap">
              <button type="button" class="px-3.5 py-1.5 rounded-lg font-label-sm text-label-sm font-semibold flex items-center gap-1.5 transition-all ${activeSource === 'bilibili' ? 'bg-surface-container-lowest text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}" data-switch-source="bilibili" ${bvid ? '' : 'disabled'}>
                <span class="material-symbols-outlined text-[16px]">live_tv</span>
                <span>B 站在线高清播放器</span>
              </button>
              <button type="button" class="px-3.5 py-1.5 rounded-lg font-label-sm text-label-sm font-semibold flex items-center gap-1.5 transition-all ${activeSource === 'html5' ? 'bg-surface-container-lowest text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}" data-switch-source="html5">
                <span class="material-symbols-outlined text-[16px]">video_library</span>
                <span>本地无损 / HTML5 播放器</span>
              </button>
              <button type="button" class="px-3.5 py-1.5 rounded-lg font-label-sm text-label-sm font-semibold flex items-center gap-1.5 transition-all ${activeSource === 'algo-demo' ? 'bg-surface-container-lowest text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}" data-switch-source="algo-demo">
                <span class="material-symbols-outlined text-[16px]">animation</span>
                <span>算法机制演练屏</span>
              </button>
            </div>

            <div class="flex items-center gap-2">
              <label class="h-8 px-3 rounded-lg bg-surface-container-lowest border border-outline-variant/40 hover:border-primary text-on-surface font-label-sm text-label-sm flex items-center gap-1.5 cursor-pointer shadow-sm transition-all" title="选取电脑中的视频文件，零网络延迟流畅播放">
                <span class="material-symbols-outlined text-[16px] text-primary">folder_open</span>
                <span>选取本地视频文件</span>
                <input type="file" id="localVideoFileInput" accept="video/mp4,video/webm,video/ogg,video/mkv,.mp4,.webm,.mkv,.mov" hidden>
              </label>
              ${localVideo?.name ? `<span class="text-xs text-on-surface-variant max-w-[200px] truncate" title="${escapeHTML(localVideo.name)}">已载入：${escapeHTML(localVideo.name)}</span>` : ''}
            </div>
          </div>

          <!-- Main Dual Workbench: Left (65%) Video & Materials, Right (35%) AI Copilot -->
          <div class="grid grid-cols-1 lg:grid-cols-12 gap-5 w-full items-start">
            <!-- Left Column (Lecture & Materials - col-span-8) -->
            <div class="lg:col-span-8 flex flex-col gap-4 min-w-0">
              <!-- Video Player Viewport Container -->
              <div class="relative w-full rounded-2xl overflow-hidden bg-inverse-surface shadow-2xl flex flex-col group border border-slate-800">
                <div class="relative w-full aspect-video bg-black flex items-center justify-center overflow-hidden">
                  ${activeSource === 'bilibili' && bvid ? `
                    <iframe id="csBilibiliPlayer" class="w-full h-full border-0" src="https://player.bilibili.com/player.html?bvid=${encodeURIComponent(bvid)}&page=${encodeURIComponent(bpage)}&high_quality=1&danmaku=0&autoplay=0" scrolling="no" border="0" frameborder="no" framespacing="0" allowfullscreen="true" sandbox="allow-top-navigation allow-same-origin allow-forms allow-scripts"></iframe>
                  ` : activeSource === 'html5' ? `
                    ${videoSrc ? `
                      <video id="csVideoPlayer" class="w-full h-full object-contain" controls preload="metadata" src="${escapeHTML(videoSrc)}">
                        <p>您的浏览器不支持 HTML5 视频播放。</p>
                      </video>
                    ` : `
                      <div class="w-full h-full bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 flex flex-col items-center justify-center p-6 text-center text-white">
                        <div class="w-16 h-16 rounded-2xl bg-white/10 flex items-center justify-center text-3xl mb-3 shadow-inner">🎬</div>
                        <h3 class="text-lg font-bold">选取电脑上的视频文件即可立即播放</h3>
                        <p class="text-sm text-slate-400 mt-1 mb-4 max-w-md">支持电脑中的 MP4、WebM、MKV 视频文件，零网络延迟，超清流畅播放！</p>
                        <label class="px-4 py-2 rounded-xl bg-primary text-white font-semibold cursor-pointer hover:bg-primary-container transition shadow flex items-center gap-2">
                          <span class="material-symbols-outlined text-[18px]">upload_file</span>
                          <span>选取电脑上的视频文件</span>
                          <input type="file" id="localVideoFileInputInner" accept="video/*" hidden>
                        </label>
                      </div>
                    `}
                  ` : `
                    <div class="w-full h-full bg-slate-950 flex flex-col items-center justify-center p-4">
                      <canvas id="algoCanvas" class="w-full max-w-[720px] aspect-[16/9] bg-slate-900 rounded-xl shadow-inner border border-slate-800" width="800" height="450"></canvas>
                      <div class="flex items-center justify-between w-full max-w-[720px] mt-3 px-2 text-xs text-slate-400">
                        <button type="button" class="px-3 py-1.5 rounded-lg bg-primary text-white font-semibold flex items-center gap-1.5 hover:bg-primary-container transition" data-run-algo-demo>
                          <span class="material-symbols-outlined text-[14px]">replay</span>
                          <span>重新开始动态演练</span>
                        </button>
                        <span>二叉搜索树（BST）插入、中序遍历与平衡树旋转机制动态可视化模拟</span>
                      </div>
                    </div>
                  `}

                  <!-- Floating Live Indicator Overlay -->
                  <div class="absolute top-3 left-3 right-3 flex items-center justify-between pointer-events-none">
                    <div class="flex items-center gap-2 pointer-events-auto">
                      <span class="px-2.5 py-1 rounded-md bg-inverse-surface/85 backdrop-blur-md text-inverse-on-surface font-label-sm text-label-sm flex items-center gap-1.5 shadow-sm text-white">
                        <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
                        1080P Ultra · 60 FPS
                      </span>
                      <span class="px-2.5 py-1 rounded-md bg-primary/85 backdrop-blur-md text-white font-label-sm text-label-sm font-semibold">
                        当前：${escapeHTML(currentEp?.title || '正在学习')}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Keypoints Tags Strip -->
              ${currentEp?.keyPoints?.length ? `
                <div class="p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/30 flex flex-col sm:flex-row items-start sm:items-center gap-3 shadow-sm">
                  <div class="flex items-center gap-1.5 text-primary font-label-md text-label-md font-semibold flex-shrink-0">
                    <span class="material-symbols-outlined text-[18px]">key</span>
                    <span>本节核心考点：</span>
                  </div>
                  <div class="flex items-center gap-2 flex-wrap">
                    ${currentEp.keyPoints.map(kp => `<span class="px-2.5 py-1 rounded-lg bg-surface-container-low text-on-surface font-label-sm text-label-sm border border-outline-variant/20">${escapeHTML(kp)}</span>`).join('')}
                  </div>
                </div>
              ` : ''}

              <!-- Course Episodes Timeline Grid -->
              <div class="p-5 rounded-2xl bg-surface-container-lowest border border-outline-variant/30 flex flex-col gap-4 shadow-sm">
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-primary text-[22px]">format_list_bulleted</span>
                    <h3 class="font-headline-sm text-headline-sm font-bold text-on-surface">课程全集选课列表</h3>
                  </div>
                  <span class="font-label-md text-label-md text-on-surface-variant font-medium">全 ${course.episodes.length} 讲 · 实时同步学情</span>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-[380px] overflow-y-auto pr-1">
                  ${course.episodes.map((ep, idx) => {
                    const epProg = courseProg.episodes?.[ep.id];
                    const epDone = Boolean(epProg?.completed);
                    const isCurrent = ep.id === (currentEp?.id || course.episodes[0].id);
                    return `
                      <button type="button" class="flex items-center justify-between p-3 rounded-xl text-left transition-all border ${isCurrent ? 'bg-primary-fixed/30 border-primary shadow-sm' : 'bg-surface-container-low/60 hover:bg-surface-container border-outline-variant/20'}" data-switch-episode="${escapeHTML(ep.id)}">
                        <div class="flex items-center gap-3 min-w-0">
                          <span class="w-6 h-6 rounded-lg ${isCurrent ? 'bg-primary text-on-primary' : 'bg-surface-container text-on-surface-variant'} flex items-center justify-center font-code-sm text-code-sm font-bold flex-shrink-0">${idx + 1}</span>
                          <div class="flex flex-col min-w-0">
                            <span class="font-label-md text-label-md font-semibold truncate ${isCurrent ? 'text-primary' : 'text-on-surface'}">${escapeHTML(ep.title)}</span>
                            <span class="text-xs text-on-surface-variant">${escapeHTML(ep.duration || '15:00')}</span>
                          </div>
                        </div>
                        <div class="flex items-center gap-1.5 flex-shrink-0 ml-2">
                          ${isCurrent ? '<span class="text-primary font-bold text-xs">正在播放</span>' : epDone ? '<span class="material-symbols-outlined text-emerald-600 text-[18px]">check_circle</span>' : '<span class="material-symbols-outlined text-outline-variant text-[18px]">play_arrow</span>'}
                        </div>
                      </button>
                    `;
                  }).join('')}
                </div>
              </div>
            </div>

            <!-- Right Column: AI Copilot Companion Workbench (col-span-4) -->
            <div class="lg:col-span-4 flex flex-col gap-4 min-w-0">
              <div class="w-full bg-surface-container-lowest/95 backdrop-blur-2xl rounded-2xl shadow-[0_12px_32px_-4px_rgba(79,70,229,0.08)] border border-outline-variant/30 flex flex-col">
                <!-- Copilot Header -->
                <div class="p-4 rounded-t-2xl bg-surface-container-lowest flex items-center justify-between gap-3 border-b border-outline-variant/20">
                  <div class="flex items-center gap-3 min-w-0">
                    <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-primary to-tertiary-container flex items-center justify-center text-on-primary shadow-sm flex-shrink-0">
                      <span class="material-symbols-outlined text-[20px]">smart_toy</span>
                    </div>
                    <div class="flex flex-col min-w-0">
                      <div class="flex items-center gap-1.5">
                        <span class="font-headline-sm text-headline-sm text-on-surface font-bold truncate">学涯 Copilot 随堂伴学</span>
                        <span class="px-1.5 py-0.2 rounded bg-tertiary-fixed text-tertiary font-label-sm text-label-sm font-semibold">MiMo 3.5</span>
                      </div>
                      <div class="flex items-center gap-1.5 text-on-surface-variant font-label-sm text-label-sm">
                        <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                        <span>已对齐当前课程与知识切片</span>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Smart Quick Chips Capsule Bar -->
                <div class="px-4 py-2.5 bg-surface-container-low flex flex-col gap-2 border-b border-outline-variant/20">
                  <div class="flex items-center gap-1 text-xs text-primary font-semibold">
                    <span class="material-symbols-outlined text-[14px]">tips_and_updates</span>
                    <span>针对本节快速提问（点击即问）：</span>
                  </div>
                  <div class="flex flex-col gap-1.5">
                    ${(currentEp?.copilotPrompts || [
                      `请结合《${escapeHTML(course.title)}》本节内容，通俗讲解其核心原理。`,
                      `本节知识点在实际生产或考研 408 中有什么典型应用和性能陷阱？`,
                      `能根据本节知识点为我出两道期末复习或面试高频题吗？`
                    ]).map(q => `
                      <button type="button" class="px-3 py-2 rounded-xl bg-surface-container-lowest hover:bg-primary-fixed/30 text-on-surface hover:text-primary font-label-sm text-label-sm flex items-center justify-between gap-2 shadow-sm transition-all text-left border border-outline-variant/20 group" data-ask-in-class="${encodeURIComponent(q)}">
                        <span class="truncate">${escapeHTML(q)}</span>
                        <span class="material-symbols-outlined text-[14px] text-outline-variant group-hover:text-primary flex-shrink-0">arrow_forward</span>
                      </button>
                    `).join('')}
                  </div>
                </div>

                <!-- Copilot In-Class Custom Question Input -->
                <div class="p-4 flex flex-col gap-3">
                  <div class="relative w-full">
                    <input type="text" id="inClassCustomInput" class="w-full h-11 pl-3.5 pr-20 rounded-xl bg-surface-container-low border border-outline-variant/40 text-on-surface placeholder:text-on-surface-variant font-body-sm text-body-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" placeholder="输入关于本节的疑问…">
                    <button type="button" class="absolute right-1.5 top-1.5 h-8 px-3 rounded-lg bg-primary text-on-primary hover:bg-primary-container font-label-sm text-label-sm font-semibold flex items-center gap-1 shadow-sm transition-all" data-send-in-class>
                      <span>随堂提问</span>
                      <span class="material-symbols-outlined text-[14px]">send</span>
                    </button>
                  </div>
                  <div class="flex items-center justify-between text-xs text-on-surface-variant px-1">
                    <span>支持 LaTeX 公式与代码推导</span>
                    <a href="#space/ask" class="text-primary hover:underline flex items-center gap-0.5">
                      <span>打开完整对话台</span>
                      <span class="material-symbols-outlined text-[12px]">open_in_new</span>
                    </a>
                  </div>
                </div>
              </div>

              <!-- Quick Link Card to Review and Analysis -->
              <div class="p-4 rounded-2xl bg-surface-container-lowest border border-outline-variant/30 flex flex-col gap-2.5 shadow-sm">
                <div class="flex items-center gap-2 text-on-surface font-semibold text-sm">
                  <span class="material-symbols-outlined text-primary text-[18px]">insights</span>
                  <span>关联学习闭环推荐</span>
                </div>
                <div class="grid grid-cols-2 gap-2">
                  <a href="#space/review" class="p-2.5 rounded-xl bg-surface-container-low hover:bg-surface-container text-xs text-on-surface font-medium flex flex-col gap-1 transition">
                    <span class="text-primary font-bold">错题复习本</span>
                    <span class="text-on-surface-variant">艾宾浩斯智能循环</span>
                  </a>
                  <a href="#space/analysis" class="p-2.5 rounded-xl bg-surface-container-low hover:bg-surface-container text-xs text-on-surface font-medium flex flex-col gap-1 transition">
                    <span class="text-primary font-bold">AI 学情报告</span>
                    <span class="text-on-surface-variant">知识断层靶向诊断</span>
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      `;
    }

    function renderAddModal() {
      if (!isAddModalOpen) return '';
      return `
        <div class="courses-modal-backdrop" id="addCourseBackdrop">
          <div class="courses-modal-card" role="dialog" aria-labelledby="addCourseTitle">
            <div class="modal-header">
              <h2 id="addCourseTitle">添加自定义计算机视频课程</h2>
              <button type="button" class="modal-close-btn" data-close-add-course aria-label="关闭">×</button>
            </div>
            <form id="addCourseForm" class="modal-form">
              <label class="form-field">
                <span>课程名称 *</span>
                <input type="text" id="addCourseName" required placeholder="如：Go 语言高并发微服务架构实战" maxlength="100">
              </label>
              <div class="form-row">
                <label class="form-field">
                  <span>课程分类</span>
                  <select id="addCourseCategory">
                    <option value="theory">核心理论 / 408</option>
                    <option value="programming">编程语言与全栈</option>
                    <option value="architecture">系统架构与数据库</option>
                    <option value="ai-agent">AI 与智能体前沿</option>
                  </select>
                </label>
                <label class="form-field">
                  <span>课程难度</span>
                  <select id="addCourseLevel">
                    <option value="入门基石">入门基石</option>
                    <option value="进阶深化" selected>进阶深化</option>
                    <option value="实战架构">实战架构</option>
                  </select>
                </label>
              </div>
              <div class="form-row">
                <label class="form-field">
                  <span>主讲人 / 出品机构</span>
                  <input type="text" id="addCourseInstructor" placeholder="如：计算机教研团队" maxlength="50">
                </label>
                <label class="form-field">
                  <span>标签 (用空格隔开)</span>
                  <input type="text" id="addCourseTags" placeholder="如：Go 微服务 gRPC 性能调优" maxlength="100">
                </label>
              </div>
              <label class="form-field">
                <span>视频播放源（支持 B站 BV号如 BV1b7411N798，或输入在线 MP4 直链）</span>
                <input type="text" id="addCourseVideoUrl" placeholder="如 BV1b7411N798 或 https://.../video.mp4" value="BV1b7411N798">
              </label>
              <label class="form-field">
                <span>课程简介</span>
                <textarea id="addCourseDesc" rows="3" placeholder="简要介绍课程主要内容和学习目标…" maxlength="500"></textarea>
              </label>
              <div class="modal-actions">
                <button type="button" class="button button-outline" data-close-add-course>取消</button>
                <button type="submit" class="button button-blue">确认添加并开始学习</button>
              </div>
            </form>
          </div>
        </div>
      `;
    }

    function drawAlgoDemoCanvas() {
      const canvas = document.getElementById('algoCanvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const w = canvas.width;
      const h = canvas.height;
      let frame = 0;
      let animId = null;

      const nodes = [
        { val: 50, x: w / 2, y: 70, parent: null },
        { val: 30, x: w / 2 - 140, y: 160, parent: 0 },
        { val: 70, x: w / 2 + 140, y: 160, parent: 0 },
        { val: 20, x: w / 2 - 210, y: 260, parent: 1 },
        { val: 40, x: w / 2 - 70, y: 260, parent: 1 },
        { val: 60, x: w / 2 + 70, y: 260, parent: 2 },
        { val: 85, x: w / 2 + 210, y: 260, parent: 2 }
      ];

      function renderFrame() {
        ctx.fillStyle = '#0f172a';
        ctx.fillRect(0, 0, w, h);

        // Title
        ctx.fillStyle = '#94a3b8';
        ctx.font = '14px sans-serif';
        ctx.fillText('二叉搜索树（BST）与 AVL 平衡因子动态演练模拟', 24, 34);

        // Draw edges
        ctx.lineWidth = 2;
        nodes.forEach((n, idx) => {
          if (n.parent !== null) {
            const p = nodes[n.parent];
            ctx.strokeStyle = '#334155';
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(n.x, n.y);
            ctx.stroke();
          }
        });

        // Current active node in traversal
        const activeIdx = Math.floor((frame / 40) % (nodes.length + 2));

        // Draw nodes
        nodes.forEach((n, idx) => {
          const isActive = idx === activeIdx;
          ctx.beginPath();
          ctx.arc(n.x, n.y, 22, 0, Math.PI * 2);
          ctx.fillStyle = isActive ? '#2563eb' : '#1e293b';
          ctx.fill();
          ctx.strokeStyle = isActive ? '#60a5fa' : '#3b82f6';
          ctx.lineWidth = isActive ? 3 : 2;
          ctx.stroke();

          ctx.fillStyle = '#fff';
          ctx.font = 'bold 13px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(String(n.val), n.x, n.y);
        });

        // Status caption
        ctx.fillStyle = '#38bdf8';
        ctx.font = '13px sans-serif';
        ctx.textAlign = 'left';
        if (activeIdx < nodes.length) {
          ctx.fillText(`查找中序遍历序列: 节点 [${nodes[activeIdx].val}] 比较成功 (左子树 < 根 < 右子树)`, 24, h - 55);
        } else {
          ctx.fillText('BST 保持中序递增序：[20, 30, 40, 50, 60, 70, 85]，查找复杂度 O(log n)', 24, h - 55);
        }

        frame++;
        animId = requestAnimationFrame(renderFrame);
      }

      renderFrame();
      return () => { if (animId) cancelAnimationFrame(animId); };
    }

    function renderView() {
      const all = getAllCourses();
      const route=typeof location!=='undefined'?location.hash.split('/'):[];
      if(route[2]&&all.some(c=>c.id===decodeURIComponent(route[2]))){activeCourseId=decodeURIComponent(route[2]);activeEpisodeId=decodeURIComponent(route[3]||'')||all.find(c=>c.id===activeCourseId).episodes[0]?.id;}
      let activeCourse = null;
      if (activeCourseId) {
        activeCourse = all.find(c => c.id === activeCourseId);
      }
      const restore=online()?'<p class="panel">课程与手动完成记录保存在当前账号。<button type="button" class="button button-small button-outline" data-import-local-courses>导入本账号的本机旧记录</button></p>':'';
      const privateControl=activeCourse&&!activeCourse.platform&&online()?`<button type="button" class="button button-small button-outline" data-delete-private-course="${escapeHTML(activeCourse.id)}">删除本人私人课程</button>`:'';
      const status=activeCourse?`<p class="panel">${activeCourse.platform?'平台课程':'本人私人课程'} · ${activeCourse.verification==='verified-metadata'?'原站元信息已核对；播放能力以播放器为准':'原站标题、作者和分集尚未核验'}。完成状态是手动确认，不表示掌握。官方嵌入播放器不提供本站可读的真实进度。</p>`:'';
      return restore+status+privateControl+(activeCourse ? renderPlayer(activeCourse) : renderCatalog()) + renderAddModal();
    }

    function mount() {
      const container = document.getElementById('spaceContent');
      if (!container) return;
      mountController?.abort();
      mountController = new AbortController();
      const listenerOptions = { signal: mountController.signal };
      const player=document.getElementById('csVideoPlayer');
      if(player&&online()&&serverCurrent()){
        const courseId=activeCourseId,episodeId=activeEpisodeId,owner=getAccountId();let savingPosition=false,lastPosition=Date.now();
        player.addEventListener('loadedmetadata',()=>{const prior=getProgress()[courseId]?.episodes?.[episodeId];if(prior?.seconds&&Number.isFinite(player.duration))player.currentTime=Math.min(prior.seconds,Math.max(0,player.duration-1));},{once:true,signal:mountController.signal});
        const savePosition=async()=>{
          if(savingPosition||owner!==getAccountId()||!Number.isFinite(player.currentTime))return;savingPosition=true;
          try{const prior=getProgress()[courseId]?.episodes?.[episodeId];const value=await api('/progress',{courseId,episodeId,seconds:Math.round(player.currentTime),positionSource:'html5-observed',expectedRevision:prior?.revision||0,operationId:operation()});
            if(owner!==getAccountId()||!serverCurrent())return;const c=serverData.progress[courseId]||={episodes:{}};c.episodes[episodeId]=value.progress;c.lastEpisodeId=episodeId;
          }catch(error){toast?.('续播位置未保存：'+error.message);}finally{savingPosition=false;lastPosition=Date.now();}
        };
        player.addEventListener('pause',savePosition,listenerOptions);player.addEventListener('ended',savePosition,listenerOptions);
        player.addEventListener('timeupdate',()=>{if(Date.now()-lastPosition>15000)savePosition();},listenerOptions);
      }
      container.addEventListener('click',async event=>{
        const importButton=event.target.closest('[data-import-local-courses]');
        const deleteButton=event.target.closest('[data-delete-private-course]');
        if(!importButton&&!deleteButton)return;
        const owner=getAccountId();
        try{
          if(deleteButton){
            const course=getAllCourses().find(c=>c.id===deleteButton.dataset.deletePrivateCourse);
            if(!confirm('删除本人私人课程？历史完成事件与备份继续保留。'))return;
            await api('/delete',{courseId:course.id,expectedRevision:course.revision,operationId:operation()});
            activeCourseId=null;activeEpisodeId=null;if(typeof location!=='undefined')location.hash='#space/courses';
          }else{
            if(owner==='local'){toast?.('匿名旧记录保持在本机；请先登录并确认数据归属后导入。');return;}
            if(!confirm('仅导入当前账号键下的本机课程与进度，不包含匿名缓存；服务器已有记录优先。'))return;
            importButton.disabled=true;
            const localCourses=JSON.parse(localStorage.getItem(getCustomStorageKey())||'[]');
            const localProgress=JSON.parse(localStorage.getItem(getProgressStorageKey())||'{}');
            for(const course of localCourses){if(!getAllCourses().some(c=>c.id===course.id))await api('/save',{course,expectedRevision:0,operationId:'import-'+owner+'-'+course.id});}
            const fresh=await api('');
            for(const [courseId,record] of Object.entries(localProgress))for(const [episodeId,ep] of Object.entries(record.episodes||{})){
              if(fresh.progress[courseId]?.episodes?.[episodeId]||!fresh.courses.some(c=>c.id===courseId&&c.episodes.some(e=>e.id===episodeId)))continue;
              await api('/progress',{courseId,episodeId,completed:!!ep.completed,seconds:Math.max(0,Number(ep.seconds)||0),positionSource:'user-position',expectedRevision:0,operationId:'import-'+owner+'-'+courseId+'-'+episodeId});
            }
          }
          const data=await api('');if(owner!==getAccountId())return;serverData=data;serverOwner=owner;toast?.('已保存，旧本机缓存继续保留');render?.();
        }catch(error){toast?.('操作未完成：'+error.message);if(importButton)importButton.disabled=false;}
      },listenerOptions);
      if(online()&&!serverLoading&&!serverCurrent()){
        serverLoading=true;const owner=getAccountId();
        api('').then(data=>{if(owner!==getAccountId())return;serverData=data;serverOwner=owner;if(render)render();})
          .catch(error=>toast?.('服务端课程未读取：'+error.message)).finally(()=>{serverLoading=false;});
      }
      if(typeof window!=='undefined'&&!mount._routeListener){
        mount._routeListener=true;window.addEventListener('hashchange',()=>{
          if(!location.hash.startsWith('#space/courses'))serverData=null;
        });
      }
      const route=typeof location!=='undefined'?location.hash.split('/'):[];
      if(route[2]&&getAllCourses().some(c=>c.id===decodeURIComponent(route[2]))){
        activeCourseId=decodeURIComponent(route[2]);activeEpisodeId=decodeURIComponent(route[3]||'')||getAllCourses().find(c=>c.id===activeCourseId).episodes[0]?.id;
      }

      // Draw canvas if in algo-demo mode
      if (activeSource === 'algo-demo') {
        setTimeout(drawAlgoDemoCanvas, 50);
      }

      // Handle local file selection
      const handleFileSelect = e => {
        const file = e.target.files?.[0];
        if (file && activeCourseId) {
          const course = getAllCourses().find(c => c.id === activeCourseId);
          const currentEp = course?.episodes?.find(ep => ep.id === activeEpisodeId) || course?.episodes?.[0];
          const url = URL.createObjectURL(file);
          const localKey = activeCourseId + ':' + currentEp?.id;
          if (localVideosMap[localKey]) URL.revokeObjectURL(localVideosMap[localKey].url);
          localVideosMap[localKey] = { url, name: file.name };
          activeSource = 'html5';
          if (toast) toast('已载入本地视频文件：' + file.name + '，立即为您播放！');
          if (render) render();
        }
      };

      const fileInp1 = document.getElementById('localVideoFileInput');
      if (fileInp1) fileInp1.onchange = handleFileSelect;

      const fileInp2 = document.getElementById('localVideoFileInputInner');
      if (fileInp2) fileInp2.onchange = handleFileSelect;

      // Click delegations
      container.addEventListener('click', e => {
        // Switch source
        const srcBtn = e.target.closest('[data-switch-source]');
        if (srcBtn) {
          activeSource = srcBtn.dataset.switchSource;
          if (render) render();
          return;
        }

        // Run algo demo
        const runDemoBtn = e.target.closest('[data-run-algo-demo]');
        if (runDemoBtn) {
          drawAlgoDemoCanvas();
          return;
        }

        // Category click
        const catBtn = e.target.closest('[data-course-category]');
        if (catBtn) {
          categoryFilter = catBtn.dataset.courseCategory;
          if (render) render();
          return;
        }

        // Enter course
        const enterBtn = e.target.closest('[data-enter-course], [data-course-card-id]');
        if (enterBtn && !e.target.closest('button:not([data-enter-course])')) {
          const cid = enterBtn.dataset.enterCourse || enterBtn.dataset.courseCardId;
          if (cid) {
            activeCourseId = cid;
            const c = getAllCourses().find(item => item.id === cid);
            const prog = getProgress()[cid];
            activeEpisodeId = prog?.lastEpisodeId || c?.episodes[0]?.id;
            activeSource = 'bilibili';
            if (render) render();
            return;
          }
        }

        // Back to catalog
        const backBtn = e.target.closest('[data-back-to-catalog]');
        if (backBtn) {
          activeCourseId = null;
          if (render) render();
          return;
        }

        // Switch episode
        const epBtn = e.target.closest('[data-switch-episode]');
        if (epBtn) {
          activeEpisodeId = epBtn.dataset.switchEpisode;
          if (render) render();
          return;
        }

        // Toggle episode complete
        const toggleBtn = e.target.closest('[data-toggle-ep-complete]');
        if (toggleBtn) {
          const epId = toggleBtn.dataset.toggleEpComplete;
          if (activeCourseId && epId) {
            const currentProg = getProgress()[activeCourseId]?.episodes?.[epId]?.completed;
            if(online()){
              toggleBtn.disabled=true;
              const courseId=activeCourseId,owner=getAccountId(),prior=getProgress()[courseId]?.episodes?.[epId];
              api('/progress',{courseId,episodeId:epId,completed:!currentProg,expectedRevision:prior?.revision||0,operationId:operation()})
                .then(value=>{if(owner!==getAccountId())return;const c=serverData.progress[courseId]||={episodes:{}};c.episodes[epId]=value.progress;c.lastEpisodeId=epId;toast?.('完成状态与计划已保存');if(render)render();})
                .catch(error=>{toast?.('未保存：'+error.message);serverData=null;if(render)render();});
            }else{
              saveProgress(activeCourseId, epId, 0, !currentProg);
              if (toast) toast(!currentProg ? '已标记为学完！' : '已重置学习状态');
              if (render) render();
            }
          }
          return;
        }

        // Open add modal
        const addBtn = e.target.closest('[data-open-add-course]');
        if (addBtn) {
          isAddModalOpen = true;
          if (render) render();
          return;
        }

        // Close add modal
        const closeBtn = e.target.closest('[data-close-add-course]');
        if (closeBtn) {
          isAddModalOpen = false;
          if (render) render();
          return;
        }

        // In-class prompt click -> transfer to Ask Copilot
        const inClassPrompt = e.target.closest('[data-ask-in-class]');
        if (inClassPrompt) {
          const prompt = decodeURIComponent(inClassPrompt.dataset.askInClass);
          location.hash = 'space/ask';
          setTimeout(() => {
            if (window.XueyaAsk) window.XueyaAsk(prompt);
          }, 60);
          return;
        }

        // Send in-class custom ask
        const sendInClass = e.target.closest('[data-send-in-class]');
        if (sendInClass) {
          const inp = document.getElementById('inClassCustomInput');
          const val = inp?.value?.trim();
          if (val) {
            const course = getAllCourses().find(c => c.id === activeCourseId);
            const currentEp = course?.episodes?.find(ep => ep.id === activeEpisodeId);
            const prompt = `关于《${course?.title || '计算机课程'}》${currentEp?.title ? '「' + currentEp.title + '」' : ''}：${val}`;
            location.hash = 'space/ask';
            setTimeout(() => {
              if (window.XueyaAsk) window.XueyaAsk(prompt);
            }, 60);
          }
          return;
        }
      }, listenerOptions);

      // Search input
      container.addEventListener('input', e => {
        if (e.target.id === 'courseSearchInput') {
          searchQuery = e.target.value;
          const grid = container.querySelector('.courses-grid');
          if (grid) {
            const template = document.createElement('template');
            template.innerHTML = renderCatalog();
            const nextGrid = template.content.querySelector('.courses-grid');
            if (nextGrid) grid.replaceWith(nextGrid);
          }
        }
      }, listenerOptions);

      // Submit add course form
      container.addEventListener('submit', async e => {
        if (e.target.id === 'addCourseForm') {
          e.preventDefault();
          const name = document.getElementById('addCourseName')?.value?.trim();
          const category = document.getElementById('addCourseCategory')?.value || 'programming';
          const level = document.getElementById('addCourseLevel')?.value || '进阶深化';
          const instructor = document.getElementById('addCourseInstructor')?.value?.trim() || '自主学习';
          const tags = (document.getElementById('addCourseTags')?.value || '').split(/\s+/).filter(Boolean);
          const rawUrl = document.getElementById('addCourseVideoUrl')?.value?.trim() || 'BV1b7411N798';
          const desc = document.getElementById('addCourseDesc')?.value?.trim() || '';

          if (!name) return;

          // Parse BV id if user pasted a bilibili URL or BV id
          let bvid = '';
          const bvMatch = rawUrl.match(/(BV[a-zA-Z0-9]+)/i);
          if (bvMatch) {
            bvid = bvMatch[1];
          }

          const catNameMap = {
            theory: '核心理论 / 408',
            programming: '编程语言与全栈',
            architecture: '系统架构与数据库',
            'ai-agent': 'AI 与智能体前沿'
          };

          const newCourse = {
            id: 'custom-' + Date.now(),
            title: name,
            category,
            categoryName: catNameMap[category] || '计算机精品课',
            level,
            badge: '用户自建',
            instructor,
            duration: '1 课时',
            bvid,
            coverGradient: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
            coverIcon: 'spark',
            description: desc || '用户添加的计算机视频课程。',
            tags: tags.length ? tags : ['计算机视频', '自主探究'],
            episodes: [
              {
                id: 'ep-1',
                title: '第 01 讲：' + name,
                duration: '自定',
                bvid,
                bpage: 1,
                videoUrl: rawUrl.startsWith('http') && !rawUrl.includes('bilibili') ? rawUrl : '',
                summary: desc || name,
                keyPoints: tags,
                copilotPrompts: [
                  `请为我通俗解析《${name}》的核心技术概念。`,
                  `学习《${name}》时有哪些最佳学习路线和建议？`
                ]
              }
            ]
          };

          if(online()){
            const owner=getAccountId();
            try{const saved=await api('/save',{course:newCourse,expectedRevision:0,operationId:operation()});
              if(owner!==getAccountId())return;serverData.courses.push(saved.course);
            }catch(error){toast?.('课程未保存：'+error.message);return;}
          }else{
            const customList = getCustomCourses();customList.unshift(newCourse);saveCustomCourses(customList);
          }
          isAddModalOpen = false;
          activeCourseId = newCourse.id;
          activeEpisodeId = newCourse.episodes[0].id;
          activeSource = bvMatch ? 'bilibili' : (rawUrl.startsWith('http') ? 'html5' : 'bilibili');
          if (toast) toast('课程添加成功，已为您开启视频播放！');
          if (render) render();
        }
      }, listenerOptions);
    }

    return {
      render: renderView,
      mount,
      getAllCourses
    };
  }

  return { create: createCoursesWorkspace };
});
