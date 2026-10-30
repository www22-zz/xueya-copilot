import re
from ..core import today, valid_date, add_days, date_at, clone
from ..rag import catalog, retrieve


def conversation_reply(question, mode='ask'):
    if mode != 'ask':
        return None
    text = re.sub(r'[，,。.!！?？~～\s]+$', '', question.strip())
    if re.fullmatch(r'(你好|您好|你们好|嗨|哈喽|早上好|下午好|晚上好|hi|hello)(呀|啊|哇|哦)?', text, re.I):
        return '你好！我是学涯 Copilot。可以聊日常问题，也可以帮你理解知识、整理课程资料、生成练习和安排复习。你想聊什么？'
    return None


def route_task(question, mode='ask'):
    if mode in ('summarize', 'quiz'):
        return mode
    if conversation_reply(question, mode):
        return 'conversation'
    for pattern, intent in [(r'(复习|学习|备考).{0,10}(计划|安排)|(计划|安排).{0,10}(复习|学习|备考)', 'plan'),
                            (r'薄弱|弱项|掌握情况|错题分析|学习情况|学习进度|复习重点', 'review'),
                            (r'总结|归纳|整理.{0,6}(重点|知识)', 'summarize'), (r'(?:出(?!现|错)|生成).{0,4}(?:练习|题目|试题)|(?:出|生成)(?:[一二两三四五六七八九十几\d]+)?(?:道|套|个)?题|(?:出|生成)[一二两三四五六七八九十几\d]+(?:道|套|个)[^。！？?]{0,12}题|练习题|测验', 'quiz')]:
        if re.search(pattern, question):
            return intent
    return 'ask'


def requires_course_evidence(question, mode='ask'):
    return mode != 'ask' or bool(re.search(r'(根据|依据|按照|结合|参照).{0,16}(资料|文档|讲义|课件|原文|笔记|教材)|(资料|文档|讲义|课件|原文|笔记|教材).{0,12}(里|中|说|提到|记载)|第.{1,6}页', question))


def refers_to_previous(question):
    return bool(re.search(r'^那|它|这个|这些|这种|这样|那个|那些|上述|刚才|上面|前面|继续|进一步|再解释|再说|展开讲|换个说法|举个例|举一个例|^(为什么|为何|怎么理解)[呢吗？?。！!\s]*$', question))


def retrieval_query(request, library):
    question = request['question']
    if refers_to_previous(question) and not retrieve(question, library):
        anchor = next((m for m in reversed(request['history']) if m['role'] == 'user' and retrieve(m['content'], library)), None)
        if anchor:
            return (anchor['content'][:3000]+'\n追问：'+question)[:4000]
    return question


def normalize_context(value):
    value = value if isinstance(value, dict) else {}
    fixtures, library, ids = catalog(), [], set()
    for item in value.get('library', []):
        source = next((s for s in fixtures['sources'] if s['id'] == item), None) if isinstance(item, str) else item
        if not isinstance(source, dict) or not isinstance(source.get('id'), str) or not isinstance(source.get('quote'), str) or not source['quote'].strip():
            continue
        key = source['id'][:150]
        if not key or key in ids:
            continue
        ids.add(key)
        library.append({'id': key, 'title': str(source.get('title') or '课程资料')[:200], 'location': str(source.get('location') or '文本片段')[:150], 'quote': source['quote'][:1500], 'keywords': [k[:30] for k in source.get('keywords', []) if isinstance(k, str)][:12], 'sample': source.get('sample') is True})
        if len(library) == 48:
            break
    questions, known = [], set()
    for q in value.get('questions', fixtures['questions'])[:100]:
        if isinstance(q, dict) and isinstance(q.get('id'), str) and isinstance(q.get('topic'), str) and q['id'][:150] not in known:
            key = q['id'][:150]
            known.add(key)
            questions.append({'id': key, 'topic': q['topic'][:80], 'sourceId': str(q.get('sourceId') or '')[:150]})
    records = [{k: r[k] for k in ('questionId', 'correct', 'createdAt') if k in r} for r in value.get('records', [])[-120:] if isinstance(r, dict) and r.get('questionId') in known and type(r.get('correct')) is bool]
    base = today()
    try:
        minutes = max(15, min(120, round(float(value.get('minutes') or 30))))
    except (ValueError, TypeError, OverflowError):
        minutes = 30
    return {'library': library, 'questions': questions, 'records': records, 'baseDate': base, 'examDate': value['examDate'] if valid_date(value.get('examDate')) else add_days(base, 21), 'minutes': minutes,
            'previousSourceIds': list(dict.fromkeys(x for x in value.get('previousSourceIds', []) if isinstance(x, str) and x in ids))[:3]}


