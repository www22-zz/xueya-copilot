"""G5 actual main-host integration. All upstream requests use a controlled transport."""
import asyncio
import base64
from dataclasses import replace
import io
import json
import time
import wave
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.agent.media_audio import assemble_wav, split_wav, wav_info
from backend.xueya.app import create_app
from backend.xueya.common import AppError
from backend.xueya.config import Config


def wav(seconds=1, rate=8000):
    data = io.BytesIO()
    with wave.open(data, 'wb') as clip:
        clip.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        clip.writeframes(b''.join(bytes([i % 128, 0])*rate for i in range(seconds)))
    return data.getvalue()


def test_shared_account_also_protects_g5_and_preserves_course_data(media_client):
    c = media_client
    credentials = {'username': 'g5-shared-test', 'password': 'controlled-g5-password'}
    assert c.post('/api/account/setup', json=credentials, headers=c.h).status_code == 200
    before = call(c, 'workspace')
    assert any(d['id'] == 'g5-doc' for d in before['documents'])
    assert c.post('/api/account/logout', json={}, headers=c.h).status_code == 200
    for path in ('workspace', 'result?id=missing', 'audio?id=missing&part=missing', 'export?id=missing'):
        assert c.get('/api/learning/media-workspace/'+path, headers=c.h).status_code == 401
    assert c.post('/api/learning/media-workspace/upload?name=private.wav', headers=c.h, content=wav()).status_code == 401
    assert c.post('/api/account/login', json=credentials).status_code == 200
    assert call(c, 'workspace')['documents'] == before['documents']
    assert c.calls == []


@pytest.fixture
def media_client(tmp_path):
    app = create_app(Config(data_dir=tmp_path/'g5', api_key='controlled-only', api_slots=1))
    calls, controls = [], {'failAt': None, 'blockAt': None}
    async def handler(request):
        value = json.loads(request.content); calls.append(value)
        if controls['blockAt'] == len(calls):
            await asyncio.sleep(30)
        if controls['failAt'] == len(calls):
            return httpx.Response(503)
        model = value['model']; message = {'content': '队列遵循先进先出。'}
        if model == 'mimo-v2.5-tts':
            message = {'content': '', 'audio': {'data': base64.b64encode(wav()).decode()}}
        elif model != 'mimo-v2.5-asr':
            message = {'content': json.dumps({'observations': ['画面中有方块'], 'uncertainties': [], 'inferences': [], 'recognizedProblem': '画面说明'})}
        return httpx.Response(200, json={'model': model, 'choices': [{'message': message, 'finish_reason': 'stop'}], 'usage': {'total_tokens': 4}})
    with TestClient(app, base_url='http://127.0.0.1') as c:
        app.state.provider.transport = httpx.MockTransport(handler)
        c.h = {'X-Xueya-Token': c.get('/api/platform/bootstrap').json()['token']}
        c.p = app.state.platform; c.calls = calls; c.controls = controls
        scope = c.p.scope()
        c.p.repo.put(scope, 'source', 'g5-source', {'id': 'g5-source', 'documentId': 'g5-doc', 'title': '队列', 'quote': '队列遵循先进先出。', 'location': '原文第一段'})
        c.p.repo.put(scope, 'document', 'g5-doc', {'id': 'g5-doc', 'name': '队列.md', 'chunks': []})
        yield c


def call(c, path, body=None, status=200, course='course-default'):
    response = c.request('POST' if body is not None else 'GET', '/api/learning/media-workspace/'+path+('&' if '?' in path else '?')+'courseId='+course,
                         headers=c.h, **({'json': body} if body is not None else {}))
    assert response.status_code == status, response.text
    return response.json().get('result', response.json())


def finish(c, run, expected='completed'):
    for _ in range(500):
        row = call(c, 'result?id='+run['id'])
        if row['content']['status'] in ('completed', 'unknown', 'failed', 'cancelled'):
            assert row['content']['status'] == expected, row
            return row
        time.sleep(.02)
    pytest.fail('G5 run timeout')


def upload(c, seconds=61):
    r = c.post('/api/learning/media-workspace/upload?name=lecture.wav', headers={**c.h, 'Content-Type': 'audio/wav'}, content=wav(seconds))
    assert r.status_code == 200, r.text
    return r.json()['result']


def prepare(c, seconds=61):
    media = upload(c, seconds)
    run = call(c, 'prepare', {'mediaId': media['content']['id'], 'mediaVersion': media['revision'], 'seconds': 30, 'confirmed': True, 'operationId': 'prepare'})
    return media, finish(c, run)


