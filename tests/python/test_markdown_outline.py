import asyncio
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.markdown_outline import markdown_outline
from backend.xueya.rag import extract_chunks


def test_outline_uses_parsed_sections_in_document_order_not_code_headings():
    text = '# 线性表\n\n## LL01 顺序表\n\n连续存储。\n\n```cpp\n## 不是章节\n```\n\n### 实现细节\n\n插入要移动元素。\n\n## LL02 链表\n\n链式存储。'
    chunks = extract_chunks(text, {'id': 'doc-1', 'name': 'linear-list.md', 'kind': 'md'})
    nodes = markdown_outline('material-1', list(reversed(chunks)))
    assert [n['label'] for n in nodes] == ['顺序表', '链表']
    assert '连续存储' in nodes[0]['descriptions'][0]
    assert '插入要移动' in nodes[0]['descriptions'][0]
    assert all(n['sourceType'] == 'markdown-outline' and n['questionIds'] == [] for n in nodes)
    assert nodes == markdown_outline('material-1', chunks)


def test_graph_opens_local_markdown_without_generation_and_removes_withdrawn_nodes(tmp_path, http_root):
    app = create_app(Config(root=http_root, data_dir=tmp_path/'data', api_key='',
        preserve_legacy_data=True, auto_import_demo=False), start_jobs=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.post('/api/account/register', json={'username': 'alice', 'password': 'Fixture123', 'confirmPassword': 'Fixture123'})
        client.headers['X-Xueya-Token'] = client.get('/api/platform/bootstrap').json()['token']
        response = client.post('/api/platform/library/text', json={'courseId': 'course-default',
            'title': 'linear-list', 'chapter': '线性表与链表', 'text': '# 线性表\n\n## LL01 顺序表\n\n连续存储。\n\n## LL02 链表\n\n链式存储。', 'idempotencyKey': 'outline-import'})
        assert response.status_code == 200, response.text
        async def drain():
            p = app.state.platform
            p.jobs.stopped = False
            for _ in range(500):
                await p.jobs.tick()
                if not p.db.one("SELECT id FROM jobs WHERE status IN ('queued','running')"):
                    return
                await asyncio.sleep(.01)
            raise AssertionError('Parsing did not finish')
        asyncio.run(drain())
        p = app.state.platform
        revisions = p.db.one('SELECT count(*) AS n FROM revisions')['n']
        graph = client.get('/api/learning/space/course-graph').json()
        nodes = [n for n in graph['nodes'] if n['kind'] == 'concept']
        assert [n['label'] for n in nodes] == ['顺序表', '链表']
        assert graph['documents'][0]['title'] == '线性表与链表'
        assert graph['coverage']['outlineNodes'] == 2
        assert graph['coverage']['completedRanges'] == 0
        assert graph['coverage']['questions'] == 0
        assert p.db.one('SELECT count(*) AS n FROM revisions')['n'] == revisions
        assert not p.db.one('SELECT id FROM invocations')
        from backend.xueya.account_scope import account_owner
        from backend.xueya.common import Scope
        scope = Scope(user_id=account_owner({'username': 'alice'}), course_id='course-default')
        doc = p.repo.all(scope, 'document')[0]
        p.repo.put(scope, 'document', doc['id'], {**doc, 'archived': True}, doc['version'])
        assert not [n for n in client.get('/api/learning/space/course-graph').json()['nodes'] if n['kind'] == 'concept']
