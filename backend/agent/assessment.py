import re
from ..core import require, clone, normalized, fingerprint, finite, instant

TYPES = {'single', 'multiple', 'boolean', 'fill', 'short', 'code'}


def validate_question(q, sources):
    require(
        q.get('id') and q.get('courseId') and q.get('version')
        and q.get('type') in TYPES
        and isinstance(q.get('prompt'), str) and q['prompt'].strip(),
        'INVALID_QUESTION',
    )
    source = next((
        s for s in sources
        if s['id'] == q.get('sourceId')
        and s.get('courseId') == q['courseId']
        and s.get('version') == q.get('sourceVersion')
    ), None)
    require(
        source and isinstance(q.get('evidenceQuote'), str)
        and q['evidenceQuote'].strip() and q['evidenceQuote'] in source['quote'],
        'INVALID_QUESTION_EVIDENCE',
    )
    if q['type'] in ('single', 'multiple'):
        options = q.get('options')
        require(
            isinstance(options, list) and 2 <= len(options) <= 8
            and all(isinstance(x, str) and x.strip() for x in options)
            and len({normalized(x) for x in options}) == len(options),
            'INVALID_OPTIONS',
        )
        answers = [q.get('answer')] if q['type'] == 'single' else q.get('answer')
        require(
            isinstance(answers, list) and answers
            and all(type(x) is int and 0 <= x < len(options) for x in answers)
            and len(set(answers)) == len(answers),
            'INVALID_ANSWER',
        )
    if q['type'] == 'boolean':
        require(type(q.get('answer')) is bool, 'INVALID_ANSWER')
    if q['type'] == 'fill':
        require(
            isinstance(q.get('answers'), list) and q['answers']
            and all(
                isinstance(g, list) and g
                and all(isinstance(v, str) and v.strip() for v in g)
                for g in q['answers']
            ),
            'INVALID_ANSWER',
        )
    if q['type'] == 'short':
        rubric = q.get('rubric')
        require(
            isinstance(rubric, list) and rubric
            and all(
                x.get('id') and isinstance(x.get('description'), str)
                and finite(x.get('points')) and x['points'] > 0
                for x in rubric
            )
            and len({x['id'] for x in rubric}) == len(rubric),
            'INVALID_RUBRIC',
        )
    if q['type'] == 'code':
        require(isinstance(q.get('solutions'), dict) and q['solutions']
                and all(isinstance(k, str) and re.fullmatch(r'[a-zA-Z0-9_+#-]{1,24}', k) and isinstance(v, str) and v.strip()
                        for k, v in q['solutions'].items()), 'INVALID_CODE_SOLUTION')
        require(isinstance(q.get('samples'), list) and q['samples']
                and all(isinstance(s, dict) and isinstance(s.get('input'), str)
                        and isinstance(s.get('output'), str) for s in q['samples']), 'INVALID_CODE_SAMPLES')
    return {**clone(q), 'status': 'approved' if q.get('status') == 'approved' else 'candidate'}


def grade(q, answer):
    if q['type'] == 'code':
        return {'status': 'awaiting_review', 'score': None, 'maxScore': 1, 'method': 'code-self-review'}
    maximum = sum(x['points'] for x in q['rubric']) if q['type'] == 'short' else 1
    if answer is None or isinstance(answer, str) and not answer.strip() or isinstance(answer, list) and not answer:
        return {'status': 'unanswered', 'score': None, 'maxScore': maximum}
    kind = q['type']
    if kind == 'short':
        return {'status': 'awaiting_review', 'score': None, 'maxScore': maximum, 'rubric': clone(q['rubric'])}
    if kind == 'single':
        require(type(answer) is int and 0 <= answer < len(q['options']), 'INVALID_RESPONSE')
        correct = answer == q['answer']
    elif kind == 'boolean':
        require(type(answer) is bool, 'INVALID_RESPONSE')
        correct = answer == q['answer']
    elif kind == 'multiple':
        require(
            isinstance(answer, list)
            and all(type(x) is int and 0 <= x < len(q['options']) for x in answer)
            and len(set(answer)) == len(answer),
            'INVALID_RESPONSE',
        )
        correct = set(answer) == set(q['answer'])
    elif kind == 'fill':
        require(
            isinstance(answer, list) and len(answer) == len(q['answers'])
            and all(isinstance(x, str) for x in answer),
            'INVALID_RESPONSE',
        )
        correct = all(any(normalized(a) == normalized(value) for a in accepted) for accepted, value in zip(q['answers'], answer))
    else:
        require(False, 'INVALID_QUESTION')
    return {'status': 'graded', 'score': int(correct), 'maxScore': 1, 'correct': correct, 'method': 'deterministic-v1'}


