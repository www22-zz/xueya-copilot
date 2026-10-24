"""Practice HTTP surface: idempotent ops, per-account isolation, note conflicts. No paid API."""
import json
import pytest
from backend.xueya import practice_bank
from backend.xueya.config import Config
from backend.xueya.app import create_app

SUBJECTS = ('数据结构与算法', '计算机网络', '操作系统', '数据库', '面向对象基础')


def fixture_bank(path):
    questions = []
    for i in range(1, 101):
        questions.append({'id': f'h100-{i:02d}', 'category': 'hot100', 'subject': '数据结构与算法', 'type': 'code',
                          'title': f'算法题{i}', 'prompt': f'题干{i}', 'difficulty': '简单',
                          'tags': ['数组'], 'explanation': '解析',
                          'samples': [{'input': '1', 'output': '1'}], 'dataRange': '1 <= n <= 10',
                          'hints': ['想一想', '再想想'], 'coreIdea': '核心思路',
                          'solutions': {'python': 'pass', 'cpp': 'int main(){}', 'java': 'class S{}'},
                          'complexity': {'time': 'O(n)', 'space': 'O(1)'}, 'pitfalls': '易错点',
                          'leetcodeUrl': 'https://leetcode.cn/problems/two-sum/'})
    for subject in SUBJECTS:
        code = {'数据结构与算法': 'dsa', '计算机网络': 'net', '操作系统': 'os', '数据库': 'db', '面向对象基础': 'oop'}[subject]
        for i in range(1, 11):
            questions.append({'id': f'b-{code}-s{i:02d}', 'category': 'basic', 'subject': subject, 'type': 'single',
                              'title': f'单选{i}', 'prompt': f'单选题干{i}', 'difficulty': '基础', 'tags': ['基础'],
                              'explanation': '解析', 'options': ['甲', '乙', '丙', '丁'], 'answer': 1})
            questions.append({'id': f'b-{code}-f{i:02d}', 'category': 'basic', 'subject': subject, 'type': 'fill',
                              'title': f'填空{i}', 'prompt': f'填空题干{i}', 'difficulty': '基础', 'tags': ['基础'],
                              'explanation': '解析', 'answer': '答案', 'acceptedAnswers': ['答案', 'answer']})
        for i in range(1, 11):
            questions.append({'id': f'i-{code}-{i:02d}', 'category': 'interview', 'subject': subject, 'type': 'short',
                              'title': f'面试{i}', 'prompt': f'面试题干{i}', 'difficulty': '基础', 'tags': ['基础'],
                              'explanation': '解析', 'answer': '一句话', 'keyPoints': ['点1', '点2', '点3'],
                              'followUps': ['追问1', '追问2']})
    path.write_text(json.dumps({'version': practice_bank.BANK_VERSION, 'questions': questions}, ensure_ascii=False),
                    encoding='utf-8')
    return path


@pytest.fixture
def app(tmp_path):
    bank = fixture_bank(tmp_path / 'bank.json')
    practice_bank.use(bank)
    application = create_app(Config(data_dir=tmp_path / 'data'), start_jobs=False)
    yield application
    practice_bank.use(None)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app, base_url='http://127.0.0.1') as c:
        token = c.get('/api/platform/bootstrap').json()['token']
        c.headers.update({'X-Xueya-Token': token})
        yield c


def store(app):
    return app.state.practice


def op(op_id, kind, question_id, payload=None):
    return {'opId': op_id, 'kind': kind, 'questionId': question_id, 'payload': payload or {}}


def test_bank_lists_all_250_in_fixed_order(client):
    response = client.get('/api/practice/bank')
    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is True
    assert body['version'] == practice_bank.BANK_VERSION
    assert len(body['questions']) == 250
    assert body['questions'][0]['id'] == 'h100-01'
    assert body['questions'][-1]['id'].startswith('i-')


def test_state_starts_empty_and_is_persisted(client):
    assert client.get('/api/practice/state').json()['statuses'] == {}
    assert client.post('/api/practice/ops', json={'ops': [
        op('op-1', 'answer', 'b-dsa-s01', {'result': 'wrong', 'questionType': 'single'})]}).json()['accepted'] == ['op-1']
    state = client.get('/api/practice/state').json()
    assert state['statuses']['b-dsa-s01']['status'] == 'wrong'
    assert state['statuses']['b-dsa-s01']['wrongCount'] == 1
    assert state['serverSeq'] == 1


