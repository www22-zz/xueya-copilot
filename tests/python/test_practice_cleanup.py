"""The one-time practice cleanup deletes the old learning data and nothing else (PRD 14)."""
import json
from backend.xueya.common import dumps, utc_now
from backend.xueya.database import Database
from backend.xueya.repository import Repository
from backend.xueya.practice_cleanup import MARKER, cleanup


def seed(db, repo):
    user = 'local-user'
    repo.ensure_course(user, {'id': 'course-default', 'name': '数据结构'})
    scope = type('S', (), {'user_id': user, 'course_id': 'course-default'})()
    repo.put(scope, 'document', 'doc-1', {'id': 'doc-1', 'name': '讲义.md', 'kind': 'md', 'status': '已解析，可检索', 'chunks': [], 'tags': [], 'meta': 'x'})
    repo.put(scope, 'source', 'src-1', {'id': 'src-1', 'title': '讲义.md', 'quote': '原文', 'documentId': 'doc-1'})
    repo.put(scope, 'note', 'old-note', {'id': 'old-note', 'text': '旧笔记'})
    repo.put(scope, 'question', 'old-q', {'id': 'old-q', 'prompt': 'AI 生成题'})
    repo.put(scope, 'plan', 'old-plan', {'id': 'old-plan', 'days': []})
    repo.put(scope, 'concept', 'old-graph', {'id': 'old-graph', 'name': '旧图谱'})
    repo.put(scope, 'artifact', 'old-package', {'id': 'old-package', 'kind': 'learning-package', 'title': '旧学习包'})
    repo.put(scope, 'run', 'run-1', {'id': 'run-1', 'status': 'completed'})
    db.execute('INSERT INTO meta(key,value) VALUES(?,?)', ('local-account-v1', dumps({'username': 'team'})))
    db.execute('INSERT INTO meta(key,value) VALUES(?,?)', ('account-v2:abc', dumps({'username': 'alice'})))
    db.execute('INSERT INTO meta(key,value) VALUES(?,?)', ('learning:preview:x', dumps({})))
    db.execute('INSERT INTO meta(key,value) VALUES(?,?)', ('practice:op:team:op-1', dumps({})))
    db.execute('INSERT INTO workspaces VALUES(?,?,?,?)',
               (user, 3, dumps({'version': 3, 'activeId': 'course-default', 'courses': [
                   {'id': 'course-default', 'name': '数据结构', 'data': {
                       'documents': [], 'messages': [], 'sessions': [], 'sessionId': '', 'courseId': 'course-default',
                       'libraryTags': [], 'mediaResults': [], 'cards': [], 'plan': [], 'bank': [], 'records': [],
                       'reviewLog': [], 'notes': {'q': 'x'}}}]}), utc_now()))
    return user


def test_cleanup_removes_old_learning_data_and_keeps_accounts_materials_and_answers(tmp_path):
    db = Database(tmp_path / 'workspace.sqlite')
    try:
        repo = Repository(db)
        user = seed(db, repo)

        first = cleanup(db, repo, dry_run=True)
        assert first['entities'] >= 4 and first['artifacts'] == 1
        assert db.one('SELECT id FROM entities WHERE kind=? AND id=?', ('note', 'old-note')) is not None

        counts = cleanup(db, repo)
        assert counts['entities'] >= 4 and counts['artifacts'] == 1 and counts['meta'] >= 2

        for kind, entity_id in [('note', 'old-note'), ('question', 'old-q'), ('plan', 'old-plan'), ('concept', 'old-graph')]:
            row = db.one('SELECT deleted FROM entities WHERE kind=? AND id=?', (kind, entity_id))
            assert row['deleted'] == 1, (kind, entity_id)
        assert db.one("SELECT deleted FROM entities WHERE kind='artifact' AND id='old-package'")['deleted'] == 1

        # 账号、课程资料、问答记录必须原样保留
        assert db.one("SELECT id FROM entities WHERE kind='document' AND id='doc-1' AND deleted=0") is not None
        assert db.one("SELECT id FROM entities WHERE kind='source' AND id='src-1' AND deleted=0") is not None
        assert db.one("SELECT id FROM entities WHERE kind='run' AND id='run-1' AND deleted=0") is not None
        assert db.one("SELECT value FROM meta WHERE key='local-account-v1'") is not None
        assert db.one("SELECT value FROM meta WHERE key='account-v2:abc'") is not None

        # 已删模块的 meta 被清掉
        assert db.one("SELECT key FROM meta WHERE key='learning:preview:x'") is None
        assert db.one("SELECT key FROM meta WHERE key='practice:op:team:op-1'") is None

        # 工作区快照里只留存活字段，旧字段无法写回
        ws = json.loads(db.one('SELECT data FROM workspaces WHERE user_id=?', (user,))['data'])
        data = ws['courses'][0]['data']
        assert set(data) == {'documents', 'messages', 'sessions', 'sessionId', 'courseId', 'libraryTags', 'mediaResults'}
    finally:
        db.close()


