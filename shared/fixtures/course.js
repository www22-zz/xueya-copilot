/* Portable module: browser script and CommonJS. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaCourse=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
  const documents=[
    {id:'doc-1',name:'数据结构讲义 · 第 3 章.pdf',meta:'树与二叉树 · 示例资料',status:'示例已索引'},
    {id:'doc-2',name:'期中复习题 2024.pdf',meta:'查找与排序 · 示例资料',status:'示例已索引'},
    {id:'doc-3',name:'实验指导书.pdf',meta:'二叉树遍历 · 示例资料',status:'示例已索引'}
  ];
  const sources=[
    {id:'source-1',documentId:'doc-1',title:'数据结构讲义 · 第 3 章',location:'树与二叉树 · p.42',quote:'二叉搜索树的左子树关键字小于根，右子树关键字大于根。查找从根节点开始，根据比较结果进入左子树或右子树，最多沿着一条根到叶的路径进行。因此查找的时间复杂度为 O(h)，h 为树的高度；平衡时为 O(log n)，退化成链时最坏为 O(n)。',keywords:['二叉搜索树','查找','复杂度','树','节点','高度','路径'],sample:true},
    {id:'source-2',documentId:'doc-2',title:'期中复习题 2024',location:'查找与排序 · p.8',quote:'平衡二叉搜索树的高度与节点数量呈对数关系，查找、插入和删除的时间复杂度为 O(log n)。AVL 树通过检查平衡因子并进行单旋或双旋保持左右子树高度差不超过 1。按顺序插入且不进行平衡调整，可能让普通二叉搜索树退化为链表。',keywords:['平衡','旋转','AVL','复杂度','查找','排序','高度差'],sample:true},
    {id:'source-3',documentId:'doc-3',title:'实验指导书',location:'二叉树遍历实验 · p.3',quote:'二叉树的中序遍历顺序是左子树、根节点、右子树。对关键字互不相同的二叉搜索树进行中序遍历，得到递增序列。遍历序列可作为验证二叉树结构和递归算法的实验输入。遍历每个节点一次，时间复杂度为 O(n)。',keywords:['遍历','中序','递归','实验','序列','二叉树'],sample:true}
  ];
  const questions=[
    {id:'q1',topic:'树的高度',prompt:'一棵有 15 个节点的满二叉树，查找节点最多需要比较多少次？',options:['3 次','4 次','7 次','15 次'],answer:1,explanation:'15 = 2⁴ − 1，满二叉树共有 4 层。从根到最深的叶节点最多比较 4 次。',sourceId:'source-1'},
    {id:'q2',topic:'二叉搜索树',prompt:'哪种插入方式最容易让未经平衡调整的二叉搜索树退化为链？',options:['按从小到大的顺序插入','每次插入后保持树高平衡','随机打乱节点再插入','让左右子树高度相近'],answer:0,explanation:'按顺序插入时，节点可能全部进入右子树，形成链状结构，最坏查找复杂度为 O(n)。',sourceId:'source-2'},
    {id:'q3',topic:'中序遍历',prompt:'对关键字互不相同的二叉搜索树进行中序遍历，会得到什么？',options:['层次序列','递减序列','递增序列','随机序列'],answer:2,explanation:'中序遍历按“左子树 → 根 → 右子树”访问，而二叉搜索树满足左小右大，所以结果递增。',sourceId:'source-3'},
    {id:'q4',topic:'平衡与旋转',prompt:'AVL 树任意节点的左右子树高度差应满足什么条件？',options:['始终等于 0','绝对值不超过 1','绝对值不超过 2','只要根节点满足即可'],answer:1,explanation:'AVL 树在每个节点保持左右子树高度差绝对值不超过 1，失衡时通过旋转恢复。',sourceId:'source-2'},
    {id:'q5',topic:'时间复杂度',prompt:'访问二叉树中每个节点一次的遍历，时间复杂度是多少？',options:['O(1)','O(log n)','O(n)','O(n²)'],answer:2,explanation:'每个节点访问一次，访问次数与节点数量 n 成正比，因此时间复杂度为 O(n)。',sourceId:'source-3'}
  ];

return {documents,sources,questions};
});
