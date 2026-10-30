import hashlib
import json

import pytest

from backend.xueya.agent import Agent
from backend.xueya.common import AppError
from backend.xueya.config import Config
from backend.xueya.rag_parse import parse_structured, structured_chunks
from scripts.import_stack_queue_markdown import MATERIAL, SPEC, install
from scripts.verify_stack_queue_material import examples
from test_pdf_knowledge import pdf
from test_rag import completed


def fixture_validation(content):
    # Controlled receipt for lifecycle tests; real C++ compilation is a separate check.
    return {'materialSha256': hashlib.sha256(content).hexdigest(), 'examples': 13, 'passed': 13,
            'rows': [{'passed': True, 'fixture': True} for _ in range(13)]}


def test_markdown_code_fences_sections_and_real_character_locations():
    content = MATERIAL.read_bytes()
    parsed = parse_structured(content, 'md')
    assert not parsed['warnings']
    code = [b for b in parsed['blocks'] if b['type'] == 'code']
    assert [b['text'] for b in code] == ['```cpp\n'+s+'\n```' for _, s in examples(content.decode())]
    chunks = structured_chunks(parsed, {'id': 'md', 'name': '教材.md', 'contentRevision': 1})
    assert all(s['page'] is None and '字符 ' in s['location'] for s in chunks)
    assert all('SQ' in s['location'] for s in chunks if s['blockType'] == 'code')
    assert len([s for s in chunks if s['blockType'] == 'code']) == 13
    for chunk in chunks:
        assert parsed['text'][chunk['start']:chunk['end']] == chunk['quote']


def test_a_high_scoring_title_does_not_displace_the_explanation():
    from backend.xueya.rag_search import compress
    heading = {'id': 'heading', 'documentId': 'd', 'start': 0, 'end': 7, 'quote': '# 栈的用途', 'blockType': 'heading'}
    paragraph = {'id': 'paragraph', 'documentId': 'd', 'start': 10, 'end': 35,
                 'quote': '栈遵循后进先出，因此不适合先提交先处理的任务。', 'blockType': 'paragraph'}
    selected, used = compress('先提交先处理为什么不选栈？', [(100, heading), (2, paragraph)], limit=1)
    assert selected[0]['id'] == 'paragraph' and used == len(paragraph['quote'].encode())
    # A document containing only a heading remains discoverable.
    fallback, _ = compress('栈的用途', [(100, heading)], limit=1)
    assert fallback[0]['id'] == 'heading'


@pytest.mark.asyncio
async def test_authored_markdown_replaces_only_declared_pdf_after_evidence_checks(platform):
    from backend.xueya.rag_service import RagService
    # Seed and import through the same production service.
    rag = RagService(platform)
    scope = platform.scope()
    old = await completed(platform, rag.upload(scope, pdf(1), 'old.pdf', 'old'))
    other = await completed(platform, rag.upload(scope, '别的资料'.encode(), 'keep.txt', 'keep'))
    old_id, keep_id = old['result']['documentId'], other['result']['documentId']
    platform.repo.put(scope, 'note', 'keep-note', {'text': '不能丢失'}, 0)
    content = MATERIAL.read_bytes()
    report = await install(platform, scope, content, fixture_validation(content), archive_pdf_ids=[old_id], rag=rag)
    assert report['evidenceChecks']['passed'] == report['evidenceChecks']['count'] == 24
    assert report['codeBlocks'] == 13 and report['providerRequests'] == 0
    # Existing artifacts remain available; archive is reversible.
    assert platform.repo.read(scope, 'document', old_id)['value']['archived']
    assert not platform.repo.read(scope, 'document', keep_id)['value'].get('archived')
    assert platform.repo.read(scope, 'note', 'keep-note')['value']['text'] == '不能丢失'
    assert not platform.db.one('SELECT id FROM invocations')


@pytest.mark.asyncio
async def test_bad_material_validation_cannot_archive_existing_pdf(platform):
    content = MATERIAL.read_bytes()
    with pytest.raises(AppError, match='MATERIAL_CODE_VALIDATION_REQUIRED'):
        await install(platform, platform.scope(), content, {'materialSha256': 'wrong'}, archive_pdf_ids=[])
    assert not platform.repo.all(platform.scope(), 'document')


