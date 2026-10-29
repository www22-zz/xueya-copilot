"""Document -> durable batches -> 100+100 -> answering. Controlled models only."""
import json
import time
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from backend.xueya.app import create_app
from backend.xueya.config import Config


@pytest.fixture(autouse=True)
def controlled_legacy_compatibility(monkeypatch):
    """Exercise the retained legacy engine explicitly; production defaults off."""
    import functools
    from backend.xueya import practice_generation
    original = practice_generation.PracticeGeneration
    monkeypatch.setattr(practice_generation,'PracticeGeneration',functools.partial(original,legacy_enabled=True))


MATERIAL = '\n'.join(f'第{i}节：植物通过光合作用将光能转化为化学能，叶绿体是主要场所；细胞呼吸分解有机物释放能量。' for i in range(80))


class Model:
    def __init__(self, fail_at=None, corrupt=None):
        self.calls = 0
        self.fail_at = fail_at
        self.corrupt = corrupt

    async def generate(self, messages, **kwargs):
        self.calls += 1
        if self.calls == self.fail_at:
            raise TimeoutError()
        args = json.loads(messages[-1]['content'])
        source = args['materials'][0]
        kind = args['types'][0]
        questions = []
        for i in range(args['count']):
            q = {'type': kind, 'prompt': f'第{self.calls}组第{i}题：分析资料中的知识及应用条件。',
                 'explanation': '依据所引原文核对定义和应用条件。', 'evidenceQuote': source['quote'][:80],
                 'sourceId': source['id'], 'conceptIds': [], 'difficulty': 'easy'}
            if kind == 'single':
                q.update(options=['甲', '乙', '丙', '丁'], answer=0)
            elif kind == 'multiple':
                q.update(options=['甲', '乙', '丙', '丁'], answer=[0, 2])
            elif kind == 'boolean':
                q['answer'] = True
            elif kind == 'fill':
                q['answers'] = [['叶绿体', 'chloroplast']]
            else:
                q.update(solutions={'python': 'def solve(x):\n    return x'}, samples=[{'input': '1', 'output': '1'}])
            if self.corrupt == 'evidence':
                q['evidenceQuote'] = '不存在的逐字依据'
            if self.corrupt == 'duplicate':
                q['prompt'] = '完全重复的题干'
            questions.append(q)
        return {'content': json.dumps({'questions': questions}, ensure_ascii=False), 'model': 'controlled'}


