"""Server-side quote repair must stay verbatim: only contiguous original text passes.

A model may retype a quote with different line wrapping, full-width glyphs or
curly punctuation. The repair path may map that back to an actual contiguous
substring of the server-owned source quote, but paraphrases, added words and
forged quotes must still be rejected before any semantic review.
"""
import pytest

from backend.agent.evidence import (normalize_claims, normalize_quote_text, quote_spans,
                                    repair_quote, validate_claims)
from backend.core import DomainError

WRAPPED = '栈只允许在\n同一端插入和删除。最后入栈者\n最先出栈。'
FLAT = '栈只允许在同一端插入和删除。最后入栈者最先出栈。'


def stack_source(**patch):
    return {'id': 's', 'documentId': 'doc', 'version': '1', 'location': '第84页',
            'quote': WRAPPED, **patch}


def ref_fields(quote):
    return {'sourceId': 's', 'documentId': 'doc', 'version': '1', 'quote': quote,
            'location': '第84页'}


class RecordingReview:
    """A review that always says supported; it must never run for forged quotes."""

    narrative = True

    def __init__(self):
        self.prepared = False
        self.calls = 0

    async def prepare(self, claims, signal=None):
        self.prepared = True

    async def __call__(self, claim, signal=None):
        self.calls += 1
        return {'supported': True, 'method': 'fake'}


async def test_exact_quote_is_accepted_unchanged_and_never_repaired(monkeypatch):
    import backend.agent.evidence as evidence
    monkeypatch.setattr(evidence, 'repair_quote', lambda *args: pytest.fail('repair attempted for an exact quote'))
    repairs = []
    checked = await validate_claims(
        [{'text': WRAPPED, 'evidence': [{'sourceId': 's', 'quote': WRAPPED}]}],
        {'sources': [stack_source()]}, on_repair=lambda: repairs.append(1))
    assert repairs == []
    assert checked[0]['support'] == 'supported' and checked[0]['kind'] == 'excerpt'
    assert checked[0]['text'] == WRAPPED
    assert checked[0]['evidence'] == [ref_fields(WRAPPED)]


async def test_newline_and_whitespace_differences_are_repaired_to_original_text():
    repairs = []
    checked = await validate_claims(
        [{'text': '栈只能在端点操作。', 'evidence': [{'sourceId': 's', 'quote': FLAT}]}],
        {'sources': [stack_source()]}, on_repair=lambda: repairs.append(1))
    assert repairs == [1]
    assert checked[0]['evidence'][0]['quote'] == WRAPPED
    # The repaired quote is a real contiguous original substring, not synthesized text.
    assert checked[0]['evidence'][0]['quote'] in WRAPPED
    # Repairing the quote does not bypass entailment review of a paraphrase.
    assert checked[0]['support'] == 'unverified' and checked[0]['kind'] == 'paraphrase'

    spaced = await validate_claims(
        [{'text': '入队时位置加一。', 'evidence': [{'sourceId': 's', 'quote': '入队时rear加1.'}]}],
        {'sources': [stack_source(quote='入队时 rear 加 1。')]})
    assert spaced[0]['evidence'][0]['quote'] == '入队时 rear 加 1。'


async def test_full_width_ascii_and_punctuation_variants_are_repaired():
    source = '队列遵循先进先出。入队Ａ在队尾，出队Ｂ在队头。'
    checked = await validate_claims(
        [{'text': '队列规则。', 'evidence': [{'sourceId': 's', 'quote': '队列遵循先进先出.入队A在队尾,出队B在队头.'}]}],
        {'sources': [stack_source(quote=source)]})
    assert checked[0]['evidence'][0]['quote'] == source

    ellipsis = await validate_claims(
        [{'text': '省略。', 'evidence': [{'sourceId': 's', 'quote': '原文省略...后续内容.'}]}],
        {'sources': [stack_source(quote='原文省略…后续内容。')]})
    assert ellipsis[0]['evidence'][0]['quote'] == '原文省略…后续内容。'

    enumeration = await validate_claims(
        [{'text': '列举。', 'evidence': [{'sourceId': 's', 'quote': '栈,队列与树.'}]}],
        {'sources': [stack_source(quote='栈、队列与树。')]})
    assert enumeration[0]['evidence'][0]['quote'] == '栈、队列与树。'


