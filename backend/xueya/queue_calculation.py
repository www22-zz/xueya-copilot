"""Bounded course-rule calculations, only when scoped sources prove the convention.

No model, network, eval(), hidden textbook, or question/answer lookup table.
Unknown wording or missing/ambiguous rules returns None to the normal RAG path.
"""
import re


def compact(text):
    return re.sub(r'\s+', '', text).translate(str.maketrans('（）％＝', '()%='))


def answer(question, sources):
    if len(question) > 1000 or not sources:
        return None
    if re.search(r'代码|C\+\+|Python|Java|编写|实现|证明|推导|复杂度', question):
        return None
    rows = [(source, compact(source['quote'])) for source in sources]

    def find(pattern):
        return next((s for s, text in rows if re.search(pattern, text)), None)

    def result(text, refs, calculation):
        refs = list({s['id']: s for s in refs if s}.values())
        return {'answer': text+''.join(f' [{i}]' for i in range(1, len(refs)+1)),
                'sources': refs, 'calculation': calculation}

    # A precise pointer question has a source-code answer; don't substitute an
    # adjacent empty-check sentence for the requested pointer location.
    if ('链队列' in question and 'rear' in question
            and re.search(r'删|出队', question) and re.search(r'最后|唯一|只有一个|仅剩一个', question)
            and re.search(r'指向|哪里|一句话', question)
            and not re.search(r'为什么|为何|原因|解释', question)
            and not re.search(r'不带|无头|不是最后|非最后', question)):
        code = find(r'if\(p->next==nullptr\)rear=front;')
        head = find(r'队头指针指向链队列的头结点|队头指针和队尾指针均指向头结点')
        if code and head:
            return result('rear应重新指向头结点，即rear = front。', [code, head], {'kind': 'last-linked-node', 'rear': 'front/header'})

    if '循环队列' not in question or re.search(r'不保留|不浪费|无需保留|无须保留|计数器|标志位|另一种约定', question):
        return None
    full_rule = find(r'队满的条件是[:：]?\(rear\+1\)%QueueSize={1,2}front(?![A-Za-z0-9_])')
    if not full_rule or not any('浪费一个数组元素空间' in text for _, text in rows):
        return None

    n_match = re.search(r'(?:数组(?:的)?(?:长度|大小)|QueueSize)\s*(?:为|是|=|：|:)?\s*(\d+)', question, re.I)
    if not n_match:
        if re.search(r'最多|容量', question) and re.search(r'\bN\b|长度为N|长度为 N', question):
            return result('按所选资料保留一个空位的约定，长度为N的数组最多存N-1个元素，而不是N个。',
                          [full_rule], {'kind': 'symbolic-capacity', 'capacity': 'N-1'})
        return None
    size = int(n_match[1])
    if not 2 <= size <= 100000:
        return None
    joint = re.search(r'front\s*=\s*rear\s*=\s*(\d+)', question)
    fm, rm = re.search(r'front\s*=\s*(\d+)', question), re.search(r'rear\s*=\s*(\d+)', question)
    if joint:
        front = rear = int(joint[1])
    elif fm and rm:
        front, rear = int(fm[1]), int(rm[1])
    else:
        # A simple numeric capacity question needs no invented queue state.
        if not re.search(r'front|rear|入队|出队', question) and re.search(r'最多|容量', question):
            return result(f'按保留一个空位的约定，最多存{size-1}个元素（{size}-1）。',
                          [full_rule], {'kind': 'capacity', 'size': size, 'capacity': size-1})
        return None
    if not 0 <= front < size or not 0 <= rear < size:
        return None

    enq = find(r'rear=\(rear\+1\)%QueueSize')
    deq = find(r'front=\(front\+1\)%QueueSize')
    empty_rule = find(r'front={1,2}rear|rear==front')
    refs = [full_rule]
    data, steps = [], []
    if joint and '初始' in question:
        if re.search(r'初始.{0,12}(?:已满|非空|队满)', question):
            return None
        if not enq or not deq or not empty_rule:
            return None
        refs += [enq, deq, empty_rule]
        tail = question[joint.end():]
        operations = list(re.finditer(r'入队|出队', tail))
        if not operations or len(operations) > 30:
            return None
        for index, op in enumerate(operations):
            body = tail[op.end():operations[index+1].start() if index+1 < len(operations) else len(tail)].strip()
            if op[0] == '入队':
                match = re.match(r'([A-Za-z0-9]{1,20}(?:\s*[、,，]\s*[A-Za-z0-9]{1,20})*)', body)
                if not match:
                    return None
                items = re.split(r'\s*[、,，]\s*', match[1])
                if len(data)+len(items) > size-1 or len(items) > 50:
                    return None  # Don't silently simulate a different successful sequence.
                for item in items:
                    rear = (rear+1) % size;data.append(item)
                    steps.append({'operation': 'enqueue', 'item': item, 'front': front, 'rear': rear})
            else:
                match = re.match(r'(\d+|一|两|二|三|四|五|六|七|八|九|十)次', body)
                if not match:
                    return None
                value = match[1]
                count = int(value) if value.isdigit() else {'一':1, '两':2, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10}[value]
                if not 1 <= count <= len(data):
                    return None
                for _ in range(count):
                    item = data.pop(0);front = (front+1) % size
                    steps.append({'operation': 'dequeue', 'item': item, 'front': front, 'rear': rear})
            remainder = body[match.end():].strip('，,、。；;？? \t\n')
            if index+1 < len(operations):
                if remainder not in ('', '再', '然后', '接着', '之后'):
                    return None
            elif remainder and not re.match(r'给出|判断|请|最终|最后|结果|现在|此时|队列|队满|是否|还能|能否', remainder):
                return None
        count = len(data)
    else:
        # Don't confuse a multi-operation problem with a static state question.
        if len(re.findall(r'入队|出队', question)) > 1:
            return None
        if (re.search(r'(?:入队|出队)\s*[A-Za-z0-9]|(?:入队|出队).{0,8}(?:后|[一二两三四五六七八九十\d]+(?:次|个))', question)
                or re.search(r'清空|重置|重新初始化|(?:front|rear).{0,4}(?:加|减|\+\+|--|移动|改为)', question)):
            return None
        if re.search(r'内容|元素是什么|元素分别|元素的值|存放什么|哪个元素|哪些元素', question):
            return None
        if not re.search(r'队满|已满|是否满|能.*入队|多少|几个|数量|最多|容量|队空|为空|能.*出队', question):
            return None
        count = (rear-front+size) % size
        if re.search(r'多少|几个|数量|最多|容量', question):
            if not enq or not deq or not empty_rule:
                return None
            refs += [enq, deq, empty_rule]

    full = (rear+1) % size == front
    facts = [f'按所选教材的保留空位约定计算：front={front}，rear={rear}。']
    if steps:
        facts += [f'队列从队头到队尾为：{"、".join(data) if data else "空"}。', f'当前{count}个元素，最多存{size-1}个。']
    elif re.search(r'多少|几个|数量', question):
        facts += [f'当前元素数=({rear}-{front}+{size})%{size}={count}。']
    if re.search(r'最多|容量', question):
        facts += [f'最多存{size-1}个元素（数组长度减1）。']
    if re.search(r'队空|是否为空|能.*出队', question):
        if not empty_rule:
            return None
        refs += [empty_rule]
        facts += ['队列为空，不能出队。' if front == rear else '队列非空，可以出队。']
    facts += [f'({rear}+1)%{size}={(rear+1)%size}，'+('等于' if full else '不等于')+f'front={front}，因此'+('队满，不能继续入队。' if full else '队列未满。')]
    return result(''.join(facts), refs, {'kind': 'circular-queue', 'size': size, 'front': front, 'rear': rear,
                  'count': count, 'capacity': size-1, 'full': full, 'items': data if steps else None, 'steps': steps})
