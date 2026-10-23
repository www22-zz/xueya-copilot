import hashlib
import json

import pytest

from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.visual_review import ppt_images
from conftest import live_server
from scripts.import_course_bundle import import_bundle, load_bundle, local_url
from test_visual_review import slides


def make_bundle(root):
    root.mkdir()
    original = root/'lecture.pptx'
    original.write_bytes(slides(True))
    sha = hashlib.sha256(original.read_bytes()).hexdigest()
    images, _ = ppt_images(original.read_bytes())
    reviews = {'schemaVersion': 1, 'reviewer': 'assistant-in-session', 'documents': [
        {'fileHash': sha, 'name': original.name, 'pages': [
            {'page': 1, 'kind': 'transcription', 'text': '双亲与孩子构成树结构。', 'imageHashes': images[1]},
            {'page': 2, 'kind': 'blank', 'text': '', 'imageHashes': []},
            {'page': 3, 'kind': 'supplement', 'imageHashes': images[3], 'imageReviews': [
                {'imageHash': images[3][0], 'kind': 'diagram', 'text': '栈顶指针top示意。', 'partial': True},
                {'imageHash': images[3][1], 'kind': 'decorative', 'text': '装饰背景', 'partial': False}]}]}]}
    (root/'reviews.json').write_text(json.dumps(reviews), encoding='utf-8')
    manifest = {'schemaVersion': 1, 'name': 'Shared bundle', 'visualReviews': {'path': 'reviews.json',
        'sha256': hashlib.sha256((root/'reviews.json').read_bytes()).hexdigest()}, 'documents': [
        {'name': original.name, 'path': original.name, 'sha256': sha, 'size': original.stat().st_size, 'pages': 3, 'expectedSources': 3}]}
    (root/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


def test_bundle_replay_on_fresh_host_is_idempotent_and_preserves_private_records(tmp_path):
    bundle = tmp_path/'bundle'
    make_bundle(bundle)
    app = create_app(Config(data_dir=tmp_path/'server'))
    with live_server(app) as url:
        p, rag = app.state.platform, app.state.rag
        p.repo.put(p.scope(), 'note', 'private-note', {'text': '私人旧笔记'}, 0)
        result = import_bundle(bundle, url)
        assert result['status'] == 'passed' and result['summary']['sources'] == 3
        scope = p.scope(result['courseId'])
        doc_id = result['documents'][0]['documentId']
        doc = rag.document(scope, doc_id)
        artifact = rag.artifact(scope, doc)
        assert '原有正文：栈后进先出。' in artifact['text'] and '栈顶指针top' in artifact['text']
        assert '装饰背景' not in artifact['text'] and artifact['pages'][2]['imageReviews'][0]['partial']
        version = doc['version']
        jobs = p.db.one('SELECT COUNT(*) AS n FROM jobs')['n']
        repeat = import_bundle(bundle, url)
        assert repeat['courseId'] == result['courseId']
        assert repeat['documents'][0]['newReviewJobs'] == 0
        assert p.db.one('SELECT COUNT(*) AS n FROM jobs')['n'] == jobs
        assert rag.document(scope, doc_id)['version'] == version
        assert p.repo.read(p.scope(), 'note', 'private-note')['value']['text'] == '私人旧笔记'
        # A changed caption cannot silently replace a previously adopted one.
        review_path = bundle/'reviews.json'
        reviews = json.loads(review_path.read_text())
        reviews['documents'][0]['pages'][2]['imageReviews'][0]['text'] = '另一种转写'
        review_path.write_text(json.dumps(reviews), encoding='utf-8')
        manifest = json.loads((bundle/'manifest.json').read_text())
        manifest['visualReviews']['sha256'] = hashlib.sha256(review_path.read_bytes()).hexdigest()
        (bundle/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        with pytest.raises(ValueError, match='COURSE_BUNDLE_REVIEW_CONFLICT'):
            import_bundle(bundle, url)
        assert rag.document(scope, doc_id)['version'] == version
        assert not p.db.all('SELECT * FROM invocations')


def test_bundle_preflight_rejects_modified_originals_review_hashes_and_paths(tmp_path):
    bundle = tmp_path/'bundle'
    manifest = make_bundle(bundle)
    assert len(load_bundle(bundle)[2]) == 1
    original = bundle/'lecture.pptx'
    raw = original.read_bytes()
    original.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
    with pytest.raises(ValueError, match='BUNDLE_ORIGINAL_HASH_MISMATCH'):
        load_bundle(bundle)
    original.write_bytes(raw)
    manifest['visualReviews']['sha256'] = '0'*64
    (bundle/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='BUNDLE_REVIEW_HASH_MISMATCH'):
        load_bundle(bundle)
    manifest['visualReviews']['path'] = '../reviews.json'
    (bundle/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='INVALID_BUNDLE_PATH'):
        load_bundle(bundle)
    for target in ('https://example.com', 'http://127.0.0.1@evil.example', 'http://localhost/path', 'http://127.0.0.1/?secret=1'):
        with pytest.raises(ValueError, match='LOCAL_HTTP_HOST_REQUIRED'):
            local_url(target)
