"""测评边界的特征测试：锁定当前判分、筛选与错误优先级。"""
import pytest

from backend.agent.assessment import (
    assemble_quiz, grade, public_quiz, review_subjective, validate_question,
)
from backend.core import DomainError, clone


@pytest.mark.parametrize(('fields', 'answer', 'expected'), [
    ({'type': 'single', 'options': ['甲', '乙'], 'answer': 1}, 1, 1),
    ({'type': 'multiple', 'options': ['甲', '乙', '丙'], 'answer': [0, 2]}, [2, 0], 1),
    ({'type': 'multiple', 'options': ['甲', '乙', '丙'], 'answer': [0, 2]}, [0], 0),
    ({'type': 'boolean', 'answer': False}, False, 1),
    ({'type': 'fill', 'answers': [['Ａ B', '别名'], ['答案']]}, ['a  b', '答案'], 1),
    ({'type': 'fill', 'answers': [['甲']]}, ['乙'], 0),
])
def test_question_types_keep_grades_and_do_not_mutate_input(course, fields, answer, expected):
    question = {**course['questions'][0], **fields}
    original = clone(question)
    validated = validate_question(question, course['sources'])
    assert grade(validated, answer) == {
        'status': 'graded', 'score': expected, 'maxScore': 1,
        'correct': bool(expected), 'method': 'deterministic-v1',
    }
    assert question == original
    if 'options' in validated:
        validated['options'].append('额外选项')
        assert question == original


@pytest.mark.parametrize('answer', [None, '', ' \n ', []])
def test_unanswered_precedes_response_type_validation(course, answer):
    assert grade(course['questions'][0], answer) == {
        'status': 'unanswered', 'score': None, 'maxScore': 1,
    }


@pytest.mark.parametrize(('patch', 'code'), [
    ({'prompt': '', 'evidenceQuote': ''}, 'INVALID_QUESTION'),
    ({'evidenceQuote': '', 'options': []}, 'INVALID_QUESTION_EVIDENCE'),
    ({'options': ['Ａ', 'a'], 'answer': -1}, 'INVALID_OPTIONS'),
    ({'options': ['甲', '乙'], 'answer': True}, 'INVALID_ANSWER'),
    ({'type': 'multiple', 'options': ['甲', '乙'], 'answer': [0, 0]}, 'INVALID_ANSWER'),
    ({'type': 'boolean', 'answer': 0}, 'INVALID_ANSWER'),
    ({'type': 'fill', 'answers': [[]]}, 'INVALID_ANSWER'),
    ({'type': 'short', 'rubric': [{'id': 'r', 'description': '要点', 'points': True}]}, 'INVALID_RUBRIC'),
    ({'type': 'short', 'rubric': [
        {'id': 'r', 'description': '甲', 'points': 1},
        {'id': 'r', 'description': '乙', 'points': 1},
    ]}, 'INVALID_RUBRIC'),
])
def test_validation_keeps_error_priority(course, patch, code):
    with pytest.raises(DomainError, match=f'^{code}$'):
        validate_question({**course['questions'][0], **patch}, course['sources'])


@pytest.mark.parametrize('status', [None, 'candidate', 'rejected', 'approved'])
def test_only_explicit_approval_survives_validation(course, status):
    result = validate_question({**course['questions'][0], 'status': status}, course['sources'])
    assert result['status'] == ('approved' if status == 'approved' else 'candidate')


def test_quiz_filtering_deduplication_and_public_answer_hiding(course):
    base = {**course['questions'][0], 'status': 'approved', 'difficulty': 'easy', 'conceptIds': ['node']}
    questions = [
        {**base, 'id': 'foreign', 'courseId': 'other'},
        {**base, 'id': 'pending', 'status': 'candidate'},
        {**base, 'id': 'excluded'},
        {**base, 'id': 'hard', 'difficulty': 'hard'},
        {**base, 'id': 'other-concept', 'conceptIds': ['tree']},
        {**base, 'id': 'first', 'prompt': 'Ａ  B'},
        {**base, 'id': 'duplicate', 'prompt': 'a b'},
        {**base, 'id': 'second', 'prompt': '另一个问题'},
    ]
    original = clone(questions)
    quiz = assemble_quiz(questions, {
        'courseId': course['courseId'], 'count': 3, 'exclude': ['excluded'],
        'difficulty': 'easy', 'conceptIds': ['node'],
    })
    assert [q['id'] for q in quiz['questions']] == ['first', 'second']
    assert (quiz['requested'], quiz['available'], quiz['complete']) == (3, 2, False)
    public = public_quiz(quiz)
    assert all(set(q) == {'id', 'version', 'courseId', 'type', 'prompt', 'conceptIds', 'difficulty', 'options'}
               for q in public['questions'])
    quiz['questions'][0]['options'].append('新增')
    assert questions == original
    assert len(public['questions'][0]['options']) == len(base['options'])


def test_subjective_rubric_totals_and_review_order(course):
    question = {**course['questions'][0], 'type': 'short', 'rubric': [
        {'id': 'a', 'description': '概念', 'points': 2},
        {'id': 'b', 'description': '依据', 'points': 3},
    ]}
    assert grade(question, None) == {'status': 'unanswered', 'score': None, 'maxScore': 5}
    pending = grade(question, '作答')
    assert pending == {'status': 'awaiting_review', 'score': None, 'maxScore': 5, 'rubric': question['rubric']}
    review = {'reviewer': 'learner', 'reason': '核对原文', 'sourceVersion': question['sourceVersion'],
              'points': [{'id': 'b', 'score': 1.5}, {'id': 'a', 'score': 2}]}
    result = review_subjective(question, review)
    assert (result['score'], result['maxScore'], result['method']) == (3.5, 5, 'human-rubric')
    assert result['points'] == review['points']
    result['points'][0]['score'] = 0
    assert review['points'][0]['score'] == 1.5
