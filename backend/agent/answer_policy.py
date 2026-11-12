import re

from ..core import require, parse_model_json, check_cancel
from .evidence import validate_claims, citation_source_id
from .tasks import answer_unavailable


def _count_repair(_info=None):
    """Count server-side quote canonicalization in the request timings."""
    from ..xueya.qa_latency import current_timing
    timing = current_timing.get()
    if timing is not None:
        try:
            timing.repairs += 1
        except AttributeError:
            timing.repairs = 1


async def finalize_answer(content, sources, model, *, review=None, signal=None, question='', mode='ask', narrative=False, prose_review=True):
    """Validate the generated answer, optionally repairing a failed claim check.

    ``prose_review=False`` is the explicit fast mode: claims and citations are
    still validated exactly, but the long narrative prose is not sent to the
    semantic reviewer. It is only published when every claim it cites passed,
    and is labelled ``claims-supported-prose``; otherwise the verified claim
    notes are published instead.
    """
    try:
        result = await _finalize_once(content, sources, model, review=review, signal=signal,
                                      question=question, mode=mode, narrative=narrative,
                                      prose_review=prose_review)
    except Exception as error:
        failure = getattr(error, 'code', None) or 'AI_INVALID_RESPONSE'
        repaired = await _repair(review, question, sources, failure, signal)
        if repaired is not None:
            return repaired
        raise
    reason = result.get('reason') if result.get('answerStatus') == 'unavailable' else None
    if reason and reason != 'INSUFFICIENT_EVIDENCE':
        repaired = await _repair(review, question, sources, reason, signal)
        if repaired is not None:
            return repaired
    return result


async def _repair(review, question, sources, failure, signal):
    if not question or not sources:
        return None
    from .answer_repair import repair_available
    if not repair_available(review):
        return None
    from .answer_repair import repair_to_excerpts
    return await repair_to_excerpts(getattr(review, 'provider', None), getattr(review, 'scope', None),
                                    question, sources, failure=failure, signal=signal)


