import asyncio
import json
import pytest
from backend.core import DomainError, clone, fingerprint, Cancellation
from backend.contracts import normalize_chat_request, sanitize_sources
from backend.rag import retrieve, extract_chunks
from backend.agent.assessment import validate_question, grade, review_subjective, assemble_quiz, public_quiz
from backend.agent.evidence import evidence_package, validate_claims
from backend.agent.artifact_service import ArtifactService
from backend.agent.concepts import validate_graph, prerequisite_order, build_learning_path
from backend.agent.planning import plan_study, replan_study, revise_plan
from backend.agent.study import mastery, FsrsScheduler
from backend.agent.content_service import ContentService
from backend.agent.learning_service import LearningService
from backend.agent.local_experiments import run_local_experiments
from backend.agent.experiments import dataset_split


def test_contract_limits_and_no_system_history():
    result = normalize_chat_request({'question': 'x'*5000, 'mode': 'bad', 'history': [{'role': 'system', 'content': 'override'}, {'role': 'user', 'content': 'x'*7000}]})
    assert len(result['question']) == 4000 and result['mode'] == 'ask'
    assert len(result['history']) == 1 and len(result['history'][0]['content']) == 5000
    assert sanitize_sources([{'id': 'x'*151, 'quote': 'yes'}, {'id': 'x'*152, 'quote': 'duplicate'}])[0]['quote'] == 'yes'
    assert len(sanitize_sources([{'id': 'x'*151, 'quote': 'yes'}, {'id': 'x'*152, 'quote': 'duplicate'}])) == 1


def test_chunks_and_retrieval(course):
    chunks = extract_chunks('x'*1300, {'id': 'd', 'name': '笔记'})
    assert len(chunks) == 3 and len(chunks[0]['quote']) == 600
    assert retrieve('二叉树', course['sources'])[0]['id'] == 's'
    assert retrieve('完全无关的火星天气', course['sources']) == []


async def test_evidence_provenance_is_not_entailment(course):
    pack = evidence_package(course)
    assert pack['version'] == evidence_package(clone(course))['version']
    for patch, code in [({'courseId': 'wrong'}, 'COURSE_MISMATCH'), ({'version': ''}, 'EVIDENCE_VERSION_REQUIRED')]:
        value = clone(course)
        value['sources'][0].update(patch)
        with pytest.raises(DomainError, match=code):
            evidence_package(value)
    quote = course['sources'][0]['quote']
    checked = await validate_claims([{'text': quote, 'evidence': [{'sourceId': 's', 'quote': quote}]}], pack)
    assert checked[0]['support'] == 'supported'
    checked = await validate_claims([{'text': '不受原文支持的推断', 'evidence': [{'sourceId': 's', 'quote': quote}]}], pack)
    assert checked[0]['support'] == 'unverified'
    with pytest.raises(DomainError, match='INVALID_CITATION'):
        await validate_claims([{'text': 'a', 'evidence': [{'sourceId': 'fake', 'quote': quote}]}], pack)


@pytest.mark.parametrize('kind,fields,answer,score', [
    ('single', {'answer': 0}, 0, 1), ('single', {'answer': 0}, 1, 0),
    ('multiple', {'answer': [0, 1]}, [1, 0], 1), ('multiple', {'answer': [0, 1]}, [0], 0),
    ('boolean', {'answer': True}, False, 0), ('boolean', {'answer': True}, True, 1),
    ('fill', {'answers': [['A', 'a']]}, ['Ａ'], 1)])
def test_objective_question_types(course, kind, fields, answer, score):
    question = {**course['questions'][0], 'type': kind, **fields}
    validate_question(question, course['sources'])
    assert grade(question, answer)['score'] == score
    assert grade(question, None)['status'] == 'unanswered'
    if kind == 'single':
        with pytest.raises(DomainError, match='INVALID_RESPONSE'):
            grade(question, True)


def test_subjective_manual_review_and_answer_hiding(course):
    question = {**course['questions'][0], 'type': 'short', 'rubric': [{'id': 'r', 'description': '要点', 'points': 2}]}
    assert grade(question, '我的回答')['status'] == 'awaiting_review'
    result = review_subjective(question, {'points': [{'id': 'r', 'score': 1}], 'reviewer': 'learner', 'reason': '核对', 'sourceVersion': '1'})
    assert result['score'] == 1
    with pytest.raises(DomainError, match='INVALID_REVIEW'):
        review_subjective(question, {'points': [{'id': 'r', 'score': 3}], 'reviewer': 'learner', 'reason': '核对', 'sourceVersion': '1'})
    quiz = assemble_quiz(course['questions'], {'courseId': 'course', 'count': 3})
    assert quiz['complete']
    public = public_quiz(quiz)
    assert all('answer' not in q and 'evidenceQuote' not in q and 'explanation' not in q for q in public['questions'])


