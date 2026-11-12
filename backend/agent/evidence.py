from ..core import require, clone, fingerprint, resolve, check_cancel
import inspect
import re
import unicodedata


# Punctuation variants folded after NFKC. NFKC already folds ASCII full-width
# forms (digits/letters/punctuation) and the ellipsis "…" to "...", while CJK
# glyphs stay 1:1, so only the variants below need an explicit mapping.
_PUNCTUATION = {'“': '"', '”': '"', '‘': "'", '’': "'", '。': '.', '、': ','}


def _normalize_unit(char):
    """Conservative normalization of one source character; may be empty."""
    if char.isspace():
        return ''
    return ''.join(_PUNCTUATION.get(unit, unit) for unit in unicodedata.normalize('NFKC', char))


def normalize_quote_text(value):
    """Normalized rendering used only to compare/repair server-checked quotes.

    Accepted normalizations: whitespace runs are removed; NFKC folds ASCII
    full-width digits/letters/punctuation and the ellipsis to its ASCII form;
    “”‘’ fold to a straight double/single quote, 。 and 、 fold to . and ,.
    CJK characters are otherwise kept 1:1. It is never used as output text.
    """
    return ''.join(_normalize_unit(char) for char in value)


def _normalized_units(value):
    """Normalized rendering plus, per output char, the original char span."""
    rendered, starts, ends = [], [], []
    for index, char in enumerate(value):
        units = _normalize_unit(char)
        for unit in units:
            rendered.append(unit)
            starts.append(index)
            ends.append(index + 1)
    return ''.join(rendered), starts, ends


def _boundary_aligned(starts, ends, start, end):
    """A match must begin/end on an original character boundary, not inside a
    multi-char expansion such as "…" -> "..."."""
    if start > 0 and starts[start - 1] == starts[start]:
        return False
    if end < len(ends) and ends[end - 1] == ends[end]:
        return False
    return True


def repair_quote(quote, source_quote):
    """Map a normalized quote back to a real contiguous span of the source.

    Returns the original ``source_quote[start:end]`` text, never synthesized
    text, or None when no safe contiguous match exists. A match is only
    accepted after re-normalizing the original span to the candidate's
    normalized form, and candidates shorter than 6 normalized characters are
    rejected to avoid accidental false positives.
    """
    candidate = normalize_quote_text(quote)
    if len(candidate) < 6:
        return None
    normalized, starts, ends = _normalized_units(source_quote)
    position = normalized.find(candidate)
    while position >= 0:
        end = position + len(candidate)
        if _boundary_aligned(starts, ends, position, end):
            original = source_quote[starts[position]:ends[end - 1]]
            if normalize_quote_text(original) == candidate:
                return original
        position = normalized.find(candidate, position + 1)
    return None


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


def _resolve_quote(ref, source):
    """Return (canonical quote, repaired flag) for one evidence reference."""
    quote = ref.get('quote')
    if 'quoteId' in ref:
        require(isinstance(ref['quoteId'], str), 'INVALID_CITATION')
        canonical = quote_spans(source).get(ref['quoteId'])
        require(canonical, 'INVALID_CITATION')
        repaired = False
        if 'quote' in ref:
            # Server-owned span wins; a provided quote only has to agree with it
            # after conservative normalization (exact equality included).
            require(isinstance(quote, str) and quote.strip()
                    and normalize_quote_text(quote) == normalize_quote_text(canonical), 'INVALID_CITATION')
            repaired = quote != canonical
        quote = canonical
    else:
        require(isinstance(quote, str) and quote.strip(), 'INVALID_CITATION')
        repaired = False
        if quote not in source['quote']:
            # Exact substring is always tried first; only then repair to a real
            # contiguous original span, never to synthesized text.
            quote = repair_quote(quote, source['quote'])
            require(quote is not None, 'INVALID_CITATION')
            repaired = True
    require(isinstance(quote, str) and quote.strip() and quote in source['quote'], 'INVALID_CITATION')
    return quote, repaired


def _notify_repair(callback, source, quote):
    """Call the optional repair hook once. Counters (no parameters) and
    detail callbacks (one positional dict) are both supported."""
    info = {'sourceId': source['id'], 'quote': quote}
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        callback(info)
        return
    if any(parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD,
                              parameter.VAR_POSITIONAL) for parameter in parameters):
        callback(info)
    else:
        callback()


def normalize_claims(claims, pack, on_repair=None, signal=None):
    """Validate citations and build review candidates ({text, evidence, kind}).

    Raises the same DomainError codes validate_claims always raised. When a
    quote is present, its exact text is accepted first; otherwise it may be
    repaired (see normalize_quote_text/repair_quote) to a contiguous original
    substring of the server-owned source quote and the repaired ref stores that
    canonical original text. Quote refs shorter than 6 normalized characters
    are never repaired, and no extra keys are added to the public ref shape.
    `on_repair` is called once per repaired ref (counting is all it changes).
    """
    require(isinstance(claims, list) and 0 < len(claims) <= 100, 'INVALID_CLAIMS')
    sources, candidates = {s['id']: s for s in pack['sources']}, []
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
            quote, repaired = _resolve_quote(ref, source)
            if repaired and on_repair is not None:
                _notify_repair(on_repair, source, quote)
            refs.append({'sourceId': source['id'], 'documentId': source.get('documentId'), 'version': source.get('version'), 'quote': quote, 'location': source.get('location')})
        exact = [ref for ref in refs if ref['quote'].strip() == claim['text'].strip()]
        candidates.append({'text': exact[0]['quote'] if exact else claim['text'], 'evidence': exact or refs,
                           'kind': 'excerpt' if exact else 'inference' if claim.get('kind') == 'inference' else 'paraphrase'})
    return candidates


async def validate_claims(claims, pack, review=None, signal=None, on_repair=None):
    candidates = normalize_claims(claims, pack, on_repair=on_repair, signal=signal)
    # Validate every citation before any external review; one batch per answer.
    prepare = getattr(review, 'prepare', None)
    if prepare and any(c['kind'] != 'excerpt' for c in candidates):
        await resolve(prepare(candidates, signal=signal))
    checked = []
    for item in candidates:
        check_cancel(signal)
        result = ({'supported': True, 'method': 'exact-excerpt'} if item['kind'] == 'excerpt'
                  else await resolve(review(item, signal=signal)) if review else {'supported': False, 'method': 'needs-review'})
        check_cancel(signal)
        checked.append({**item, 'support': 'supported' if isinstance(result, dict) and result.get('supported') is True else 'unverified', 'review': result})
    return checked
