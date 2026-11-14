import asyncio

from scripts.sync_local_knowledge import inventory, install


def test_default_inventory_has_only_the_user_selected_markdown():
    items = inventory()
    assert len(items) == 1
    assert items[0]['name'] == '栈与队列知识库.md'
    assert items[0]['path'].parent.name == 'stack-queue'


def test_narrowing_retires_only_prior_import_and_retains_originals(platform):
    p = platform
    other = p.files.put(b'previous corpus original')
    p.repo.put(p.scope(), 'document', 'previous-import', {
        'id': 'previous-import', 'name': 'other.md', 'kind': 'md', 'fileHash': other['hash'],
        'status': '等待解析', 'chunks': [], 'origin': {'type': 'repository-corpus'}})
    result = asyncio.run(install(p, p.scope(), inventory()))
    assert result['summary']['documents'] == 1
    assert result['summary']['sources'] > 0
    assert result['retiredDocumentIds'] == ['previous-import']
    assert p.document(p.scope(), 'previous-import')['archived']
    assert p.files.read(other['hash']) == b'previous corpus original'
    assert all(row['onlySelectedFile'] for row in result['checks'])
    assert result['providerRequests'] == 0
    p.repo.ensure_course(p.user_id, {'id': 'course-default', 'name': '数据结构'})
    assert p.repo.courses(p.user_id)[0]['name'] == '数据结构'
    workspace = {'version': 3, 'activeId': 'course-default', 'courses': [
        {'id': 'course-default', 'name': '数据结构', 'data': {'documents': [], 'messages': []}}]}
    saved = p.repo.save_workspace(p.user_id, workspace)
    assert saved['data']['courses'][0]['name'] == '数据结构'
    assert p.repo.get_workspace(p.user_id)['data']['courses'][0]['name'] == '数据结构'
