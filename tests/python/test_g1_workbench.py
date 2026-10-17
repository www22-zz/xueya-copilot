import json


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
