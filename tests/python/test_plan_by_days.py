"""Day-based scheduling: complete coverage, dependencies and map compatibility."""
import json

import pytest

from backend.xueya.common import AppError
from backend.xueya.learning_map import build_tree, mm_bytes, xmind_bytes
from backend.xueya.space_planning import ConversationPlanning
from backend.xueya.study_space_service import StudySpaceService


def tasks():
    return [{'key': f't{i}', 'title': f'学习任务{i+1}', 'minutes': 60,
             'phase': f'阶段{i//5+1}', 'dependsOn': [f't{i-1}'] if i else []}
            for i in range(20)]


def conditions(**extra):
    return {'title': '按天数复习', 'goal': '学习基础知识', 'difficulty': '基础',
            'startDate': '2026-11-14', 'daysCount': 14, 'restDays': [7],
            'schedulingMode': 'by-days', **extra}


def test_all_tasks_fit_days_without_splitting_or_losing_dependencies_and_map(platform):
    service = StudySpaceService(platform)
    plan = service.create_plan_draft('alice', conditions(tasks=list(reversed(tasks()))))
    study = [d for d in plan['days'] if not d['isRestDay']]
    rows = [t for d in plan['days'] for t in d['tasks']]
    assert len(study) == 12 and len(rows) == 20 and not plan['remaining']
    assert max(len(d['tasks']) for d in study) - min(len(d['tasks']) for d in study) <= 1
    assert [t['title'] for t in rows] == [t['title'] for t in tasks()]
    assert len({t['id'] for t in rows}) == 20
    assert sum(t['minutes'] for t in rows) == 1200 and plan['dailyMinutes'] == 100
    assert all(not d['tasks'] and not d['budgetMinutes'] for d in plan['days'] if d['isRestDay'])
    assert all(d['budgetMinutes'] == sum(t['minutes'] for t in d['tasks']) for d in study)
    tree = build_tree(plan, source='plan')
    assert tree['stats']['tasks'] == 20 and tree['stats']['phases'] == 4
    assert '按可学习天数' in json.dumps(tree, ensure_ascii=False)
    assert xmind_bytes(tree).startswith(b'PK')
    assert '学习任务20' in mm_bytes(tree).decode('utf-8')


def test_fewer_days_put_more_complete_tasks_in_each_day(platform):
    service = StudySpaceService(platform)
    short = service.create_plan_draft('alice', conditions(tasks=tasks(), daysCount=2, restDays=[]))
    long = service.create_plan_draft('alice', conditions(tasks=tasks(), daysCount=10, restDays=[]))
    assert [len(d['tasks']) for d in short['days']] == [10, 10]
    assert [len(d['tasks']) for d in long['days']] == [2] * 10
    assert short['dailyMinutes'] == 600 and not short['remaining']


def test_fixed_budget_api_remains_compatible(platform):
    data = conditions(tasks=tasks(), dailyMinutes=60)
    data.pop('schedulingMode')
    plan = StudySpaceService(platform).create_plan_draft('alice', data)
    assert len(plan['remaining']) == 8
    assert sum(len(d['tasks']) for d in plan['days']) == 12


async def test_model_sees_days_without_an_invented_time_budget(platform):
    class Model:
        calls = []
        async def generate(self, messages, **kwargs):
            self.calls.append(messages)
            return {'content': json.dumps({'explanation': '按目标拆分任务', 'tasks': tasks()})}
    model = Model()
    plan = await StudySpaceService(platform).generate_model_plan('alice', model, conditions(dailyMinutes=60))
    payload = json.loads(model.calls[0][-1]['content'])
    assert payload['schedulingMode'] == 'by-days' and payload['availableStudyDays'] == 12
    assert 'dailyMinutes' not in payload and 'availableStudyMinutes' not in payload
    assert not plan['remaining'] and sum(len(d['tasks']) for d in plan['days']) == 20


async def test_no_study_days_rejected_before_model_call(platform):
    class NeverModel:
        async def generate(self, *args, **kwargs):
            pytest.fail('Invalid dates must not invoke a provider')
    with pytest.raises(AppError, match='NO_STUDY_DAYS'):
        await StudySpaceService(platform).generate_model_plan('alice', NeverModel(), conditions(restDays=list(range(1, 8))))
    ConversationPlanning.validate(conditions())
    with pytest.raises(AppError, match='NO_STUDY_DAYS'):
        ConversationPlanning.validate(conditions(restDays=list(range(1, 8))))
