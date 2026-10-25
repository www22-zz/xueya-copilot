from ..core import require, clone, fingerprint, today, valid_date, add_days, days_until
from .concepts import build_learning_path


def daily_budget(date, minutes, availability):
    return availability.get(date, minutes)


def history_totals(history):
    require(isinstance(history, list), 'INVALID_PLAN_HISTORY')
    full, amounts, parts, seen = set(), {}, {}, {}
    for item in history:
        if isinstance(item, str):
            full.add(item)
            continue
        require(
            isinstance(item, dict)
            and isinstance(item.get('id'), str)
            and item['id']
            and ('date' not in item or valid_date(item['date'])),
            'INVALID_PLAN_HISTORY',
        )
        if 'minutes' not in item:
            full.add(item['id'])
            continue
        require(
            type(item['minutes']) is int
            and item['minutes'] > 0
            and type(item.get('part')) is int
            and item['part'] > 0,
            'INVALID_PLAN_HISTORY',
        )
        key, digest = (item['id'], item['part']), fingerprint(item)
        if key in seen:
            require(seen[key] == digest, 'PLAN_HISTORY_CONFLICT')
            continue
        seen[key] = digest
        amounts[item['id']] = amounts.get(item['id'], 0) + item['minutes']
        parts[item['id']] = max(parts.get(item['id'], 0), item['part'])
    return full, amounts, parts


def plan_study(value):
    course, graph = value.get('courseId'), value.get('graph')
    base, exam, minutes = value.get('baseDate', today()), value.get('examDate'), value.get('minutes', 30)
    availability, max_days = value.get('availability', {}), value.get('maxDays', 90)
    require(
        course
        and graph
        and graph['courseId'] == course
        and valid_date(base)
        and valid_date(exam)
        and type(minutes) is int
        and 1 <= minutes <= 480
        and type(max_days) is int
        and 1 <= max_days <= 366
        and isinstance(availability, dict),
        'INVALID_PLAN',
    )
    require(
        all(valid_date(d) and type(n) is int and 0 <= n <= 480 for d, n in availability.items()),
        'INVALID_AVAILABILITY',
    )
    previous = value.get('previousPlan')
    require(not previous or previous['courseId'] == course, 'COURSE_MISMATCH')
    completed, skipped = value.get('completed', []), value.get('skipped', [])
    done, done_amounts, done_parts = history_totals(completed)
    omitted, omitted_amounts, omitted_parts = history_totals(skipped)
    path = build_learning_path(value)
    tasks = []
    for entry in path['entries']:
        for i, kind in enumerate(('read', 'practice', 'review')):
            tasks.append(
                {
                    'id': entry['conceptId'] + ':' + kind,
                    'conceptId': entry['conceptId'],
                    'kind': kind,
                    'minutes': (10, 15, 5)[i],
                    'dependsOn': (
                        [p + ':practice' for p in entry['prerequisites']]
                        if kind == 'read'
                        else [entry['conceptId'] + (':' + ('read' if kind == 'practice' else 'practice'))]
                    ),
                    'reason': ('按先修顺序核对原文' if kind == 'read' else entry['reason'] if kind == 'practice' else '回顾并自评记忆'),
                    'evidence': entry['eventEvidence'],
                    'sourceEvidence': entry['sourceEvidence'],
                },
            )
    seen = set()
    for card in value.get('cards', []):
        require(
            card.get('courseId') == course
            and card.get('id')
            and valid_date(card.get('dueDate'))
            and ('eligibleDate' not in card or valid_date(card['eligibleDate'])),
            'INVALID_PLAN_CARD',
        )
        require(card['id'] not in seen, 'DUPLICATE_PLAN_CARD')
        seen.add(card['id'])
        if card['dueDate'] <= exam:
            tasks.insert(
                0,
                {
                    'id': 'card:' + fingerprint([course, card['id'], card['dueDate']])[:24],
                    'cardId': card['id'],
                    'kind': 'card-review',
                    'minutes': 5,
                    'dependsOn': [],
                    'notBefore': card.get('eligibleDate', card['dueDate']),
                    'reason': ('逾期记忆卡复习' if card['dueDate'] < base else '记忆卡到期复习'),
                    'evidence': card.get('evidence', []),
                },
            )
    previous_tasks = (
        [{**t, 'date': d['date']} for d in previous['days'] for t in d['tasks']]
        if previous
        else value.get('previous', [])
    )
    queue = [{
        **t,
        'minutes': max(0, t['minutes'] - done_amounts.get(t['id'], 0) - omitted_amounts.get(t['id'], 0)),
        'part': max(done_parts.get(t['id'], 0), omitted_parts.get(t['id'], 0)) + 1,
        'overdue': any(old['id'] == t['id'] and old.get('date', base) < base for old in previous_tasks),
    } for t in tasks if t['id'] not in done | omitted]
    queue = [t for t in queue if t['minutes'] > 0]
    scheduled = {t['id'] for t in tasks if not any(p['id'] == t['id'] for p in queue)}
    pending_minutes, days = sum(t['minutes'] for t in queue), []
    for offset in range(max(0, min(max_days, days_until(exam, base) + 1))):
        if not queue:
            break
        date = add_days(base, offset)
        budget = daily_budget(date, minutes, availability)
        free, items = budget, []
        while free > 0:
            ready = [t for t in queue if t.get('notBefore', date) <= date and all(p in scheduled for p in t['dependsOn'])]
            ready.sort(
                key=lambda t: (0 if t['kind'] == 'card-review' else 1 if t['overdue'] else 2, queue.index(t)),
            )
            if not ready:
                break
            task = ready[0]
            used = min(task['minutes'], free)
            items.append({**clone(task), 'minutes': used})
            task['minutes'] -= used
            free -= used
            if not task['minutes']:
                queue.remove(task)
                scheduled.add(task['id'])
            else:
                task['part'] += 1
        days.append({'date': date, 'budget': budget, 'tasks': items})
    warnings = (['EXAM_DATE_PASSED'] if exam < base else []) + (['INSUFFICIENT_CAPACITY'] if queue else []) + (['HORIZON_LIMIT'] if days_until(exam, base) + 1 > max_days else []) + (['SKIPPED_NOT_COMPLETED'] if skipped else [])
    proposed = list(dict.fromkeys(t['id'] for d in days for t in d['tasks']))
    old_ids = list(dict.fromkeys(t['id'] for t in previous_tasks))
    moved = [key for key in proposed if (
        key in old_ids
        and [d['date'] for d in days if any(t['id'] == key for t in d['tasks'])] != list(dict.fromkeys(t.get('date') for t in previous_tasks if t['id'] == key))
    )]
    return {
        'courseId': course,
        'status': ('expired' if exam < base else 'preview'),
        'baseDate': base,
        'examDate': exam,
        'minutes': minutes,
        'availability': clone(availability),
        'maxDays': max_days,
        'days': days,
        'remaining': queue,
        'completed': clone(completed),
        'skipped': clone(skipped),
        'path': path,
        'warnings': warnings,
        'workload': {
            'pendingMinutes': pending_minutes,
            'scheduledMinutes': sum(t['minutes'] for d in days for t in d['tasks']),
            'remainingMinutes': sum(t['minutes'] for t in queue),
        },
        'difference': {
            'removed': [key for key in old_ids if key not in proposed and key not in done],
            'added': [key for key in proposed if key not in old_ids],
            'moved': moved,
        },
        'previousPlanVersion': (fingerprint(previous) if previous else None),
        'requiresConfirmation': True,
        'algorithm': 'calendar-prerequisite-budget-v2',
    }


