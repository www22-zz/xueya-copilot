"""F independent acceptance fixtures, strict evidence metrics and a full durable loop."""
import asyncio
from datetime import date, timedelta

from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.backup import create_backup, restore_backup
from backend.xueya.config import Config
from backend.xueya.rag import parse_document
from backend.xueya.rag_eval import finish
from scripts.build_quality_materials import build
from scripts.check_quality import score_case


def test_original_material_formats_do_not_invent_scan_text(tmp_path):
    value = build(tmp_path/'materials')
    assert len(value['cases']) == 60 and sum(c['split'] == 'test' for c in value['cases']) == 46
    original = parse_document((tmp_path/'materials/structures.md').read_bytes(), 'md')
    assert {'table', 'code', 'formula'} <= {b['type'] for b in original['blocks']}
    docx = parse_document((tmp_path/'materials/lecture.docx').read_bytes(), 'docx')
    assert 'Queue' in docx['text'] and 'FIFO' in docx['text']
    assert 'first in, first out' in parse_document((tmp_path/'materials/lecture.pdf').read_bytes(), 'pdf')['text']
    scan = parse_document((tmp_path/'materials/scan-only.pdf').read_bytes(), 'pdf')
    assert not scan['text'].strip() and scan['pages'][0]['needsOcr']
    long = parse_document((tmp_path/'materials/long-chapter.md').read_bytes(), 'md')
    assert 'END_MARKER_40' in long['text']


def test_multiple_gold_evidence_requires_both_documents():
    case = {'gold': [{'document': 'a', 'quote': '正面声明'}, {'document': 'b', 'quote': '相反声明'}]}
    ids = {'a': 'a-id', 'b': 'b-id'}
    one = score_case(case, [{'documentId': 'a-id', 'quote': '正面声明'}], ids)
    assert not one['passed'] and one['matchedGold'] == 1
    assert score_case(case, [{'documentId': 'a-id', 'quote': '正面声明'}, {'documentId': 'b-id', 'quote': '相反声明'}], ids)['passed']
    assert not score_case({'gold': []}, [{'documentId': 'a-id', 'quote': '无关命中'}], ids)['passed']


def test_actual_course_learning_loop_survives_backup_restore(tmp_path):
    data, backup, restored = tmp_path/'data', tmp_path/'backup', tmp_path/'restored'
    with TestClient(create_app(Config(data_dir=data), start_jobs=False), base_url='http://127.0.0.1') as client:
        h = {'X-Xueya-Token': client.get('/api/platform/bootstrap').json()['token']}
        raw = '# 队列\n\n队列遵循先进先出，最早进入队列的元素最先离开。'
        result = client.post('/api/platform/documents/upload?name=queue.md', headers={**h, 'Idempotency-Key': 'f-course'}, content=raw.encode()).json()
        async def complete():
            p = client.app.state.platform
            job = p.jobs.get(result['job']['id'], p.user_id)
            return await finish(p, job)
        doc = client.portal.call(complete)['documentId']
        def post(path, body):
            response = client.post('/api/learning/'+path, headers=h, json=body)
            assert response.status_code == 200, response.text
            return response.json()['result']
        selection = {'documentIds': [doc]}
        sources = client.portal.call(client.app.state.learning.sources, {'courseId': 'course-default', 'selection': selection})
        source = next(s for s in sources if '先进先出' in s['quote'])
        answer = post('answers', {'selection': selection, 'question': '队列的次序是什么？'})
        assert answer['sources'] and answer['verification'] == 'verbatim-only'
        def adopt(draft, operation):
            return post('draft/adopt', {'draftId': draft['draftId'], 'operationId': operation, 'confirmed': True})
        summary = post('summary/preview', {'id': 'f-summary', 'selection': selection})
        adopt(summary, 'f-summary-adopt')
        note = post('note/preview', {'id': 'f-note', 'text': '我的理解：队列先进入的先离开。', 'title': '队列理解', 'expectedRevision': 0})
        adopt(note, 'f-note-adopt')
        q = post('questions/manual', {'id': 'f-q', 'operationId': 'f-q-create', 'expectedRevision': 0, 'selection': selection,
            'question': {'type': 'single', 'prompt': '队列按什么次序离开？', 'options': ['先进先出', '后进先出'],
                         'answer': 0, 'sourceId': source['id'], 'evidenceQuote': source['quote'], 'explanation': '最早进入者最先离开。'}})['content']
        post('questions/review', {'id': q['id'], 'expectedRevision': 1, 'expectedVersion': q['version'], 'operationId': 'f-q-review', 'approved': True, 'reason': '验收者逐字核对原文'})
        quiz = adopt(post('quiz/preview', {'id': 'f-quiz', 'questionIds': ['f-q'], 'count': 1, 'selection': selection}), 'f-quiz-adopt')
        attempt = post('attempts', {'id': 'f-attempt', 'quizId': quiz['id'], 'quizRevision': quiz['revision'], 'responses': [{'questionId': 'f-q', 'answer': 1}]})
        assert attempt['content']['events'][0]['grade']['score'] == 0
        event = attempt['content']['events'][0]
        corrected = post('diagnosis/correct', {'attemptId': 'f-attempt', 'eventId': event['id'], 'expectedRevision': 1,
                            'operationId': 'f-correct', 'cause': 'misread', 'reason': '重新核对后确认把次序看反了。'})
        assert corrected['content']['diagnoses'][0]['status'] == 'confirmed'
        adopt(post('card/preview', {'id': 'f-card', 'prompt': '队列的次序？', 'answer': '先进先出', 'selection': selection,
            'evidence': [{'sourceId': source['id'], 'quote': source['quote']}]}), 'f-card-adopt')
        rated = post('reviews/rate', {'id': 'f-card', 'expectedRevision': 1, 'operationId': 'f-rate', 'rating': 3})
        assert rated['content']['schedule']['algorithm'].startswith('py-fsrs')
        graph = {'courseId': 'course-default', 'concepts': [{'id': 'queue', 'courseId': 'course-default', 'name': '队列', 'aliases': [],
            'status': 'confirmed', 'evidence': [{'sourceId': source['id'], 'version': source['version'], 'quote': source['quote']}]}], 'edges': []}
        adopt(post('graph/preview', {'graph': graph, 'expectedRevision': 0, 'selection': selection}), 'f-graph-adopt')
        adopt(post('plan/preview', {'id': 'f-plan', 'selection': selection, 'examDate': (date.today()+timedelta(days=20)).isoformat(), 'minutes': 30}), 'f-plan-adopt')
        assert client.portal.call(client.app.state.learning.repo.get, 'course-default', 'f-plan')['kind'] == 'plan'
        create_backup(data, backup)
    restore_backup(backup, restored)
    with TestClient(create_app(Config(data_dir=restored), start_jobs=False), base_url='http://127.0.0.1') as client:
        host = client.app.state.learning
        for key, revision in [('f-card', 2), ('f-attempt', 2), ('f-note', 1), ('f-plan', 1)]:
            assert client.portal.call(host.repo.get, 'course-default', key)['revision'] == revision
