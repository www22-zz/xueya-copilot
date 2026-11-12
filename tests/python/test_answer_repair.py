"""Excerpt-only repair after a failed claim check (offline, no paid API)."""
import asyncio
from types import SimpleNamespace

from backend.agent import answer_repair
from backend.agent.answer_policy import finalize_answer

SOURCE = {'id': 'queue-1', 'documentId': 'doc-1', 'title': '队列', 'location': '第1页',
          'version': '3', 'quote': '队列遵循先进先出。队尾入队，队首出队。'}

CONTENT = {'answer': '队列是一种先进先出的结构。', 'sources': [SOURCE['id']],
           'claims': [{'text': '队列是一种先进先出的结构。', 'kind': 'paraphrase',
                       'evidence': [{'sourceId': SOURCE['id'], 'quote': SOURCE['quote']}]}]}


class Provider:
    def __init__(self, content, enabled=True):
        self.content, self.calls = content, []
        self.config = SimpleNamespace(model='controlled', max_output_tokens=4096,
                                      answer_repair_enabled=enabled, answer_repair_tokens=1024)

    async def generate(self, messages, **options):
        self.calls.append((messages, options))
        if isinstance(self.content, Exception):
            raise self.content
        return {'content': self.content, 'model': 'controlled', 'usage': {'completion_tokens': 8}}


class Review:
    def __init__(self, provider, supported=False):
        self.provider, self.scope, self.supported = provider, None, supported
        self.prepared, self.verdicts = False, {}

    async def prepare(self, claims, signal=None):
        self.prepared = True

    async def __call__(self, claim, signal=None):
        return {'supported': self.supported, 'method': 'model-entailment'}


def dumps(value):
    import json
    return json.dumps(value, ensure_ascii=False)


def run(content=CONTENT, repair_content=None, enabled=True):
    provider = Provider(repair_content if repair_content is not None else
                        dumps({'answerable': True, 'quotes': [{'sourceId': 'cite1', 'quoteId': 's1'}]}), enabled)
    review = Review(provider)
    result = asyncio.run(finalize_answer(dumps(content), [SOURCE], 'controlled', review=review,
                                         question='队列是什么？', narrative=True))
    return result, provider


def test_failed_narrative_is_repaired_from_server_owned_quotes():
    result, provider = run()
    assert result['verification'] == 'repaired-excerpts'
    assert result['sources'] == [SOURCE['id']]
    assert result['answer'] == '队列遵循先进先出。 [1]'
    assert result['claims'][0]['kind'] == 'excerpt'
    assert result['repair']['mode'] == 'excerpt'
    assert result.get('answerStatus') is None
    assert len(provider.calls) == 1
    messages, options = provider.calls[0]
    assert options['response_format'] == {'type': 'json_object'}
    assert options['thinking'] == {'type': 'disabled'}
    assert options['max_output_tokens'] == 1024


def test_repair_disabled_keeps_fail_closed_fallback():
    result, provider = run(enabled=False)
    assert result['answerStatus'] == 'unavailable' and result['verification'] == 'not-generated'
    assert provider.calls == []


def test_repair_declining_keeps_fail_closed_fallback():
    result, provider = run(repair_content=dumps({'answerable': False, 'quotes': []}))
    assert result['answerStatus'] == 'unavailable' and result['verification'] == 'not-generated'
    assert len(provider.calls) == 1


def test_repair_invalid_quote_id_never_publishes_content():
    result, provider = run(repair_content=dumps({'answerable': True,
                                                 'quotes': [{'sourceId': 'cite1', 'quoteId': 's999'}]}))
    assert result['answerStatus'] == 'unavailable'
    assert '队尾入队' not in result['answer']
    assert len(provider.calls) == 1


def test_repair_provider_failure_keeps_original_result():
    result, provider = run(repair_content=RuntimeError('boom'))
    assert result['answerStatus'] == 'unavailable'
    assert len(provider.calls) == 1


def test_repair_never_invents_text_beyond_the_original_source():
    result, provider = run(repair_content=dumps({'answerable': True,
                                                 'quotes': [{'sourceId': 'cite1', 'quoteId': 's1'},
                                                            {'sourceId': 'cite1', 'quoteId': 's1'}]}))
    assert result['answer'] == '队列遵循先进先出。 [1]'
    assert result['answer'].count('队列遵循先进先出。') == 1
