from ..core import require, parse_model_json, check_cancel
from .evidence import validate_claims
from .tasks import answer_unavailable


async def finalize_answer(content, sources, model, *, review=None, signal=None, question='', mode='ask'):
    check_cancel(signal)
    parsed = parse_model_json(content)
    require(isinstance(parsed, dict) and isinstance(parsed.get('answer'), str) and parsed['answer'].strip(), 'AI_INVALID_RESPONSE')
    allowed = {s['id']: s for s in sources}
    refs = parsed.get('sources', [])
    require(isinstance(refs, list), 'AI_INVALID_RESPONSE')
    selected = list(dict.fromkeys(x for x in refs if isinstance(x, str) and x in allowed))
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
    try:
        checked = await validate_claims(claims, {'sources': sources}, review, signal)
    except (ValueError, TypeError, KeyError, AttributeError):
        return fallback('INVALID_CLAIM_EVIDENCE')
    omitted = sum(c['support'] != 'supported' for c in checked)
    checked = [c for c in checked if c['support'] == 'supported']
    if not checked:
        return fallback('CLAIMS_NEED_REVIEW')
    ids = list(dict.fromkeys(ref['sourceId'] for c in checked for ref in c['evidence']))
    answer = '\n\n'.join(('基于资料的推理：' if c['kind'] == 'inference' else '')+c['text']+''.join(f" [{ids.index(source_id)+1}]" for source_id in dict.fromkeys(r['sourceId'] for r in c['evidence'])) for c in checked)
    if omitted:
        answer += '\n\n部分解释的资料依据不足，已省略。'
    require(len(answer) <= 16000, 'AI_INVALID_RESPONSE')
    points = parsed.get('knowledgePoints', [])
    return {'ok': True, 'answer': answer, 'sources': ids, 'sourceDetails': [allowed[key] for key in ids], 'knowledgePoints': [p for p in points if isinstance(p, str) and any(p in allowed[key]['quote'] for key in ids)][:8] if isinstance(points, list) else [],
            'model': model, 'claims': checked, 'omittedClaims': omitted, 'verification': 'verbatim-only' if all(c['kind'] == 'excerpt' for c in checked) else 'reviewed-claims', 'engine': 'xiaomi-mimo'}
