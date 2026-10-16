from ..core import require, parse_model_json, check_cancel
from .evidence import validate_claims
from .tasks import local_answer


async def finalize_answer(content, sources, model, *, review=None, signal=None, question='', mode='ask'):
    check_cancel(signal)
    parsed = parse_model_json(content)
    require(isinstance(parsed, dict) and isinstance(parsed.get('answer'), str) and parsed['answer'].strip(), 'AI_INVALID_RESPONSE')
    allowed = {s['id']: s for s in sources}
    selected = list(dict.fromkeys(x for x in parsed.get('sources', []) if isinstance(x, str) and x in allowed))
    require(selected, 'AI_INVALID_RESPONSE')

    def fallback(reason):
        return {'ok': True, 'answer': local_answer(question, mode, [allowed[key] for key in selected]), 'sources': selected, 'knowledgePoints': [], 'model': 'local-excerpts', 'engine': 'local-workflow', 'verification': 'verbatim-only', 'reason': reason}
    claims = parsed.get('claims')
    if claims is None:
        original = next((allowed[key] for key in selected if parsed['answer'].strip() in allowed[key]['quote']), None)
        if not original:
            return fallback('CLAIMS_NEED_REVIEW')
        claims = [{'text': parsed['answer'].strip(), 'evidence': [{'sourceId': original['id'], 'quote': parsed['answer'].strip()}]}]
    try:
        checked = await validate_claims(claims, {'sources': sources}, review, signal)
    except (ValueError, TypeError, KeyError):
        return fallback('INVALID_CLAIM_EVIDENCE')
    if any(c['support'] != 'supported' for c in checked):
        return fallback('CLAIMS_NEED_REVIEW')
    ids = list(dict.fromkeys(ref['sourceId'] for c in checked for ref in c['evidence']))
    answer = '\n\n'.join(c['text']+''.join(f" [{ids.index(r['sourceId'])+1}]" for r in c['evidence']) for c in checked)
    require(len(answer) <= 16000, 'AI_INVALID_RESPONSE')
    return {'ok': True, 'answer': answer, 'sources': ids, 'knowledgePoints': [p for p in parsed.get('knowledgePoints', []) if isinstance(p, str) and any(p in s['quote'] for s in sources)][:8],
            'model': model, 'claims': checked, 'verification': 'verbatim-only' if all(c['kind'] == 'excerpt' for c in checked) else 'reviewed-claims', 'engine': 'xiaomi-mimo'}
