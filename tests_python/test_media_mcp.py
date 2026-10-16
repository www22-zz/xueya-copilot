import asyncio
import json
import pytest
from backend.core import DomainError, dumps
from backend.agent.tasks import normalize_context
from backend.mcp.course_session import open_course_session
from backend.agent.media_service import MediaService
from backend.agent.question_service import QuestionService
from backend.agent.concept_service import ConceptService


async def test_real_python_mcp_stdio_search_read_and_learning_stats(course):
    questions = [{'id': q['id'], 'topic': q['conceptIds'][0], 'sourceId': q['sourceId']} for q in course['questions']]
    context = normalize_context({'library': course['sources'], 'questions': questions})
    async with open_course_session(context, timeout_ms=15000) as session:
        definitions = await session.list_tools()
        assert {t['name'] for t in definitions} == {'search_materials', 'read_source', 'analyze_progress', 'build_review_plan'}
        found = await session.call('search_materials', {'query': '二叉树'})
        assert found['sources'][0]['id'] == 's'
        assert (await session.call('read_source', {'sourceId': 's'}))['source']['quote'] == course['sources'][0]['quote']
        assert (await session.call('analyze_progress'))['total'] == 0
        assert (await session.call('build_review_plan'))['days']
        with pytest.raises(DomainError, match='MCP_TOOL_NOT_FOUND'):
            await session.call('write_unapproved_tool')


class Model:
    def __init__(self, content):
        self.content, self.calls = content, []
    async def generate(self, request):
        self.calls.append(request)
        return {'content': dumps(self.content), 'model': 'controlled'}


async def test_media_scope_confirmation_segment_timestamps_and_tts(course):
    async def resolver(value, signal=None):
        return {**value, 'mime': 'image/png' if value['kind'] == 'image' else 'audio/wav', 'bytes': b'local-synthetic', 'startMs': 0, 'endMs': 1000}
    model = Model({'observations': ['可见题干'], 'uncertainties': [], 'inferences': [], 'recognizedProblem': '三加二'})
    class Speech:
        async def transcribe(self, request):
            return {'text': '合成录音'}
        async def synthesize(self, request):
            return {'data': 'UklGRg==', 'mime': 'audio/wav'}
    service = MediaService(resolver, model, Speech(), Speech())
    result = await service.image_question({'courseId': 'course', 'id': 'image', 'version': '1', 'question': '识别题目'})
    assert result['status'] == 'awaiting_user' and not result['masteryUpdated']
    with pytest.raises(DomainError, match='RECOGNITION_CONFIRMATION_REQUIRED'):
        service.confirm_recognition(result, {'confirmed': 'yes'})
    confirmed = service.confirm_recognition(result, {'confirmed': True, 'correctedProblem': '三加二等于多少'})
    assert confirmed['recognizedProblem'] == '三加二等于多少'
    transcript = await service.transcribe({'courseId': 'course', 'segments': [{'id': 'audio', 'version': '1', 'startMs': 0, 'endMs': 1000}]})
    assert transcript['segments'][0]['timestampPrecision'] == 'segment' and not transcript['wordAlignment']
    with pytest.raises(DomainError, match='MEDIA_TIMELINE_MISMATCH'):
        await service.transcribe({'courseId': 'course', 'segments': [{'id': 'audio', 'version': '1', 'startMs': 0, 'endMs': 2000}]})
    with pytest.raises(DomainError, match='VERIFIED_TEXT_REQUIRED'):
        await service.speak({'courseId': 'course', 'artifactId': 'n', 'revision': 1, 'text': '正文', 'verified': False})
    spoken = await service.speak({'courseId': 'course', 'artifactId': 'n', 'revision': 1, 'text': '正文[1]', 'verified': True})
    assert spoken['synthetic'] and '[' not in spoken['chunks'][0]['text']
    async def wrong(value, signal=None):
        return {**await resolver(value), 'courseId': 'another-course'}
    with pytest.raises(DomainError, match='MEDIA_SCOPE_MISMATCH'):
        await MediaService(wrong, model).image_question({'courseId': 'course', 'id': 'image', 'version': '1', 'question': '识别'})


async def test_photo_step_diagnosis_is_candidate_not_grade(course):
    recognition = {'status': 'confirmed', 'revision': 'v', 'courseId': 'course', 'recognizedProblem': '题干', 'media': {'id': 'photo', 'version': '1'}}
    model = Model({'steps': [{'index': 0, 'status': 'supported', 'hint': '核对定义', 'explanation': '根据原文', 'evidence': [{'sourceId': 's', 'quote': course['sources'][0]['quote']}]}]})
    service = MediaService(lambda value: None, image_model=model)
    result = await service.photo_diagnosis({'recognition': recognition, 'steps': ['学生步骤'], 'sources': course['sources']})
    assert not result['masteryUpdated'] and result['requiresReview']
    assert 'explanation' not in result['steps'][0]


async def test_question_generation_duplicate_rejection_and_human_review(course):
    q = course['questions'][0]
    candidate = {k: q[k] for k in ('type', 'prompt', 'options', 'answer', 'explanation', 'sourceId', 'evidenceQuote', 'conceptIds', 'difficulty')}
    service = QuestionService(Model({'questions': [candidate, candidate]}))
    result = await service.generate({'courseId': 'course', 'sources': course['sources'], 'conceptIds': ['node'], 'count': 2})
    assert len(result['questions']) == 1 and result['rejected'][0]['code'] == 'DUPLICATE_QUESTION'
    generated = result['questions'][0]
    assert generated['status'] == 'candidate'
    approved = service.review_question(generated, {'expectedVersion': generated['version'], 'approved': True, 'reviewer': 'user', 'reason': '核对答案'}, course['sources'])
    assert approved['status'] == 'approved'
    edited = service.edit_question(approved, {'prompt': '修改题干'}, course['sources'])
    assert edited['status'] == 'candidate' and edited['quality']['answerSupport'] == 'pending'


async def test_concept_extraction_preserves_curated_values_and_candidate_edges(course):
    source = course['sources'][0]
    model = Model({'concepts': [{'name': '节点', 'aliases': [], 'sourceId': 's', 'quote': source['quote'], 'confidence': .9}], 'edges': []})
    service = ConceptService(model)
    result = await service.extract({'courseId': 'course', 'sources': course['sources'], 'existing': course['graph']})
    assert result['graph']['concepts'] == course['graph']['concepts']
    corrected = service.correct(result['graph'], {'conceptId': 'node', 'patch': {'aliases': ['结点']}, 'reviewer': 'user', 'reason': '别名'}, course['sources'])
    assert corrected['concepts'][0]['aliases'] == ['结点']
