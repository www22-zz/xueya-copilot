import base64
import json
from dataclasses import replace
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider
from test_c_integration import upload


def upstream(request):
    payload = json.loads(request.content)
    system = str(payload['messages'][0]['content'])
    if payload['model'] == 'mimo-v2.5-asr':
        content, audio = '转写后的课程内容', None
    elif payload['model'] == 'mimo-v2.5-tts':
        content, audio = '', {'data': base64.b64encode(b'RIFF-test-audio').decode()}
    elif 'observations' in system:
        content, audio = json.dumps({'observations': ['图中有一道题'], 'uncertainties': ['符号需核对'], 'inferences': [], 'recognizedProblem': '树由什么组成？'}, ensure_ascii=False), None
    elif '逐项结论' in system or '"claims"' in system:
        user = json.loads(payload['messages'][-1]['content'])
        sources = user.get('materials', user.get('sources', []))
        content, audio = json.dumps({'claims': [{'text': s['quote'], 'evidence': [{'sourceId': s['id'], 'quote': s['quote']}]} for s in sources], 'concepts': []}), None
    elif '候选题' in system:
        source = json.loads(payload['messages'][-1]['content'])['materials'][0]
        content, audio = json.dumps({'questions': [{'type': 'single', 'prompt': 'What is in a tree?', 'options': ['Nodes and edges', 'No nodes'], 'answer': 0,
            'explanation': 'According to the source.', 'evidenceQuote': source['quote'], 'sourceId': source['id'], 'conceptIds': [], 'difficulty': 'easy'}]}), None
    else:
        content, audio = '{}', None
    return httpx.Response(200, json={'model': payload['model'], 'choices': [{'message': {'content': content, **({'audio': audio} if audio else {})}, 'finish_reason': 'stop'}], 'usage': {'total_tokens': 10}})


@pytest.fixture
def pages(tmp_path):
    config = Config(data_dir=tmp_path/'data', api_key='controlled-test-only', base_url='https://controlled.invalid/v1')
    app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)), start_jobs=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        headers, doc = upload(client)
        def call(path, value=None, status=200):
            response = client.get('/api/learning/'+path, headers=headers) if value is None else client.post('/api/learning/'+path, json=value, headers=headers)
            assert response.status_code == status, response.text
            return response.json().get('result', response.json())
        yield client, call, headers, doc


def adopt(call, draft, operation):
    return call('draft/adopt', {'draftId': draft['draftId'], 'operationId': operation, 'confirmed': True})


def test_candidates_review_receipts_quiz_and_protected_sync(pages):
    client, call, headers, doc = pages
    generated = call('questions/generate', {'selection': {'documentIds': [doc]}, 'count': 1})
    assert len(generated['questions']) == 1
    q = generated['questions'][0]
    command = {'id': q['id'], 'expectedRevision': 1, 'expectedVersion': q['version'], 'operationId': 'review-q', 'approved': True, 'reason': '已核对原文'}
    approved = call('questions/review', command)
    assert call('questions/review', command) == approved
    call('questions/review', {**command, 'reason': 'changed'}, 409)
    q = approved['content']
    quiz = adopt(call, call('quiz/preview', {'id': 'quiz', 'questionIds': [q['id']], 'count': 1}), 'adopt-quiz')
    public = call('quiz/quiz')
    assert 'answer' not in public['questions'][0]
    attempt = call('attempts', {'id': 'attempt', 'quizId': 'quiz', 'quizRevision': quiz['revision'], 'responses': [{'questionId': q['id'], 'answer': 1}]})
    event = attempt['content']['events'][0]
    assert event['grade']['score'] == 0
    corrected = call('diagnosis/correct', {'attemptId': 'attempt', 'eventId': event['id'], 'expectedRevision': 1, 'operationId': 'correct', 'cause': 'misread', 'reason': '已重新审题'})
    assert corrected['content']['diagnoses'][0]['status'] == 'confirmed'
    assert len(call('history?id=attempt')['items']) == 2
    scope = client.app.state.platform.scope()
    source_before = client.app.state.platform.repo.all(scope, 'source')
    ws = {'version': 3, 'activeId': 'course-default', 'courses': [{'id': 'course-default', 'name': 'Trees', 'archived': False, 'data': {'documents': [], 'cards': [], 'bank': [], 'records': [], 'messages': [], 'sessions': [], 'plan': []}}]}
    client.app.state.platform.repo.save_workspace(scope.user_id, ws, 0)
    assert client.app.state.platform.repo.read(scope, 'question', q['id'])['value']['status'] == 'approved'
    current = {s['id']: s for s in client.app.state.platform.repo.all(scope, 'source')}
    assert all(current[s['id']] == s for s in source_before)
    client.app.state.platform.repo.ensure_course(scope.user_id, {'id': 'other', 'name': 'Other'})
    assert call('artifacts?id=attempt&courseId=other', status=404)['error'] == 'ARTIFACT_NOT_FOUND'
    assert call('workspace?courseId=other')['artifacts'] == []


