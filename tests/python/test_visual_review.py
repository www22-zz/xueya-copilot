import base64
import io
import time
import zipfile

from test_knowledge_base import wait, catalog

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jXioAAAAASUVORK5CYII=')


def slides(with_text_images=False):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('ppt/presentation.xml', '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldId r:id="r1"/><p:sldId r:id="r2"/><p:sldId r:id="r3"/></p:presentation>')
        z.writestr('ppt/_rels/presentation.xml.rels', '<Relationships>'+''.join(f'<Relationship Id="r{i}" Target="slides/slide{i}.xml"/>' for i in (1,2,3))+'</Relationships>')
        for i, body in [(1, '<p:pic><a:blip r:embed="img1"/></p:pic>'), (2, ''), (3, '<p:sp><a:p><a:t>原有正文：栈后进先出。</a:t></a:p></p:sp>')]:
            if i == 3 and with_text_images:
                body += '<p:pic><a:blip r:embed="img1"/><a:blip r:embed="img2"/></p:pic>'
            z.writestr(f'ppt/slides/slide{i}.xml', f'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:spTree>{body}</p:spTree></p:sld>')
        z.writestr('ppt/slides/_rels/slide1.xml.rels', '<Relationships><Relationship Id="img1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/></Relationships>')
        z.writestr('ppt/media/image1.png', PNG)
        if with_text_images:
            z.writestr('ppt/slides/_rels/slide3.xml.rels', '<Relationships>'+''.join(f'<Relationship Id="img{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image{i}.png"/>' for i in (1,2))+'</Relationships>')
            z.writestr('ppt/media/image2.png', PNG+b'fixture-two')
    return out.getvalue()


def post(client, operation, value):
    return client.post('/api/platform/knowledge/'+operation, headers=client.platform_headers, json=value)


def prepare(client, with_text_images=False):
    job = client.post('/api/platform/knowledge/upload', params={'name':'images.pptx'}, headers={**client.platform_headers, 'Idempotency-Key':'visual-file'}, content=slides(with_text_images)).json()['job']
    result = wait(client, job)
    assert result['status'] == 'succeeded', result
    document_id = result['result']['documentId']
    pack = client.get('/api/platform/knowledge/visual-pack', params={'documentId':document_id}, headers=client.platform_headers).json()['pack']
    value = {'documentId':document_id, 'version':pack['version'], 'fileHash':pack['fileHash'], 'reviewer':'assistant-in-session',
             'pages':[{'page':1,'kind':'transcription','text':'树的逻辑关系为双亲与孩子。','imageHashes':pack['pages'][0]['imageHashes']},
                      {'page':2,'kind':'blank','text':'','imageHashes':[]}]}
    return pack, value


def test_preview_apply_rebuild_preserves_original_and_is_idempotent(client):
    pack, value = prepare(client)
    old = client.app.state.rag.document(client.platform.scope(), pack['documentId'])
    preview = post(client, 'visual-preview', value).json()['preview']
    assert 'independent' not in preview
    assert client.app.state.rag.document(client.platform.scope(), pack['documentId'])['contentRevision'] == old['contentRevision']
    assert post(client, 'visual-apply', {'previewId':preview['previewId']}).json()['error'] == 'CONFIRMATION_REQUIRED'
    job = post(client, 'visual-apply', {'previewId':preview['previewId'],'confirmed':True}).json()['job']
    assert wait(client, job)['status'] == 'succeeded'
    repeat = post(client, 'visual-apply', {'previewId':preview['previewId'],'confirmed':True}).json()['job']
    assert repeat['id'] == job['id']
    doc = client.app.state.rag.document(client.platform.scope(), pack['documentId'])
    assert doc['fileHash'] == old['fileHash'] and doc['contentRevision'] == old['contentRevision']+1
    artifact = client.app.state.rag.artifact(client.platform.scope(), doc)
    assert artifact['pages'][1]['method'] == 'confirmed-empty-slide'
    assert not artifact['warnings']
    assert '原有正文：栈后进先出。' in artifact['text']
    assert any(s['method'] == 'assisted-visual-transcription' for s in doc['chunks'])
    assert any(s['method'] == 'ooxml-slide-order' for s in doc['chunks'])
    for s in doc['chunks']:
        assert artifact['text'][s['start']:s['end']] == s['quote']
        assert client.app.state.rag.validate(client.platform.scope(), client.app.state.rag.read(client.platform.scope(), s['id']))
    read = client.get('/api/platform/library/read', params={'documentId':pack['documentId'],'version':old['version']}, headers=client.platform_headers).json()
    assert read['artifact']['text'] == '\n\n原有正文：栈后进先出。'
    summary = catalog(client, 'course-default')['documents'][0]['review']
    assert summary['transcribedPages'] == [1] and summary['blankPages'] == [2] and not summary['pendingPages']
    assert not client.platform.db.all('SELECT * FROM invocations')