def replan_study(previous, value):
    require(value.get('courseId', previous['courseId']) == previous['courseId'], 'COURSE_MISMATCH')
    return plan_study(
        {
            **{k: previous[k] for k in ('courseId', 'examDate', 'minutes', 'completed')},
            'availability': previous.get('availability', {}),
            'skipped': previous.get('skipped', []),
            'maxDays': previous.get('maxDays', 90),
            **value,
            'previousPlan': previous,
        },
    )


def revise_plan(plan, change):
    action, key, part = change.get('action'), change.get('taskId'), change.get('part', 1)
    require(action in ('complete', 'skip', 'postpone') and key, 'INVALID_PLAN_ACTION')
    result, found, start = clone(plan), None, None
    for day in result['days']:
        for task in day['tasks']:
            if task['id'] == key and task.get('part', 1) == part:
                found, start = task, day['date']
                day['tasks'].remove(task)
                break
        if found:
            break
    require(found, 'PLAN_TASK_NOT_FOUND')
    if action in ('complete', 'skip'):
        result.setdefault('completed' if action == 'complete' else 'skipped', []).append(
            {'id': key, 'part': part, 'minutes': found['minutes'], 'date': start},
        )
    else:
        date = change.get('date')
        require(valid_date(date) and start <= date <= plan['examDate'], 'INVALID_POSTPONE_DATE')
        original = [(d['date'], t) for d in plan['days'] for t in d['tasks']]
        index = next(i for i, (_, t) in enumerate(original) if t['id'] == key and t.get('part', 1) == part)
        require(not any(d < date for d, _ in original[index + 1:]), 'PLAN_ORDER_REQUIRES_REBUILD')
        target = next((d for d in result['days'] if d['date'] == date), None)
        if target is None:
            target = {'date': date, 'tasks': []}
            result['days'].append(target)
        require(
            sum(t['minutes'] for t in target['tasks']) + found['minutes'] <= daily_budget(date, plan['minutes'], plan.get('availability', {})),
            'PLAN_DAILY_BUDGET',
        )
        target['tasks'].append(found)
        result['days'].sort(key=lambda d: d['date'])
    return {**result, 'status': 'preview', 'requiresConfirmation': True}