def test_graph_plan_summary_and_versions(pages):
    client, call, headers, doc = pages
    source = call('workspace')['sources'][0]
    graph = {'courseId': 'course-default', 'concepts': [{'id': 'nodes', 'courseId': 'course-default', 'name': 'Nodes', 'status': 'confirmed', 'aliases': [],
        'evidence': [{'sourceId': source['id'], 'version': source['version'], 'quote': source['quote']}]}], 'edges': []}
    adopt(call, call('graph/preview', {'graph': graph, 'expectedRevision': 0}), 'graph-adopt')
    assert call('graph')['content']['concepts'][0]['id'] == 'nodes'
    assert call('graph/path', {})['entries']
    plan = adopt(call, call('plan/preview', {'id': 'plan', 'examDate': '2026-11-01', 'minutes': 30}), 'adopt-plan')
    assert plan['content']['days']
    summary = adopt(call, call('summary/preview', {'id': 'summary'}), 'adopt-summary')
    assert summary['content']['claims'][0]['support'] == 'supported'
    note = adopt(call, call('note/preview', {'id': 'note', 'text': '我的核对笔记', 'title': '笔记'}), 'adopt-note')
    edited = adopt(call, call('note/edit', {'id': 'note', 'expectedRevision': 1, 'text': '新的笔记'}), 'edit-note')
    assert edited['revision'] == 2
    assert len(call('history?id=note')['items']) == 2
    restored = adopt(call, call('history/preview', {'id': 'note', 'version': 1, 'expectedRevision': 2}), 'restore-note')
    assert restored['revision'] == 3 and restored['content']['text'] == '我的核对笔记'
    assert len(call('history?id=note')['items']) == 3
    call('note/preview', {'id': 'cross', 'text': 'x', 'courseId': 'other'}, 403)
    assert call('workspace')['graph']['revision'] == 1
    call('note/preview', {'id': ['bad-id'], 'text': 'invalid'}, 400)


def test_native_media_tracking_recognition_and_speech(pages):
    client, call, headers, doc = pages
    uploaded = client.post('/api/learning/media/upload?name=question.png', content=b'\x89PNG\r\ncontrolled', headers={**headers, 'Content-Type': 'image/png'}).json()['result']
    recognition = call('media/recognize', {'id': uploaded['id'], 'version': '1', 'question': '识别题干'})
    assert recognition['content']['status'] == 'awaiting_user'
    confirmed = call('media/confirm', {'id': uploaded['id'], 'expectedRevision': 1, 'operationId': 'confirm', 'confirmed': True, 'correctedProblem': '核对后的题干'})
    assert confirmed['content']['recognizedProblem'] == '核对后的题干'
    audio = client.post('/api/learning/media/upload?name=course.wav&durationMs=1000', content=b'RIFFcontrolled', headers={**headers, 'Content-Type': 'audio/wav'}).json()['result']
    transcription = call('media/transcribe', {'segments': [{'id': audio['id'], 'version': '1', 'startMs': 0, 'endMs': 1000}]})
    assert transcription['text'] == '转写后的课程内容'
    adopt(call, call('note/preview', {'id': 'spoken-note', 'text': '朗读正文'}), 'spoken-note')
    spoken = call('media/speak', {'id': 'spoken-note', 'revision': 1, 'confirmed': True})
    assert spoken['synthetic'] and spoken['chunks'][0]['audio']['mime'] == 'audio/wav'
    rows = client.app.state.platform.db.all('SELECT status,usage_json FROM invocations')
    assert len(rows) == 3 and all(r['status'] == 'succeeded' and r['usage_json'] for r in rows)


def test_workspace_requires_host_auth_and_accepts_empty_course(tmp_path):
    with TestClient(create_app(Config(data_dir=tmp_path/'empty')), base_url='http://127.0.0.1') as client:
        assert client.get('/api/learning/workspace').status_code == 403
        headers = {'X-Xueya-Token': client.get('/api/platform/bootstrap').json()['token']}
        result = client.get('/api/learning/workspace', headers=headers).json()['result']
        assert result['sources'] == [] and result['artifacts'] == []
        assert not result['capabilities']['model']
        assert client.post('/api/learning/workspace', json={}, headers=headers).status_code == 405


