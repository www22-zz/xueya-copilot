import re

from ..core import require, parse_model_json, check_cancel
from .evidence import validate_claims, citation_source_id
from .tasks import answer_unavailable


async def finalize_answer(content, sources, model, *, review=None, signal=None, question='', mode='ask', narrative=False):
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
    claims = parsed.get('claims')
    if claims is None:
        original = next((allowed[key] for key in selected if parsed['answer'].strip() in allowed[key]['quote']), None)
        if not original:
            return fallback('CLAIMS_NEED_REVIEW')
        claims = [{'text': parsed['answer'].strip(), 'evidence': [{'sourceId': original['id'], 'quote': parsed['answer'].strip()}]}]
    if narrative:
        # Review the actual prose as well as its supporting claims in ONE batch.
        # Checking claim notes alone must never authorize unrelated final prose.
        require(isinstance(claims, list) and claims, 'INVALID_CLAIMS')
        refs = []
        for claim in claims:
            require(isinstance(claim, dict) and isinstance(claim.get('evidence'), list), 'INVALID_CLAIMS')
            for ref in claim['evidence']:
                if ref not in refs:
                    refs.append(ref)
        prose = parsed['answer'].strip()
        claims = [*claims, {'text': prose, 'kind': 'inference', 'evidence': refs}]
    try:
        checked = await validate_claims(claims, {'sources': sources}, review, signal)
    except (ValueError, TypeError, KeyError, AttributeError):
        return fallback('INVALID_CLAIM_EVIDENCE')
    narrative_claim = checked.pop() if narrative else None
    if narrative_claim and narrative_claim['support'] != 'supported':
        return fallback('CLAIMS_NEED_REVIEW')
    omitted = sum(c['support'] != 'supported' for c in checked)
    if narrative and omitted:
        return fallback('CLAIMS_NEED_REVIEW')
    checked = [c for c in checked if c['support'] == 'supported']
    if not checked:
        return fallback('CLAIMS_NEED_REVIEW')
    ids = list(dict.fromkeys(ref['sourceId'] for c in checked for ref in c['evidence']))
    if narrative:
        ids = [key for key in selected if key in ids] + [key for key in ids if key not in selected]
    answer = '\n\n'.join(('基于资料的推理：' if c['kind'] == 'inference' else '')+c['text']+''.join(f" [{ids.index(source_id)+1}]" for source_id in dict.fromkeys(r['sourceId'] for r in c['evidence'])) for c in checked)
    if narrative_claim and not omitted:
        # Remap inline citations without altering C++ array subscripts or code.
        cited = set()
        def citation(match):
            index = int(match[1]) - 1
            require(0 <= index < len(selected) and selected[index] in ids, 'INVALID_CITATION')
            number = ids.index(selected[index]) + 1
            cited.add(number)
            return f'[{number}]'
        blocks = re.split(r'(```.*?```|`[^`]*`)', narrative_claim['text'], flags=re.S)
        answer = ''.join(block if i % 2 else re.sub(r'(?<![\w])\[(\d+)\](?!\()', citation, block)
                         for i, block in enumerate(blocks))
        answer += ''.join(f' [{i}]' for i in range(1, len(ids)+1) if i not in cited)
    if omitted:
        answer += '\n\n部分解释的资料依据不足，已省略；当前仅保留通过核对的部分，回答尚未完成。'
    require(len(answer) <= 16000, 'AI_INVALID_RESPONSE')
    points = parsed.get('knowledgePoints', [])
    return {'ok': True, 'answer': answer, 'sources': ids, 'sourceDetails': [allowed[key] for key in ids], 'knowledgePoints': [p for p in points if isinstance(p, str) and any(p in allowed[key]['quote'] for key in ids)][:8] if isinstance(points, list) else [],
            'model': model, 'claims': checked, 'omittedClaims': omitted, 'verification': 'verbatim-only' if narrative and narrative_claim['kind'] == 'excerpt' else 'reviewed-narrative' if narrative else 'verbatim-only' if all(c['kind'] == 'excerpt' for c in checked) else 'reviewed-claims', 'engine': 'xiaomi-mimo',
            **({'answerStatus': 'unavailable', 'reason': 'CLAIMS_NEED_REVIEW'} if omitted else {})}