def test_forged_images_nonempty_pages_and_cross_course_rejected(client):
    pack, value = prepare(client)
    wrong = {**value,'pages':[{**value['pages'][0],'imageHashes':['a'*64]}]}
    assert post(client, 'visual-preview', wrong).json()['error'] == 'VISUAL_IMAGE_MISMATCH'
    assert post(client, 'visual-preview', {**value,'pages':[{'page':3,'kind':'blank','text':'','imageHashes':[]}]}).json()['error'] == 'VISUAL_PAGE_NOT_EMPTY'
    assert post(client, 'visual-preview', {**value,'pages':[{**value['pages'][0],'kind':'blank','text':''}]}).json()['error'] == 'INVALID_VISUAL_TEXT'
    client.platform.repo.ensure_course(client.platform.user_id, {'id':'other','name':'Other'})
    assert post(client, 'visual-preview', {**value,'courseId':'other'}).status_code == 404
    preview = post(client, 'visual-preview', value).json()['preview']
    assert post(client, 'visual-apply', {'previewId':preview['previewId'],'confirmed':True,'courseId':'other'}).status_code == 404


def test_stale_expired_and_duplicate_page_previews_rejected(client):
    pack, value = prepare(client)
    assert post(client, 'visual-preview', {**value,'pages':[value['pages'][0]]*2}).json()['error'] == 'INVALID_VISUAL_PAGE'
    preview = post(client, 'visual-preview', value).json()['preview']
    p = client.platform
    row = p.repo.read(p.scope(), 'artifact', preview['previewId'])
    p.repo.put(p.scope(), 'artifact', row['id'], {**row['value'],'expiresAt':time.time()-1}, row['version'])
    assert post(client, 'visual-apply', {'previewId':row['id'],'confirmed':True}).json()['error'] == 'VISUAL_PREVIEW_EXPIRED'
    p.repo.put(p.scope(), 'document', pack['documentId'], {**client.app.state.rag.document(p.scope(), pack['documentId']), 'chapter':'changed'})
    assert post(client, 'visual-apply', {'previewId':row['id'],'confirmed':True}).status_code == 409
    assert not p.db.all("SELECT * FROM jobs WHERE type='rag-visual-apply'")


def test_generic_jobs_cannot_publish_unconfirmed_visual_preview(client):
    _, value = prepare(client)
    preview = post(client, 'visual-preview', value).json()['preview']
    p = client.platform
    before = client.app.state.rag.document(p.scope(), value['documentId'])['contentRevision']
    job = p.jobs.submit(p.user_id, {'type':'rag-visual-apply','courseId':'course-default','resource':'cpu','maxAttempts':1,'idempotencyKey':'unconfirmed', 'input':{'previewId':preview['previewId']}})
    result = wait(client, job)
    assert result['status'] == 'failed' and result['error'] == 'VISUAL_CONFIRMATION_REQUIRED'
    assert client.app.state.rag.document(p.scope(), value['documentId'])['contentRevision'] == before


def test_cancel_and_explicit_cpu_retry_preserve_current_until_publish(client):
    pack, value = prepare(client)
    p = client.platform
    client.portal.call(p.jobs.stop)
    preview = post(client, 'visual-preview', value).json()['preview']
    job = post(client, 'visual-apply', {'previewId':preview['previewId'],'confirmed':True}).json()['job']
    assert job['status'] == 'queued'
    assert post(client, 'task', {'id':job['id'],'action':'cancel'}).json()['job']['status'] == 'cancelled'
    assert client.app.state.rag.document(p.scope(),pack['documentId'])['contentRevision'] == 1
    assert post(client, 'task', {'id':job['id'],'action':'retry'}).json()['job']['status'] == 'queued'
    client.portal.call(p.jobs.start)
    assert wait(client, job)['status'] == 'succeeded'
    assert client.app.state.rag.document(p.scope(),pack['documentId'])['contentRevision'] == 2
    assert not p.db.all('SELECT * FROM invocations')