def local_answer(question, mode, hits):
    if not hits:
        return '当前资料中没有找到足够依据。请补充具体的课程关键词，或者上传相关 TXT / MD 资料后再试。'
    quotes = '\n\n'.join(f"[{i+1}] {s['quote']}" for i, s in enumerate(hits))
    if mode == 'quiz':
        return f'可以先用这个问题检验理解：\n{question}\n\n请结合下列原文，写出定义、适用条件和边界情况：\n{quotes}'
    if mode == 'summarize':
        return f'知识卡片：{question}\n\n{quotes}\n\n复习时，先遮住答案，用自己的话复述这些重点。'
    return f'根据当前资料，可以从以下原文理解这个问题：\n\n{quotes}\n\n以上是本地检索摘录。点击引用可核对原文。'


def answer_unavailable(reason, *, configured=True):
    if not configured:
        return '已找到相关资料，但尚未配置 AI 问答服务，暂时无法整理解释。你可以先查看下方参考资料。'
    if reason in ('CLAIMS_NEED_REVIEW', 'INVALID_CLAIM_EVIDENCE'):
        return '已找到相关资料，但这次解释未通过来源核对，暂未生成可用回答。你可以先查看下方参考资料。'
    if reason == 'AI_TIMEOUT':
        return '已找到相关资料，但 AI 服务响应超时，本次未生成回答。没有自动重试；你可以先查看下方参考资料，并在任务与用量中核对本次调用。'
    return '这次 AI 回答未能完成，未将检索原文作为答案返回。相关资料保留在下方，供你核对。'


def local_study(context, intent):
    records, questions = context['records'], context['questions']
    last = {r['questionId']: r for r in records}
    weak = list(dict.fromkeys(q['topic'] for q in questions if q['id'] in last and not last[q['id']]['correct']))
    memory = {}
    for r in sorted(records, key=lambda r: r.get('createdAt', '')):
        q = next(q for q in questions if q['id'] == r['questionId'])
        card = memory.setdefault(q['topic'], {'wrong': 0})
        card['wrong'] = 0 if r['correct'] else card['wrong']+1
        interval = 7 if not card['wrong'] else 3 if card['wrong'] == 1 else 2 if card['wrong'] == 2 else 1
        try:
            answered = date_at(r['createdAt'])
        except (KeyError, ValueError):
            answered = context['baseDate']
        card['due'] = add_days(answered, interval)
    progress = {'total': len(records), 'correct': sum(r['correct'] for r in records), 'weakTopics': weak, 'dueTopics': [topic for topic, c in memory.items() if c['due'] <= context['baseDate']]}
    plan = None
    if intent == 'plan':
        from ..core import days_until
        topics = list(dict.fromkeys([*weak, *(q['topic'] for q in questions)]))
        days, minutes = [], context['minutes']
        for offset in range(max(0, min(7, days_until(context['examDate'], context['baseDate'])+1)) if topics else 0):
            date, topic = add_days(context['baseDate'], offset), topics[offset % len(topics)]
            first = (minutes*6+9)//10
            days.append({'date': date, 'tasks': [{'id': f'{date}-{topic}-read', 'title': ('回顾薄弱点' if topic in weak else '理解')+'：'+topic, 'detail': '阅读课程原文，保存一张重点卡片', 'minutes': first}, {'id': f'{date}-{topic}-practice', 'title': '练习与复述：'+topic, 'detail': '完成练习，用自己的话解释答案', 'minutes': minutes-first}]})
        plan = {'examDate': context['examDate'], 'minutes': minutes, 'days': days}
    return {'progress': progress, 'plan': plan}


def study_text(intent, progress, plan, base):
    summary = f"最近 {progress['total']} 次作答中，答对 {progress['correct']} 次。\n当前待巩固：{'、'.join(progress['weakTopics']) or '暂无未解决的错题'}。\n今日到期复习：{'、'.join(progress['dueTopics']) or '暂无'}。" if progress['total'] else '目前还没有可分析的作答记录。先完成一组练习，就能根据结果识别薄弱点。'
    if intent != 'plan':
        return summary
    if plan['examDate'] < base:
        return summary+'\n\n考试日期已经过去，请先更新考试日期。当前计划未作修改。'
    if not plan['days']:
        return summary+'\n\n暂时没有可安排的任务，请先完成练习或检查考试日期。'
    details = '\n\n'.join(d['date']+'\n'+'\n'.join(f"· {t['title']}（{t['minutes']} 分钟）" for t in d['tasks']) for d in plan['days'])
    return f"复习计划预览（每天 {plan['minutes']} 分钟，考试日期 {plan['examDate']}）：\n\n{details}\n\n{summary}\n\n这是一份预览，尚未修改你已有的复习计划。"
