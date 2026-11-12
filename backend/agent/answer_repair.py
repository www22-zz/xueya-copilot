"""One cheap, excerpt-only repair after a failed evidence check.

The repair never invents prose: the model may only choose server-owned quote
spans, and the host rebuilds the answer from the canonical original text. The
result is therefore verifiable locally (exact excerpts) and needs no second
semantic review. If the model cannot produce a usable selection, callers keep
their existing fail-closed fallback behavior.
"""
from __future__ import annotations

import logging

from backend.core import DomainError, check_cancel, parse_model_json
from .evidence import citation_aliases, quote_spans

from ..xueya.common import dumps
from ..xueya.qa_latency import current_timing

SYSTEM = (
    "你是课程回答的保守修复器。上一次回答没有通过逐字引文核对。"
    "请只从给定资料中选择能直接回答问题的原文句子，按回答顺序组成一条纯摘录回答。\n"
    "规则：\n"
    "1. 只能选择资料中给出的 quoteId，不要改写、拼接或补充任何文字。\n"
    "2. 最多选择 4 条；优先选择语义完整、直接回答问题的句子。\n"
    "3. 不要解释、不要过渡句、不要资料外的知识、不要输出引用编号。\n"
    "4. 资料不足以回答时输出 {\"answerable\":false,\"quotes\":[]}。\n"
    "5. sourceId 使用资料中的 citationId（cite1、cite2…）；quoteId 使用该资料的片段编号。\n"
    "只输出 JSON：{\"answerable\":true,\"quotes\":[{\"sourceId\":\"cite1\",\"quoteId\":\"s2\"}]}"
)


def _provider_of(review):
    return getattr(review, 'provider', None) if review is not None else None


def repair_available(review):
    provider = _provider_of(review)
    if provider is None:
        return False
    config = getattr(provider, 'config', None)
    return bool(getattr(config, 'answer_repair_enabled', False))


def _materials(sources):
    """Only spans the model can name; keep the payload modest."""
    aliases = {original: alias for alias, original in citation_aliases(sources).items()}
    materials, total = [], 0
    for source in sources[:8]:
        spans = quote_spans(source)
        spans = {key: (value[:1200] if isinstance(value, str) else value) for key, value in spans.items()
                 if key == 'q0' or key.startswith('s') or key.startswith('q')}
        item = {'citationId': aliases.get(source['id'], ''),
                'title': str(source.get('title', ''))[:120],
                'location': str(source.get('location', ''))[:120],
                'quoteSpans': spans}
        size = len(dumps(item).encode('utf-8'))
        if total+size > 60000:
            break
        total += size
        materials.append(item)
    return materials


def _resolve_quote(item, sources):
    if not isinstance(item, dict):
        return None
    by_id = {source['id']: source for source in sources}
    by_alias = {alias: by_id[original] for alias, original in citation_aliases(sources).items()
                if original in by_id}
    value = item.get('sourceId')
    source = (by_id.get(value) or by_alias.get(value)) if isinstance(value, str) else None
    if source is None:
        return None
    spans = quote_spans(source)
    quote_id = item.get('quoteId')
    canonical = spans.get(quote_id) if isinstance(quote_id, str) else None
    if canonical is None:
        quote = item.get('quote')
        if isinstance(quote, str) and quote.strip() and quote in source['quote']:
            canonical = quote
        else:
            return None
    return {'text': canonical,
            'kind': 'excerpt',
            'evidence': [{'sourceId': source['id'], 'documentId': source.get('documentId'),
                          'version': source.get('version'), 'quote': canonical,
                          'location': source.get('location')}]}


def _result(selected, response, failure):
    claims, ids = [], []
    for claim in selected:
        if claim['text'] in [existing['text'] for existing in claims]:
            continue
        claims.append(claim)
        for ref in claim['evidence']:
            if ref['sourceId'] not in ids:
                ids.append(ref['sourceId'])
    if not claims:
        return None
    answer = '\n\n'.join(
        claim['text'] + ''.join(
            f" [{ids.index(source_id)+1}]"
            for source_id in dict.fromkeys(ref['sourceId'] for ref in claim['evidence']))
        for claim in claims)
    if len(answer) > 16000:
        return None
    source_details, seen = [], set()
    for claim in claims:
        for ref in claim['evidence']:
            if ref['sourceId'] not in seen:
                seen.add(ref['sourceId'])
                source_details.append(ref)
    return {'ok': True, 'answer': answer, 'sources': ids, 'sourceDetails': source_details,
            'knowledgePoints': [], 'claims': claims,
            'model': (response.get('model') if isinstance(response, dict) else None) or 'xiaomi-mimo',
            'usage': response.get('usage') if isinstance(response, dict) else None,
            'engine': 'xiaomi-mimo', 'verification': 'repaired-excerpts',
            'repair': {'mode': 'excerpt', 'reason': failure}}


async def repair_to_excerpts(provider, scope, question, sources, *, failure='CLAIMS_NEED_REVIEW', signal=None, timeout=30):
    """Ask once for an excerpt-only answer; return a verified result or None.

    No retries and no content logging: a failure keeps the caller's existing
    fallback. All returned quote text is the server's canonical original.
    """
    if not isinstance(question, str) or not question.strip() or not isinstance(sources, list) or not sources:
        return None
    config = getattr(provider, 'config', None)
    if not getattr(config, 'answer_repair_enabled', False):
        return None
    check_cancel(signal)
    materials = _materials(sources)
    if not materials:
        return None
    payload = {'question': question[:4000], 'failure': str(failure)[:120], 'materials': materials}
    if len(dumps(payload).encode('utf-8')) > 96000:
        return None
    timing = current_timing.get()
    try:
        response = await provider.generate(
            [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': dumps(payload)}],
            scope=scope, temperature=0, timeout=timeout,
            max_output_tokens=min(getattr(config, 'answer_repair_tokens', 1024), getattr(config, 'max_output_tokens', 4096)),
            response_format={'type': 'json_object'}, thinking={'type': 'disabled'})
        check_cancel(signal)
        data = parse_model_json(response.get('content'))
    except (DomainError, ValueError, TypeError, KeyError, AttributeError):
        return None
    except Exception as error:  # provider/budget/transport plumbing
        logging.getLogger(__name__).info('answer repair skipped: %s', getattr(error, 'code', type(error).__name__))
        return None
    if not isinstance(data, dict) or data.get('answerable') is False:
        return None
    quotes = data.get('quotes')
    if not isinstance(quotes, list) or not quotes:
        return None
    selected = [claim for claim in (_resolve_quote(item, sources) for item in quotes[:4]) if claim is not None]
    result = _result(selected, response, failure)
    if result is None:
        return None
    if timing is not None:
        try:
            timing.repairs += 1
        except AttributeError:
            timing.repairs = 1
    return result