async def _finalize_once(content, sources, model, *, review=None, signal=None, question='', mode='ask', narrative=False, prose_review=True):
    check_cancel(signal)
    parsed = parse_model_json(content)
    require(isinstance(parsed, dict), 'AI_INVALID_RESPONSE')
    if parsed.get('answerable') is False:
        # A model may decline, but its ungrounded refusal text is never published.
        return {'ok': True, 'answer': '当前所选资料不足以支持这个问题的回答。请补充相关资料，或改问本章已有内容。',
                'sources': [], 'sourceDetails': [], 'knowledgePoints': [], 'claims': [], 'model': model,
                'engine': 'local-workflow', 'verification': 'not-generated', 'answerStatus': 'unavailable',
                'reason': 'INSUFFICIENT_EVIDENCE'}
    require(isinstance(parsed.get('answer'), str) and parsed['answer'].strip(), 'AI_INVALID_RESPONSE')
    allowed = {s['id']: s for s in sources}
    refs = parsed.get('sources', [])
    require(isinstance(refs, list), 'AI_INVALID_RESPONSE')
    selected = list(dict.fromkeys(key for x in refs if (key := citation_source_id(x, sources)) in allowed))
    require(selected, 'AI_INVALID_RESPONSE')

    def fallback(reason):
        return {'ok': True, 'answer': answer_unavailable(reason), 'sources': selected, 'sourceDetails': [allowed[key] for key in selected],
                'knowledgePoints': [], 'model': model, 'engine': 'local-workflow',
                'verification': 'not-generated', 'answerStatus': 'unavailable', 'reason': reason}

    def suggestions(value):
        rows = value.get('suggestedQuestions') if isinstance(value, dict) else None
        if not isinstance(rows, list):
            return None
        items = []
        for row in rows:
            if not isinstance(row, str):
                continue
            text = row.strip()
            if 4 <= len(text) <= 80 and text not in items and text != prose:
                items.append(text)
        return items[:3] or None

    claims = parsed.get('claims')
    if claims is None:
        original = next((allowed[key] for key in selected if parsed['answer'].strip() in allowed[key]['quote']), None)
        if not original:
            return fallback('CLAIMS_NEED_REVIEW')
        claims = [{'text': parsed['answer'].strip(), 'evidence': [{'sourceId': original['id'], 'quote': parsed['answer'].strip()}]}]
    prose = parsed['answer'].strip()
    if narrative and prose_review:
        # Review the actual prose as well as its supporting claims in ONE batch.
        # Checking claim notes alone must never authorize unrelated final prose.
        require(isinstance(claims, list) and claims, 'INVALID_CLAIMS')
        refs = []
        for claim in claims:
            require(isinstance(claim, dict) and isinstance(claim.get('evidence'), list), 'INVALID_CLAIMS')
            for ref in claim['evidence']:
                if ref not in refs:
                    refs.append(ref)
        claims = [*claims, {'text': prose, 'kind': 'inference', 'evidence': refs}]
    try:
        checked = await validate_claims(claims, {'sources': sources}, review, signal, on_repair=_count_repair)
    except (ValueError, TypeError, KeyError, AttributeError):
        return fallback('INVALID_CLAIM_EVIDENCE')
    narrative_claim = checked.pop() if narrative and prose_review else None
    supported = [claim for claim in checked if claim['support'] == 'supported']
    omitted = len(checked)-len(supported)
    if narrative and prose_review:
        if narrative_claim and narrative_claim['support'] != 'supported':
            # The unverified prose is never published; let the caller switch to
            # a natural general answer instead of dumping a mechanical excerpt.
            return fallback('CLAIMS_NEED_REVIEW')
        if omitted:
            return fallback('CLAIMS_NEED_REVIEW')
    elif omitted:
        return fallback('CLAIMS_NEED_REVIEW')
    checked = supported
    if not checked:
        return fallback('CLAIMS_NEED_REVIEW')
    ids = list(dict.fromkeys(ref['sourceId'] for c in checked for ref in c['evidence']))
    if narrative:
        ids = [key for key in selected if key in ids] + [key for key in ids if key not in selected]
    answer = '\n\n'.join(('基于资料的推理：' if c['kind'] == 'inference' else '')+c['text']+''.join(f" [{ids.index(source_id)+1}]" for source_id in dict.fromkeys(r['sourceId'] for r in c['evidence'])) for c in checked)
    if narrative and (narrative_claim is not None or not prose_review):
        # Remap inline citations without altering C++ array subscripts or code.
        cited = set()
        def citation(match):
            index = int(match[1]) - 1
            require(0 <= index < len(selected) and selected[index] in ids, 'INVALID_CITATION')
            number = ids.index(selected[index]) + 1
            cited.add(number)
            return f'[{number}]'
        blocks = re.split(r'(```.*?```|`[^`]*`)', prose, flags=re.S)
        answer = ''.join(block if i % 2 else re.sub(r'(?<![\w])\[(\d+)\](?!\()', citation, block)
                         for i, block in enumerate(blocks))
        answer += ''.join(f' [{i}]' for i in range(1, len(ids)+1) if i not in cited)
    if omitted:
        answer += '\n\n部分解释的资料依据不足，已省略；当前仅保留通过核对的部分，回答尚未完成。'
    require(len(answer) <= 16000, 'AI_INVALID_RESPONSE')
    points = parsed.get('knowledgePoints', [])
    verification = ('verbatim-only' if narrative and narrative_claim and narrative_claim['kind'] == 'excerpt'
                    else 'reviewed-narrative' if narrative_claim is not None
                    else 'claims-supported-prose' if narrative and not prose_review
                    else 'verbatim-only' if all(c['kind'] == 'excerpt' for c in checked) else 'reviewed-claims')
    return {'ok': True, 'answer': answer, 'sources': ids, 'sourceDetails': [allowed[key] for key in ids], 'knowledgePoints': [p for p in points if isinstance(p, str) and any(p in allowed[key]['quote'] for key in ids)][:8] if isinstance(points, list) else [],
            'model': model, 'claims': checked, 'omittedClaims': omitted, 'suggestedQuestions': suggestions(parsed), 'verification': verification, 'engine': 'xiaomi-mimo',
            **({'proseReview': 'skipped'} if narrative and not prose_review else {}),
            **({'answerStatus': 'unavailable', 'reason': 'CLAIMS_NEED_REVIEW'} if omitted else {})}