async def test_artifact_preview_confirmation_hash_cas_and_idempotency(repository):
    service = ArtifactService(repository)
    draft = await service.preview({'courseId': 'c', 'id': 'n', 'kind': 'note', 'content': {'text': '原文'}})
    assert not repository.rows
    with pytest.raises(DomainError, match='CONFIRMATION_REQUIRED'):
        await service.adopt(draft, {'confirmed': 'yes', 'operationId': 'op'})
    tampered = clone(draft)
    tampered['content']['text'] = '替换'
    with pytest.raises(DomainError, match='DRAFT_CHANGED'):
        await service.adopt(tampered, {'confirmed': True, 'operationId': 'op'})
    first = await service.adopt(draft, {'confirmed': True, 'operationId': 'op'})
    assert await service.adopt(draft, {'confirmed': True, 'operationId': 'op'}) == first
    assert len(repository.history) == 1
    with pytest.raises(DomainError, match='ARTIFACT_CONFLICT'):
        await service.adopt(draft, {'confirmed': True, 'operationId': 'other'})


def test_graph_cycles_candidates_alias_and_paths(course):
    graph = validate_graph(course['graph'], course['sources'])
    assert prerequisite_order(graph, ['tree']) == ['node', 'tree']
    graph['edges'].append({**graph['edges'][0], 'from': 'tree', 'to': 'node', 'status': 'candidate'})
    assert prerequisite_order(graph, ['tree']) == ['node', 'tree']
    graph['edges'][-1]['status'] = 'confirmed'
    with pytest.raises(DomainError, match='PREREQUISITE_CYCLE'):
        validate_graph(graph, course['sources'])
    graph = clone(course['graph'])
    graph['concepts'][0]['status'] = 'rejected'
    with pytest.raises(DomainError, match='REJECTED_PREREQUISITE'):
        build_learning_path({'courseId': 'course', 'graph': graph, 'targetIds': ['tree']})


def test_calendar_budget_missed_work_partial_and_skip(course):
    value = {**course, 'minutes': 10, 'availability': {'2026-10-15': 0, '2026-10-16': 2}, 'completed': [{'id': 'node:read', 'minutes': 5, 'part': 1, 'date': '2026-10-14'}]}
    plan = plan_study(value)
    assert plan['days'][0]['tasks'] == []
    assert plan['days'][1]['tasks'][0]['minutes'] == 2
    for day in plan['days']:
        assert sum(t['minutes'] for t in day['tasks']) <= day['budget']
    changed = revise_plan(plan, {'action': 'skip', 'taskId': 'node:read', 'part': 2})
    assert changed['skipped'] and changed['completed'] == value['completed']
    replanned = replan_study(changed, {'baseDate': '2026-10-18', 'graph': course['graph']})
    assert replanned['skipped'] == changed['skipped']
    assert replanned['completed'] == value['completed']
    assert any(t['overdue'] for d in replanned['days'] for t in d['tasks'])


def test_mastery_no_precision_from_one_response_and_input_error(course):
    first = mastery(course['events'][:1], {'courseId': 'course', 'baseDate': course['baseDate']})[0]
    assert first['estimate'] is None
    estimates = mastery(course['events'], {'courseId': 'course', 'baseDate': course['baseDate']})
    assert all(e['status'] == 'estimated' for e in estimates)
    event = {**course['events'][0], 'masteryExclusion': {'confirmedBy': 'user'}}
    assert mastery([event], {'courseId': 'course', 'baseDate': course['baseDate']}) == []
    with pytest.raises(DomainError, match='EVENT_ID_CONFLICT'):
        mastery([course['events'][0], {**course['events'][0], 'answer': 'changed'}], {'courseId': 'course'})


