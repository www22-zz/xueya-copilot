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
      "id": "cs-ds-algo",
      "title": "清华大学邓俊辉《数据结构与算法》（公开课）",
      "category": "theory",
      "categoryName": "核心理论 / 408",
      "level": "进阶必修",
      "badge": "408 核心 · 清华名课",
      "instructor": "清华大学 · 邓俊辉",
      "duration": "4 讲精选 · 约 34.5 小时",
      "bvid": "BV1jt4y117KR",
      "totalPages": 474,
      "cover": "https://i0.hdslb.com/bfs/archive/29062bbdff63049cbe3e8c2f1b8c3e1d0391692e.png",
      "coverGradient": "linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%)",
      "coverIcon": "tree",
      "description": "清华大学邓俊辉《数据结构与算法》公开课精讲：渐进复杂度、二叉树、图的广度优先搜索、平衡搜索树与红黑树。站内通过 B 站官方嵌入播放器在线播放。",
      "tags": [
        "复杂度分析",
        "二叉树",
        "图算法",
        "AVL",
        "红黑树"
      ],
      "platform": true,
      "sourceType": "platform",
      "verification": "verified-playback",
      "episodes": [
        {
          "id": "ds-ep-1",
          "title": "第 01 讲：渐进复杂度与大 O 记号",
          "duration": "10:07",
          "bvid": "BV1jt4y117KR",
          "bpage": 8,
          "videoUrl": "",
          "summary": "渐进分析的基本记号：大 O、大 Ω、大 Θ 与常见复杂度量级。",
          "keyPoints": [
            "大 O 表示法",
            "上界/下界/确界",
            "常见复杂度量级"
          ],
          "copilotPrompts": [
            "大 O 记号为什么只看增长趋势、忽略常数和低阶项？",
            "大 Ω 和大 Θ 与 O 记号的区别是什么？",
            "如何比较 n log n 与 n² 两种算法的复杂度？"
          ]
        },
        {
          "id": "ds-ep-2",
          "title": "第 02 讲：树与二叉树概述",
          "duration": "05:12",
          "bvid": "BV1jt4y117KR",
          "bpage": 152,
          "videoUrl": "",
          "summary": "二叉树的定义、性质与基本术语，为后续遍历与平衡搜索树打基础。",
          "keyPoints": [
            "二叉树定义",
            "真二叉树与满二叉树",
            "节点度数与高度关系"
          ],
          "copilotPrompts": [
            "二叉树和一般树的区别是什么？",
            "满二叉树和完全二叉树的区别？",
            "含 n 个节点的二叉树最小高度是多少？"
          ]
        },
        {
          "id": "ds-ep-3",
          "title": "第 03 讲：图的广度优先搜索（BFS）",
          "duration": "03:00",
          "bvid": "BV1jt4y117KR",
          "bpage": 194,
          "videoUrl": "",
          "summary": "图的广度优先搜索：化繁为简的遍历策略、队列实现与最短路径应用。",
          "keyPoints": [
            "BFS 遍历策略",
            "队列实现与访问标记",
            "无权图最短路径"
          ],
          "copilotPrompts": [
            "BFS 为什么能求出无权图的最短路径？",
            "BFS 和 DFS 分别适合什么场景？",
            "如何用 BFS 求连通分量的个数？"
          ]
        },
        {
          "id": "ds-ep-4",
          "title": "第 04 讲：红黑树的结构与规则",
          "duration": "03:48",
          "bvid": "BV1jt4y117KR",
          "bpage": 300,
          "videoUrl": "",
          "summary": "红黑树的定义与规则：为何放弃绝对平衡，用四条规则保证对数高度。",
          "keyPoints": [
            "红黑树规则",
            "与 4 阶 B 树的对应",
            "对数高度保证"
          ],
          "copilotPrompts": [
            "红黑树为什么允许最长路径是较短路径的两倍？",
            "红黑树的规则如何对应 4 阶 B 树？",
            "与 AVL 树相比，红黑树在插入删除场景的取舍是什么？"
          ]
        }
      ]
    },
    {
      "id": "cs-arch-sys",
      "title": "王道计算机考研 计算机组成原理（408 核心精讲）",
      "category": "theory",
      "categoryName": "核心理论 / 408",
      "level": "进阶必修",
      "badge": "408 核心 · 王道精讲",
      "instructor": "王道计算机教育",
      "duration": "6 讲精选 · 约 34.1 小时",
      "bvid": "BV1ps4y1d73V",
      "totalPages": 92,
      "cover": "https://i0.hdslb.com/bfs/archive/6c8b11c80e44f2880356d9137f84c844bbbbe323.jpg",
      "coverGradient": "linear-gradient(135deg, #1e293b 0%, #475569 100%)",
      "coverIcon": "cpu",
      "description": "王道 408 计算机组成原理：系统概述与性能指标、数据表示、存储与 Cache、指令系统、CPU 流水线与中断 I/O。站内通过 B 站官方嵌入播放器在线播放。",
      "tags": [
        "冯诺依曼",
        "补码与浮点",
        "Cache映射",
        "指令系统",
        "流水线"
      ],
      "platform": true,
      "sourceType": "platform",
      "verification": "verified-playback",
      "episodes": [
        {
          "id": "arch-ep-1",
          "title": "第 01 讲：计算机系统概述与性能指标",
          "duration": "23:17",
          "bvid": "BV1ps4y1d73V",
          "bpage": 9,
          "videoUrl": "",
          "summary": "计算机系统层次结构、冯·诺依曼组成与主频、CPI、MIPS 等性能指标的计算。",
          "keyPoints": [
            "冯·诺依曼结构",
            "存储程序思想",
            "CPI 与 MIPS"
          ],
          "copilotPrompts": [
            "冯·诺依曼体系结构的核心特点是什么，指令与数据在存储器中如何区分？",
            "CPI 和 MIPS 指标在评估 CPU 性能时有哪些局限？",
            "字长如何影响寻址范围和计算精度？"
          ]
        },
        {
          "id": "arch-ep-2",
          "title": "第 02 讲：数据表示与定点数编码",
          "duration": "32:31",
          "bvid": "BV1ps4y1d73V",
          "bpage": 11,
          "videoUrl": "",
          "summary": "原码、反码、补码与移码，定点数的编码与基本运算基础。",
          "keyPoints": [
            "原码/反码/补码",
            "补码加减运算",
            "溢出判断"
          ],
          "copilotPrompts": [
            "为什么计算机底层定点整数普遍采用补码而不是原码？",
            "补码加减运算中如何判断结果是否溢出？",
            "移码和补码之间有什么关系？"
          ]
        },
        {
          "id": "arch-ep-3",
          "title": "第 03 讲：Cache 与主存的映射方式",
          "duration": "21:58",
          "bvid": "BV1ps4y1d73V",
          "bpage": 47,
          "videoUrl": "",
          "summary": "Cache 的基本原理及其与主存的三种映射：直接映射、全相联与组相联。",
          "keyPoints": [
            "Cache 命中与缺失",
            "直接/全相联/组相联",
            "地址划分与替换"
          ],
          "copilotPrompts": [
            "组相联映射相比全相联和直接映射，如何平衡冲突与开销？",
            "已知主存与 Cache 容量，如何计算主存地址的 Tag、Index、Offset 位数？",
            "Cache 的写直达与写回策略各有什么优缺点？"
          ]
        },
        {
          "id": "arch-ep-4",
          "title": "第 04 讲：指令格式与寻址方式",
          "duration": "23:07",
          "bvid": "BV1ps4y1d73V",
          "bpage": 50,
          "videoUrl": "",
          "summary": "指令的基本格式、扩展操作码设计，以及数据寻址与指令寻址。",
          "keyPoints": [
            "指令字格式",
            "扩展操作码",
            "寻址方式分类"
          ],
          "copilotPrompts": [
            "采用扩展操作码时，如何设计短指令与长指令共存的前缀编码？",
            "基址寻址与变址寻址在硬件实现和编程场景上有何区别？",
            "为什么现代 CISC CPU 内部会把复杂指令译码为微操作执行？"
          ]
        },
        {
          "id": "arch-ep-5",
          "title": "第 05 讲：CPU 与指令流水线",
          "duration": "18:51",
          "bvid": "BV1ps4y1d73V",
          "bpage": 75,
          "videoUrl": "",
          "summary": "指令流水线的基本概念、性能指标与五段式流水线的组织方式。",
          "keyPoints": [
            "流水线性能指标",
            "五段式流水线",
            "流水线冲突"
          ],
          "copilotPrompts": [
            "流水线中的结构冒险、数据冒险和控制冒险分别是如何产生的？",
            "数据旁路转发（Forwarding）如何在不暂停流水线的情况下解决 RAW 冒险？",
            "分支预测失败为什么会造成明显的性能损失？"
          ]
        },
        {
          "id": "arch-ep-6",
          "title": "第 06 讲：中断系统与 I/O 控制方式",
          "duration": "43:43",
          "bvid": "BV1ps4y1d73V",
          "bpage": 89,
          "videoUrl": "",
          "summary": "中断的作用与响应过程、多重中断与中断屏蔽，以及程序中断与 DMA 控制方式。",
          "keyPoints": [
            "中断响应与隐指令",
            "多重中断与屏蔽字",
            "程序中断与 DMA"
          ],
          "copilotPrompts": [
            "CPU 响应外部中断需要满足哪些先决条件，中断服务程序入口地址如何获取？",
            "多重中断系统中，中断优先级如何通过硬件屏蔽字动态调整？",
            "DMA 方式与中断方式在数据传输开销上有何本质不同？"
          ]
        }
      ]
    },
    {
      "id": "cs-os-kernel",
      "title": "操作系统（哈尔滨工业大学 · 李治军公开课）",
      "category": "theory",
      "categoryName": "核心理论 / 408",
      "level": "进阶必修",
      "badge": "计算机底座 · 哈工大名课",
      "instructor": "哈尔滨工业大学 · 李治军",
      "duration": "3 讲精选 · 约 22.2 小时",
      "bvid": "BV1P44y1Z7Nw",
      "totalPages": 32,
      "cover": "https://i1.hdslb.com/bfs/archive/86985706b425f151ae17ec9f8ddc8934310af005.png",
      "coverGradient": "linear-gradient(135deg, #0f172a 0%, #334155 100%)",
      "coverIcon": "layers",
      "description": "哈工大李治军操作系统公开课：多进程图像与线程、虚拟内存与多级页表、信号量同步与临界区保护。站内通过 B 站官方嵌入播放器在线播放。",
      "tags": [
        "进程线程",
        "虚拟内存",
        "多级页表",
        "信号量",
        "死锁"
      ],
      "platform": true,
      "sourceType": "platform",
      "verification": "verified-playback",
      "episodes": [
        {
          "id": "os-ep-1",
          "title": "第 01 讲：多进程图像与线程模型",
          "duration": "53:23",
          "bvid": "BV1P44y1Z7Nw",
          "bpage": 9,
          "videoUrl": "",
          "summary": "操作系统如何组织多进程图像：进程控制块、用户级与内核级线程、CPU 调度与进程切换。",
          "keyPoints": [
            "PCB 与进程状态",
            "用户级/内核级线程",
            "CPU 调度与切换"
          ],
          "copilotPrompts": [
            "为什么线程上下文切换的开销通常小于进程上下文切换？",
            "用户级线程和内核级线程各有什么优缺点？",
            "系统调用发生时，CPU 寄存器和堆栈是如何保存与恢复的？"
          ]
        },
        {
          "id": "os-ep-2",
          "title": "第 02 讲：虚拟内存、多级页表与快表",
          "duration": "52:09",
          "bvid": "BV1P44y1Z7Nw",
          "bpage": 22,
          "videoUrl": "",
          "summary": "内存分区、分页与多级页表，快表（TLB）加速地址翻译以及缺页处理。",
          "keyPoints": [
            "分页与地址翻译",
            "多级页表",
            "TLB 快表"
          ],
          "copilotPrompts": [
            "64 位系统为什么普遍采用多级页表而不是单级大页表？",
            "TLB 未命中时硬件和内核分别做了什么？",
            "写时复制（COW）是如何借助页表权限实现的？"
          ]
        },
        {
          "id": "os-ep-3",
          "title": "第 03 讲：进程同步与临界区保护",
          "duration": "52:56",
          "bvid": "BV1P44y1Z7Nw",
          "bpage": 17,
          "videoUrl": "",
          "summary": "进程同步与信号量机制，临界区的进入与退出保护，以及死锁问题的处理。",
          "keyPoints": [
            "信号量与 P/V 操作",
            "临界区保护",
            "死锁与处理"
          ],
          "copilotPrompts": [
            "什么场景下应该使用自旋锁而不是互斥锁？",
            "信号量如何保证临界区的互斥访问？",
            "死锁产生的四个必要条件是什么？如何通过锁排序规避？"
          ]
        }
      ]
    },
    {
      "id": "cs-network-http",
      "title": "计算机网络原理：TCP/IP 协议栈（王道 408 精讲）",
      "category": "theory",
      "categoryName": "核心理论 / 408",
      "level": "体系精讲",
      "badge": "通信基石 · 王道精讲",
      "instructor": "王道计算机教育",
      "duration": "3 讲精选 · 约 35.1 小时",
      "bvid": "BV19E411D78Q",
      "totalPages": 94,
      "cover": "https://i2.hdslb.com/bfs/archive/fb3d3f987949aecc3a77a991f55ac3fa49a17e26.jpg",
      "coverGradient": "linear-gradient(135deg, #047857 0%, #10b981 100%)",
      "coverIcon": "link",
      "description": "王道 408 计算机网络：TCP 连接管理（三次握手）、拥塞控制与 HTTP 协议。站内通过 B 站官方嵌入播放器在线播放。",
      "tags": [
        "TCP/IP",
        "三次握手",
        "拥塞控制",
        "HTTP"
      ],
      "platform": true,
      "sourceType": "platform",
      "verification": "verified-playback",
      "episodes": [
        {
          "id": "net-ep-1",
          "title": "第 01 讲：TCP 连接管理与三次握手",
          "duration": "22:20",
          "bvid": "BV19E411D78Q",
          "bpage": 79,
          "videoUrl": "",
          "summary": "TCP 连接管理：三次握手的报文交互、状态变迁与 TIME_WAIT 等待策略。",
          "keyPoints": [
            "SYN/ACK 与序号",
            "三次握手过程",
            "TIME_WAIT 状态"
          ],
          "copilotPrompts": [
            "为什么 TCP 建立连接需要三次握手，而关闭连接需要四次挥手？",
            "TIME_WAIT 状态为什么要等待 2MSL 才彻底释放？",
            "大量 CLOSE_WAIT 连接通常意味着什么？"
          ]
        },
        {
          "id": "net-ep-2",
          "title": "第 02 讲：TCP 拥塞控制",
          "duration": "41:10",
          "bvid": "BV19E411D78Q",
          "bpage": 85,
          "videoUrl": "",
          "summary": "TCP 拥塞控制：慢开始、拥塞避免、快重传与快恢复的完整流程。",
          "keyPoints": [
            "拥塞窗口",
            "慢开始与拥塞避免",
            "快重传与快恢复"
          ],
          "copilotPrompts": [
            "TCP 流量控制和拥塞控制有什么根本区别？",
            "为什么收到 3 个重复 ACK 就触发快重传？",
            "慢开始门限 ssthresh 是如何调整的？"
          ]
        },
        {
          "id": "net-ep-3",
          "title": "第 03 讲：HTTP 协议",
          "duration": "22:04",
          "bvid": "BV19E411D78Q",
          "bpage": 94,
          "videoUrl": "",
          "summary": "超文本传输协议 HTTP 的报文格式、连接类型与无状态特性。",
          "keyPoints": [
            "HTTP 请求/响应报文",
            "持久连接与非持久连接",
            "Cookie 与无状态"
          ],
          "copilotPrompts": [
            "HTTP/1.1 的持久连接解决了什么问题？",
            "Cookie 是如何弥补 HTTP 无状态缺陷的？",
            "HTTP 常见状态码 1xx/2xx/3xx/4xx/5xx 分别代表什么？"
          ]
        }
      ]
    },
    {
      "id": "cs-prog-fullstack",
      "title": "尚硅谷 TypeScript 入门与实战教程",
      "category": "programming",
      "categoryName": "编程语言与全栈",
      "level": "实战进阶",
      "badge": "前端工程 · TS 入门到实战",
      "instructor": "尚硅谷 · TypeScript 教研组",
      "duration": "2 讲精选 · 约 10.4 小时",
      "bvid": "BV1Xy4y1v7S2",
      "totalPages": 30,
      "cover": "https://i1.hdslb.com/bfs/archive/a2df7e38355ae4fe9fab1d314b2105e554e3c18f.jpg",
      "coverGradient": "linear-gradient(135deg, #4338ca 0%, #6366f1 100%)",
      "coverIcon": "spark",
      "description": "尚硅谷 TypeScript 教程：类型声明与常用类型、编译配置与 webpack 打包、类与接口、泛型与面向对象实战。站内通过 B 站官方嵌入播放器在线播放。",
      "tags": [
        "TypeScript",
        "类型系统",
        "泛型",
        "类与接口",
        "webpack"
      ],
      "platform": true,
      "sourceType": "platform",
      "verification": "verified-playback",
      "episodes": [
        {
          "id": "ts-ep-1",
          "title": "第 01 讲：TypeScript 类型系统",
          "duration": "34:36",
          "bvid": "BV1Xy4y1v7S2",
          "bpage": 5,
          "videoUrl": "",
          "summary": "TypeScript 常用类型、类型声明与编译选项，用静态类型约束接口数据。",
          "keyPoints": [
            "基础类型与联合类型",
            "类型声明与编译",
            "静态类型检查"
          ],
          "copilotPrompts": [
            "TypeScript 相比 JavaScript 在工程维护上的核心优势是什么？",
            "联合类型和类型别名适合解决什么问题？",
            "tsconfig 中 strict 相关选项分别控制什么？"
          ]
        },
        {
          "id": "ts-ep-2",
          "title": "第 02 讲：泛型与面向对象",
          "duration": "15:07",
          "bvid": "BV1Xy4y1v7S2",
          "bpage": 21,
          "videoUrl": "",
          "summary": "泛型与面向对象：类、接口和泛型约束，构建可复用的类型安全组件。",
          "keyPoints": [
            "泛型函数与泛型类",
            "接口与类实现",
            "泛型约束"
          ],
          "copilotPrompts": [
            "泛型在函数和类中分别如何声明与使用？",
            "接口与抽象类在 TypeScript 中该如何选择？",
            "如何用泛型约束限制类型参数必须具备某些属性？"
          ]
        }
      ]
    },
    {
      "id": "cs-sys-database",
      "title": "尚硅谷 MySQL 数据库：索引与事务精讲",
      "category": "architecture",
      "categoryName": "系统架构与数据库",
      "level": "核心架构",
      "badge": "数据库调优 · 索引与事务",
      "instructor": "尚硅谷 · MySQL 教研组",
      "duration": "2 讲精选 · 约 68.9 小时",
      "bvid": "BV12b411K7Zu",
      "totalPages": 350,
      "cover": "https://i1.hdslb.com/bfs/archive/06bd78636fc24b4d8e68519b7979e5e1c94f6b12.jpg",
      "coverGradient": "linear-gradient(135deg, #c2410c 0%, #ea580c 100%)",
      "coverIcon": "target",
      "description": "尚硅谷 MySQL 教程高级篇精选：索引结构与检索原理、事务并发问题与隔离级别。站内通过 B 站官方嵌入播放器在线播放。",
      "tags": [
        "MySQL",
        "B+树",
        "索引",
        "事务",
        "隔离级别"
      ],
      "platform": true,
      "sourceType": "platform",
      "verification": "verified-playback",
      "episodes": [
        {
          "id": "db-ep-1",
          "title": "第 01 讲：MySQL 索引结构与检索原理",
          "duration": "09:09",
          "bvid": "BV12b411K7Zu",
          "bpage": 195,
          "videoUrl": "",
          "summary": "MySQL 索引结构与检索原理：B+ 树索引如何加速查询、以及回表的代价。",
          "keyPoints": [
            "B+ 树索引",
            "聚簇索引与二级索引",
            "索引检索过程"
          ],
          "copilotPrompts": [
            "为什么 MySQL 的索引底层选择 B+ 树而不是红黑树或哈希表？",
            "什么是覆盖索引，它如何避免回表？",
            "联合索引的最左前缀匹配原则在底层如何生效？"
          ]
        },
        {
          "id": "db-ep-2",
          "title": "第 02 讲：事务隔离级别与并发问题",
          "duration": "24:45",
          "bvid": "BV12b411K7Zu",
          "bpage": 137,
          "videoUrl": "",
          "summary": "事务与隔离级别演示：并发读写问题以及四种隔离级别的表现。",
          "keyPoints": [
            "事务 ACID",
            "脏读/不可重复读/幻读",
            "四种隔离级别"
          ],
          "copilotPrompts": [
            "脏读、不可重复读和幻读分别由什么并发操作引起？",
            "MySQL 默认可重复读隔离级别下如何避免不可重复读？",
            "串行化隔离级别为什么性能最差？"
          ]
        }
      ]
    },
    {
      "id": "cs-ai-agent",
      "title": "黑马程序员：大模型 RAG 与 Agent 智能体实战",
      "category": "ai-agent",
      "categoryName": "AI 与智能体前沿",
      "level": "前沿实战",
      "badge": "大模型 · RAG 与 Agent 实战",
      "instructor": "黑马程序员 · AI 大模型教研组",
      "duration": "2 讲精选 · 约 15.5 小时",
      "bvid": "BV1yjz5BLEoY",
      "totalPages": 67,
      "cover": "https://i0.hdslb.com/bfs/archive/ec034de58ed78ca875c6561c7b2a93c212ffbf8a.jpg",
      "coverGradient": "linear-gradient(135deg, #701a75 0%, #a21caf 100%)",
      "coverIcon": "spark",
      "description": "黑马程序员大模型实战：Prompt 工程、LangChain 与 RAG 检索增强、Agent 智能体与 ReAct 工具调用。站内通过 B 站官方嵌入播放器在线播放。",
      "tags": [
        "LLM",
        "RAG",
        "Agent",
        "LangChain",
        "ReAct"
      ],
      "platform": true,
      "sourceType": "platform",
      "verification": "verified-playback",
      "episodes": [
        {
          "id": "ai-ep-1",
          "title": "第 01 讲：RAG 检索增强生成",
          "duration": "13:44",
          "bvid": "BV1yjz5BLEoY",
          "bpage": 19,
          "videoUrl": "",
          "summary": "RAG 检索增强生成：为什么需要外部知识、离线建库与在线检索增强流程。",
          "keyPoints": [
            "RAG 流程",
            "检索与上下文增强",
            "缓解模型幻觉"
          ],
          "copilotPrompts": [
            "RAG 的离线建库和在线检索分别包含哪些步骤？",
            "文档切分（Chunking）的大小和重叠如何选择？",
            "RAG 能缓解大模型幻觉，但它自身还有哪些失败模式？"
          ]
        },
        {
          "id": "ai-ep-2",
          "title": "第 02 讲：Agent 智能体与工具调用",
          "duration": "06:28",
          "bvid": "BV1yjz5BLEoY",
          "bpage": 55,
          "videoUrl": "",
          "summary": "Agent 智能体的基本概念、运行流程与工具调用方式，为 ReAct 与项目实战打基础。",
          "keyPoints": [
            "Agent 定义与组成",
            "工具调用",
            "ReAct 行动框架"
          ],
          "copilotPrompts": [
            "一个 LLM Agent 通常由哪些组件构成？",
            "ReAct 循环中 Thought、Action、Observation 如何交替推进任务？",
            "工具调用失败时，Agent 应如何设计重试与纠错？"
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

  function createCoursesWorkspace({ state, store, toast, ask, render, navigate, host=null, subjects=null, embedded=false }) {
    let activeCourseId = null;
    let activeEpisodeId = null;
    let categoryFilter = 'all';
    let searchQuery = '';
    let isAddModalOpen = false;
    let activeSource = 'bilibili'; // 'bilibili' | 'html5'
    let mountController;
    const localVideosMap = {}; // key: "courseId:epId" -> { url, name }
    /* Per-lecture in-class Q&A. Answers render inside the course page instead of
       navigating to the global AI assistant, so video playback is never lost. */
    const inClassThreads = new Map(); // key: "courseId:episodeId" -> { messages, pending, controller }
    let inClassPaintFrame = null;
    let inClassStreaming = null;

    function inClassKey(courseId, episodeId) {
      return String(courseId || '') + ':' + String(episodeId || '');
    }

    function getInClassThread(courseId, episodeId) {
      const key = inClassKey(courseId, episodeId);
      let thread = inClassThreads.get(key);
      if (!thread) {
        thread = { messages: [], pending: false, controller: null };
        inClassThreads.set(key, thread);
      }
      return thread;
    }

    function inClassContext(course, episode) {
      return `关于《${course?.title || '计算机课程'}》${episode?.title ? '「' + episode.title + '」' : ''}：`;
    }

    function inClassActive() {
      const course = getAllCourses().find(c => c.id === activeCourseId);
      const episode = course?.episodes?.find(e => e.id === activeEpisodeId) || course?.episodes?.[0];
      return { course, episode, thread: course && episode ? getInClassThread(course.id, episode.id) : null };
    }

    function renderInClassMessages(thread) {
      if (!thread?.messages?.length) return '';
      return thread.messages.map((message, index) => {
        if (message.role === 'user') {
          return `<div class="cs-inclass-msg is-user"><div class="cs-inclass-user-bubble">${escapeHTML(message.text)}</div></div>`;
        }
        const answer = message.text
          ? (window.XueyaRich?.render ? window.XueyaRich.render(message.text) : `<p>${escapeHTML(message.text)}</p>`)
          : '';
        const pending = message.pending
          ? `<div class="cs-inclass-pending" role="status"><span class="cs-inclass-typing" aria-hidden="true"><i></i><i></i><i></i></span><span>${escapeHTML(message.progress || '正在回答…')}</span></div>`
          : '';
        const actions = message.pending
          ? '<button type="button" class="cs-inclass-action" data-inclass-stop>停止生成</button>'
          : `${message.failed ? `<button type="button" class="cs-inclass-action" data-inclass-retry="${index}">重新回答</button>` : ''}${message.sources?.length ? `<span class="cs-inclass-sources">已参考 ${message.sources.length} 条资料</span>` : ''}`;
        const cursor = message.pending && message.text ? '<span class="stream-cursor" aria-hidden="true"></span>' : '';
        return `<div class="cs-inclass-msg is-ai">
          <div class="cs-inclass-avatar" aria-hidden="true"><span class="material-symbols-outlined">smart_toy</span></div>
          <div class="cs-inclass-bubble">
            <div class="cs-inclass-meta"><strong>学涯 Copilot</strong><span>${escapeHTML(message.engine || '随堂伴学')}</span></div>
            ${pending}
            <div class="cs-inclass-answer">${answer}${cursor}</div>
            ${actions ? `<div class="cs-inclass-actions">${actions}</div>` : ''}
          </div>
        </div>`;
      }).join('');
    }

    function paintInClassThread() {
      const container = document.getElementById('csInClassThread');
      if (!container) return;
      const { course, episode, thread } = inClassActive();
      const key = inClassKey(course?.id, episode?.id);
      const active = Boolean(thread && (thread.messages.length || thread.pending));
      container.hidden = !active;
      if (!active) {
        container.innerHTML = '';
        container.dataset.threadKey = '';
        return;
      }
      container.dataset.threadKey = key;
      container.innerHTML = `<div class="cs-inclass-head">
          <span class="material-symbols-outlined" aria-hidden="true">forum</span>
          <span>本节随堂问答</span>
          <button type="button" class="cs-inclass-clear" data-inclass-clear>清空</button>
        </div>
        <div class="cs-inclass-list">${renderInClassMessages(thread)}</div>`;
      const list = container.querySelector('.cs-inclass-list');
      if (list) list.scrollTop = list.scrollHeight;
    }

    function scheduleInClassPaint() {
      if (inClassPaintFrame) return;
      inClassPaintFrame = requestAnimationFrame(() => {
        inClassPaintFrame = null;
        paintInClassThread();
      });
    }

    function cancelInClassAnswer(showNotice = true, targetThread = null) {
      const thread = targetThread || inClassActive().thread;
      if (!thread || !thread.pending) return;
      const controller = thread.controller;
      thread.pending = false;
      thread.controller = null;
      if (inClassStreaming?.thread === thread) inClassStreaming = null;
      if (controller) controller.abort();
      const message = [...thread.messages].reverse().find(item => item.role === 'ai' && item.pending);
      if (message) {
        message.pending = false;
        message.draft = false;
        message.progress = '';
        message.text = showNotice ? '已停止生成。' : message.text;
        message.cancelled = true;
      }
      paintInClassThread();
    }

    async function askInClass(question, prompt) {
      const course = getAllCourses().find(c => c.id === activeCourseId);
      const episode = course?.episodes?.find(e => e.id === activeEpisodeId) || course?.episodes?.[0];
      const clean = String(question || '').trim();
      if (!course || !episode || !clean) return;
      const thread = getInClassThread(course.id, episode.id);
      if (thread.pending) { toast?.('正在回答中，请稍候'); return; }
      const inlineAsk = window.XueyaAskInline;
      const history = thread.messages
        .filter(message => !message.pending && message.text)
        .slice(-8)
        .map(message => ({ role: message.role === 'user' ? 'user' : 'assistant', content: message.text }));
      const previousSources = [...thread.messages].reverse().find(message => message.role === 'ai' && message.sources?.length)?.sources || [];
      const userMessage = { id: 'q-' + Date.now(), role: 'user', text: clean };
      const answerMessage = { id: 'a-' + Date.now(), role: 'ai', text: '', pending: true, progress: '', draft: false, engine: '', sources: [] };
      thread.messages.push(userMessage, answerMessage);
      thread.pending = true;
      const controller = new AbortController();
      thread.controller = controller;
      inClassStreaming = { thread, message: answerMessage, controller };
      paintInClassThread();
      try {
        document.getElementById('csInClassThread')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      } catch {}
      const input = document.getElementById('inClassCustomInput');
      if (input) input.value = '';
      if (typeof inlineAsk !== 'function') {
        answerMessage.pending = false;
        answerMessage.failed = true;
        answerMessage.text = '当前页面无法直接生成回答，请点击下方「打开完整对话台」继续提问。';
        thread.pending = false;
        thread.controller = null;
        inClassStreaming = null;
        paintInClassThread();
        return;
      }
      const sendPrompt = prompt || (inClassContext(course, episode) + clean);
      try {
        const result = await inlineAsk(sendPrompt, {
          courseId: state?.courseId,
          history,
          previousSources,
          signal: controller.signal,
          onUpdate(update) {
            if (!update || typeof update !== 'object') return;
            if (typeof update.draft === 'boolean') answerMessage.draft = update.draft;
            if (typeof update.reasoning === 'string' && update.reasoning) answerMessage.reasoning = update.reasoning;
            if (typeof update.progress === 'string' && update.progress) answerMessage.progress = update.progress;
            if (update.draft !== true && typeof update.answer === 'string') answerMessage.text = update.answer;
            scheduleInClassPaint();
          },
        });
        if (controller.signal.aborted) throw new DOMException('已停止生成', 'AbortError');
        answerMessage.text = typeof result?.answer === 'string' ? result.answer : '';
        answerMessage.engine = result?.engine || '随堂伴学';
        answerMessage.sources = Array.isArray(result?.sources) ? result.sources : [];
        answerMessage.failed = Boolean(result?.failed) || result?.answerStatus === 'unavailable';
        answerMessage.pending = false;
        answerMessage.draft = false;
        answerMessage.progress = '';
      } catch (error) {
        const aborted = controller.signal.aborted || error?.name === 'AbortError';
        answerMessage.pending = false;
        answerMessage.draft = false;
        answerMessage.progress = '';
        if (aborted) {
          answerMessage.text = answerMessage.text || '已停止生成。';
          answerMessage.cancelled = true;
        } else {
          answerMessage.failed = true;
          answerMessage.text = answerMessage.text || '这次回答未能完成，请稍后重试。';
        }
      } finally {
        if (thread.controller === controller) {
          thread.pending = false;
          thread.controller = null;
        }
        if (inClassStreaming?.controller === controller) inClassStreaming = null;
        paintInClassThread();
      }
    }

    function retryInClass(index) {
      const { thread } = inClassActive();
      if (!thread || thread.pending) return;
      const message = thread.messages[index];
      if (!message || message.role !== 'ai') return;
      let userIndex = index - 1;
      while (userIndex >= 0 && thread.messages[userIndex].role !== 'user') userIndex -= 1;
      if (userIndex < 0) return;
      const question = thread.messages[userIndex].text;
      thread.messages.splice(userIndex, index - userIndex + 1);
      paintInClassThread();
      askInClass(question).catch(() => {});
    }

    function getAllCourses() {
      if(serverCurrent())return serverData.courses.filter(c=>!subjects||(c.verification==='verified-metadata'&&subjects.includes(c.subject)));
      if(embedded)return [];
      const custom = getCustomCourses();
      return [...BUILTIN_COURSES.map(c=>({...c,platform:true})), ...custom];
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
                    课程视频目录
                  </span>
                  <span class="inline-flex items-center gap-1.5 text-on-surface-variant font-code-sm text-xs">
                    <span class="w-2 h-2 rounded-full bg-secondary"></span>
                    全部课程均可站内播放
                  </span>
                </div>
                <div class="flex flex-col gap-1">
                  <h1 class="font-display-lg text-2xl lg:text-3xl text-on-surface tracking-tight font-bold">配套视频课程</h1>
                  <p class="font-body-md text-sm text-on-surface-variant">按课程和主题查找视频；全部课程通过 B 站官方嵌入播放器在线播放，不下载视频到本地。</p>
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
                      <span class="text-xs text-outline">手动标记完成</span>
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
                    <span>课程手动完成记录</span>
                    <span class="font-code-sm text-outline font-medium">按自己的学习计划安排</span>
                  </div>
                  <div class="w-full h-2 rounded-full bg-surface-container-highest overflow-hidden">
                    <div class="h-full bg-gradient-to-r from-primary to-secondary rounded-full transition-all duration-700" style="width: ${stats.percentage}%;"></div>
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
                      ${c.cover ? `<img src="${escapeHTML(c.cover)}" alt="" class="absolute inset-0 w-full h-full object-cover" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ''}
                      <div class="absolute inset-0 bg-gradient-to-t from-black/75 via-black/25 to-black/10 pointer-events-none"></div>
                      <div class="flex items-center justify-between relative z-10">
                        <span class="px-2.5 py-0.5 rounded-full bg-surface-container-lowest/85 backdrop-blur-md text-primary font-bold text-[11px]">${escapeHTML(c.badge || c.categoryName)}</span>
                        <span class="px-2.5 py-0.5 rounded-full bg-black/40 backdrop-blur-md text-white text-[11px]">${escapeHTML(c.level || '精选')}</span>
                      </div>
                      <div class="flex items-center justify-center relative z-10">
                        <div class="w-12 h-12 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center text-white shadow-lg group-hover:scale-110 transition-transform">
                          <span class="material-symbols-outlined text-[28px]">play_arrow</span>
                        </div>
                      </div>
                      <div class="flex items-center justify-between gap-3 text-white/90 text-xs relative z-10">
                        <span class="flex items-center gap-1 min-w-0"><span class="material-symbols-outlined text-[14px]">timer</span><span class="truncate">${escapeHTML(c.duration || (c.episodes.length + ' 讲精选'))}</span></span>
                        <span class="font-code-sm text-[11px] flex-shrink-0">${escapeHTML(c.sourceUrl ? '原站课程 · 站内可播' : 'B 站官方嵌入 · 站内可播')}</span>
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
                        <span class="truncate max-w-[120px]">${escapeHTML(c.instructor || '讲师信息未提供')}</span>
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
                    ${escapeHTML(course.instructor || '讲师信息未提供')} · ${escapeHTML(course.title)}
                  </span>
                </div>
                <div class="flex items-center gap-3 text-on-surface-variant font-body-sm text-body-sm mt-1">
                  <span class="flex items-center gap-1 font-code-sm text-code-sm text-primary font-semibold">
                    <span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
                    ${escapeHTML(currentEp?.duration || '时长未提供')}
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

              ${course.sourceUrl ? `<a href="${escapeHTML(course.sourceUrl)}" target="_blank" rel="noopener noreferrer" class="h-9 px-3 rounded-lg bg-surface-container-low hover:bg-surface-container text-on-surface-variant hover:text-on-surface font-label-md text-label-md flex items-center gap-1.5 transition-all shadow-sm">
                <span class="material-symbols-outlined text-[18px]">open_in_new</span>
                <span>原站课程页</span>
              </a>` : ''}

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
                  ` : course.sourceUrl ? `
                    <div class="w-full h-full bg-slate-950 flex flex-col items-center justify-center gap-3 p-6 text-center">
                      <span class="material-symbols-outlined text-4xl text-slate-400">live_tv</span>
                      <p class="text-sm text-slate-300">当前浏览器未能加载站内嵌入播放器，可前往官方原站观看。</p>
                      <a class="button button-blue" href="${escapeHTML(course.sourceUrl)}" target="_blank" rel="noopener noreferrer">前往原站课程</a>
                    </div>
                  ` : videoSrc ? `
                    <video id="csVideoPlayer" class="w-full h-full object-contain" controls preload="metadata" src="${escapeHTML(videoSrc)}">
                      <p>您的浏览器不支持 HTML5 视频播放。</p>
                    </video>
                  ` : `
                    <div class="w-full h-full bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 flex flex-col items-center justify-center p-6 text-center text-white">
                      <div class="w-16 h-16 rounded-2xl bg-white/10 flex items-center justify-center text-3xl mb-3 shadow-inner">🎬</div>
                      <h3 class="text-lg font-bold">${activeSource === 'html5' ? '选取电脑上的视频文件即可立即播放' : '当前课程暂未提供站内播放源'}</h3>
                      <p class="text-sm text-slate-400 mt-1 mb-4 max-w-md">支持电脑中的 MP4、WebM、MKV 视频文件，零网络延迟，超清流畅播放！</p>
                      <label class="px-4 py-2 rounded-xl bg-primary text-white font-semibold cursor-pointer hover:bg-primary-container transition shadow flex items-center gap-2">
                        <span class="material-symbols-outlined text-[18px]">upload_file</span>
                        <span>选取电脑上的视频文件</span>
                        <input type="file" id="localVideoFileInputInner" accept="video/*" hidden>
                      </label>
                    </div>
                  `}

                  <!-- Floating Live Indicator Overlay -->
                  <div class="absolute top-3 left-3 right-3 flex items-center justify-between pointer-events-none">
                    <div class="flex items-center gap-2 pointer-events-auto">
                      <span class="px-2.5 py-1 rounded-md bg-inverse-surface/85 backdrop-blur-md text-inverse-on-surface font-label-sm text-label-sm flex items-center gap-1.5 shadow-sm text-white">
                        <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
                        ${activeSource==='html5'?'HTML5 本机播放':'B 站官方嵌入 · 已核验可播'}
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
                  <span class="font-label-md text-label-md text-on-surface-variant font-medium">精选 ${course.episodes.length} 讲 · 原视频共 ${course.totalPages || course.episodes.length} 讲</span>
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
                            <span class="text-xs text-on-surface-variant">${escapeHTML(ep.duration || '时长未提供')}</span>
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
                    <span>针对本节快速提问（点击即答）：</span>
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

                <!-- In-class answers stay on this page so the video never stops -->
                <div id="csInClassThread" class="cs-inclass" role="log" aria-live="polite" aria-label="本节随堂问答" hidden></div>

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
                    <span>回答显示在本页 · 支持 LaTeX</span>
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


    function renderView() {
      const all = getAllCourses();
      const route=typeof location!=='undefined'?location.hash.split('/'):[];
      if(!embedded&&route[2]&&all.some(c=>c.id===decodeURIComponent(route[2]))){activeCourseId=decodeURIComponent(route[2]);activeEpisodeId=decodeURIComponent(route[3]||'')||all.find(c=>c.id===activeCourseId).episodes[0]?.id;}
      let activeCourse = null;
      if (activeCourseId) {
        activeCourse = all.find(c => c.id === activeCourseId);
      }
      const privateControl=activeCourse&&!activeCourse.platform&&online()?`<button type="button" class="button button-small button-outline" data-delete-private-course="${escapeHTML(activeCourse.id)}">删除本人私人课程</button>`:'';
      let contextBanner='';try{const ctx=JSON.parse(sessionStorage.getItem((window.XueyaDataKey||((k)=>k))('xueya-video-context'))||'null');if(ctx&&activeCourse?.id===ctx.courseId&&ctx.returnHash?.startsWith('#space/'))contextBanner=`<p class="panel">关联学习位置：${escapeHTML(ctx.label)} · 已核验课程入口，尚未定位到该学习位置的具体分集。<a href="${escapeHTML(ctx.returnHash)}" data-video-learning-return>返回原学习位置</a></p>`;}catch{}
      return contextBanner+privateControl+(activeCourse ? renderPlayer(activeCourse) : renderCatalog()) + renderAddModal();
    }

    function mount() {
      const container = host || document.getElementById('spaceContent');
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
        if(!embedded&&typeof location!=='undefined'&&!location.hash.startsWith('#space/courses'))return;
        if(event.target.closest('[data-video-learning-return]')){try{const ctx=JSON.parse(sessionStorage.getItem((window.XueyaDataKey||((k)=>k))('xueya-video-context')));sessionStorage.setItem((window.XueyaDataKey||((k)=>k))('xueya-material-return-tab'),ctx.returnTab||'corpus');}catch{}return;}
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
          if(!location.hash.startsWith('#space/courses')){serverData=null;if(!embedded)mountController?.abort();}
        });
      }

      const route=typeof location!=='undefined'?location.hash.split('/'):[];
      if(!embedded&&route[2]&&getAllCourses().some(c=>c.id===decodeURIComponent(route[2]))){
        activeCourseId=decodeURIComponent(route[2]);activeEpisodeId=decodeURIComponent(route[3]||'')||getAllCourses().find(c=>c.id===activeCourseId).episodes[0]?.id;
      }

      // Restore the in-class answer thread after every re-render.
      paintInClassThread();

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
        if(!embedded&&typeof location!=='undefined'&&!location.hash.startsWith('#space/courses'))return;
        // Switch source
        const srcBtn = e.target.closest('[data-switch-source]');
        if (srcBtn) {
          activeSource = srcBtn.dataset.switchSource;
          if (render) render();
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
            if(typeof scrollTo==='function')scrollTo({top:0,behavior:'instant'});
            return;
          }
        }

        // Back to catalog
        const backBtn = e.target.closest('[data-back-to-catalog]');
        if (backBtn) {
          activeCourseId = null;
          if (render) render();
          if(typeof scrollTo==='function')scrollTo({top:0,behavior:'instant'});
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

        // In-class quick prompt -> answer inline on the current page
        const inClassPrompt = e.target.closest('[data-ask-in-class]');
        if (inClassPrompt) {
          const question = decodeURIComponent(inClassPrompt.dataset.askInClass || '');
          if (question) askInClass(question).catch(() => {});
          return;
        }

        // In-class custom question -> answer inline on the current page
        const sendInClass = e.target.closest('[data-send-in-class]');
        if (sendInClass) {
          const inp = document.getElementById('inClassCustomInput');
          const val = inp?.value?.trim();
          if (val) {
            const { course, episode } = inClassActive();
            askInClass(val, inClassContext(course, episode) + val).catch(() => {});
          }
          return;
        }

        // Stop / retry / clear the in-class answer thread
        if (e.target.closest('[data-inclass-stop]')) {
          cancelInClassAnswer();
          return;
        }
        const retryBtn = e.target.closest('[data-inclass-retry]');
        if (retryBtn) {
          retryInClass(Number(retryBtn.dataset.inclassRetry));
          return;
        }
        const clearBtn = e.target.closest('[data-inclass-clear]');
        if (clearBtn) {
          const { thread } = inClassActive();
          if (thread) {
            if (thread.pending) cancelInClassAnswer(false, thread);
            thread.messages.length = 0;
            paintInClassThread();
          }
          return;
        }
      }, listenerOptions);

      // Enter sends the in-class question without leaving the video page.
      container.addEventListener('keydown', e => {
        if (e.target.id !== 'inClassCustomInput' || e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
        e.preventDefault();
        container.querySelector('[data-send-in-class]')?.click();
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
      getAllCourses,
      unmount(){mountController?.abort();}
    };
  }

  return { create: createCoursesWorkspace };
});
