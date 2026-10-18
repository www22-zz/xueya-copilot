import json
import socket
import time
import pytest
from backend.xueya.common import AppError
from backend.xueya.library_fetch import public_target, Extractor


def wait_job(client, job):
    for _ in range(180):
        result = client.platform.jobs.get(job['id'], client.platform.user_id)
        if result['status'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
            assert result['status'] == 'succeeded', result
            return result
        time.sleep(.03)
    raise AssertionError('job did not finish')


def post(client, operation, value):
    return client.post('/api/platform/library/'+operation, headers=client.platform_headers, json=value)


def import_text(client, key='text-1', course='course-default'):
    value = {'courseId': course, 'title': '课程讲义', 'text': '# 第一章\n栈按照后进先出规则组织数据。\n队列按照先进先出规则组织数据。', 'chapter': '第一章', 'idempotencyKey': key}
    response = post(client, 'text', value)
    assert response.status_code == 200, response.text
    result = wait_job(client, response.json()['job'])
    return result['result']['documentId'], value


def catalog(client, course='course-default'):
    return client.get('/api/platform/library/catalog?courseId='+course, headers=client.platform_headers).json()


def test_text_import_read_idempotency_profile_archive_and_restore(client):
    document_id, value = import_text(client)
    repeat = post(client, 'text', value)
    assert repeat.status_code == 200
    assert len(catalog(client)['documents']) == 1
    assert post(client, 'text', {**value, 'chapter': '另一个章节'}).status_code == 409
    read = client.get('/api/platform/library/read?documentId='+document_id, headers=client.platform_headers).json()
    assert read['artifact']['blocks'] and read['document']['origin']['type'] == 'pasted-text'
    assert read['document']['chapter'] == '第一章'
    profile = {'version': 0, 'description': '数据结构', 'goals': '掌握基础', 'chapters': ['第一章', '第二章']}
    assert post(client, 'profile', profile).status_code == 200
    assert post(client, 'profile', profile).status_code == 409
    doc = read['document']
    assert post(client, 'organize', {'documentId': doc['id'], 'version': doc['version'], 'action': 'archive'}).status_code == 400
    archived = post(client, 'organize', {'documentId': doc['id'], 'version': doc['version'], 'action': 'archive', 'confirmed': True}).json()['document']
    assert not client.app.state.rag.sources(client.platform.scope('course-default'))
    answer = client.post('/api/agent', json={'courseId': 'course-default', 'question': '根据讲义解释栈', 'mode': 'ask', 'sources': []}).json()
    assert answer['sources'] == []
    historical = client.get('/api/platform/library/read?documentId='+document_id+'&version='+str(doc['version']), headers=client.platform_headers).json()
    assert historical['artifact'] == read['artifact']
    assert post(client, 'organize', {'documentId': doc['id'], 'version': archived['version'], 'action': 'restore', 'confirmed': True}).status_code == 200
    assert client.app.state.rag.sources(client.platform.scope('course-default'))
    excluded = client.post('/api/agent', json={'courseId': 'course-default', 'question': '根据讲义解释栈', 'documentIds': [], 'sources': []}).json()
    assert excluded['sources'] == []


def test_cross_course_reuse_has_new_evidence_and_independent_deletion(client):
    document_id, _ = import_text(client)
    p = client.platform
    p.repo.ensure_course(p.user_id, {'id': 'other', 'name': '其他课程'})
    doc = catalog(client)['documents'][0]
    response = post(client, 'reuse', {'documentId': document_id, 'version': doc['version'], 'targetCourseId': 'other', 'confirmed': True, 'idempotencyKey': 'reuse-1'})
    job = wait_job(client, response.json()['job'])
    copy_id = job['result']['documentId']
    assert copy_id != document_id
    copied = catalog(client, 'other')['documents'][0]
    assert copied['fileHash'] == doc['fileHash']
    assert {s['id'] for s in copied['chunks']}.isdisjoint(s['id'] for s in doc['chunks'])
    assert client.get('/api/platform/library/read?courseId=other&documentId='+document_id, headers=client.platform_headers).status_code == 404
    client.app.state.rag.remove(p.scope('course-default'), document_id, doc['version'])
    assert client.app.state.rag.sources(p.scope('other'))
    assert p.files.read(copied['fileHash'])


def test_url_job_persists_snapshot_and_refresh_retains_old_version(client, monkeypatch):
    monkeypatch.setattr('backend.xueya.library_http.fetch_snapshot', lambda url: {'text': '# 网页课程\n栈是后进先出的结构。', 'title': '公开讲义', 'originalUrl': url, 'finalUrl': url})
    value = {'url': 'https://example.org/course', 'confirmed': True, 'idempotencyKey': 'url-1'}
    response = post(client, 'url', value)
    outer = wait_job(client, response.json()['job'])
    parsed = wait_job(client, {'id': outer['result']['parseJobId']})
    old = catalog(client)['documents'][0]
    assert old['origin']['contentHash'] and old['origin']['capturedAt']
    assert post(client, 'url', {**value, 'idempotencyKey': 'url-2', 'previousDocumentId': old['id']}).status_code == 200
    for _ in range(180):
        rows = catalog(client)['documents']
        if len(rows) == 1 and rows[0]['id'] != old['id'] and rows[0].get('activeArtifact'):
            break
        time.sleep(.03)
    else:
        raise AssertionError('refreshed version was not published')
    read = client.get('/api/platform/library/read?documentId='+old['id'], headers=client.platform_headers).json()
    assert read['artifact']['text']


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://127.0.0.1/a', 'http://[::1]/a', 'http://169.254.169.254/meta', 'https://user:password@example.org', 'http://localhost/a'])
def test_web_import_rejects_private_and_unsafe_targets(url):
    with pytest.raises(AppError):
        public_target(url)


def test_dns_answers_are_all_validated_and_html_is_data(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443)), (socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))])
    with pytest.raises(AppError, match='PRIVATE_URL_FORBIDDEN'):
        public_target('https://example.org')
    parser = Extractor()
    parser.feed('<title>讲义</title><p>栈</p><script>stealSecrets()</script><p>队列</p>')
    assert 'stealSecrets' not in ''.join(parser.parts)
    assert '栈' in ''.join(parser.parts)