def start_transcript(c, media, prepared, operation='asr', **extra):
    return call(c, 'transcribe', {'mediaId': media['content']['id'], 'mediaVersion': media['revision'], 'preparedId': prepared['id'],
        'confirmed': True, 'allowApi': True, 'maxCalls': 3, 'operationId': operation, **extra})


def script(c, style='dialogue'):
    draft = call(c, 'script/draft', {'style': style, 'selection': {'documentIds': ['g5-doc']}})['content']
    for part in draft['segments']: part['reviewed'] = True
    row = call(c, 'script/save', {'id': 'g5-script', 'expectedRevision': 0, 'operationId': 'save-script', 'confirmed': True, 'content': draft})
    return row


def synthesize(c, row, operation='tts', max_calls=40):
    return finish(c, call(c, 'synthesize', {'scriptId': row['id'], 'scriptRevision': row['revision'], 'confirmed': True,
        'allowApi': True, 'maxCalls': max_calls, 'voices': {'A': '冰糖', 'B': '苏打'}, 'operationId': operation}))


def test_pcm_boundaries_and_corrupt_input():
    raw = wav(61); info, parts = split_wav(raw, 30)
    assert [(p['startMs'], p['endMs']) for p in parts] == [(0, 30000), (30000, 60000), (60000, 61000)]
    assert sum(wav_info(p['bytes'])['frames'] for p in parts) == info['frames']
    for bad in (b'not wave', raw[:-200]):
        with pytest.raises(AppError): wav_info(bad)
    with pytest.raises(AppError): split_wav(raw, 0)


def test_upload_transcribe_review_import_and_original_links(media_client):
    c = media_client; media, prepared = prepare(c)
    assert not c.calls and len(prepared['content']['items']) == 3
    run = finish(c, start_transcript(c, media, prepared))
    assert len(c.calls) == 3 and all(p['timestampPrecision'] == 'segment' for p in run['content']['items'])
    call(c, 'transcript/import', {'id': run['id'], 'revision': run['revision'], 'confirmed': True, 'operationId': 'import'}, status=400)
    edited = [{'id': p['id'], 'text': p['text']+'已听原件核对。', 'reviewed': True} for p in run['content']['items']]
    reviewed = call(c, 'transcript/save', {'id': run['id'], 'revision': run['revision'], 'items': edited, 'confirmed': True, 'operationId': 'review'})
    assert reviewed['content']['items'][0]['originalText'] != reviewed['content']['items'][0]['text']
    value = {'id': run['id'], 'revision': reviewed['revision'], 'confirmed': True, 'operationId': 'import'}
    imported = call(c, 'transcript/import', value)
    assert call(c, 'transcript/import', value)['job']['id'] == imported['job']['id']
    for _ in range(300):
        job = c.p.jobs.get(imported['job']['id'], c.p.user_id)
        if job['status'] in ('succeeded', 'failed'): break
        time.sleep(.02)
    assert job['status'] == 'succeeded', job
    linked = call(c, 'transcript/link', {**value, 'documentId': imported['documentId']})
    assert linked['linkedSegments'] == 3
    catalog = c.get('/api/platform/library/catalog', headers=c.h).json()
    assert len(catalog['links']) == 3 and catalog['links'][0]['kind'] == 'library-media-link'
    source = c.get('/api/platform/library/media-original?id='+media['content']['id']+'&version=1', headers={**c.h, 'Range': 'bytes=0-43'})
    assert source.status_code == 206 and source.content[:4] == b'RIFF'


def test_script_confirm_incremental_synthesis_export_and_ledger(media_client):
    c = media_client
    draft = call(c, 'script/draft', {'style': 'dialogue'})['content']
    call(c, 'script/save', {'id': 'unreviewed', 'expectedRevision': 0, 'operationId': 'bad', 'confirmed': True, 'content': draft}, status=400)
    row = script(c); before = len(c.p.repo.all(c.p.scope(), 'review'))
    rendered = synthesize(c, row)
    calls = len(c.calls)
    assert {'冰糖', '苏打'} == {v['audio']['voice'] for v in c.calls}
    assert calls == sum(p['kind'] != 'pause' for p in row['content']['segments'])
    unchanged = synthesize(c, row, 'cached', max_calls=0)
    assert len(c.calls) == calls and all(p.get('reused') for p in unchanged['content']['items'] if p['kind'] != 'pause')
    edited = row['content']; edited['segments'][1]['text'] += '请再次核对。'
    newer = call(c, 'script/save', {'id': row['id'], 'expectedRevision': row['revision'], 'operationId': 'edit', 'confirmed': True, 'content': edited})
    rendered = synthesize(c, newer, 'changed', max_calls=1)
    assert len(c.calls) == calls+1
    data = c.get('/api/learning/media-workspace/export?id='+rendered['id'], headers=c.h)
    assert data.status_code == 200
    with zipfile.ZipFile(io.BytesIO(data.content)) as archive:
        assert set(archive.namelist()) == {'review.wav', 'script.json', 'script.md', 'captions.srt'}
        assert wav_info(archive.read('review.wav'))['durationMs'] == (calls+8)*1000
    assert len(c.p.repo.all(c.p.scope(), 'review')) == before
    invocations = c.p.db.all('SELECT id FROM invocations')
    assert len(invocations) == calls+1
    assert all(json.loads(c.p.db.one('SELECT value FROM meta WHERE key=?', ('invocation-context:'+r['id'],))['value'])['jobId'] for r in invocations)