def test_append_preserves_blocks_legacy_reviews_history_and_skips_decoration(client):
    pack, value = prepare(client, True)
    legacy = post(client, 'visual-preview', value).json()['preview']
    assert wait(client, post(client, 'visual-apply', {'previewId':legacy['previewId'],'confirmed':True}).json()['job'])['status'] == 'succeeded'
    p, rag = client.platform, client.app.state.rag
    old = rag.document(p.scope(), pack['documentId'])
    old_artifact = rag.artifact(p.scope(), old)
    pack = client.get('/api/platform/knowledge/visual-pack', params={'documentId':pack['documentId']}, headers=client.platform_headers).json()['pack']
    hashes = pack['pages'][2]['imageHashes']
    value.update(version=pack['version'], pages=[{'page':3,'kind':'supplement','imageHashes':hashes,'imageReviews':[
        {'imageHash':hashes[0],'kind':'diagram','text':'栈顶指针top随入栈增加。','partial':True},
        {'imageHash':hashes[1],'kind':'decorative','text':'不进入知识来源的装饰标记'}]}])
    preview = post(client, 'visual-preview', value).json()['preview']
    assert '栈顶指针' in preview['pages'][0]['text'] and '装饰标记' not in preview['pages'][0]['text']
    job = post(client, 'visual-apply', {'previewId':preview['previewId'],'confirmed':True}).json()['job']
    assert wait(client, job)['status'] == 'succeeded'
    new = rag.document(p.scope(), pack['documentId'])
    artifact = rag.artifact(p.scope(), new)
    assert artifact['text'].startswith(old_artifact['text'])
    assert artifact['pages'][0]['visualReview'] == old_artifact['pages'][0]['visualReview']
    assert artifact['pages'][1]['visualReview'] == old_artifact['pages'][1]['visualReview']
    assert '装饰标记' not in artifact['text'] and '部分转写' in artifact['text']
    for block in old_artifact['blocks']:
        preserved = next(b for b in artifact['blocks'] if b['text'] == block['text'])
        assert all(preserved[k] == block[k] for k in ('page','start','end','method','type'))
    assert all(artifact['text'][c['start']:c['end']] == c['quote'] for c in new['chunks'])
    assert rag.artifact(p.scope(),old)['text'] == old_artifact['text']
    value['version'] = new['version']
    assert post(client, 'visual-preview', value).json()['error'] == 'VISUAL_IMAGE_ALREADY_REVIEWED'
    assert post(client, 'visual-apply', {'previewId':preview['previewId'],'confirmed':True}).json()['job']['id'] == job['id']
    summary = catalog(client, 'course-default')['documents'][0]['review']
    assert summary['reviewedImages'] == 2 and summary['supplementedPages'] == [3] and summary['partialImages'] == 1
    assert not p.db.all('SELECT * FROM invocations')


def test_supplement_metadata_validation_and_unreadable_not_evidence(client):
    pack, value = prepare(client, True)
    sha = pack['pages'][2]['imageHashes'][0]
    row = {'page':3,'kind':'supplement','imageHashes':[sha],'imageReviews':[{'imageHash':sha,'kind':'unreadable','text':'字迹无法可靠转写','partial':True}]}
    value['pages'] = [row]
    for change, error in [({'imageHashes':['a'*64]}, 'VISUAL_IMAGE_MISMATCH'),
                           ({'imageReviews':row['imageReviews']*2}, 'VISUAL_IMAGE_MISMATCH'),
                           ({'text':'替换正文'}, 'INVALID_VISUAL_TEXT'),
                           ({'imageReviews':[{**row['imageReviews'][0],'kind':'unknown'}]}, 'INVALID_IMAGE_REVIEW'),
                           ({'imageReviews':[{**row['imageReviews'][0],'partial':'true'}]}, 'INVALID_IMAGE_REVIEW')]:
        assert post(client, 'visual-preview', {**value,'pages':[{**row,**change}]}).json()['error'] == error
    preview = post(client, 'visual-preview', value).json()['preview']
    job = post(client, 'visual-apply', {'previewId':preview['previewId'],'confirmed':True}).json()['job']
    assert wait(client,job)['status'] == 'succeeded'
    doc = client.app.state.rag.document(client.platform.scope(),pack['documentId'])
    assert '字迹' not in client.app.state.rag.artifact(client.platform.scope(),doc)['text']
    review = catalog(client,'course-default')['documents'][0]['review']
    assert review['unreadableImages'] == 1 and review['supplementedPages'] == []