def test_replayed_ops_are_duplicates_and_never_double_count(client):
    batch = {'ops': [op('op-1', 'answer', 'b-dsa-s01', {'result': 'wrong', 'questionType': 'single'})]}
    assert client.post('/api/practice/ops', json=batch).json()['accepted'] == ['op-1']
    again = client.post('/api/practice/ops', json=batch).json()
    assert again['accepted'] == []
    assert again['duplicates'] == ['op-1']
    assert again['statuses']['b-dsa-s01']['wrongCount'] == 1
    assert again['serverSeq'] == 1


def test_wrong_answer_auto_enters_wrong_book(client):
    body = client.post('/api/practice/ops', json={'ops': [
        op('op-1', 'answer', 'b-dsa-f01', {'result': 'wrong', 'questionType': 'fill'})]}).json()
    assert body['statuses']['b-dsa-f01']['status'] == 'wrong'


def test_fill_correction_reverts_this_increment_only(client):
    client.post('/api/practice/ops', json={'ops': [
        op('op-1', 'answer', 'b-dsa-f01', {'result': 'wrong', 'questionType': 'fill'}),
        op('op-2', 'answer', 'b-dsa-f01', {'result': 'wrong', 'questionType': 'fill'})]})
    body = client.post('/api/practice/ops', json={'ops': [
        op('op-3', 'correct', 'b-dsa-f01', {'questionType': 'fill'})]}).json()
    row = body['statuses']['b-dsa-f01']
    assert row['wrongCount'] == 1
    assert row['status'] == 'pending'


def test_master_conquer_reset_flow(client):
    client.post('/api/practice/ops', json={'ops': [
        op('op-1', 'answer', 'b-dsa-s01', {'result': 'wrong', 'questionType': 'single'})]})
    body = client.post('/api/practice/ops', json={'ops': [op('op-2', 'conquer', 'b-dsa-s01')]}).json()
    assert body['statuses']['b-dsa-s01']['status'] == 'mastered'
    body = client.post('/api/practice/ops', json={'ops': [op('op-3', 'reset', 'b-dsa-s01')]}).json()
    assert body['statuses']['b-dsa-s01']['status'] == 'pending'
    assert body['statuses']['b-dsa-s01']['wrongCount'] == 1


def test_unknown_question_is_rejected(client):
    body = client.post('/api/practice/ops', json={'ops': [op('op-1', 'master', 'nope')]}).json()
    assert body['ok'] is True
    assert body['rejected'] == [{'opId': 'op-1', 'error': 'UNKNOWN_QUESTION'}]
    assert body['accepted'] == []
    mixed = client.post('/api/practice/ops', json={'ops': [op('old-q', 'master', 'removed-question'),
        op('save-note', 'note-save', 'h100-01', {'text': 'bank upgrade cannot block this save', 'baseRevision': 0})]}).json()
    assert mixed['accepted'] == ['save-note'] and mixed['rejected'][0]['opId'] == 'old-q'
    assert mixed['notes']['h100-01']['text'] == 'bank upgrade cannot block this save'


def test_illegal_action_is_rejected_without_mutating(client):
    body = client.post('/api/practice/ops', json={'ops': [
        op('op-1', 'conquer', 'b-dsa-s01')]}).json()
    assert body['rejected'] and body['rejected'][0]['error']
    assert client.get('/api/practice/state').json()['statuses'] == {}


def test_note_save_and_conflict_keeps_both_copies(client):
    client.post('/api/practice/ops', json={'ops': [
        op('op-1', 'note-save', 'b-dsa-s01', {'text': '第一条', 'baseRevision': 0})]})
    body = client.post('/api/practice/ops', json={'ops': [
        op('op-2', 'note-save', 'b-dsa-s01', {'text': '另一浏览器', 'baseRevision': 0})]}).json()
    note = body['notes']['b-dsa-s01']
    assert note['text'] == '第一条'
    assert [c['text'] for c in note['conflicts']] == ['另一浏览器']
    fetched = client.get('/api/practice/notes/b-dsa-s01').json()['note']
    assert fetched['text'] == '第一条'
    assert len(fetched['conflicts']) == 1


def test_accounts_are_isolated(app, client):
    client.post('/api/practice/ops', json={'ops': [
        op('op-1', 'answer', 'b-dsa-s01', {'result': 'wrong', 'questionType': 'single'})]})
    state = store(app)
    assert state.state('alice')['statuses'] == {}
    state.accept('alice', [op('op-9', 'answer', 'b-dsa-s01', {'result': 'wrong', 'questionType': 'single'})])
    assert state.state('alice')['statuses']['b-dsa-s01']['wrongCount'] == 1
    assert state.state('local')['statuses']['b-dsa-s01']['wrongCount'] == 1


