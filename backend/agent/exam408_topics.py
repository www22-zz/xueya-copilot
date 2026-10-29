"""Stable chapter/subtopic classification for the four 408 subjects."""

CHAPTERS = {
 '数据结构': {
  '基础与复杂度': '几何级数求和 递归空间 增长阶 依赖建模 问题建模 逻辑结构 抽象数据类型 算法性质 基本操作',
  '线性表': '双指针去重 链表删除 头插法 顺序存储 单链表结点 头结点 顺序表删除 线性扫描 链表遍历 双指针逆置 双指针去重实现',
  '栈与队列': '入栈出栈序列 栈排列 循环队列容量 表达式求值 后进先出 先进先出 栈顶约定 循环队列判空 括号平衡 中缀转后缀',
  '串、数组与矩阵': '特殊矩阵 数组寻址 KMP 稀疏矩阵 串长 空串 数组维度 子串与子序列',
  '树与二叉树': '完全二叉树 森林的概念 哈夫曼树 树的概念 二叉树计数 遍历序列重建 哈夫曼WPL 二叉树定义 先序遍历 中序遍历 叶子结点 二叉树高度',
  '图': '图的概念 图的遍历 复杂度分析 Dijkstra BFS最短路 拓扑排序 邻接矩阵扫描 有向图遍历与拓扑序',
  '查找': 'B树 数组查找 线性探测 二分边界 开放定址删除 LRU缓存 二分边界维护 二叉排序树构建与删除',
  '排序': '排序算法 外部排序 堆调整 建堆复杂度 排序稳定性 快速排序退化 稳定归并 小根堆检验 插入排序实现 排序的阶段结果与稳定性 堆与插入排序的中间状态',
 },
 '计算机组成原理': {
  '计算机系统与性能': '计算机体系结构 指令执行指标 平均CPI CPU时间 CPI与性能',
  '数据表示与运算': 'IEEE浮点数表示 补码 组成原理 类型转换 数制转换 补码范围 符号扩展 溢出判断 算术右移 字节序 定点小数 IEEE754 浮点精度 汉明距离 奇偶校验 差错控制 补码与溢出 浮点表示',
  '存储系统': '主存容量的扩展 存储器概念 RAID cache概念 虚拟页式管理 平均访存时间 DRAM刷新 SRAM 程序局部性 Cache地址划分 组相联映射 写直达 写回标记 TLB 页内偏移 Cache映射 组相联与替换 写策略 地址转换 TLB、页表与有效访存时间',
  '指令系统与CPU': '寄存器类型 指令编码 指令寻址方式 流水线冒险 指令寄存器 程序计数器 RISC 理想流水线 数据相关 流水线 指令格式与数据通路 寄存器传送与控制信号',
  '总线、中断与I/O': '总线类型 总线概念 总线指标 异常和中断 IO接口 DMA 中断与异常 总线带宽 I/O编址 总线传输 DMA与CPU开销 磁盘寻址与DMA传输',
 },
 '操作系统': {
  '系统基础与运行机制': '用户态和内核态 操作系统概念 系统调用 系统引导流程 系统引导、文件系统与格式化',
  '进程、线程与调度': '进程状态 进程概念 进程 调度 处理机调度算法 CPU调度 时间片轮转 抢占式调度',
  '同步、互斥与死锁': '硬件互斥指令 死锁 PV操作 同步互斥 读者写者 银行家算法 信号量与有界缓冲 线程同步与任务先后约束',
  '内存管理': '内存管理方式 程序的链接 页表 访存过程 页面置换算法 动态分区分配 分页 虚拟内存 页面置换 分页地址转换 TLB与缺页',
  '文件系统': 'inode 目录 外存空间管理 文件物理结构 文件系统 文件索引 文件索引与路径解析',
  '设备与I/O管理': '设备分配和回收 磁盘概念 缓冲区 寄存器类型 中断IO 中断 I/O 磁盘调度',
 },
 '计算机网络': {
  '网络体系结构': 'OSI模型 TCP/IP模型 网络协议 软件定义网络',
  '物理层与传输': '奈奎斯特定理 物理层接口特性 香农定理 传输介质 调制方法',
  '数据链路与局域网': '介质访问控制 交换机 以太网 HDLC ARQ协议 存储转发 滑动窗口 序号空间 CRC CSMA/CD 局域网接入、DHCP与退避',
  '网络层与路由': '子网划分 ARP 网络号和主机号 路由协议 IP路由 IPv4子网 CIDR聚合 最长前缀匹配 IPv4转发与链路地址',
  '传输层': 'UDP TCP 四次挥手 拥塞控制 TCP序号 RTT估计',
  '应用层': 'HTTP 电子邮件 DNS 应用层时延',
 },
}


def classify(question):
    subtopic=question['topic']
    # The old public index classified this tree-counting concept as a stack item.
    if question['id']=='e408-2015-02':subtopic='二叉树计数'
    for chapter,topics in CHAPTERS[question['subject']].items():
        if subtopic in topics.split():
            question['subtopic']=subtopic
            question['topic']=chapter
            question['tags']=list(dict.fromkeys([chapter,subtopic]+question.get('tags',[])))
            return
    raise ValueError(f"Unclassified 408 subtopic: {question['id']} {subtopic}")


def order(question):
    subject=list(CHAPTERS).index(question['subject'])
    chapter=list(CHAPTERS[question['subject']]).index(question['topic'])
    return subject,chapter,question['type']=='short',question.get('year',9999),question['id']
