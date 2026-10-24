"""测验提交的顺序、快照、幂等与校验优先级特征测试。"""
import pytest

from backend.agent.learning_service import LearningService
from backend.core import DomainError, clone

NOW = '2026-10-25T01:02:03Z'


@pytest.fixture
async def quiz_context(repository, course):
    service = LearningService(repository, clock=lambda: NOW)
    draft = await service.preview_quiz({**course, 'id': 'quiz', 'count': 3})
    saved = await service.artifacts.adopt(draft, {'confirmed': True, 'operationId': 'save-quiz'})
    value = {'courseId': course['courseId'], 'id': 'attempt', 'quizId': 'quiz',
             'quizRevision': saved['revision'], 'responses': []}
    return service, value, saved['content']['questions']


@pytest.mark.parametrize('respond', [False, True])
async def test_events_follow_quiz_order_and_preserve_unanswered_questions(quiz_context, repository, respond):
    service, value, questions = quiz_context
    if respond:
        value['responses'] = [
            {'questionId': questions[2]['id'], 'answer': 0, 'confidence': 0.8, 'elapsedMs': 12},
            {'questionId': questions[0]['id'], 'answer': 1, 'reasoning': '我的依据'},
        ]
    original = clone(value)
    result = await service.submit_quiz(value)
    events = result['content']['events']
    assert [e['questionId'] for e in events] == [q['id'] for q in questions]
    assert [e['answer'] for e in events] == ([1, None, 0] if respond else [None, None, None])
    assert [e['grade']['status'] for e in events] == (
        ['graded', 'unanswered', 'graded'] if respond else ['unanswered'] * 3
    )
    assert [e['grade']['score'] for e in events] == ([0, None, 1] if respond else [None] * 3)
    assert all(e['createdAt'] == NOW for e in events)
    assert len({e['id'] for e in events}) == 3
    assert result['content']['questionSnapshots'] == questions
    assert result['revision'] == 1 and result['updatedAt'] == NOW and result['kind'] == 'attempt'
    assert [d['eventId'] for d in result['content']['diagnoses']] == [e['id'] for e in events]
    assert result == await repository.get(value['courseId'], value['id'])
    assert len(repository.history) == 2
    assert value == original
    questions[0]['prompt'] = '之后修改题干'
    assert result['content']['questionSnapshots'][0]['prompt'] != questions[0]['prompt']


async def test_replay_returns_original_attempt_even_after_quiz_is_removed(quiz_context, repository):
    service, value, _ = quiz_context
    first = await service.submit_quiz(value)
    repository.rows.pop((value['courseId'], value['quizId']))
    assert await service.submit_quiz(value) == first
    assert len(repository.history) == 2
    with pytest.raises(DomainError, match='^IDEMPOTENCY_CONFLICT$'):
        await service.submit_quiz({**value, 'quizRevision': 2})
    assert len(repository.history) == 2


@pytest.mark.parametrize('responses', [
    [{'questionId': 'missing', 'answer': 0}],
    [{'questionId': 'old-node-0', 'answer': 0}, {'questionId': 'old-node-0', 'answer': 1}],
    [{'answer': 0}],
])
async def test_invalid_question_ids_do_not_write_attempts(quiz_context, repository, responses):
    service, value, _ = quiz_context
    with pytest.raises(DomainError, match='^INVALID_SUBMISSION$'):
        await service.submit_quiz({**value, 'responses': responses})
    assert await repository.get(value['courseId'], 'attempt') is None
    assert len(repository.history) == 1


@pytest.mark.parametrize('patch', [
    {'id': ''}, {'id': ' '}, {'id': 'x' * 161}, {'quizRevision': True},
    {'quizRevision': 0}, {'responses': {}},
])
async def test_submission_shape_is_checked_before_quiz_lookup(quiz_context, patch):
    service, value, _ = quiz_context
    with pytest.raises(DomainError, match='^INVALID_SUBMISSION$'):
        await service.submit_quiz({**value, 'quizId': 'missing', **patch})


async def test_quiz_revision_precedes_response_membership_validation(quiz_context):
    service, value, _ = quiz_context
    with pytest.raises(DomainError, match='^QUIZ_VERSION_CONFLICT$'):
        await service.submit_quiz({**value, 'quizRevision': 2, 'responses': [{'questionId': 'missing'}]})


async def test_other_course_cannot_load_quiz(quiz_context):
    service, value, _ = quiz_context
    with pytest.raises(DomainError, match='^ARTIFACT_NOT_FOUND$'):
        await service.submit_quiz({**value, 'courseId': 'other'})


async def test_subjective_correction_uses_attempt_snapshot(quiz_context, repository):
    service, value, _ = quiz_context
    quiz = repository.rows[(value['courseId'], value['quizId'])]
    question = quiz['content']['questions'][0]
    question.update(type='short', rubric=[{'id': 'r', 'description': '评分依据', 'points': 2}])
    value['responses'] = [{'questionId': question['id'], 'answer': '我的回答'}]
    attempt = await service.submit_quiz(value)
    assert attempt['content']['events'][0]['grade']['status'] == 'awaiting_review'
    question['rubric'][0]['points'] = 100
    corrected = await service.correct_subjective({
        'courseId': value['courseId'], 'attemptId': value['id'], 'questionId': question['id'],
        'expectedRevision': 1, 'operationId': 'review',
        'review': {'sourceVersion': question['sourceVersion'], 'reviewer': 'learner', 'reason': '按原量规',
                   'points': [{'id': 'r', 'score': 1}]},
    })
    grade = corrected['content']['events'][0]['grade']
    assert (grade['score'], grade['maxScore']) == (1, 2)
    assert corrected['content']['questionSnapshots'][0]['rubric'][0]['points'] == 2


async def test_legacy_non_string_question_id_can_still_be_left_unanswered(quiz_context, repository):
    service, value, _ = quiz_context
    questions = repository.rows[(value['courseId'], value['quizId'])]['content']['questions']
    # 当前领域校验只要求 ID 为真值；历史列表 ID 的缺答行为也不能在重构中改变。
    questions[0]['id'] = ['legacy-id']
    value['responses'] = [{'questionId': questions[1]['id'], 'answer': 0}]
    attempt = await service.submit_quiz(value)
    assert attempt['content']['events'][0]['questionId'] == ['legacy-id']
    assert attempt['content']['events'][0]['grade']['status'] == 'unanswered'
    assert attempt['content']['events'][1]['grade']['score'] == 1
