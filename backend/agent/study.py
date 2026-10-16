from datetime import timezone
from importlib.metadata import version
from ..core import require, clone, fingerprint, date_at, today, valid_date, days_until, finite, instant, add_days
from .planning import plan_study, replan_study, revise_plan


def mastery(events, options):
    course, base, half = options.get('courseId'), options.get('baseDate', today()), options.get('halfLifeDays', 30)
    require(course and valid_date(base) and finite(half) and half > 0, 'INVALID_MASTERY_CONTEXT')
    seen, latest = {}, {}
    for event in events:
        if event['courseId'] != course:
            continue
        require(event.get('id'), 'INVALID_LEARNING_EVENT')
        time = instant(event['createdAt'])
        digest = fingerprint(event)
        if event['id'] in seen:
            require(seen[event['id']] == digest, 'EVENT_ID_CONFLICT')
            continue
        seen[event['id']] = digest
        date = date_at(event['createdAt'])
        if date > base or event.get('grade', {}).get('status') != 'graded':
            continue
        grade = event['grade']
        require(finite(grade.get('score')) and finite(grade.get('maxScore')) and grade['maxScore'] > 0 and 0 <= grade['score'] <= grade['maxScore'], 'INVALID_GRADE')
        old = latest.get(event['questionId'])
        if not old or (time, event['id']) > (instant(old['createdAt']), old['id']):
            latest[event['questionId']] = {**event, 'date': date}
    concepts = {}
    for event in latest.values():
        for key in set([] if (event.get('masteryExclusion') or {}).get('confirmedBy') else event.get('conceptIds', [])):
            value = concepts.setdefault(key, {'weight': 0, 'success': 0, 'evidence': []})
            weight = 2**(-max(0, days_until(base, event['date']))/half)
            value['weight'] += weight
            value['success'] += weight*event['grade']['score']/event['grade']['maxScore']
            value['evidence'].append(event['id'])
    result = []
    for key, value in concepts.items():
        sufficient = len(value['evidence']) >= 3 and value['weight'] >= 1.5
        result.append({'conceptId': key, 'status': 'estimated' if sufficient else 'insufficient', 'estimate': (value['success']+1)/(value['weight']+2) if sufficient else None,
                       'confidence': 'moderate' if sufficient and len(value['evidence']) >= 10 else 'low' if sufficient else 'insufficient', 'samples': len(value['evidence']),
                       'evidence': value['evidence'], 'algorithm': 'latest-question-beta-decay-v1', 'baseDate': base, 'limitation': '描述近期练习证据，不等同真实能力或已证明学习效果'})
    return result


class FsrsScheduler:
    """Official Python FSRS; old ts-fsrs states are replayed from immutable events."""
    def __init__(self, retention=.9):
        from fsrs import Scheduler
        require(finite(retention) and .7 <= retention <= .97, 'INVALID_RETENTION')
        self.retention = retention
        self.scheduler = Scheduler(desired_retention=retention, enable_fuzzing=False)
        self.algorithm = 'py-fsrs-'+version('fsrs')

    def replay(self, events, context):
        from fsrs import Card, Rating
        created = instant(context['createdAt']).astimezone(timezone.utc)
        require(context.get('courseId') and context.get('cardId'), 'INVALID_REVIEW_TIME')
        card, logs, seen, last = Card(card_id=int(fingerprint([context['courseId'], context['cardId']])[:12], 16), due=created), [], {}, created
        for event in events:
            require(event.get('courseId') == context['courseId'] and event.get('cardId') == context['cardId'], 'REVIEW_SCOPE_MISMATCH')
            digest = fingerprint(event)
            if event.get('id') in seen:
                require(seen[event['id']] == digest, 'EVENT_ID_CONFLICT')
                continue
            time = instant(event['createdAt']).astimezone(timezone.utc)
            require(event.get('id') and time >= last and type(event.get('rating')) is int and event['rating'] in (1, 2, 3, 4), 'INVALID_REVIEW_EVENT')
            seen[event['id']], last = digest, time
            card, log = self.scheduler.review_card(card, Rating(event['rating']), review_datetime=time)
            logs.append({'eventId': event['id'], **log.to_dict()})
        return {'card': card.to_dict(), 'logs': logs, 'algorithm': self.algorithm, 'retention': self.retention, 'personalized': False}


def baseline_review(card, event):
    require(card.get('id') and card.get('kind') == 'memory-card' and event.get('id') and event.get('cardId') == card['id'] and event.get('courseId') == card['courseId'] and valid_date(event.get('date')) and type(event.get('rating')) is int and event['rating'] in (1, 2, 3, 4), 'INVALID_REVIEW_EVENT')
    old = next((e for e in card.get('history', []) if e['id'] == event['id']), None)
    if old:
        require(fingerprint(old) == fingerprint(event), 'EVENT_ID_CONFLICT')
        return clone(card)
    require(not card.get('lastReviewed') or event['date'] >= card['lastReviewed'], 'OUT_OF_ORDER_REVIEW')
    interval = (0, 1, 3, 7, 14)[event['rating']]
    return {**clone(card), 'lastReviewed': event['date'], 'interval': interval, 'due': add_days(event['date'], interval), 'history': [*card.get('history', []), clone(event)], 'algorithm': 'fixed-rating-baseline-v1'}


def recommend(value):
    base, skip = value.get('baseDate', today()), value.get('skip', [])
    require(valid_date(base), 'INVALID_DATE')
    due = [{'id': c['id'], 'kind': 'review', 'minutes': 5, 'reason': '复习已到期', 'evidence': [e['id'] for e in c.get('history', [])]} for c in value.get('cards', []) if c.get('due') and c['due'] <= base and c['id'] not in skip]
    estimates = value.get('estimates', [])
    weak = [{'id': e['conceptId'], 'kind': 'practice', 'minutes': 10, 'reason': '近期练习证据显示需要巩固', 'evidence': e['evidence']} for e in sorted([e for e in estimates if e.get('estimate') is not None and e['estimate'] < .6 and e['conceptId'] not in skip], key=lambda e: e['estimate'])]
    explore = next((e for e in estimates if e['status'] == 'insufficient' and e['conceptId'] not in skip), None)
    return due+weak+([{'id': explore['conceptId'], 'kind': 'explore', 'minutes': 10, 'reason': '证据不足，补充不同知识点的练习', 'evidence': explore['evidence']}] if explore else [])
