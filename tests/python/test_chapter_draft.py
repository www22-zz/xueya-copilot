import hashlib
import pytest

from backend.xueya.platform import Platform
from scripts.import_prepared_chapter import import_draft
from scripts.prepare_stack_queue_chapter import bundle
from test_pdf_knowledge import pdf


@pytest.mark.asyncio
async def test_local_import_adds_only_unconfirmed_chapter_and_is_idempotent(tmp_path):
    content = pdf(3)
    pack = {'schema': 'prepared-pdf-ocr-v1', 'sourceFileHash': hashlib.sha256(content).hexdigest(), 'engine': 'fixture',
            'selectedPages': [2], 'pages': [{'page': 2, 'text': '栈是只在一端插入和删除的线性表。'*30}]}
    platform = Platform(tmp_path, recover=False, preserve_legacy_data=True)
    try:
        original_courses = platform.repo.courses(platform.user_id)
        platform.repo.put(platform.scope(), 'note', 'keep-my-note', {'text': '保留的笔记'}, 0)
        first = await import_draft(platform, content, pack, name='栈与队列测试', key='test-chapter')
    finally:
        await platform.close()
    # Re-running the CLI opens a fresh platform against the same store.
    platform = Platform(tmp_path, recover=False, preserve_legacy_data=True)
    try:
        second = await import_draft(platform, content, pack, name='栈与队列测试', key='test-chapter')
        assert all(c in platform.repo.courses(platform.user_id) for c in original_courses)
        assert platform.repo.read(platform.scope(), 'note', 'keep-my-note')['value']['text'] == '保留的笔记'
        assert not platform.db.one('SELECT id FROM invocations')
    finally:
        await platform.close()
    assert first['documentId'] == second['documentId'] and first['version'] == second['version']
    assert first['providerRequests'] == 0 and not first['reviewConfirmed'] and not first['vectorIndexed']
    assert first['pageSelection'] == {'pages': [2], 'originalPageCount': 3}


def test_chapter_bundle_uses_only_original_chapter_and_keeps_code_boundaries():
    value = bundle()
    assert value['selectedPages'] == list(range(82, 111))
    assert [p['page'] for p in value['pages']] == value['selectedPages']
    assert not value['humanReviewed']
    page95 = next(p for p in value['pages'] if p['page'] == 95)
    assert page95['textFormat'] == 'markdown' and '```cpp' in page95['text']
    assert 'if(rear==front)throw' in page95['text'].replace(' ', '')