def test_unknown_keeps_successes_and_explicit_resume_never_replays_them(media_client):
    c = media_client; media, prepared = prepare(c)
    c.controls['failAt'] = 2
    run = finish(c, start_transcript(c, media, prepared), 'unknown')
    assert len(c.calls) == 2 and sum(bool(p.get('done')) for p in run['content']['items']) == 1
    time.sleep(.2); assert len(c.calls) == 2
    value = {'resumeId': run['id'], 'operationId': 'resume', 'confirmed': True, 'allowApi': True, 'maxCalls': 2}
    call(c, 'transcribe', value, status=400)
    assert len(c.calls) == 2
    resumed = finish(c, call(c, 'transcribe', {**value, 'reviewedUnknown': True}))
    assert len(c.calls) == 4 and resumed['content']['items'][0] == run['content']['items'][0]
    replay = call(c, 'transcribe', {**value, 'reviewedUnknown': True})
    assert replay['id'] == resumed['id'] and len(c.calls) == 4


def test_cancel_propagates_to_provider_and_does_not_continue_chain(media_client):
    c = media_client; media, prepared = prepare(c)
    c.controls['blockAt'] = 1
    run = start_transcript(c, media, prepared)
    for _ in range(100):
        if c.calls: break
        time.sleep(.02)
    call(c, 'cancel', {'id': run['id']})
    finish(c, run, 'unknown'); time.sleep(.15)
    assert len(c.calls) == 1
    assert c.p.db.one('SELECT status FROM invocations')['status'] == 'unknown'


def test_source_change_blocks_script(media_client):
    c = media_client; row = script(c)
    scope = c.p.scope(); source = c.p.repo.read(scope, 'source', 'g5-source')
    c.p.repo.put(scope, 'source', 'g5-source', {**source['value'], 'quote': '新版本内容'}, source['version'])
    call(c, 'synthesize', {'scriptId': row['id'], 'scriptRevision': row['revision'], 'confirmed': True, 'allowApi': True, 'maxCalls': 40, 'operationId': 'stale'}, status=400)
    assert not c.calls


def test_queue_configuration_drift_and_cross_course_are_rejected(media_client):
    c = media_client; row = script(c)
    c.p.repo.ensure_course(c.p.user_id, {'id': 'other', 'name': '另一个课程'})
    call(c, 'result?id='+row['id'], status=400, course='other')
    call(c, 'script/draft', {'courseId':'other'}, status=400)
    c.portal.call(c.p.jobs.stop)
    run = call(c, 'synthesize', {'scriptId':row['id'],'scriptRevision':row['revision'],'operationId':'drift','confirmed':True,'allowApi':True,'maxCalls':40})
    c.app.state.config = replace(c.app.state.config, api_key='changed-controlled-key')
    c.portal.call(c.p.jobs.start)
    result = finish(c, run, 'failed')
    assert result['content']['error'] == 'NOT_SENT' and not c.calls


def test_restart_marks_unfinished_paid_work_unknown_without_resending(tmp_path):
    config = Config(data_dir=tmp_path/'restart', api_key='controlled-only')
    app = create_app(config, start_jobs=False)
    with TestClient(app, base_url='http://127.0.0.1') as c:
        c.h={'X-Xueya-Token':c.get('/api/platform/bootstrap').json()['token']};c.p=app.state.platform
        source = {'id':'g5-source','documentId':'g5-doc','title':'队列','quote':'队列遵循先进先出。','location':'第一段'}
        c.p.repo.put(c.p.scope(),'source','g5-source',source)
        row=script(c)
        run=call(c,'synthesize',{'scriptId':row['id'],'scriptRevision':row['revision'],'operationId':'restart','confirmed':True,'allowApi':True,'maxCalls':40})
    with TestClient(create_app(config),base_url='http://127.0.0.1') as c:
        c.h={'X-Xueya-Token':c.get('/api/platform/bootstrap').json()['token']}
        result=call(c,'result?id='+run['id'])
        assert result['content']['status']=='unknown'
        assert not c.app.state.platform.db.all('SELECT id FROM invocations')


