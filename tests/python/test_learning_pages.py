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
    rows = client.app.state.platform.db.all('SELECT status,usage_json FROM invocations')
    assert len(rows) == 2 and all(r['status'] == 'succeeded' and r['usage_json'] for r in rows)


def test_workspace_requires_host_auth_and_accepts_empty_course(tmp_path):
    with TestClient(create_app(Config(data_dir=tmp_path/'empty')), base_url='http://127.0.0.1') as client:
        assert client.get('/api/learning/workspace').status_code == 403
        headers = {'X-Xueya-Token': client.get('/api/platform/bootstrap').json()['token']}
        result = client.get('/api/learning/workspace', headers=headers).json()['result']
        assert result['sources'] == [] and result['artifacts'] == []
        assert not result['capabilities']['model']
        assert client.post('/api/learning/workspace', json={}, headers=headers).status_code == 405



def test_video_uses_owned_frames_and_persists_result(pages):
    client, call, headers, doc = pages
    image = client.post('/api/learning/media/upload?name=frame.png', content=b'\x89PNGcontrolled', headers={**headers, 'Content-Type': 'image/png'}).json()['result']
    video = client.post('/api/learning/media/upload?name=course.mp4', content=b'controlled-original-video', headers={**headers, 'Content-Type': 'video/mp4'}).json()['result']
    frames = [{'id': image['id'], 'version': '1', 'timeMs': 500}]
    registered = call('media/video-register', {'id': video['id'], 'frames': frames, 'durationMs': 1000, 'operationId': 'register-video', 'expectedRevision': 1})
    result = call('media/video', {'id': video['id'], 'version': str(registered['revision']), 'question': '识别视频中的题目'})
    assert result['coverage'] == 'sampled-frames-only' and result['sampleTimesMs'] == [500]
    assert any(a['kind'] == 'video-analysis' for a in call('workspace')['artifacts'])