def test_cleanup_is_one_time_only(tmp_path):
    db = Database(tmp_path / 'workspace.sqlite')
    try:
        repo = Repository(db)
        seed(db, repo)
        cleanup(db, repo)
        db.execute('INSERT INTO meta(key,value) VALUES(?,?)', (MARKER, dumps({'doneAt': utc_now()})))
        assert db.one('SELECT value FROM meta WHERE key=?', (MARKER,)) is not None
    finally:
        db.close()


def test_supplemental_purge_removes_retired_revisions_but_keeps_new_bank_and_chat(tmp_path):
    from backend.xueya.practice_cleanup import purge_retired_learning
    from backend.xueya.common import Scope
    db = Database(tmp_path / 'workspace.sqlite')
    try:
        repo = Repository(db)
        seed(db, repo)
        repo.ensure_course('practice:alice', {'id': 'practice-global', 'name': '练习'})
        scope = Scope(user_id='practice:alice', course_id='practice-global')
        repo.put(scope, 'event', 'new-practice', {'id': 'new-practice', 'action': 'master'})
        purge_retired_learning(db)
        assert db.one("SELECT id FROM entities WHERE id='old-note'") is None
        assert db.one("SELECT id FROM revisions WHERE id='old-note'") is None
        assert db.one("SELECT id FROM entities WHERE id='new-practice'") is not None
        assert db.one("SELECT id FROM entities WHERE id='doc-1'") is not None
        assert db.one("SELECT user_id FROM workspaces") is not None
        purge_retired_learning(db)
        assert db.one("SELECT id FROM entities WHERE id='new-practice'") is not None
    finally:
        db.close()


def test_residue_cleanup_removes_jobs_checkpoints_and_raw_backups_only(tmp_path):
    from backend.xueya.practice_cleanup import purge_retired_residue
    db = Database(tmp_path / 'residue.sqlite')
    try:
        repo = Repository(db)
        user = seed(db, repo)
        keep = {'documents': [{'id': 'keep', 'notes': 'document metadata'}],
                'messages': [{'role': 'user', 'text': 'keep conversation'}],
                'cards': [{'text': 'REMOVE_NOTE'}], 'bank': [{'id': 'REMOVE_QUESTION'}]}
        envelope = {'workspace': {'version': 3, 'courses': [{'data': keep}]},
                    'raw': {'xueya-copilot-state-v1': dumps(keep)}}
        db.execute('INSERT INTO imports VALUES(?,?,?,?,?)', (user, 'old', dumps(envelope), 1, utc_now()))
        for name, kind in [('retired', 'learning-chapter'), ('keep-parse', 'parse-document')]:
            db.execute('INSERT INTO jobs(id,user_id,course_id,type,input,resource,status,max_attempts,idempotency_key,available_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (name,user,'course-default',kind,dumps({'secret':'old chapter'}),'cpu','succeeded',1,name,0,utc_now(),utc_now()))
            db.execute('INSERT INTO job_events(job_id,event,at) VALUES(?,?,?)',(name,'{}',utc_now()))
        purge_retired_residue(db)
        assert db.one("SELECT id FROM jobs WHERE id='retired'") is None
        assert db.one("SELECT job_id FROM job_events WHERE job_id='retired'") is None
        assert db.one("SELECT id FROM jobs WHERE id='keep-parse'") is not None
        backup = db.one('SELECT backup FROM imports')['backup']
        assert 'REMOVE_NOTE' not in backup and 'REMOVE_QUESTION' not in backup
        assert 'keep conversation' in backup and 'document metadata' in backup
        assert db.one("SELECT id FROM entities WHERE id='doc-1'") is not None
        assert db.one("SELECT value FROM meta WHERE key='local-account-v1'") is not None
        purge_retired_residue(db)
    finally:
        db.close()
