"""Draft preview events are display-only and never become verified content."""
import asyncio
import json
from types import SimpleNamespace

from backend.xueya.agent import Agent, start_early_review

SOURCE = {'id': 'queue-1', 'documentId': 'doc-1', 'title': '队列', 'location': '第1页',
          'version': '3', 'quote': '队列遵循先进先出。队尾入队，队首出队。', 'keywords': ['队列']}

RESPONSE = json.dumps({
    'claims': [{'text': '队列是一种先进先出的结构。', 'kind': 'paraphrase',
                'evidence': [{'sourceId': SOURCE['id'], 'quote': '队列遵循先进先出。'}]}],
    'answer': 'DRAFT-ANSWER-TEXT',
    'sources': [SOURCE['id']],
}, ensure_ascii=False)


def chunks(text, size=7):
    return [text[index:index+size] for index in range(0, len(text), size)]


class Model:
    def __init__(self, chunks_, **options):
        self.chunks, self.config = chunks_, SimpleNamespace(
            model='controlled', draft_streaming=options.get('draft_streaming', True),
            answer_thinking_disabled=False, max_output_tokens=4096, answer_output_tokens=4096,
            answer_repair_enabled=False, early_review=False, early_review_failfast=False,
            answer_cache_ttl=0, retrieval_limit=6, api_key='offline-only',
            agent_planning_enabled=False)

    async def stream(self, messages, **options):
        for chunk in self.chunks:
            yield {'type': 'content', 'text': chunk, 'model': 'controlled'}

    async def generate(self, *args, **kwargs):
        raise RuntimeError('no review provider in this controlled test')


def run(draft_streaming=True):
    model = Model(chunks(RESPONSE), draft_streaming=draft_streaming)
    events = asyncio.run(_collect(Agent(model).workflow({'question': '队列是什么？',
                                                         'context': {'library': [SOURCE]}})))
    return events


async def _collect(stream):
    return [event async for event in stream]


def test_draft_events_precede_done_and_stay_out_of_verified_content():
    events = run()
    drafts = [event for event in events if event['type'] == 'draft']
    assert drafts and all(event.get('draft') is True for event in drafts)
    resets = [index for index, event in enumerate(drafts) if event.get('reset') is True]
    assert len(resets) == 1
    # Claims are previewed first, then the preview resets to the answer prose.
    assert '队列是一种先进先出的结构。' in ''.join(event['text'] for event in drafts[:resets[0]])
    assert ''.join(event['text'] for event in drafts[resets[0]+1:]) == 'DRAFT-ANSWER-TEXT'
    done = events[-1]
    assert done['type'] == 'done'
    assert events.index(drafts[-1]) < len(events)-1
    assert 'DRAFT-ANSWER-TEXT' not in ''.join(event.get('text', '') for event in events
                                             if event['type'] == 'content')
    # The rejected prose must never be published as a verified answer.
    assert 'DRAFT-ANSWER-TEXT' not in done['answer']
    assert done['answerStatus'] == 'unavailable'


def test_draft_streaming_disabled_emits_no_preview():
    events = run(draft_streaming=False)
    assert not any(event['type'] == 'draft' for event in events)


class Review:
    def __init__(self):
        self.prepared = []

    async def prepare(self, claims, signal=None):
        self.prepared.append(claims)


def test_early_review_starts_only_for_reviewable_claims():
    review = Review()

    async def scenario():
        task = start_early_review(review, [{'text': '队列是先进先出的。', 'kind': 'paraphrase',
                                            'evidence': [{'sourceId': SOURCE['id'],
                                                          'quote': '队列遵循先进先出。'}]}], [SOURCE])
        assert task is not None
        await task
        only_excerpt = start_early_review(review, [{'text': '队列遵循先进先出。', 'kind': 'excerpt',
                                                    'evidence': [{'sourceId': SOURCE['id'],
                                                                  'quote': '队列遵循先进先出。'}]}], [SOURCE])
        assert only_excerpt is None
        return start_early_review(review, [], [SOURCE])

    assert asyncio.run(scenario()) is None
    assert review.prepared and review.prepared[0][0]['kind'] == 'paraphrase'


def test_early_review_ignores_unparseable_claims():
    class Broken:
        async def prepare(self, claims, signal=None):
            raise AssertionError('must not be called')

    bad = [{'text': 'x', 'kind': 'paraphrase', 'evidence': [{'sourceId': 'forged', 'quote': '伪造'}]}]
    assert asyncio.run(_task_or_none(bad)) is None


async def _task_or_none(claims):
    from backend.xueya.agent import start_early_review
    return start_early_review(object(), claims, [SOURCE])
