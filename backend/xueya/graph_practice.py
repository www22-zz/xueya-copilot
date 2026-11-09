"""Read-only links to the same account-visible fixed practice catalog."""
from urllib.parse import quote
from .common import digest


def attach_practice(documents, concepts, edges, questions):
    fixed = [q for q in questions if q.get('bankSource') == 'legacy'
             and '数据结构' in q.get('subject', '')]
    # The chapter outline comes from installed course exercises, not AI artifacts.
    for doc in documents:
        if not doc['ready'] or not any(s in doc['name'] for s in ('栈和队列', '栈与队列')):
            continue
        labels = {
            '栈排列': '出栈序列与合法性',
            '后进先出': '栈的基本概念与顺序栈', '栈顶约定': '栈的基本概念与顺序栈', '栈边界': '栈的基本概念与顺序栈',
            '循环队列容量': '循环队列的判空、判满与长度', '循环队列长度': '循环队列的判空、判满与长度',
            '循环队列判空': '循环队列的判空、判满与长度', '循环队列判满': '循环队列的判空、判满与长度',
            '先进先出': '队列的基本操作与链队列', '队列操作': '队列的基本操作与链队列', '链队列边界': '队列的基本操作与链队列',
            '表达式求值': '表达式求值', '栈应用': '栈的应用与递归', '递归调用栈': '栈的应用与递归',
            '两栈队列': '两栈实现队列', '括号匹配': '括号匹配', '括号平衡': '括号匹配', '栈': '栈的设计与应用',
        }
        groups = {}
        for q in fixed:
            if q.get('topic') == '栈与队列':
                label = labels.get(q.get('subtopic'), q.get('subtopic') or q['title'])
                groups.setdefault(label, []).append(q)
        for label, rows in groups.items():
            key = 'fixed-concept-' + digest([doc['id'], label])[:24]
            concepts[key] = {'id': key, 'label': label, 'kind': 'concept',
                             'references': [{'documentId': doc['id'], 'page': None}],
                             'questionIds': [], 'descriptions': ['课程固定练习知识点：' + label],
                             'sourceType': 'fixed-practice', 'fixedQuestions': [link(q) for q in rows]}
            edges.append({'source': doc['id'], 'target': key, 'relation': 'contains'})
    aliases = (('时间复杂度', '复杂度'), ('随机存取', '随机访问'),
               ('行优先', '行主序'), ('列优先', '列主序'), ('压缩存储', '压缩'),
               ('链式存储', '链式'), ('顺序存储', '顺序'), ('头插法', '头插'), ('尾插法', '尾插'))
    def normalize(text):
        for a, b in aliases:
            text = text.replace(a, b)
        return text
    for node in concepts.values():
        if 'fixedQuestions' in node:
            continue
        label = normalize(node['label'])
        rows = [q for q in fixed if any(len(term) >= 2 and normalize(term) in label
                for term in [q.get('subtopic', ''), *q.get('tags', [])]
                if term not in ('数据结构', '数据结构与算法', q.get('topic')))]
        node['fixedQuestions'] = [link(q) for q in rows]


def link(q):
    return {'id': q['id'], 'title': q['title'],
            'url': '#space/practice/legacy/' + quote(q['id'], safe='')}
