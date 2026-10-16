from ..core import clone, fingerprint, add_days, date_at
from .planning import plan_study
from .study import mastery, baseline_review, FsrsScheduler
from .question_service import select_practice


def planning_metrics(plan, scenario):
    days = [{'date': d['date'], 'used': sum(t['minutes'] for t in d['tasks']), 'budget': scenario.get('availability', {}).get(d['date'], scenario['minutes'])} for d in plan['days']]
    return {'scheduledMinutes': sum(d['used'] for d in days), 'budgetViolationDays': sum(d['used'] > d['budget'] for d in days), 'excessMinutes': sum(max(0, d['used']-d['budget']) for d in days), 'remainingMinutes': sum(t['minutes'] for t in plan['remaining']), 'days': days}


def fixed_daily_baseline(value):
    """Historical fixed daily capacity; use the same task order, ignore per-day calendar."""
    return {**plan_study({**value, 'availability': {}}), 'algorithm': 'fixed-daily-pre-calendar-python-port'}


def run_local_experiments(value):
    base = value['baseDate']
    scenarios = [
        {'id': 'closed-and-short-days', 'minutes': 20, 'availability': {base: 0, add_days(base, 2): 7}},
        {'id': 'small-sessions', 'minutes': 10, 'availability': {base: 2, add_days(base, 1): 0, add_days(base, 2): 8}},
        {'id': 'alternating-days', 'minutes': 15, 'availability': {base: 0, add_days(base, 1): 30, add_days(base, 2): 0, add_days(base, 3): 30}},
        {'id': 'uniform-control', 'minutes': 30, 'availability': {}}]
    planning = []
    for settings in scenarios:
        scenario = {**clone(value), **settings}
        planning.append({'id': settings['id'], 'input': {k: scenario[k] for k in ('minutes', 'availability', 'baseDate', 'examDate')}, 'baseline': planning_metrics(fixed_daily_baseline(scenario), scenario), 'candidate': planning_metrics(plan_study(scenario), scenario)})
    estimates = mastery(value['events'], {'courseId': value['courseId'], 'baseDate': base})
    recent = [e['questionId'] for e in value['events']]
    fixed = [q for q in value['questions'] if q['status'] == 'approved'][:3]
    adaptive = [i['question'] for i in select_practice(value['questions'], {'courseId': value['courseId'], 'count': 3, 'estimates': estimates, 'recentQuestionIds': recent})['items']]
    weak = {e['conceptId'] for e in estimates if e['estimate'] is not None and e['estimate'] < .6}
    def metrics(questions):
        return {'ids': [q['id'] for q in questions], 'recentRepeats': sum(q['id'] in recent for q in questions), 'weakTopicQuestions': sum(bool(set(q.get('conceptIds', [])) & weak) for q in questions), 'conceptCoverage': len({c for q in questions for c in q.get('conceptIds', [])})}
    events = [{'id': 'synthetic-review-'+str(i), 'courseId': value['courseId'], 'cardId': 'synthetic-card', 'rating': rating, 'createdAt': add_days('2026-10-01', day)+'T00:00:00Z'} for i, (day, rating) in enumerate([(0, 3), (1, 3), (3, 1), (4, 2), (7, 4)])]
    card, reviews, scheduler = {'id': 'synthetic-card', 'courseId': value['courseId'], 'kind': 'memory-card'}, [], FsrsScheduler()
    for index, event in enumerate(events):
        card = baseline_review(card, {k: event[k] for k in ('id', 'courseId', 'cardId', 'rating')} | {'date': date_at(event['createdAt'])})
        replay = scheduler.replay(events[:index+1], {'courseId': value['courseId'], 'cardId': event['cardId'], 'createdAt': events[0]['createdAt']})
        reviews.append({'eventId': event['id'], 'rating': event['rating'], 'reviewedAt': event['createdAt'], 'baselineDueDate': card['due'], 'fsrsDueAt': replay['card']['due'], 'fsrsDueDate': date_at(replay['card']['due'])})
    return {'schemaVersion': 2, 'experiment': 'C-local-rules-python-v1', 'dataKind': 'authored-synthetic', 'datasetHash': fingerprint(value), 'randomization': 'none',
            'algorithms': {'baseline': 'fixed-daily-pre-calendar-python-port / fixed-input-order / fixed-rating-baseline-v1', 'candidate': 'calendar-prerequisite-budget-v2 / weakness-with-exploration-v1 / '+scheduler.algorithm}, 'planning': planning, 'practice': {'baseline': metrics(fixed), 'candidate': metrics(adaptive)}, 'reviews': reviews,
            'limitations': ['合成小样本，仅验证规则行为与约束，不代表真实用户总体', '没有测量记忆保持率、成绩提升或模型质量', 'Python FSRS 与历史 ts-fsrs 结果分别版本化，不宣称调度时间相同', '固定日预算基线保留相同任务顺序，逐日空闲时间是比较变量']}


def render_local_experiment_report(result):
    lines = ['# C Python 本地规则对照实验', '', '数据为自行编写的合成记录，不使用 API；不衡量真实学习收益。', '', '版本：`'+result['experiment']+'`；数据指纹：`'+result['datasetHash']+'`。', '', '| 场景 | 基线超预算天数 | 候选超预算天数 | 基线超出分钟 | 候选超出分钟 |', '| --- | ---: | ---: | ---: | ---: |']
    lines += [f"| {p['id']} | {p['baseline']['budgetViolationDays']} | {p['candidate']['budgetViolationDays']} | {p['baseline']['excessMinutes']} | {p['candidate']['excessMinutes']} |" for p in result['planning']]
    lines += ['', '选题与 FSRS 精确调度结果见同目录 results.json。', '', *['- '+s for s in result['limitations']], '']
    return '\n'.join(lines)
