"""AI analysis accuracy, account isolation and durable jobs; all providers are controlled."""
from datetime import datetime, timezone
import json
import time

import pytest
import httpx
from fastapi.testclient import TestClient

from backend.agent.practice_analysis import build_snapshot, validate_report
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.practice_bank import bank
from backend.xueya.provider import MimoProvider


NOW = datetime(2026, 10, 27, 4, tzinfo=timezone.utc)


def catalog():
    return [{'id': 'fill', 'title': '填空', 'category': 'basic', 'subject': '操作系统', 'type': 'fill',
             'difficulty': '基础', 'tags': ['进程'], 'prompt': '解释进程'},
            {'id': 'code', 'title': '算法', 'category': 'hot100', 'subject': '数据结构与算法', 'type': 'code',
             'difficulty': '简单', 'tags': ['数组']}]


def event(key, action, at, q='fill', **payload):
    return {'id': key, 'questionId': q, 'action': action, 'effectiveAt': at, 'payload': payload}


def result_for(snapshot):
    key = snapshot['questions'][0]['id']
    return {'title': '从练习找到下一步', 'summary': '当前记录较少，建议继续补充练习。',
            'findings': [{'kind': 'weakness', 'title': '优先巩固', 'detail': '根据这道题的实际记录进一步练习。', 'questionIds': [key]}],
            'recommendations': [{'title': '重练并复述', 'reason': '先解释概念，再尝试答题。', 'questionIds': [key]}],
            'limitations': ['记录较少，不据此推断真实能力。']}


def test_snapshot_cst_window_corrections_and_self_report_are_separate():
    events = [event('older', 'answer', '2026-10-19T16:00:00Z', result='wrong'),
              event('edge', 'answer', '2026-10-20T16:00:00Z', result='wrong'),
              event('corr', 'correct', '2026-10-26T16:00:00Z', attemptId='edge'),
              event('corr-again', 'correct', '2026-10-26T16:01:00Z', attemptId='edge'),
              event('self', 'master', '2026-10-26T17:00:00Z', q='code'),
              event('future', 'answer', '2026-10-28T00:00:00Z', result='wrong')]
    snap = build_snapshot(catalog(), events, {'statuses': {'code': {'status': 'mastered'}}}, {'days': 7}, NOW)
    assert snap['stats']['attempts'] == 1
    assert snap['stats']['correct'] == 1
    assert snap['stats']['selfAssessments'] == 1
    assert snap['stats']['practicedQuestions'] == 2
    assert snap['previousPeriod']['attempts'] == 1
    assert snap['previousPeriod']['correct'] == 0
    assert snap['stats']['daily'][0]['date'] == '2026-10-21'
    assert snap['questions'][1]['attempts'] == 0
    assert snap['questions'][1]['selfAssessments'] == 1
    assert snap['questions'][1]['recentActivity'][0]['action'] == 'master'
    assert snap['questions'][0]['previousPeriod']['attempts'] == 1


def test_correction_outside_window_adjusts_original_attempt_not_new_attempt():
    snap = build_snapshot(catalog(), [event('old', 'answer', '2026-10-01T00:00:00Z', result='wrong'),
        event('fix', 'correct', '2026-10-26T00:00:00Z', attemptId='old')], {}, {'days': 7}, NOW)
    assert snap['stats']['attempts'] == 0
    assert snap['stats']['practicedQuestions'] == 0


def test_scope_notes_omission_and_all_history():
    state = {'notes': {'fill': {'text': '<script>override</script>'}}}
    snap = build_snapshot(catalog(), [], state, {'days': 0, 'category': 'basic', 'includeNotes': False}, NOW)
    assert snap['previousPeriod'] is None and snap['start'] is None
    assert [q['id'] for q in snap['questions']] == ['fill']
    assert 'noteExcerpt' not in snap['questions'][0]
    for value in ({'days': True}, {'days': -1}, {'category': 'other'}, {'includeNotes': 'true'}):
        with pytest.raises(Exception):
            build_snapshot(catalog(), [], state, value, NOW)