def test_notes_are_isolated_per_account(app, client):
    client.post('/api/practice/ops', json={'ops': [
        op('op-1', 'note-save', 'i-dsa-01', {'text': '本地账号笔记', 'baseRevision': 0})]})
    state = store(app)
    assert state.note('alice', 'i-dsa-01') is None
    assert state.note('local', 'i-dsa-01')['text'] == '本地账号笔记'


def test_batch_rejects_only_bad_ops(client):
    body = client.post('/api/practice/ops', json={'ops': [
        op('op-1', 'answer', 'b-dsa-s01', {'result': 'wrong', 'questionType': 'single'}),
        op('op-2', 'nonsense', 'b-dsa-s01'),
        op('op-3', 'master', 'h100-01')]}).json()
    assert body['accepted'] == ['op-1', 'op-3']
    assert len(body['rejected']) == 1
    assert body['statuses']['b-dsa-s01']['status'] == 'wrong'
    assert body['statuses']['h100-01']['status'] == 'mastered'


def test_offline_state_uses_operation_time_not_reconnect_order(client):
    newer = op('newer', 'master', 'h100-01')
    newer['clientTs'] = '2026-01-02T00:00:00.000Z'
    older = op('older', 'mark-wrong', 'h100-01')
    older['clientTs'] = '2026-01-01T00:00:00.000Z'
    assert client.post('/api/practice/ops', json={'ops': [newer]}).json()['accepted'] == ['newer']
    result = client.post('/api/practice/ops', json={'ops': [older]}).json()
    assert result['statuses']['h100-01']['status'] == 'mastered'
    assert result['statuses']['h100-01']['wrongCount'] == 0


def test_resolving_note_conflict_is_persisted_and_not_only_hidden_locally(client):
    client.post('/api/practice/ops', json={'ops': [
        op('note-a', 'note-save', 'h100-01', {'text': 'A', 'baseRevision': 0}),
        op('note-b', 'note-save', 'h100-01', {'text': 'B', 'baseRevision': 0})]})
    result = client.post('/api/practice/ops', json={'ops': [
        op('resolve', 'note-save', 'h100-01', {'text': 'B', 'baseRevision': 2, 'resolve': True})]}).json()
    assert result['notes']['h100-01']['text'] == 'B'
    assert result['notes']['h100-01']['conflicts'] == []
    assert client.get('/api/practice/state').json()['notes']['h100-01']['conflicts'] == []


def test_real_registered_accounts_do_not_share_practice_state(client):
    for username in ('practicealice', 'practicebob'):
        registered = client.post('/api/account/register', json={
            'username': username, 'password': 'Password123', 'confirmPassword': 'Password123'})
        assert registered.status_code == 200
        state = client.get('/api/practice/state').json()
        assert state['statuses'] == {} and state['notes'] == {}
        client.post('/api/practice/ops', json={'ops': [op(username, 'master', 'h100-01')]})
        assert client.get('/api/practice/state').json()['statuses']['h100-01']['status'] == 'mastered'


def test_corrections_target_distinct_attempts_and_cannot_correct_another_question(client):
    q = 'b-dsa-f01'
    def submit(*ops):
        return client.post('/api/practice/ops', json={'ops': list(ops)}).json()
    submit(op('wrong-A', 'answer', q, {'questionType': 'fill', 'result': 'wrong'}),
           op('wrong-B', 'answer', q, {'questionType': 'fill', 'result': 'wrong'}))
    first = submit(op('correct-A', 'correct', q, {'questionType': 'fill', 'attemptId': 'wrong-A'}))
    assert first['statuses'][q]['wrongCount'] == 1
    second = submit(op('correct-B', 'correct', q, {'questionType': 'fill', 'attemptId': 'wrong-B'}))
    assert second['accepted'] == ['correct-B'] and second['statuses'][q]['wrongCount'] == 0
    repeat = submit(op('repeat-A', 'correct', q, {'questionType': 'fill', 'attemptId': 'wrong-A'}))
    assert repeat['statuses'][q]['correctCount'] == 2
    invalid = submit(op('other-question', 'correct', 'b-dsa-f02', {'questionType': 'fill', 'attemptId': 'wrong-A'}),
                     op('good-note', 'note-save', 'h100-01', {'text': 'not blocked', 'baseRevision': 0}))
    assert invalid['rejected'][0]['error'] == 'INVALID_CORRECTION_ATTEMPT'
    assert invalid['notes']['h100-01']['text'] == 'not blocked'