def test_video_selected_frames_are_bounded_and_persisted(media_client):
    c = media_client
    original = c.post('/api/learning/media/upload?name=course.mp4&durationMs=10000', headers={**c.h,'Content-Type':'video/mp4'},content=b'controlled-video-original').json()['result']
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kP6kAAAAASUVORK5CYII=')
    image = c.post('/api/learning/media/upload?name=frame.png',headers={**c.h,'Content-Type':'image/png'},content=png).json()['result']
    frames = [{'id':image['id'],'version':image['version'],'timeMs':i*1000+500} for i in range(8)]
    value = {'mediaId':original['id'],'mediaVersion':1,'startMs':0,'endMs':10000,'frames':frames,'confirmed':True,'operationId':'register'}
    registered = call(c,'video/register',value)
    assert registered['content']['coverage'] == 'sampled-frames-only'
    run = finish(c,call(c,'video',{'mediaId':original['id'],'mediaVersion':2,'allowApi':True,'confirmed':True,'maxCalls':8,'operationId':'video'}))
    assert len(c.calls)==8 and [p['timeMs'] for p in run['content']['items']] == [f['timeMs'] for f in frames]
    edited = [{'id':p['id'],'timeMs':p['timeMs'],'text':'已核对：彩色方块。','reviewed':True} for p in run['content']['items']]
    reviewed = call(c,'video/save',{'id':run['id'],'revision':run['revision'],'items':edited,'confirmed':True,'operationId':'video-reviewed'})
    assert reviewed['content']['items'][0]['analysis']['observations']
    assert reviewed['content']['items'][0]['originalText'] != reviewed['content']['items'][0]['text']
    call(c,'video/register',{**value,'mediaVersion':2,'frames':frames*4},status=400)


def test_scripts_cannot_overwrite_other_learning_kinds(media_client):
    c=media_client; media=upload(c,1)
    content=call(c,'script/draft',{})['content']
    for part in content['segments']:part['reviewed']=True
    result=call(c,'script/save',{'id':media['id'],'expectedRevision':1,'content':content,'operationId':'overwrite','confirmed':True},status=400)
    assert result['error']=='ARTIFACT_KIND_CONFLICT'
    assert call(c,'result?id='+media['id'])['kind']=='media'


def test_media_over_ten_megabytes_survives_real_backup_restore(media_client,tmp_path):
    from backend.xueya.backup import create_backup,restore_backup
    c=media_client;media=upload(c,700)
    assert c.p.files.path(media['content']['fileHash']).stat().st_size>10*1024*1024
    backup=tmp_path/'backup';restored=tmp_path/'restored'
    create_backup(c.app.state.config.data_dir,backup)
    restore_backup(backup,restored)
    with TestClient(create_app(Config(data_dir=restored)),base_url='http://127.0.0.1') as other:
        headers={'X-Xueya-Token':other.get('/api/platform/bootstrap').json()['token'],'Range':'bytes=0-43'}
        response=other.get('/api/platform/library/media-original?id='+media['content']['id']+'&version=1',headers=headers)
        assert response.status_code==206 and response.content[:4]==b'RIFF'


def test_decoded_pcm_keeps_immutable_original_and_version_binding(media_client):
    c=media_client;raw=b'opaque controlled container, not a codec quality test'
    response=c.post('/api/learning/media-workspace/upload-original?name=recording.bin',headers={**c.h,'Content-Type':'application/octet-stream'},content=raw)
    original=response.json()['result']
    decoded=c.post('/api/learning/media-workspace/upload?name=processing.wav&originalId='+original['content']['id']+'&originalVersion=1',
                   headers={**c.h,'Content-Type':'audio/wav'},content=wav()).json()['result']
    assert decoded['content']['originalMediaVersion']==2
    stored=call(c,'result?id='+original['id'])
    assert stored['content']['processingMediaId']==decoded['content']['id']
    assert c.p.files.read(stored['content']['fileHash'])==raw
    c.p.repo.ensure_course(c.p.user_id,{'id':'other','name':'其他'})
    response=c.post('/api/learning/media-workspace/upload?courseId=other&originalId='+original['content']['id']+'&originalVersion=2',
                    headers={**c.h,'Content-Type':'audio/wav'},content=wav())
    assert response.status_code==400