@pytest.mark.asyncio
async def test_markdown_rules_run_actual_workflow_without_any_model(platform):
    from backend.xueya.rag_service import RagService
    rag = RagService(platform)
    scope = platform.scope()
    done = await completed(platform, rag.upload(scope, MATERIAL.read_bytes(), MATERIAL.name, 'md'))
    doc_id = done['result']['documentId']
    class NoModel:
        config = Config()
        async def stream(self, *args, **kwargs):
            raise AssertionError('This workflow must not call a model')
            yield
    agent = Agent(NoModel(), platform)
    agent.rag = rag
    for case in json.loads(SPEC.read_text(encoding='utf-8'))['calculations']:
        final = [e async for e in agent.workflow({'question': case['query'], 'documentIds': [doc_id]})][-1]
        assert final.get('verification') == 'calculated-from-cited-rules', case['id']
        assert final['timings']['modelCalls'] == 0
        for key, expected in case['expected'].items():
            assert final['calculation'][key] == expected, case['id']
        assert all(rag.validate(scope, s) for s in final['sourceDetails'])
        assert set(final['sources']) == {s['id'] for s in final['sourceDetails']}


@pytest.mark.asyncio
async def test_explicit_code_section_is_pinned_only_within_selected_documents(platform):
    from backend.xueya.rag_service import RagService
    rag = RagService(platform)
    scope = platform.scope()
    first = await completed(platform, rag.upload(scope, MATERIAL.read_bytes(), MATERIAL.name, 'book'))
    second = await completed(platform, rag.upload(scope, '# C06 其他资料\n\n不要越过文档范围。'.encode(), 'other.md', 'other'))
    query = '请依据C06给出链队列dequeue函数，并解释删除最后元素的指针操作。'
    a = await rag.search(scope, query, document_ids=[first['result']['documentId']], mode='lexical', budget=9000)
    assert a['sources'][0]['blockType'] == 'code' and 'class LinkedQueue' in a['sources'][0]['quote']
    assert all(rag.validate(scope, s) for s in a['sources'])
    b = await rag.search(scope, query, document_ids=[second['result']['documentId']], mode='lexical', budget=9000)
    assert all(s['documentId'] == second['result']['documentId'] for s in b['sources'])
    assert not any('class LinkedQueue' in s['quote'] for s in b['sources'])


def test_choosing_against_an_alternative_keeps_both_definitions():
    from backend.xueya.rag_search import comparison_subjects
    assert comparison_subjects('先提交先处理选择队列，那为什么不选栈？') == ['栈', '队列']


@pytest.mark.asyncio
async def test_followup_review_receives_user_goal_but_not_assistant_assertions(platform):
    from backend.xueya.rag_service import RagService
    rag = RagService(platform)
    scope = platform.scope()
    done = await completed(platform, rag.upload(scope, '栈只在同一端插入删除，遵循后进先出。'.encode(), 'stack.md', 'stack'))
    source = rag.sources(scope)[0]
    questions = []
    class Model:
        config = Config(api_key='fixture-only')
        async def stream(self, *args, **kwargs):
            yield {'type': 'content', 'text': json.dumps({'answer': '栈不符合先来先服务。', 'sources': [source['id']],
                'claims': [{'text': '任务要求先提交先处理，而栈后进先出，所以不选栈。', 'kind': 'inference',
                            'evidence': [{'sourceId': source['id'], 'quoteId': 'q0'}]}]})}
        async def generate(self, messages, **kwargs):
            batch = json.loads(messages[-1]['content'])
            question = batch['question']
            questions.append(question)
            valid = '任务要求先提交先处理' in question and '以后应该后提交先处理' not in question
            return {'content': json.dumps({'verdicts': [{'index': i, 'status': 'supported' if valid else 'unsupported'} for i in range(len(batch['claims']))]})}
    agent = Agent(Model(), platform);agent.rag = rag
    final = [e async for e in agent.workflow({'question': '那为什么不选栈？', 'documentIds': [done['result']['documentId']],
        'history': [{'role': 'user', 'content': '任务要求先提交先处理，我选择了队列。'},
                    {'role': 'assistant', 'content': '以后应该后提交先处理。'}]})][-1]
    assert questions and '那为什么不选栈' in questions[0]
    assert final.get('answerStatus') != 'unavailable' and final['verification'] == 'reviewed-narrative'
