from ..core import require, clone, fingerprint, resolve, check_cancel


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
    sources, checked = {s['id']: s for s in pack['sources']}, []
    for claim in claims:
        check_cancel(signal)
        require(isinstance(claim.get('text'), str) and claim['text'].strip() and isinstance(claim.get('evidence'), list) and claim['evidence'], 'UNSUPPORTED_CLAIM')
        refs = []
        for ref in claim['evidence']:
            source = sources.get(ref.get('sourceId'))
            require(source and isinstance(ref.get('quote'), str) and ref['quote'].strip() and ref['quote'] in source['quote'], 'INVALID_CITATION')
            refs.append({'sourceId': source['id'], 'documentId': source.get('documentId'), 'version': source.get('version'), 'quote': ref['quote'], 'location': source.get('location')})
        exact = any(ref['quote'] == claim['text'] for ref in refs)
        result = {'supported': True, 'method': 'exact-excerpt'} if exact else await resolve(review({'text': claim['text'], 'evidence': refs}, signal=signal)) if review else {'supported': False, 'method': 'needs-review'}
        check_cancel(signal)
        checked.append({'text': claim['text'], 'evidence': refs, 'kind': 'excerpt' if exact else 'inference' if claim.get('kind') == 'inference' else 'paraphrase', 'support': 'supported' if result.get('supported') is True else 'unverified', 'review': result})
    return checked
