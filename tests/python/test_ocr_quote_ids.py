import pytest
from backend.agent.evidence import quote_spans, validate_claims
from backend.core import DomainError
from backend.xueya.agent import build_messages
import json


@pytest.mark.asyncio
async def test_ocr_quote_ids_restore_exact_original_and_keep_review_required():
    source = {'id': 'scan', 'quote': '功能；人栈操作在栈顶插人二个元素\n元素具有后进先出特性', 'location': 'PDF第85页'}
    pack = {'sources': [source]}
    claim = {'text': '栈的元素后进先出。', 'evidence': [{'sourceId': 'scan', 'quoteId': 'q2'}]}
    checked = await validate_claims([claim], pack)
    assert checked[0]['evidence'][0]['quote'] == '元素具有后进先出特性'
    assert checked[0]['support'] == 'unverified'  # IDs do not bypass entailment review.
    assert quote_spans(source)['q0'] == source['quote']
    for ref in ({'sourceId': 'other', 'quoteId': 'q2'}, {'sourceId': 'scan', 'quoteId': 'q99'},
                {'sourceId': 'scan', 'quoteId': 'q1', 'quote': '功能；入栈操作在栈顶插入一个元素'},
                {'sourceId': 'scan', 'quote': '功能；入栈操作在栈顶插入一个元素'}):
        with pytest.raises(DomainError):
            await validate_claims([{**claim, 'evidence': [ref]}], pack)
    request = {'mode': 'ask', 'history': [], 'question': '栈是什么？'}
    materials = json.loads(build_messages(request, [source])[-1]['content'])['materials']
    assert materials[0]['quoteSpans'][1] == {'quoteId': 'q2', 'quote': '元素具有后进先出特性'}
    assert 'quoteSpans' not in source
