"""Pure practice state transitions. Parity twin of frontend/js/state/practice-store.js.

Status model is mutually exclusive (PRD 5.1): 待刷 pending / 已掌握 mastered / 错题本 wrong.
confidence is the 待巩固 flag (PRD 5.2): it only raises the random-pick weight, never the list order.
"""
from __future__ import annotations

STATUS_PENDING = 'pending'
STATUS_MASTERED = 'mastered'
STATUS_WRONG = 'wrong'
CONFIDENCE_UNKNOWN = 'unknown'
CONFIDENCE_FUZZY = 'fuzzy'
CONFIDENCE_MASTERED = 'mastered'
OBJECTIVE = ('single', 'multiple', 'boolean', 'fill')

ACTIONS = ('answer', 'correct', 'master', 'conquer', 'fuzzy', 'mark-wrong', 'reset')


def blank():
    return {'status': STATUS_PENDING, 'confidence': CONFIDENCE_UNKNOWN, 'wrongCount': 0, 'correctCount': 0,
            'wrongEnteredAt': None, 'lastWrongAt': None, 'lastResult': None, 'masteredAt': None,
            'lastOperationAt': None, 'revision': 0}


def entry(progress, question_id):
    row = progress.get(question_id)
    if row is None:
        row = blank()
        progress[question_id] = row
    return row


def is_objective(question):
    return question.get('type') in OBJECTIVE


def _now(payload):
    return payload.get('at') or ''


def apply(progress, question, action, payload):
    """Mutate and return the progress row for question['id']. Raises ValueError on an illegal action."""
    kind = question.get('type')
    row = entry(progress, question['id'])
    at = _now(payload)
    if action == 'answer':
        # PRD 5.3: only 单选/填空 actually-wrong answers raise wrongCount; every re-answer wrong counts.
        if not is_objective(question):
            raise ValueError('OBJECTIVE_ANSWER_ONLY')
        result = payload.get('result')
        if result not in ('correct', 'wrong'):
            raise ValueError('INVALID_ANSWER_RESULT')
        row['lastResult'] = result
        row['lastOperationAt'] = at
        row['revision'] += 1
        if result == 'wrong':
            row['wrongCount'] += 1
            row['lastWrongAt'] = at
            if row['status'] != STATUS_WRONG:
                row['wrongEnteredAt'] = at
            # PRD 6.1: wrong answers auto-enter the wrong book.
            row['status'] = STATUS_WRONG
        else:
            row['correctCount'] += 1
            # PRD 6.2: a correct re-answer stays in the wrong book until 错题已攻克.
        return row
    if action == 'correct':
        # PRD 6.3: 此答案也正确 — only 填空判错 after a wrong submit.
        if kind != 'fill':
            raise ValueError('FILL_ONLY')
        attempt_id = payload.get('attemptId')
        if attempt_id and attempt_id in row.get('correctedAttemptIds', []):
            return row
        if (not attempt_id and row['lastResult'] != 'wrong') or row['wrongCount'] <= 0:
            raise ValueError('NOTHING_TO_CORRECT')
        if attempt_id:
            row.setdefault('correctedAttemptIds', []).append(attempt_id)
        row['wrongCount'] -= 1
        row['correctCount'] += 1
        row['lastResult'] = 'correct'
        row['status'] = STATUS_PENDING
        row['confidence'] = CONFIDENCE_UNKNOWN
        row['lastOperationAt'] = at
        row['revision'] += 1
        return row
    if action == 'fuzzy':
        # PRD 5.2: stays in 待刷, raises the random weight.
        if row['status'] != STATUS_PENDING:
            raise ValueError('PENDING_ONLY')
        row['confidence'] = CONFIDENCE_FUZZY
        row['lastOperationAt'] = at
        row['revision'] += 1
        return row
    if action == 'master':
        if row['status'] != STATUS_PENDING:
            raise ValueError('PENDING_ONLY')
        row['status'] = STATUS_MASTERED
        row['confidence'] = CONFIDENCE_MASTERED
        row['masteredAt'] = at
        row['lastOperationAt'] = at
        row['revision'] += 1
        return row
    if action == 'conquer':
        # PRD 8.3: 错题已攻克 -> 已掌握.
        if row['status'] != STATUS_WRONG:
            raise ValueError('WRONG_ONLY')
        row['status'] = STATUS_MASTERED
        row['confidence'] = CONFIDENCE_MASTERED
        row['masteredAt'] = at
        row['lastOperationAt'] = at
        row['revision'] += 1
        return row
    if action == 'mark-wrong':
        # PRD 5.3: manual add / 忘记 records the entry time but does NOT raise wrongCount.
        row['status'] = STATUS_WRONG
        row['wrongEnteredAt'] = at
        row['lastOperationAt'] = at
        row['revision'] += 1
        return row
    if action == 'reset':
        # PRD 5.2/8.3: 移回待刷 keeps the history (wrongCount untouched).
        if row['status'] == STATUS_PENDING:
            raise ValueError('ALREADY_PENDING')
        row['status'] = STATUS_PENDING
        row['confidence'] = CONFIDENCE_UNKNOWN
        row['lastOperationAt'] = at
        row['revision'] += 1
        return row
    raise ValueError('UNKNOWN_ACTION')


def weight(row):
    """PRD 7.2: 待巩固 raises the random weight and nothing else changes."""
    return 3 if (row or {}).get('confidence') == CONFIDENCE_FUZZY else 1


def random_pick(candidates, progress, *, last_id=None, roll=None):
    """PRD 7.2: weighted pick among candidates, avoiding a repeat of last_id when possible."""
    items = [q for q in candidates if q and q.get('id')]
    if not items:
        return None
    pool = [q for q in items if q['id'] != last_id] if len(items) > 1 else items
    weights = [weight(progress.get(q['id'])) for q in pool]
    total = sum(weights)
    roll = (roll if roll is not None else 0.5) % 1.0
    target = roll * total
    running = 0
    for q, w in zip(pool, weights):
        running += w
        if target < running:
            return q
    return pool[-1]


def sort_wrong(rows, *, mode='recent'):
    """PRD 8.1: 最近出错优先 (default) or 错误次数最多. Ties break by question id ascending."""
    def stamp(item):
        row = item[1]
        return max(row.get('lastWrongAt') or '', row.get('wrongEnteredAt') or '')
    ordered = sorted(rows, key=lambda item: item[0])
    ordered.sort(key=stamp, reverse=True)
    if mode == 'count':
        ordered.sort(key=lambda item: item[1].get('wrongCount', 0), reverse=True)
    return ordered


def merge_note(existing, incoming_text, base_revision, *, at='', device=''):
    """PRD 9.4/10.5: a revision mismatch keeps BOTH copies for the user to choose."""
    existing = existing or {'text': '', 'revision': 0, 'updatedAt': None, 'conflicts': []}
    conflicts = list(existing.get('conflicts') or [])
    revision = existing.get('revision', 0)
    if base_revision != revision:
        conflicts.append({'text': incoming_text, 'createdAt': at, 'deviceTag': device, 'baseRevision': base_revision})
        return {'text': existing.get('text', ''), 'revision': revision + 1, 'updatedAt': at,
                'conflicts': conflicts, 'merged': True}
    return {'text': incoming_text, 'revision': revision + 1, 'updatedAt': at, 'conflicts': conflicts, 'merged': False}
