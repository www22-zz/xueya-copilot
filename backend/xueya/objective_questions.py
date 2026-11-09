"""Validated objective answer formats shared by generated questions and attempts."""
import unicodedata
from .common import require

TYPES = ('single', 'multiple', 'boolean', 'fill')


def validate(question):
    kind = question['type']
    answer = question.get('answer')
    if kind in ('single', 'multiple'):
        options = question.get('options')
        require(isinstance(options, list) and 2 <= len(options) <= 6
                and all(isinstance(x, str) and x.strip() for x in options)
                and len(set(options)) == len(options), 'AI_INVALID_RESPONSE')
        if kind == 'single':
            require(type(answer) is int and 0 <= answer < len(options), 'AI_INVALID_RESPONSE')
        else:
            require(isinstance(answer, list) and len(answer) >= 2
                    and all(type(x) is int and 0 <= x < len(options) for x in answer)
                    and len(set(answer)) == len(answer), 'AI_INVALID_RESPONSE')
    elif kind == 'boolean':
        require(type(answer) is bool, 'AI_INVALID_RESPONSE')
    elif kind == 'fill':
        require(isinstance(answer, list) and 1 <= len(answer) <= 10
                and all(isinstance(x, list) and 1 <= len(x) <= 10
                        and all(isinstance(s, str) and 0 < len(s.strip()) <= 500 for s in x) for x in answer),
                'AI_INVALID_RESPONSE')
        require(question['prompt'].count('____') == len(answer), 'AI_INVALID_RESPONSE')


def normalized(value):
    # Preserve case and internal whitespace: code, formulas and units are case-sensitive.
    return unicodedata.normalize('NFC', value).strip()


def grade(question, answer):
    validate(question)
    kind = question['type']
    expected = question['answer']
    if kind == 'single':
        require(type(answer) is int and 0 <= answer < len(question['options']), 'INVALID_ANSWER')
        correct = answer == expected
    elif kind == 'multiple':
        require(isinstance(answer, list) and 0 < len(answer) <= len(question['options'])
                and all(type(x) is int and 0 <= x < len(question['options']) for x in answer), 'INVALID_ANSWER')
        require(len(set(answer)) == len(answer), 'INVALID_ANSWER')
        correct = set(answer) == set(expected)
    elif kind == 'boolean':
        require(type(answer) is bool, 'INVALID_ANSWER')
        correct = answer == expected
    else:
        require(isinstance(answer, list) and len(answer) == len(expected)
                and all(isinstance(x, str) and 0 < len(x.strip()) <= 500 for x in answer), 'INVALID_ANSWER')
        correct = all(normalized(a) in [normalized(x) for x in choices] for a, choices in zip(answer, expected))
        if not correct:
            return {'status': 'pending-review', 'userAnswer': answer,
                    'feedback': '答案未匹配保存的标准形式，待复核；不自动记零分或判错。',
                    'method': 'exact-answer-v1', 'explanation': question.get('explanation', '')}
    return {'status': 'graded', 'correct': correct, 'score': int(correct), 'maxScore': 1,
            'correctAnswer': expected, 'userAnswer': answer, 'explanation': question.get('explanation', ''),
            'method': 'deterministic-v1'}