def test_fetch_pins_checked_ip_and_revalidates_redirect(monkeypatch):
    import backend.xueya.library_fetch as fetch
    connections = []
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 80))])
    class Sock:
        def close(self):
            pass
    monkeypatch.setattr(socket, 'create_connection', lambda target, **k: connections.append(target) or Sock())
    class Redirect:
        status = 302
        def getheader(self, name, default=None):
            return 'http://127.0.0.1/private' if name == 'Location' else default
    class Connection:
        def __init__(self, *a, **k):
            self.sock = None
        def request(self, *a, **k):
            pass
        def getresponse(self):
            return Redirect()
        def close(self):
            self.sock.close()
    monkeypatch.setattr(fetch.http.client, 'HTTPConnection', Connection)
    with pytest.raises(AppError, match='PRIVATE_URL_FORBIDDEN'):
        fetch.fetch_snapshot('http://example.org/lecture')
    assert connections == [('8.8.8.8', 80)]


def test_web_failure_keeps_existing_material_and_has_no_provider_calls(client, monkeypatch):
    document_id, _ = import_text(client)
    def fail(url):
        raise AppError('URL_NOT_ACCESSIBLE')
    monkeypatch.setattr('backend.xueya.library_http.fetch_snapshot', fail)
    response = post(client, 'url', {'url': 'https://example.org/private', 'previousDocumentId': document_id, 'confirmed': True, 'idempotencyKey': 'failed-web'})
    for _ in range(120):
        job = client.platform.jobs.get(response.json()['job']['id'], client.platform.user_id)
        if job['status'] == 'failed':
            break
        time.sleep(.03)
    assert job['status'] == 'failed'
    assert catalog(client)['documents'][0]['id'] == document_id
    assert client.app.state.rag.sources(client.platform.scope('course-default'))
    assert not client.platform.db.all('SELECT * FROM invocations')


def test_media_original_range_scope_and_real_location_link(client):
    doc_id, _ = import_text(client)
    headers = client.platform_headers
    upload = client.post('/api/learning/media/upload?name=lecture.wav&durationMs=2000', headers={**headers, 'Content-Type': 'audio/wav'}, content=b'RIFF-controlled-audio')
    assert upload.status_code == 200, upload.text
    media = upload.json()['result']
    doc = catalog(client)['documents'][0]
    value = {'documentId': doc_id, 'documentVersion': doc['version'], 'mediaId': media['id'], 'mediaVersion': 1, 'location': {'startMs': 100, 'endMs': 1500}, 'confirmed': True, 'idempotencyKey': 'link-1'}
    response = post(client, 'media-link', value)
    assert response.status_code == 200, response.text
    assert post(client, 'media-link', {**value, 'location': {'startMs': 0, 'endMs': 5000}}).status_code == 400
    response = client.get('/api/platform/library/media-original?id='+media['id']+'&version=1', headers={**headers, 'Range': 'bytes=0-3'})
    assert response.status_code == 206 and response.content == b'RIFF'
    assert catalog(client)['media'][0]['durationMs'] == 2000
