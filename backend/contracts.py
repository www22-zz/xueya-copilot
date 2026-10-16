from .core import DomainError, require

LIMITS = {'question': 4000, 'history': 8, 'historyContent': 5000, 'sources': 6,
          'quote': 3000, 'answer': 16000, 'requestBytes': 524288, 'fileBytes': 10485760,
          'parsedCharacters': 1200000}


def normalize_chat_request(value):
    require(isinstance(value, dict), 'EMPTY_QUESTION')
    question = str(value.get('question') or '').strip()[:4000]
    require(question, 'EMPTY_QUESTION')
    history = value.get('history') if isinstance(value.get('history'), list) else []
    return {'question': question, 'mode': value.get('mode') if value.get('mode') in ('ask', 'summarize', 'quiz') else 'ask',
            'history': [{'role': x['role'], 'content': x['content'][:5000]} for x in history[-8:]
                        if isinstance(x, dict) and x.get('role') in ('user', 'assistant') and isinstance(x.get('content'), str)],
            'sources': value.get('sources') if isinstance(value.get('sources'), list) else []}


def sanitize_sources(values, catalog=()):
    result, seen = [], set()
    for value in (values if isinstance(values, list) else [])[:6]:
        source = next((s for s in catalog if s['id'] == value), None) if isinstance(value, str) else value
        if not isinstance(source, dict) or not isinstance(source.get('id'), str) or not isinstance(source.get('quote'), str) or not source['quote'].strip():
            continue
        key = source['id'][:150]
        if not key or key in seen:
            continue
        seen.add(key)
        result.append({'id': key, 'title': str(source.get('title') or '课程资料')[:200],
                       'location': str(source.get('location') or '')[:150], 'quote': source['quote'][:3000]})
    return result