async def test_curly_quotes_are_repaired():
    source = '老师说：“栈是后进先出。”学生点头。'
    checked = await validate_claims(
        [{'text': '老师引用了规则。', 'evidence': [{'sourceId': 's', 'quote': '老师说:"栈是后进先出."'}]}],
        {'sources': [stack_source(quote=source)]})
    assert checked[0]['evidence'][0]['quote'] == '老师说：“栈是后进先出。”'


@pytest.mark.parametrize('quote', [
    '栈只允许在同一端插入和删除，且不能从中间操作。',      # added words
    '栈只允许在同一端插入和删除最后入栈者最先出栈。',      # dropped sentence punctuation
    '栈只允许在同一端插人和删除。',                        # changed character
])
async def test_paraphrase_and_changed_text_are_still_rejected(quote):
    with pytest.raises(DomainError, match='INVALID_CITATION'):
        await validate_claims([{'text': '结论。', 'evidence': [{'sourceId': 's', 'quote': quote}]}],
                              {'sources': [stack_source()]})


async def test_short_normalized_quote_is_not_repaired_but_short_exact_quote_still_works():
    source = stack_source(quote='队列遵循先进先出。入队在队尾进行。')
    with pytest.raises(DomainError, match='INVALID_CITATION'):
        await validate_claims([{'text': '队列。', 'evidence': [{'sourceId': 's', 'quote': '队列\n先进'}]}],
                              {'sources': [source]})
    assert repair_quote('队列\n先进', source['quote']) is None
    checked = await validate_claims([{'text': '队列遵循', 'evidence': [{'sourceId': 's', 'quote': '队列遵循'}]}],
                                    {'sources': [source]})
    assert checked[0]['support'] == 'supported' and checked[0]['kind'] == 'excerpt'


async def test_forged_quote_is_rejected_before_any_review():
    review = RecordingReview()
    with pytest.raises(DomainError, match='INVALID_CITATION'):
        await validate_claims(
            [{'text': '伪造结论。', 'evidence': [{'sourceId': 's', 'quote': '这段引文在原文中并不存在。'}]}],
            {'sources': [stack_source()]}, review)
    assert not review.prepared and review.calls == 0


async def test_quote_id_canonical_span_wins_and_normalized_agreement_is_accepted():
    ocr = {'id': 'scan', 'documentId': 'doc', 'version': '1', 'location': 'PDF第85页',
           'quote': '功能；人栈操作在栈顶插人二个元素\n元素具有后进先出特性'}
    spans = quote_spans(ocr)
    checked = await validate_claims(
        [{'text': '栈的元素后进先出。',
          'evidence': [{'sourceId': 'scan', 'quoteId': 'q2', 'quote': '  元素具有后进先出特性  '}]}],
        {'sources': [ocr]})
    assert checked[0]['evidence'][0]['quote'] == spans['q2']
    assert checked[0]['support'] == 'unverified'  # quote IDs do not bypass review.
    with pytest.raises(DomainError, match='INVALID_CITATION'):
        await validate_claims(
            [{'text': '栈。', 'evidence': [{'sourceId': 'scan', 'quoteId': 'q1',
                                            'quote': '功能；入栈操作在栈顶插入一个元素'}]}],
            {'sources': [ocr]})


