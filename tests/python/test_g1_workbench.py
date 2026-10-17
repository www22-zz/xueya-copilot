import json
import time
from dataclasses import replace
import httpx
from backend.xueya.provider import MimoProvider


def test_capability_status_and_local_check_never_echo_credentials(client):
    headers = client.platform_headers
    assert client.get('/api/platform/workbench/capabilities').status_code == 403
    response = client.get('/api/platform/workbench/capabilities', headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data['capabilities']) == 7
    assert all(not c['connectionVerified'] for c in data['capabilities'])
    assert not data['paidTestsEnabled']
    check = client.post('/api/platform/workbench/check', headers=headers, json={'mode': 'local'})
    assert check.json()['networkRequests'] == 0
    assert not check.json()['connectionVerified']
    assert client.post('/api/platform/workbench/check', headers=headers, json={'mode': 'paid'}).status_code == 403


def test_task_projection_scope_redaction_unknown_and_safe_retry(client):
    p, headers = client.platform, client.platform_headers
    async def handler(*args, **kwargs):
        return {}
    if 'parse-document' not in p.jobs.handlers:
        p.jobs.register('parse-document', handler)
    for course in ['course-default', 'other']:
        p.repo.ensure_course(p.user_id, {'id': course, 'name': course})
    job = p.jobs.submit(p.user_id, {'type': 'parse-document', 'courseId': 'course-default', 'idempotencyKey': 'cpu', 'resource': 'cpu'})
    other = p.jobs.submit(p.user_id, {'type': 'parse-document', 'courseId': 'other', 'idempotencyKey': 'api', 'resource': 'api'})
    p.db.execute("UPDATE jobs SET status='unknown',error=? WHERE id=?", ('private-secret-body', other['id']))
    result = client.get('/api/platform/workbench/tasks', headers=headers).json()
    assert {j['id'] for j in result['tasks']} == {job['id']}
    result = client.get('/api/platform/workbench/tasks?scope=all', headers=headers).json()
    assert len(result['tasks']) == 2
    assert 'private-secret-body' not in json.dumps(result)
    assert not next(j for j in result['tasks'] if j['id'] == other['id'])['canRetry']
    assert client.post('/api/platform/workbench/task-action', headers=headers, json={'id': other['id'], 'courseId': 'other', 'action': 'retry'}).status_code == 400
    assert client.post('/api/platform/workbench/task-action', headers=headers, json={'id': other['id'], 'action': 'cancel'}).status_code == 404
    assert client.post('/api/platform/workbench/task-action', headers=headers, json={'id': job['id'], 'action': 'cancel'}).json()['status'] == 'cancelled'
    assert client.post('/api/platform/workbench/task-action', headers=headers, json={'id': job['id'], 'action': 'retry'}).json()['status'] == 'queued'


def test_actual_ledger_context_links_job_and_verifies_only_matching_capability(client):
    p, headers = client.platform, client.platform_headers
    config = replace(client.app.state.config, api_key='controlled-private-credential', base_url='https://controlled.invalid/v1')
    client.app.state.config = config
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'choices': [{'message': {'content': 'ok'}}], 'usage': {'prompt_tokens': 3, 'completion_tokens': 1}}))
    provider = MimoProvider(config, p, transport=transport)
    async def handler(scope, args, **callbacks):
        await provider.generate([{'role': 'user', 'content': 'controlled fixture'}], scope=scope)
        return {'completed': True}
    p.jobs.register('g1-model-test', handler)
    job = p.jobs.submit(p.user_id, {'type': 'g1-model-test', 'courseId': 'course-default', 'idempotencyKey': 'model-job', 'maxAttempts': 1})
    for _ in range(100):
        data = client.get('/api/platform/workbench/tasks', headers=headers).json()
        if data['invocations'] and data['invocations'][0]['status'] == 'succeeded':
            break
        time.sleep(.03)
    call = data['invocations'][0]
    assert call['jobId'] == job['id'] and call['capability'] == 'text'
    assert call['usage']['prompt_tokens'] == 3
    assert next(t for t in data['tasks'] if t['id'] == job['id'])['invocationIds'] == [call['id']]
    capabilities = client.get('/api/platform/workbench/capabilities', headers=headers).json()['capabilities']
    assert next(c for c in capabilities if c['id'] == 'text')['connectionVerified']
    assert not next(c for c in capabilities if c['id'] == 'image')['connectionVerified']
    assert config.api_key not in json.dumps(data)+json.dumps(capabilities)
    client.app.state.config = replace(config, api_key='changed-controlled-credential')
    capabilities = client.get('/api/platform/workbench/capabilities', headers=headers).json()['capabilities']
    assert not next(c for c in capabilities if c['id'] == 'text')['connectionVerified']