def test_validation_rejects_unknown_question_and_empty_action():
    snap = build_snapshot(catalog(), [], {}, {}, NOW)
    good = result_for(snap)
    assert validate_report(json.dumps(good), snap)['title'] == good['title']
    good['recommendations'][0]['questionIds'] = ['made-up']
    with pytest.raises(Exception, match='ANALYSIS_INVALID_REFERENCE'):
        validate_report(json.dumps(good), snap)
    good['recommendations'][0]['questionIds'] = []
    with pytest.raises(Exception, match='ANALYSIS_INVALID_REFERENCE'):
        validate_report(json.dumps(good), snap)


class ControlledProvider:
    def __init__(self):
        self.calls = []
        self.fail = False

    async def generate(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.fail:
            raise TimeoutError()
        if kwargs.get('response_format'):
            snapshot = json.loads(messages[1]['content'])
            content = json.dumps(result_for(snapshot), ensure_ascii=False)
        else:
            content = '这份报告的记录较少，请先重练关联题目。'
        return {'content': content, 'model': 'controlled'}


@pytest.fixture
def setup(tmp_path):
    provider = ControlledProvider()
    app = create_app(Config(data_dir=tmp_path / 'data', api_key='controlled', api_slots=1), provider=provider)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        token = client.get('/api/platform/bootstrap').json()['token']
        client.headers['X-Xueya-Token'] = token
        yield app, client, provider


def seed(client, op='answer-one'):
    q = next(q for q in bank()['questions'] if q['type'] == 'single')
    response = client.post('/api/practice/ops', json={'ops': [{'opId': op, 'kind': 'answer', 'questionId': q['id'],
        'payload': {'questionType': 'single', 'result': 'wrong', 'selected': 0}}]}).json()
    assert response['accepted']
    return q


def wait(client, job):
    for _ in range(150):
        row = client.get('/api/practice/analysis/jobs/' + job['id']).json()['job']
        if row['status'] not in ('queued', 'running', 'cancelling'):
            return row
        time.sleep(.02)
    pytest.fail('analysis job did not finish')


def test_report_chat_history_idempotency_and_isolation(setup):
    app, client, provider = setup
    assert client.get('/api/practice/analysis').json()['reports'] == []
    assert not provider.calls
    seed(client)
    request = {'days': 7, 'category': 'basic', 'includeNotes': True, 'idempotencyKey': 'report-one'}
    job = client.post('/api/practice/analysis', json=request).json()['job']
    finished = wait(client, job)
    assert finished['status'] == 'succeeded'
    report_id = finished['result']['reportId']
    seed(client, 'answer-two')
    assert client.post('/api/practice/analysis', json=request).json()['job']['id'] == job['id']
    assert len(provider.calls) == 1
    report = client.get('/api/practice/analysis/reports/' + report_id).json()['report']
    assert report['snapshot']['stats']['attempts'] == 1  # Historical snapshot stays fixed.
    assert app.state.practice_analysis.listing('other')['reports'] == []
    with pytest.raises(Exception, match='ANALYSIS_NOT_FOUND'):
        app.state.practice_analysis.report('other', report_id)
    assert app.state.platform.jobs.get(job['id'], 'practice:other') is None
    chat = client.post('/api/practice/analysis/reports/' + report_id + '/chat',
                       json={'message': '为什么先练这道题？', 'idempotencyKey': 'chat-one'}).json()['job']
    assert wait(client, chat)['status'] == 'succeeded'
    restored = client.get('/api/practice/analysis/reports/' + report_id).json()['report']
    assert len(restored['conversation']) == 2
    assert len(client.get('/api/practice/analysis').json()['reports']) == 1
    assert len(provider.calls) == 2
    assert all(call[1]['scope'].user_id == 'practice:local' for call in provider.calls)


def test_empty_records_and_scope_never_invoke_ai(setup):
    _, client, provider = setup
    response = client.post('/api/practice/analysis', json={'idempotencyKey': 'empty'})
    assert response.json()['error'] == 'ANALYSIS_NO_RECORDS'
    assert not provider.calls
    seed(client)
    assert client.post('/api/practice/analysis', json={'days': 99, 'idempotencyKey': 'bad'}).json()['error'] == 'INVALID_ANALYSIS_RANGE'
    assert not provider.calls


def test_ambiguous_paid_job_never_auto_retries(setup):
    _, client, provider = setup
    seed(client)
    provider.fail = True
    body = {'idempotencyKey': 'timeout'}
    job = client.post('/api/practice/analysis', json=body).json()['job']
    assert wait(client, job)['status'] == 'unknown'
    time.sleep(.4)
    assert len(provider.calls) == 1
    assert client.post('/api/practice/analysis', json=body).json()['job']['id'] == job['id']
    assert client.get('/api/practice/analysis').json()['reports'] == []


def test_token_and_cross_account_history_protected(setup):
    _, client, _ = setup
    response = client.get('/api/practice/analysis', headers={'X-Xueya-Token': 'wrong'})
    assert response.status_code == 403


def test_single_api_slot_uses_host_ledger_and_nonreasoning_transport(tmp_path):
    seen = []
    config = Config(data_dir=tmp_path / 'data', api_key='controlled', api_slots=1, run_model_calls=1)

    def upstream(request):
        payload = json.loads(request.content)
        seen.append(payload)
        assert payload['thinking'] == {'type': 'disabled'}
        assert payload['response_format'] == {'type': 'json_object'}
        content = json.dumps(result_for(json.loads(payload['messages'][1]['content'])))
        return httpx.Response(200, json={'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}],
                                         'usage': {'prompt_tokens': 100, 'completion_tokens': 100}})

    provider = MimoProvider(config, transport=httpx.MockTransport(upstream))
    app = create_app(config, provider=provider)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.headers['X-Xueya-Token'] = client.get('/api/platform/bootstrap').json()['token']
        seed(client)
        job = client.post('/api/practice/analysis', json={'idempotencyKey': 'ledger'}).json()['job']
        assert wait(client, job)['status'] == 'succeeded'
        rows = app.state.platform.db.all('SELECT user_id,course_id,status FROM invocations')
        assert rows == [{'user_id': 'practice:local', 'course_id': 'practice-global', 'status': 'succeeded'}]
        context = app.state.platform.db.one("SELECT value FROM meta WHERE key LIKE 'invocation-context:%'")
        assert json.loads(context['value'])['jobId'] == job['id']
        assert len(seen) == 1


def test_history_survives_service_restart(tmp_path):
    config = Config(data_dir=tmp_path / 'restart-data', api_key='controlled')
    first_provider = ControlledProvider()
    with TestClient(create_app(config, provider=first_provider), base_url='http://127.0.0.1') as client:
        client.headers['X-Xueya-Token'] = client.get('/api/platform/bootstrap').json()['token']
        seed(client)
        job = client.post('/api/practice/analysis', json={'idempotencyKey': 'persist'}).json()['job']
        report_id = wait(client, job)['result']['reportId']
    second_provider = ControlledProvider()
    with TestClient(create_app(config, provider=second_provider), base_url='http://127.0.0.1') as client:
        client.headers['X-Xueya-Token'] = client.get('/api/platform/bootstrap').json()['token']
        report = client.get('/api/practice/analysis/reports/' + report_id).json()['report']
        assert report['snapshot']['stats']['attempts'] == 1
        assert len(client.get('/api/practice/analysis').json()['reports']) == 1
        assert not second_provider.calls


def test_active_job_guard_and_changed_idempotency_request(tmp_path):
    provider = ControlledProvider()
    app = create_app(Config(data_dir=tmp_path / 'data', api_key='controlled'), provider=provider, start_jobs=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.headers['X-Xueya-Token'] = client.get('/api/platform/bootstrap').json()['token']
        seed(client)
        body = {'idempotencyKey': 'pending-key'}
        job = client.post('/api/practice/analysis', json=body).json()['job']
        assert job['status'] == 'queued'
        assert client.post('/api/practice/analysis', json=body).json()['job']['id'] == job['id']
        assert client.post('/api/practice/analysis', json={**body, 'days': 30}).json()['error'] == 'IDEMPOTENCY_CONFLICT'
        assert client.post('/api/practice/analysis', json={'idempotencyKey': 'second-key'}).json()['error'] == 'ANALYSIS_BUSY'
        assert not provider.calls
