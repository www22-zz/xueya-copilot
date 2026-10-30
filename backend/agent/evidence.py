from ..core import require, clone, fingerprint, resolve, check_cancel
import re


def citation_aliases(sources):
    """Request-local short handles, disjoint from all real IDs in this package."""
    used, aliases = {s['id'] for s in sources}, {}
    for index, source in enumerate(sources, 1):
        alias = 'cite'+str(index)
        while alias in used:
            alias = '_'+alias
        used.add(alias)
        aliases[alias] = source['id']
    return aliases


def citation_source_id(value, sources):
    if not isinstance(value, str):
        return None
    if value in {s['id'] for s in sources}:
        return value
    return citation_aliases(sources).get(value)


def quote_spans(source):
    """Server-owned exact quotes. IDs avoid asking a model to retype OCR glyphs."""
    quote = source['quote']
    lines = list(dict.fromkeys(line.strip() for line in quote.splitlines() if line.strip()))[:128]
    result = {'q0': quote, **{'q'+str(i): line for i, line in enumerate(lines, 1)}}
    # Keep legacy line IDs stable, and offer complete sentences spanning PDF
    # line wraps. These are exact substrings, never repaired or paraphrased text.
    if source.get('blockType') != 'code' and not quote.lstrip().startswith('```'):
        sentences = [m[0].strip() for m in re.finditer(r'[^。！？]+[。！？]|[^。！？]+$', quote)]
        result.update({'s'+str(i): text for i, text in enumerate(sentences[:16], 1) if 6 <= len(text) <= 1500})
    return result


def evidence_package(value):
    course, sources = value.get('courseId'), value.get('sources')
    require(isinstance(course, str) and course.strip() and isinstance(sources, list) and sources, 'NO_SOURCES')
    seen, result = set(), []
    for source in sources:
        require(isinstance(source, dict) and isinstance(source.get('id'), str) and source['id'] and source['id'] not in seen and isinstance(source.get('quote'), str) and source['quote'].strip(), 'INVALID_EVIDENCE')
        require(source.get('courseId') == course, 'COURSE_MISMATCH')
        require(isinstance(source.get('documentId'), str) and source['documentId'] and isinstance(source.get('version'), str) and source['version'], 'EVIDENCE_VERSION_REQUIRED')
        seen.add(source['id'])
        result.append(clone(source))
    return {'courseId': course, 'sources': result, 'version': fingerprint([[s['id'], s['documentId'], s['version'], s['quote']] for s in result])}


async def validate_claims(claims, pack, review=None, signal=None):
    require(isinstance(claims, list) and 0 < len(claims) <= 100, 'INVALID_CLAIMS')
    sources, candidates, checked = {s['id']: s for s in pack['sources']}, [], []
    for claim in claims:
        check_cancel(signal)
        require(isinstance(claim, dict) and isinstance(claim.get('text'), str) and claim['text'].strip()
                and len(claim['text']) <= 8000 and isinstance(claim.get('evidence'), list)
                and 0 < len(claim['evidence']) <= 12, 'UNSUPPORTED_CLAIM')
        refs = []
        for ref in claim['evidence']:
            require(isinstance(ref, dict), 'INVALID_CITATION')
            source = sources.get(citation_source_id(ref.get('sourceId'), pack['sources']))
            require(source, 'INVALID_CITATION')
            quote = ref.get('quote')
            if 'quoteId' in ref:
                require(isinstance(ref['quoteId'], str), 'INVALID_CITATION')
                canonical = quote_spans(source).get(ref['quoteId'])
                require(canonical and ('quote' not in ref or quote == canonical), 'INVALID_CITATION')
                quote = canonical
            require(isinstance(quote, str) and quote.strip() and quote in source['quote'], 'INVALID_CITATION')
            refs.append({'sourceId': source['id'], 'documentId': source.get('documentId'), 'version': source.get('version'), 'quote': quote, 'location': source.get('location')})
        exact = [ref for ref in refs if ref['quote'].strip() == claim['text'].strip()]
        candidates.append({'text': exact[0]['quote'] if exact else claim['text'], 'evidence': exact or refs,
                           'kind': 'excerpt' if exact else 'inference' if claim.get('kind') == 'inference' else 'paraphrase'})
    # Validate every citation before any external review; one batch per answer.
    prepare = getattr(review, 'prepare', None)
    if prepare and any(c['kind'] != 'excerpt' for c in candidates):
        await resolve(prepare(candidates, signal=signal))
    for item in candidates:
        check_cancel(signal)
        result = ({'supported': True, 'method': 'exact-excerpt'} if item['kind'] == 'excerpt'
                  else await resolve(review(item, signal=signal)) if review else {'supported': False, 'method': 'needs-review'})
        check_cancel(signal)
        checked.append({**item, 'support': 'supported' if isinstance(result, dict) and result.get('supported') is True else 'unverified', 'review': result})
    return checked