def review_subjective(q, value):
    require(
        q['type'] == 'short' and value.get('reviewer') and value.get('reason')
        and value.get('sourceVersion') == q['sourceVersion']
        and isinstance(value.get('points'), list)
        and len(value['points']) == len(q['rubric']),
        'INVALID_REVIEW',
    )
    scores = {x['id']: x['score'] for x in value['points']}
    require(
        len(scores) == len(q['rubric'])
        and all(
            finite(scores.get(x['id'])) and 0 <= scores[x['id']] <= x['points']
            for x in q['rubric']
        ),
        'INVALID_REVIEW',
    )
    return {'status': 'graded', 'score': sum(scores.values()), 'maxScore': sum(x['points'] for x in q['rubric']), 'method': 'human-rubric', **{k: clone(value[k]) for k in ('reviewer', 'reason', 'points')}}


def assemble_quiz(questions, options):
    count, course = options.get('count', 5), options['courseId']
    require(type(count) is int and 1 <= count <= 100, 'INVALID_QUIZ_SIZE')
    seen, selected = set(), []
    for q in questions:
        if (
            q['courseId'] != course or q.get('status') != 'approved'
            or q['id'] in options.get('exclude', [])
            or options.get('difficulty') and q.get('difficulty') != options['difficulty']
            or options.get('conceptIds') and not set(q.get('conceptIds', [])) & set(options['conceptIds'])
        ):
            continue
        key = normalized(q['prompt'])
        if key not in seen:
            seen.add(key)
            selected.append(clone(q))
        if len(selected) == count:
            break
    return {'courseId': course, 'questions': selected, 'requested': count, 'available': len(selected), 'complete': len(selected) == count, 'version': fingerprint([[q['id'], q['version']] for q in selected])}


def public_quiz(quiz):
    questions = []
    for q in quiz['questions']:
        row = {k: clone(q[k]) for k in ('id', 'version', 'courseId', 'type', 'prompt')}
        row.update(conceptIds=q.get('conceptIds', []), difficulty=q.get('difficulty'))
        if 'options' in q:
            row['options'] = clone(q['options'])
        if q['type'] == 'fill':
            row['blankCount'] = len(q['answers'])
        if q['type'] == 'short':
            row['maxScore'] = sum(x['points'] for x in q['rubric'])
        questions.append(row)
    return {**{k: quiz[k] for k in ('courseId', 'version', 'requested', 'available', 'complete')}, 'questions': questions}


def attempt_event(q, value):
    require(
        value.get('id') and finite(value.get('elapsedMs', 0))
        and value.get('elapsedMs', 0) >= 0
        and (value.get('confidence') is None or finite(value['confidence']) and 0 <= value['confidence'] <= 1),
        'INVALID_ATTEMPT',
    )
    instant(value.get('createdAt'))
    require(not value.get('gradeOverride'), 'USE_REVIEW_SERVICE')
    return {**{k: q[k] for k in ('courseId', 'sourceId', 'sourceVersion')}, 'questionId': q['id'], 'questionVersion': q['version'],
            'conceptIds': q.get('conceptIds', []), 'id': value['id'], 'answer': clone(value.get('answer')), 'grade': grade(q, value.get('answer')),
            'createdAt': value['createdAt'], 'elapsedMs': value.get('elapsedMs', 0), 'confidence': value.get('confidence'), 'reasoning': str(value.get('reasoning', ''))[:8000]}


def diagnose(event):
    if event['grade']['status'] != 'graded':
        return {'status': 'insufficient', 'causes': [], 'reason': '尚无已核验评分'}
    if event['grade']['score'] == event['grade']['maxScore']:
        return {'status': 'observed', 'causes': [], 'reason': '本次作答通过，不能据此断言完全掌握'}
    return {'status': 'candidate', 'causes': [{'type': 'knowledge-or-response-gap', 'label': '可能存在知识理解或作答偏差', 'evidenceEventId': event['id']}],
            'reason': '已保留解题过程，具体错因需要结合原文或人工核对' if event.get('reasoning') else '仅有答案，不能推断真实思考过程'}