def wait_for(client, headers, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get('/api/practice/bank?courseId=course-default', headers=headers)
        assert response.status_code == 200, response.text
        value = response.json()
        if predicate(value):
            return value
        time.sleep(.03)
    raise AssertionError(value)


def upload(client, headers, material=MATERIAL, name='生物学.md'):
    response = client.post('/api/platform/knowledge/upload?courseId=course-default&name='+name,
                           headers={**headers, 'Idempotency-Key': 'material-one'}, content=material.encode())
    assert response.status_code == 200, response.text
    return response.json()


def token(client):
    return {'X-Xueya-Token': client.get('/api/platform/bootstrap').json()['token']}


def test_upload_generates_100_hot_and_100_basic_and_can_answer(tmp_path):
    model = Model()
    app = create_app(Config(data_dir=tmp_path, api_key='controlled'), provider=model)
    with TestClient(app, base_url='http://localhost') as client:
        headers = token(client)
        uploaded = upload(client, headers)
        value = wait_for(client, headers, lambda v: len(v['questions']) == 200)
        assert model.calls == 40
        assert Counter(q['category'] for q in value['questions']) == {'hot100': 100, 'basic': 100}
        assert Counter(q['type'] for q in value['questions']) == {'single': 50, 'multiple': 50, 'boolean': 50, 'fill': 50}
        assert len({q['prompt'] for q in value['questions']}) == 200
        assert all(q['evidenceQuote'] in MATERIAL and q['documentId'] == uploaded['documentId'] for q in value['questions'])
        assert all(q['quality']['answerSupport'] == 'pending' for q in value['questions'])
        upload(client, headers)
        time.sleep(.15)
        assert model.calls == 40
        q = next(q for q in value['questions'] if q['type'] == 'multiple')
        result = client.post('/api/practice/ops', headers=headers, json={'ops': [
            {'opId': 'answer-generated', 'kind': 'answer', 'questionId': q['id'],
             'payload': {'questionType': 'multiple', 'result': 'wrong', 'selected': [0]}}]}).json()
        assert result['accepted'] == ['answer-generated']
        assert result['statuses'][q['id']]['status'] == 'wrong'
        assert client.get('/api/practice/bank', headers=headers).json()['questions']  # legacy clients still work
        client.post('/api/platform/courses', headers=headers, json={'id':'other-course','name':'其他课程'})
        assert client.get('/api/practice/bank?courseId=other-course', headers=headers).json()['questions'] == []
        assert app.state.practice_generation.catalog('another-account')['questions'] == []
        # Revisions invalidate the active bank, but preserve old evidence and progress for history.
        scope = app.state.platform.scope('course-default')
        doc = app.state.rag.document(scope, uploaded['documentId'])
        app.state.platform.repo.put(scope, 'document', doc['id'], {**doc, 'contentRevision': doc['contentRevision']+1})
        assert client.get('/api/practice/bank?courseId=course-default', headers=headers).json()['questions'] == []
        assert len(app.state.practice_generation.catalog('local', history=True)['questions']) == 200


def test_programming_material_can_generate_code_in_both_categories(tmp_path):
    model = Model()
    with TestClient(create_app(Config(data_dir=tmp_path, api_key='controlled'), provider=model), base_url='http://localhost') as client:
        headers = token(client)
        upload(client, headers, MATERIAL + '\n程序设计与算法实现：```python\ndef solve(x): return x\n```', '程序设计.md')
        result = wait_for(client, headers, lambda v: len(v['questions']) == 200)
        for category in ('hot100', 'basic'):
            counts = Counter(q['type'] for q in result['questions'] if q['category'] == category)
            assert set(counts) == {'single', 'multiple', 'boolean', 'fill', 'code'}
            assert sum(counts.values()) == 100
            assert 0 < counts['code'] < 100


@pytest.mark.parametrize('material,key,status', [('短资料', 'controlled', 'insufficient_material'), (MATERIAL, '', 'model_unavailable')], ids=['too-short','no-model'])
def test_not_enough_content_or_no_model_is_explicit_and_never_calls(tmp_path, material, key, status):
    model = Model()
    with TestClient(create_app(Config(data_dir=tmp_path, api_key=key), provider=model), base_url='http://localhost') as client:
        headers = token(client)
        upload(client, headers, material)
        result = wait_for(client, headers, lambda v: v['generations'] and v['generations'][0]['status'] == status)
        assert not result['questions']
        assert model.calls == 0


def test_failed_batch_is_not_replayed_and_explicit_resume_keeps_completed_work(tmp_path):
    model = Model(fail_at=2)
    with TestClient(create_app(Config(data_dir=tmp_path, api_key='controlled'), provider=model), base_url='http://localhost') as client:
        headers = token(client)
        upload(client, headers)
        failed = wait_for(client, headers, lambda v: v['generations'] and v['generations'][0]['status'] == 'unknown')
        assert failed['generations'][0]['completed'] == 5
        assert not failed['questions']
        time.sleep(.25)
        assert model.calls == 2
        set_id = failed['generations'][0]['id']
        assert client.post(f'/api/practice/generation/{set_id}/resume', headers=headers, json={}).status_code == 200
        done = wait_for(client, headers, lambda v: len(v['questions']) == 200)
        assert done['generations'][0]['status'] == 'succeeded'
        assert model.calls == 41


@pytest.mark.parametrize('corrupt', ['evidence', 'duplicate'])
def test_invalid_or_duplicate_questions_never_publish_or_retry(tmp_path, corrupt):
    model = Model(corrupt=corrupt)
    with TestClient(create_app(Config(data_dir=tmp_path, api_key='controlled'), provider=model), base_url='http://localhost') as client:
        headers = token(client)
        upload(client, headers)
        result = wait_for(client, headers, lambda v: v['generations'] and v['generations'][0]['status'] == 'unknown')
        assert not result['questions'] and result['generations'][0]['completed'] == 0
        assert result['generations'][0]['error'] == 'PRACTICE_BATCH_INCOMPLETE'
        assert model.calls == 1


def test_server_restart_resumes_queued_batches_without_replaying_completed_batches(tmp_path):
    model = Model(fail_at=2)
    config = Config(data_dir=tmp_path, api_key='controlled')
    with TestClient(create_app(config, provider=model), base_url='http://localhost') as client:
        headers = token(client)
        upload(client, headers)
        failed = wait_for(client, headers, lambda v: v['generations'] and v['generations'][0]['status'] == 'unknown')
        set_id = failed['generations'][0]['id']
    replacement = Model()
    replacement.calls = 2  # distinct controlled prompts after the first completed batch
    with TestClient(create_app(config, provider=replacement, start_jobs=False), base_url='http://localhost') as client:
        headers = token(client)
        assert client.post(f'/api/practice/generation/{set_id}/resume', headers=headers, json={}).status_code == 200
    with TestClient(create_app(config, provider=replacement), base_url='http://localhost') as client:
        headers = token(client)
        result = wait_for(client, headers, lambda v: len(v['questions']) == 200)
        assert result['generations'][0]['completed'] == 200
        assert replacement.calls == 41


def test_cancel_queued_work_never_calls_model(tmp_path):
    model = Model()
    app = create_app(Config(data_dir=tmp_path, api_key='controlled'), provider=model, start_jobs=False)
    with TestClient(app, base_url='http://localhost') as client:
        headers = token(client)
        uploaded = upload(client, headers)
        scope = app.state.platform.scope('course-default')
        doc = app.state.rag.document(scope, uploaded['documentId'])
        from backend.xueya.rag_parse import parse_structured
        # Parse through the normal publisher, with the queue intentionally stopped.
        parsed = parse_structured(MATERIAL.encode(), 'md')
        app.state.rag._publish(scope, doc, parsed)
        result = client.post(f"/api/practice/generation/{uploaded['practiceGeneration']['id']}/cancel", headers=headers, json={})
        assert result.status_code == 200
        assert result.json()['generation']['status'] == 'cancelled'
        assert model.calls == 0