def test_server_preview_recovery_scope_and_stale_graph(pages):
    client, call, headers, doc = pages
    draft = call('note/preview', {'id': 'recover-note', 'text': 'Unconfirmed draft'})
    assert call('draft?id='+draft['draftId']) == draft
    assert call('workspace')['artifacts'] == []
    client.app.state.platform.repo.ensure_course('local-user', {'id': 'other', 'name': 'Other'})
    call('draft?id='+draft['draftId']+'&courseId=other', status=404)
    source = call('workspace')['sources'][0]
    graph = {'courseId': 'course-default', 'concepts': [{'id': 'n', 'courseId': 'course-default', 'name': 'Nodes', 'evidence': [{'sourceId': source['id'], 'version': source['version'], 'quote': source['quote']}]}], 'edges': []}
    pending = call('graph/preview', {'graph': graph, 'expectedRevision': 0})
    current = client.app.state.rag.document(client.app.state.platform.scope(), doc)
    client.app.state.rag.remove(client.app.state.platform.scope(), doc, current['version'])
    call('draft/adopt', {'draftId': pending['draftId'], 'operationId': 'stale-graph', 'confirmed': True}, 409)
    assert not [a for a in call('workspace')['artifacts'] if a['kind'] == 'concept-graph']


def test_video_uses_owned_frames_and_persists_result(pages):
    client, call, headers, doc = pages
    image = client.post('/api/learning/media/upload?name=frame.png', content=b'\x89PNGcontrolled', headers={**headers, 'Content-Type': 'image/png'}).json()['result']
    video = client.post('/api/learning/media/upload?name=course.mp4', content=b'controlled-original-video', headers={**headers, 'Content-Type': 'video/mp4'}).json()['result']
    frames = [{'id': image['id'], 'version': '1', 'timeMs': 500}]
    registered = call('media/video-register', {'id': video['id'], 'frames': frames, 'durationMs': 1000, 'operationId': 'register-video', 'expectedRevision': 1})
    result = call('media/video', {'id': video['id'], 'version': str(registered['revision']), 'question': '识别视频中的题目'})
    assert result['coverage'] == 'sampled-frames-only' and result['sampleTimesMs'] == [500]
    assert any(a['kind'] == 'video-analysis' for a in call('workspace')['artifacts'])
    call('media/video-register', {'id': video['id'], 'frames': [{'id': video['id'], 'version': '2', 'timeMs': 500}], 'durationMs': 1000, 'operationId': 'invalid-frame', 'expectedRevision': 2}, 400)


@pytest.mark.parametrize('kind, fields, answer', [
    ('multiple', {'options': ['A', 'B', 'C'], 'answer': [0, 2]}, [0, 2]),
    ('boolean', {'answer': True}, True),
    ('fill', {'answers': [['Nodes', 'vertices']]}, ['vertices']),
    ('short', {'rubric': [{'id': 'point', 'description': 'mentions nodes', 'points': 2}]}, 'Nodes'),
])
def test_page_question_types_and_subjective_review(pages, kind, fields, answer):
    client, call, headers, doc = pages
    source = call('workspace')['sources'][0]
    question = {'type': kind, 'prompt': 'Course question '+kind, 'sourceId': source['id'], 'evidenceQuote': source['quote'], 'explanation': 'See original.', **fields}
    row = call('questions/manual', {'id': 'q-'+kind, 'expectedRevision': 0, 'operationId': 'manual-'+kind, 'question': question})
    q = row['content']
    approved = call('questions/review', {'id': q['id'], 'expectedVersion': q['version'], 'expectedRevision': 1, 'operationId': 'approve-'+kind, 'approved': True, 'reason': 'reviewed original'})
    quiz = adopt(call, call('quiz/preview', {'id': 'quiz-'+kind, 'questionIds': [q['id']], 'count': 1}), 'adopt-'+kind)
    attempt = call('attempts', {'id': 'attempt-'+kind, 'quizId': quiz['id'], 'quizRevision': 1, 'responses': [{'questionId': q['id'], 'answer': answer}]})
    grade = attempt['content']['events'][0]['grade']
    if kind == 'short':
        assert grade['status'] == 'awaiting_review'
        reviewed = call('attempts/review', {'attemptId': attempt['id'], 'expectedRevision': 1, 'questionId': q['id'], 'operationId': 'grade-short',
            'review': {'reviewer': 'local-user', 'reason': 'Checked rubric', 'sourceVersion': source['version'], 'points': [{'id': 'point', 'score': 1.5}]}})
        assert reviewed['content']['events'][0]['grade']['score'] == 1.5
    else:
        assert grade['score'] == 1
