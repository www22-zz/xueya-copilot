"""锁定减少嵌套前的计划动作和运行恢复行为。"""
import pytest

from backend.agent.planning import revise_plan
from backend.agent.run_service import RunService
from backend.core import DomainError, clone


@pytest.fixture
def saved_plan():
    return {
        'courseId': 'c', 'examDate': '2026-10-30', 'minutes': 25,
        'days': [
            {'date': '2026-10-25', 'tasks': [{'id': 't', 'part': 1, 'minutes': 5}]},
            {'date': '2026-10-26', 'tasks': [{'id': 't', 'part': 2, 'minutes': 10}]},
            {'date': '2026-10-27', 'tasks': [{'id': 'u', 'minutes': 20}]},
        ],
        'completed': [], 'skipped': [],
    }


@pytest.mark.parametrize('action', ['complete', 'skip'])
def test_finished_plan_action_keeps_other_parts_and_ignores_postpone_date(saved_plan, action):
    before = clone(saved_plan)
    result = revise_plan(saved_plan, {'action': action, 'taskId': 't', 'part': 2, 'date': 'invalid'})
    assert result['days'][0] == before['days'][0]
    assert result['days'][1]['tasks'] == []
    assert result['days'][2] == before['days'][2]
    recorded = 'completed' if action == 'complete' else 'skipped'
    other = 'skipped' if action == 'complete' else 'completed'
    assert result[recorded] == [{'id': 't', 'part': 2, 'minutes': 10, 'date': '2026-10-26'}]
    assert result[other] == []
    assert result['status'] == 'preview' and result['requiresConfirmation'] is True
    assert saved_plan == before


def test_postpone_creates_target_day_and_preserves_empty_source_day(saved_plan):
    before = clone(saved_plan)
    result = revise_plan(saved_plan, {'action': 'postpone', 'taskId': 'u', 'date': '2026-10-29'})
    assert [day['date'] for day in result['days']] == ['2026-10-25', '2026-10-26', '2026-10-27', '2026-10-29']
    assert result['days'][2]['tasks'] == []
    assert result['days'][3]['tasks'] == [{'id': 'u', 'minutes': 20}]
    assert result['completed'] == [] and result['skipped'] == []
    assert result['status'] == 'preview' and result['requiresConfirmation'] is True
    assert saved_plan == before


@pytest.mark.parametrize(('change', 'code'), [
    ({'action': 'unknown', 'taskId': 'missing'}, 'INVALID_PLAN_ACTION'),
    ({'action': 'postpone', 'taskId': 'missing', 'date': 'bad'}, 'PLAN_TASK_NOT_FOUND'),
    ({'action': 'postpone', 'taskId': 't', 'date': '2026-10-24'}, 'INVALID_POSTPONE_DATE'),
    ({'action': 'postpone', 'taskId': 't', 'date': '2026-10-28'}, 'PLAN_ORDER_REQUIRES_REBUILD'),
    ({'action': 'postpone', 'taskId': 't', 'part': 2, 'date': '2026-10-27'}, 'PLAN_DAILY_BUDGET'),
])
def test_plan_errors_keep_priority_and_do_not_mutate_input(saved_plan, change, code):
    before = clone(saved_plan)
    with pytest.raises(DomainError, match=f'^{code}$'):
        revise_plan(saved_plan, change)
    assert saved_plan == before


@pytest.fixture
async def waiting_run(repository):
    service = RunService(repository, {'step': lambda step: None}, lambda course, snapshot: True, clock=lambda: 10)
    run = await service.create({
        'courseId': 'c', 'id': 'r', 'input': {}, 'snapshot': 'v1',
        'steps': [{'id': key, 'type': 'step', 'effect': 'read'} for key in ['done', 'waiting', 'later']],
    })
    run.update(status='failed', waitingStep='waiting', prompt='旧问题', error={'code': 'OLD_ERROR'})
    run['steps'][0].update(status='completed', output={'kept': True})
    run['steps'][1]['status'] = 'running'
    repository.rows['c', 'r'] = clone(run)
    return service, run


@pytest.mark.parametrize(('status', 'options'), [
    ('failed', {}),
    ('unknown', {'acknowledgeUnknown': True}),
    ('awaiting_confirmation', {'confirmation': True}),
    ('awaiting_user', {'userInput': None}),
    ('awaiting_user', {'userInput': {'answer': ['内容']}, 'confirmation': True}),
])
async def test_resume_only_patches_waiting_unfinished_step(waiting_run, repository, status, options):
    service, run = waiting_run
    run['status'] = status
    repository.rows['c', 'r'] = clone(run)
    result = await service.resume('c', 'r', {'revision': run['revision'], **options})
    assert result['status'] == 'queued' and result['revision'] == run['revision'] + 1
    assert result['steps'][0] == run['steps'][0]
    assert [step['status'] for step in result['steps']] == ['completed', 'pending', 'pending']
    assert 'confirmed' not in result['steps'][2] and 'userInput' not in result['steps'][2]
    if options.get('confirmation') is True:
        assert result['steps'][1]['confirmed'] is True
    if 'userInput' in options:
        assert result['steps'][1]['userInput'] == options['userInput']
        if isinstance(options['userInput'], dict):
            options['userInput']['answer'].append('修改调用方输入')
            assert result['steps'][1]['userInput']['answer'] == ['内容']
    assert result['error'] is None and result['waitingStep'] is None and result['prompt'] is None
    assert repository.rows['c', 'r'] == result


@pytest.mark.parametrize(('status', 'options', 'code'), [
    ('unknown', {}, 'UNKNOWN_OUTCOME_REQUIRES_REVIEW'),
    ('awaiting_confirmation', {}, 'CONFIRMATION_REQUIRED'),
    ('awaiting_user', {}, 'USER_INPUT_REQUIRED'),
    ('awaiting_user', {'revision': 99}, 'RUN_CONFLICT'),
])
async def test_resume_rejection_preserves_stored_steps(waiting_run, repository, status, options, code):
    service, run = waiting_run
    run['status'] = status
    repository.rows['c', 'r'] = clone(run)
    with pytest.raises(DomainError, match=f'^{code}$'):
        await service.resume('c', 'r', {'revision': run['revision'], **options})
    assert repository.rows['c', 'r'] == run