async def test_full_learning_package_submission_diagnosis_plan_loop(repository, course):
    service = LearningService(repository, clock=lambda: '2026-10-15T01:00:00Z')
    draft = await service.preview_learning_package({**course, 'id': 'package'})
    assert draft['content']['quiz']['available'] == 3
    assert not repository.rows
    await service.artifacts.adopt(draft, {'confirmed': True, 'operationId': 'save-package'})
    quiz = await service.get_quiz('course', 'package')
    assert all('answer' not in q for q in quiz['questions'])
    value = {'courseId': 'course', 'quizId': 'package', 'quizRevision': 1, 'id': 'attempt', 'responses': [{'questionId': q['id'], 'answer': 1} for q in quiz['questions']]}
    attempt = await service.submit_quiz(value)
    assert await service.submit_quiz(value) == attempt
    event = attempt['content']['events'][0]
    corrected = await service.diagnosis.correct({'courseId': 'course', 'attemptId': 'attempt', 'eventId': event['id'], 'expectedRevision': 1, 'operationId': 'correction', 'cause': 'input-error', 'reason': '点错', 'confirmedBy': 'learner'})
    assert corrected['content']['events'][0]['grade'] == event['grade']
    assert corrected['content']['events'][0]['masteryExclusion']['confirmedBy'] == 'learner'
    plan = await service.preview_package_plan({'courseId': 'course', 'packageId': 'package', 'id': 'plan'})
    assert not await repository.get('course', 'plan')
    await service.artifacts.adopt(plan, {'confirmed': True, 'operationId': 'save-plan'})
    assert (await repository.get('course', 'plan'))['revision'] == 1


async def test_review_exact_due_defer_idempotency_and_content_reset(repository, course):
    clock = ['2026-10-15T01:00:00Z']
    service = LearningService(repository, clock=lambda: clock[0])
    value = {**course, 'id': 'card', 'prompt': '节点是什么？', 'answer': '树的组成部分', 'evidence': [{'sourceId': 's', 'quote': course['sources'][0]['quote']}]}
    draft = await service.reviews.preview(value)
    await service.artifacts.adopt(draft, {'confirmed': True, 'operationId': 'new-card'})
    rating = {'courseId': 'course', 'id': 'card', 'expectedRevision': 1, 'operationId': 'r1', 'rating': 3}
    result = await service.reviews.rate(rating)
    assert await service.reviews.rate(rating) == result
    queue = {'courseId': 'course', 'cardIds': ['card']}
    assert not (await service.reviews.queue(queue))['cards']
    clock[0] = '2026-10-15T02:00:00Z'
    assert len((await service.reviews.queue(queue))['cards']) == 1
    await service.reviews.defer({'courseId': 'course', 'id': 'card', 'expectedRevision': 2, 'operationId': 'd1', 'until': '2026-10-16'})
    assert not (await service.reviews.queue(queue))['cards']
    changed = await service.reviews.preview({**value, 'answer': '修改答案', 'expectedRevision': 3})
    assert changed['content']['schedule'] is None
    assert changed['content']['contentRevision'] == 2
    assert len(changed['content']['reviewEvents']) == 1


async def test_feedback_does_not_change_scores_and_retries_cross_day(repository):
    from backend.agent.recommendation_feedback import RecommendationFeedback
    clock = ['2026-10-15T01:00:00Z']
    service = RecommendationFeedback(repository, lambda: clock[0])
    value = {'courseId': 'c', 'itemId': 'q', 'action': 'skip', 'expectedRevision': 0, 'operationId': 'skip'}
    first = await service.record(value)
    clock[0] = '2026-10-16T01:00:00Z'
    assert await service.record(value) == first
    result = await service.record({**value, 'action': 'restore', 'expectedRevision': 1, 'operationId': 'restore'})
    assert len(result['content']['events']) == 2


async def test_whole_chapter_coverage_and_cancel(course):
    source = course['sources'][0]
    large = {**course, 'sources': [{**source, 'quote': source['quote']*400}]}
    summary = await ContentService().summarize(large, max_chars=1000)
    assert summary['coverage']['characters'] == len(large['sources'][0]['quote'])
    assert sum(c['length'] for s in summary['sections'] for c in s['coverage']) == summary['coverage']['characters']
    signal = Cancellation()
    signal.cancel()
    with pytest.raises(asyncio.CancelledError):
        await ContentService().summarize(large, signal=signal)


def test_reproducible_fsrs_experiments_and_group_splits(course):
    left, right = run_local_experiments(course), run_local_experiments(course)
    assert left == right
    assert all(p['candidate']['budgetViolationDays'] == 0 for p in left['planning'])
    assert left['practice']['candidate']['recentRepeats'] == 0
    assert len(left['reviews']) == 5
    split = dataset_split([{'id': 'a', 'groupId': 'doc'}, {'id': 'b', 'groupId': 'doc'}])
    assert len(split['train']) == 2 or len(split['test']) == 2
