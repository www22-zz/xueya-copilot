"""Local task briefs and stable references to the existing objective banks."""
import copy
import re
from .common import digest, require, utc_now
from .practice_bank import bank
from .practice_catalog import exam_bank

# Small curriculum labels, not a second learning or scheduling algorithm.
PROFILES = (
    (r'矩阵|三角|压缩存储', ('矩阵', '对称', '三角', '压缩', '三元组', '数组寻址'),
     '理解特殊矩阵怎样压缩存储，再用练习核对下标与存储位置的对应关系。',
     ['对称矩阵与三角矩阵', '压缩存储的下标映射', '稀疏矩阵与三元组']),
    (r'数组|索引', ('数组', '寻址', '随机访问', '索引', '行优先', '列优先'),
     '先理清数组的维度、下标范围和存储顺序，再练习元素个数与地址计算。',
     ['维度与下标范围', '行优先与列优先存储', '元素地址与偏移量']),
    (r'栈|队列|中缀|后缀', ('栈', '队列', '中缀', '后缀'),
     '通过视频梳理栈和队列的操作顺序，再用题目练习出入顺序与表达式处理。',
     ['栈的后进先出', '队列的先进先出', '中缀转后缀与表达式求值']),
    (r'B树|查找|排序', ('查找', '二分', '排序', 'B树', '散列'),
     '区分查找与排序方法的适用条件，再比较它们的执行过程和效率。',
     ['查找的前提条件', '排序过程与稳定性', '时间复杂度比较']),
    (r'复杂度|频度|渐进|算法第?01', ('复杂度', '频度', '增长', '工作量', '常数', '递归', '二分'),
     '从基本操作的执行次数入手分析增长趋势，再用循环和递归题检查复杂度判断。',
     ['基本操作与频度', '渐进增长阶', '循环、递归与空间开销']),
    (r'二叉树|哈夫曼|树的', ('二叉树', '完全二叉树', '树', '哈夫曼'),
     '理解二叉树的结构与常用性质，重点练习完全二叉树的结点关系和计数。',
     ['二叉树的结点与层次', '完全二叉树的编号关系', '遍历与结构性质']),
    (r'图的|图论|MOOC第03|第03讲', ('图', '邻接', '遍历', '连通', '拓扑', '生成树', '最短路径'),
     '先认识图的基本术语和表示方式，再通过题目辨别遍历、连通性与路径问题。',
     ['顶点、边与度', '邻接表示和图遍历', '连通、路径与生成树']),
    (r'线性表|顺序表|链表', ('顺序表', '链表', '随机访问', '随机存取', '头结点', '链接字段'),
     '比较顺序表与链表的存储和操作方式，再判断不同操作的代价。',
     ['顺序存储与链式存储', '访问、插入与删除', '头结点和指针关系']),
    (r'数据结构|逻辑结构|存储结构', ('逻辑结构', '存储结构', '抽象数据类型', 'ADT', '链接字段', '随机访问', '链表'),
     '区分数据之间的逻辑关系和它们的存储方式，再通过代表题判断两者的联系与区别。',
     ['数据对象、关系与操作', '逻辑结构与存储结构', '顺序存储与链式存储']),
)


def task_brief(task):
    title = task.get('title', '')
    subject=task.get('subject','')
    for pattern, keywords, summary, points in PROFILES:
        if subject in ('','数据结构','数据结构与算法') and re.search(pattern, title, re.I):
            return {'taskSummary': summary, 'knowledgePoints': list(points), 'keywords': keywords}
    return {'taskSummary': '先观看相关视频梳理本次任务，再完成对应练习并核对解析。',
            'knowledgePoints': [], 'keywords': ()}


def fixed_candidates(task):
    keywords = task_brief(task)['keywords']
    subject = task.get('subject', '')
    if keywords:
        subject = '数据结构'
    found = []
    for source in (bank(), exam_bank()):
        for question in source['questions']:
            if question['type'] != 'single':
                continue
            qsubject = question.get('subject', '').replace('数据结构与算法', '数据结构')
            if subject and qsubject != subject:
                continue
            # Exclude the broad chapter tag: e.g. "串、数组与矩阵" should
            # not cause a KMP question to match an array-address task.
            tags = [tag for tag in question.get('tags', []) if tag != question.get('topic')]
            text = ' '.join([question.get('title', ''), question.get('subtopic', ''), question['prompt'], *tags])
            score = sum(len(word) for word in keywords if word.casefold() in text.casefold())
            if not keywords:
                score = max((len(tag) for tag in tags if len(tag) >= 2 and tag in task.get('title', '')), default=0)
            if score:
                found.append((score, question['id'], question, source['version']))
    unique=[];seen=set()
    for row in sorted(found,key=lambda row:(-row[0],row[1])):
        prompt=re.sub(r'\s+','',row[2]['prompt'])
        if prompt not in seen:unique.append(row);seen.add(prompt)
    return unique


def prepare(service, account, plan_id, node_ids):
    """Fill only empty groups; repeated calls never reshuffle saved exercises."""
    from .learning_route import nodes
    require(isinstance(node_ids, list) and 0 < len(node_ids) <= 20
            and all(isinstance(key, str) for key in node_ids), 'INVALID_PLAN_NODES')
    scope = service._scope(account)
    with service.platform.db.transaction():
        row = service.repo.read(scope, 'plan', plan_id)
        require(row is not None, 'PLAN_NOT_FOUND')
        plan = row['value']
        require(plan.get('status') in ('active', 'draft'), 'PLAN_NOT_ACTIVE')
        selected = [node for node in nodes(plan.get('learningRoute') or {'phases': []}) if node['id'] in node_ids]
        require({node['id'] for node in selected} == set(node_ids), 'PLAN_NODE_NOT_FOUND')
        tasks = {task['id']: task for day in plan['days'] for task in day.get('tasks', [])}
        changed = False
        for node in selected:
            if node.get('questions') or node.get('fixedPracticePrepared'):
                continue
            task = tasks.get(node['id'], {'title': node['title']})
            wanted = max(1, min(6, (node['minutes'] + 9) // 10))
            refs = []
            for _, original_id, question, version in fixed_candidates(task)[:wanted]:
                qid = 'plan-fixed-' + digest([original_id, version])[:32]
                saved = service.repo.read(scope, 'question', qid)
                if not saved:
                    value = {**copy.deepcopy(question), 'id': qid, 'sourceType': 'fixed',
                             'originalQuestionId': original_id, 'sourceRevision': version, 'createdAt': utc_now()}
                    saved = service.repo.put(scope, 'question', qid, value, 0)
                refs.append({'id': qid, 'revision': saved['version'], 'sourceRevision': version,
                             'sourceType': 'fixed-bank', 'originalQuestionId': original_id})
            node.update(questions=refs, fixedPracticePrepared=True, plannedQuestionCount=node.get('requiredCount'),
                        requiredCount=len(refs), missingCount=0 if refs else wanted,
                        readiness='ready' if refs else 'questions-needed')
            changed = True
        if changed:
            plan['revision'] = plan.get('revision', 1) + 1
            plan['updatedAt'] = utc_now()
            service.repo.put(scope, 'plan', plan_id, plan, row['version'])
        return service.plan_view(account, plan)