async def test_on_repair_counts_repaired_refs_without_changing_public_output():
    claims = [
        {'text': WRAPPED, 'evidence': [{'sourceId': 's', 'quote': WRAPPED}]},                    # exact
        {'text': '端点是操作位置。', 'evidence': [{'sourceId': 's', 'quote': FLAT}]},             # repaired
        {'text': '删除也在同一端。', 'evidence': [{'sourceId': 's', 'quote': '栈只允许在 同一端插入和删除。'}]},  # repaired
    ]
    repairs = []
    with_hook = await validate_claims(claims, {'sources': [stack_source()]},
                                      on_repair=lambda: repairs.append(1))
    plain = await validate_claims(claims, {'sources': [stack_source()]})
    assert len(repairs) == 2
    assert with_hook == plain
    assert with_hook[0]['evidence'][0]['quote'] == WRAPPED
    assert with_hook[1]['evidence'][0]['quote'] == WRAPPED
    assert with_hook[2]['evidence'][0]['quote'] == '栈只允许在\n同一端插入和删除。'
    # No internal repair marker may leak into the public ref shape.
    assert all(set(ref) == {'sourceId', 'documentId', 'version', 'quote', 'location'}
               for item in with_hook for ref in item['evidence'])


async def test_on_repair_also_accepts_a_detail_callback():
    infos = []
    await validate_claims([{'text': '端点是操作位置。', 'evidence': [{'sourceId': 's', 'quote': FLAT}]}],
                          {'sources': [stack_source()]}, on_repair=infos.append)
    assert infos == [{'sourceId': 's', 'quote': WRAPPED}]


def test_normalize_claims_returns_candidates_and_keeps_the_old_domain_errors():
    source = stack_source()
    candidates = normalize_claims(
        [{'text': WRAPPED, 'evidence': [{'sourceId': 's', 'quote': WRAPPED}]}], {'sources': [source]})
    assert candidates == [{'text': WRAPPED, 'evidence': [ref_fields(WRAPPED)], 'kind': 'excerpt'}]
    # No internal validation/review fields are produced by the extraction.
    assert set(candidates[0]) == {'text', 'evidence', 'kind'}
    for claims, code in (
            ([], 'INVALID_CLAIMS'),
            ([{'text': ' ', 'evidence': [{'sourceId': 's', 'quote': WRAPPED}]}], 'UNSUPPORTED_CLAIM'),
            ([{'text': '结论。', 'evidence': [{'sourceId': 'nope', 'quote': WRAPPED}]}], 'INVALID_CITATION'),
            ([{'text': '结论。', 'evidence': [{'sourceId': 's', 'quote': '伪造的引文内容。'}]}], 'INVALID_CITATION')):
        with pytest.raises(DomainError, match=code):
            normalize_claims(claims, {'sources': [source]})


async def test_validate_claims_delegates_to_normalize_claims(monkeypatch):
    import backend.agent.evidence as evidence
    seen = []
    candidate = {'text': WRAPPED, 'evidence': [ref_fields(WRAPPED)], 'kind': 'excerpt'}

    def wrapper(claims, pack, on_repair=None, signal=None):
        seen.append(on_repair)
        return [candidate]

    monkeypatch.setattr(evidence, 'normalize_claims', wrapper)
    checked = await validate_claims(
        [{'text': WRAPPED, 'evidence': [{'sourceId': 's', 'quote': WRAPPED}]}],
        {'sources': [stack_source()]}, on_repair=seen.append)
    assert seen and seen[0] is not None
    assert checked == [{**candidate, 'support': 'supported',
                        'review': {'supported': True, 'method': 'exact-excerpt'}}]


def test_repair_quote_never_returns_synthesized_or_misaligned_text():
    assert normalize_quote_text(FLAT) == normalize_quote_text(WRAPPED)
    repaired = repair_quote(FLAT, WRAPPED)
    assert repaired == WRAPPED and repaired in WRAPPED
    # A match ending inside an ellipsis expansion is not a real original span.
    assert repair_quote('..继续正文内容', '省略号之后…继续正文内容') is None
    # A candidate longer than the source can never be mapped back.
    assert repair_quote(FLAT, '栈只允许在\n同一端插入和删除。') is None
