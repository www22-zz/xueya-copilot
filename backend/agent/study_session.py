from ..core import require, valid_date, today, add_days, date_at, days_until, instant, fingerprint
from .evidence import evidence_package
from .concepts import validate_graph, build_learning_path
from .assessment import validate_question, diagnose
from .study import mastery
from .planning import plan_study
from .question_service import select_practice

FOLLOW_UP = {'knowledge-gap': ('read-and-practice', '已确认知识缺口，先核对原文再做不同题目'), 'misread': ('mark-conditions', '已确认审题问题，先标出条件再换题核对'),
             'calculation': ('check-calculation', '已确认计算偏差，逐步复核计算后做相关练习'), 'method': ('review-prerequisite', '已确认方法问题，先回顾先修知识和适用条件'),
             'notation': ('explain-notation', '已确认符号问题，先解释符号含义再练习'), 'input-error': ('optional-retry', '学习者确认输入误操作，不据此判断知识薄弱'), 'uncertain': ('explain-solution', '错因尚不明确，补充解题过程再核对')}


def build_study_session(value):
    course, base = value['courseId'], value.get('baseDate', today())
    recent = value.get('recentDays', 7)
    require(valid_date(base) and type(recent) is int and 1 <= recent <= 365, 'INVALID_STUDY_SESSION')
    pack = evidence_package(value)
    graph = validate_graph(value.get('graph', {'courseId': course, 'concepts': [], 'edges': []}), pack['sources'])
    questions, cards = value.get('questions', []), value.get('cards', [])
    require(all(q['courseId'] == course for q in [*questions, *cards]), 'COURSE_MISMATCH')
    pool, unavailable, excluded, events = [], [], [], []
    for question in questions:
        try:
            pool.append(validate_question(question, pack['sources']))
        except ValueError as error:
            unavailable.append({'id': question['id'], 'reason': str(error)})
    versions = {s['id']: s['version'] for s in pack['sources']}
    for event in value.get('events', []):
        if event['courseId'] != course:
            continue
        if versions.get(event['sourceId']) != event['sourceVersion']:
            excluded.append({'id': event['id'], 'reason': 'OUTDATED_OR_OUT_OF_SCOPE_EVIDENCE'})
        elif date_at(event['createdAt']) <= base:
            events.append(event)
    computed = {e['conceptId']: e for e in mastery(events, {'courseId': course, 'baseDate': base})}
    estimates = [computed.get(c['id'], {'conceptId': c['id'], 'status': 'unknown', 'estimate': None, 'confidence': 'insufficient', 'samples': 0, 'evidence': [], 'algorithm': 'latest-question-beta-decay-v1', 'baseDate': base}) for c in graph['concepts'] if c.get('status') != 'rejected']
    path = build_learning_path({'courseId': course, 'graph': graph, 'estimates': estimates, **({'targetIds': value['targetIds']} if 'targetIds' in value else {})})
    feedback = {e['itemId']: e for e in value.get('feedback', []) if e['courseId'] == course}
    suppressed = {e['itemId'] for e in feedback.values() if e['action'] in ('skip', 'dismiss', 'completed') and valid_date(e.get('until')) and e['until'] >= base}
    practice = select_practice(pool, {'courseId': course, 'count': value.get('practiceCount', 5), 'estimates': estimates, 'recentQuestionIds': list({e['questionId'] for e in events if e['grade']['status'] == 'graded' and days_until(base, date_at(e['createdAt'])) < recent}), 'skip': list(suppressed)})
    latest = {}
    for event in events:
        old = latest.get(event['questionId'])
        if not old or (instant(event['createdAt']), event['id']) > (instant(old['createdAt']), old['id']):
            latest[event['questionId']] = event
    actions = []
    for event in latest.values():
        confirmation = next((d for d in value.get('diagnoses', []) if d['eventId'] == event['id'] and d['status'] == 'confirmed'), None)
        diagnostic = diagnose(event)
        cause = confirmation['cause'] if confirmation else 'uncertain'
        action, reason = ('spaced-review', '本次作答通过，后续用复习和不同题目核对') if diagnostic['status'] == 'observed' and not confirmation else FOLLOW_UP[cause]
        related = [item['question']['id'] for item in practice['items'] if set(item['question'].get('conceptIds', [])) & set(event.get('conceptIds', []))]
        actions.append({**{k: event[k] for k in ('questionId', 'questionVersion', 'sourceId', 'sourceVersion')}, 'eventId': event['id'], 'status': 'confirmed' if confirmation else diagnostic['status'], 'cause': cause, 'action': action, 'reason': reason,
                        'relatedQuestionIds': related, 'followUpStatus': 'approved-alternatives-available' if related else 'no-unseen-approved-alternative', 'evidence': [event['id']], 'limitation': '按学习者明确订正安排' if confirmation else '没有足够信息推断真实思考过程'})
    plan = plan_study({**value, 'courseId': course, 'graph': graph, 'estimates': estimates, 'baseDate': base, 'examDate': value.get('examDate', add_days(base, 7))})
    recommendations, emitted = [], set()
    def practice_item(item, minutes):
        specific = next((a for a in actions if item['question']['id'] in a['relatedQuestionIds'] and a['status'] == 'confirmed'), None)
        return {'id': item['question']['id'], 'kind': 'practice', 'questionId': item['question']['id'], 'questionVersion': item['question']['version'], 'minutes': minutes,
                'reason': specific['reason'] if specific else item['reason'], 'evidence': list(dict.fromkeys(item['evidence']+(specific['evidence'] if specific else []))), 'conceptIds': item['question'].get('conceptIds', [])}
    now = value.get('now')
    def waiting(card):
        return card.get('eligibleAt') and now and date_at(now) == base and instant(card['eligibleAt']) > instant(now)
    for task in next((d['tasks'] for d in plan['days'] if d['date'] == base), []):
        if task['id'] in suppressed:
            continue
        if task['kind'] == 'card-review':
            card = next(c for c in cards if c['id'] == task['cardId'])
            if not waiting(card) and card['id'] not in suppressed:
                recommendations.append({'id': card['id'], 'kind': task['kind'], 'minutes': task['minutes'], 'reason': task['reason'], 'evidence': card.get('evidence', []), 'dueDate': card['dueDate']})
            continue
        matching = [item for item in practice['items'] if item['question']['id'] not in emitted and task.get('conceptId') in item['question'].get('conceptIds', [])] if task['kind'] == 'practice' else []
        if matching:
            remaining = task['minutes']
            for item in matching:
                if not remaining:
                    break
                allocation = min(5, remaining)
                recommendations.append(practice_item(item, allocation))
                emitted.add(item['question']['id'])
                remaining -= allocation
            if remaining:
                recommendations.append({**{k: task[k] for k in ('id', 'conceptId', 'evidence', 'sourceEvidence')}, 'kind': 'self-explanation', 'minutes': remaining, 'reason': '练习后回到原文复述并核对'})
        else:
            recommendations.append({k: task[k] for k in ('id', 'kind', 'conceptId', 'minutes', 'reason', 'evidence', 'sourceEvidence')})
    if not path['entries']:
        recommendations.extend(practice_item(item, 5) for item in practice['items'])
    budget, used, daily = value.get('availability', {}).get(base, value.get('minutes', 30)), 0, []
    for item in recommendations:
        if item['id'] in suppressed or used >= budget:
            continue
        allocated = min(item['minutes'], budget-used)
        daily.append({**item, 'minutes': allocated, 'partial': allocated < item['minutes']})
        used += allocated
    return {'courseId': course, 'baseDate': base, 'evidenceVersion': pack['version'], 'estimates': estimates, 'path': path, 'practice': practice, 'diagnosticActions': actions, 'plan': plan, 'feedbackRevision': value.get('feedbackRevision', 0),
            'daily': {'budget': budget, 'allocatedMinutes': used, 'items': daily}, 'unavailableQuestions': unavailable, 'excludedEvents': excluded,
            'waitingCards': [{'id': c['id'], 'readyAt': c['eligibleAt'], 'reason': '今天稍后到期，暂不重复推荐'} for c in cards if c.get('eligibleDate', base) <= base and waiting(c)],
            'version': fingerprint({'evidence': pack['version'], 'input': value, 'daily': daily}), 'warnings': (['QUESTION_VERSIONS_UNAVAILABLE'] if unavailable else [])+(['HISTORICAL_EVIDENCE_EXCLUDED'] if excluded else []), 'algorithm': 'local-study-loop-v1'}
