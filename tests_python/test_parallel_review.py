"""Parallel review shards and incremental prepare for EvidenceReviewer."""
import asyncio
import json

import httpx
import pytest

from backend.xueya.common import dumps
from backend.xueya.config import Config
from backend.xueya.evidence_review import SYSTEM, EvidenceReviewer
from backend.xueya.provider import MimoProvider
from backend.xueya.qa_latency import ResponseTiming, current_timing

QUOTE = '队列遵循先进先出，入队在队尾，出队在队首。'


def claim(text, kind='paraphrase'):
    return {'text': text, 'kind': kind,
            'evidence': [{'sourceId': 'source-1', 'quote': QUOTE}]}


def make_reviewer(handler, **options):
    options.setdefault('api_key', 'offline-only')
    config = Config(**options)
    return EvidenceReviewer(MimoProvider(config, transport=httpx.MockTransport(handler)), None)


def batch_of(body):
    return json.loads(body['messages'][-1]['content'])['claims']


def verdict_response(body, statuses=None):
    statuses = statuses or {}
    batch = batch_of(body)
    verdicts = [{'index': item['index'], 'status': statuses.get(item['text'], 'supported')} for item in batch]
    return httpx.Response(200, json={'choices': [{'message': {'content': dumps({'verdicts': verdicts})},
                                                  'finish_reason': 'stop'}]})


async def test_five_claims_split_into_two_concurrent_shards():
    claims = [claim(f'说法{i}') for i in range(5)]
    calls, state, both = [], {'now': 0, 'peak': 0}, asyncio.Event()

    async def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        state['now'] += 1
        state['peak'] = max(state['peak'], state['now'])
        if state['now'] >= 2:
            both.set()
        try:
            await asyncio.wait_for(both.wait(), 2)
        finally:
            state['now'] -= 1
        return verdict_response(body)

    reviewer = make_reviewer(upstream, review_shards=2, review_shard_min_claims=4)
    await reviewer.prepare(claims)

    assert len(calls) == 2 and state['peak'] == 2
    assert sorted(len(batch_of(body)) for body in calls) == [2, 3]
    for body in calls:
        assert body['messages'][0]['content'] == SYSTEM
        assert body['temperature'] == 0
        assert body['max_completion_tokens'] == 1536
        assert body['response_format'] == {'type': 'json_object'}
        assert body['thinking'] == {'type': 'disabled'}
    assert all([(await reviewer(item))['supported'] is True for item in claims])
    assert reviewer.prepared is True


async def test_three_claims_stay_in_one_request():
    claims = [claim(f'说法{i}') for i in range(3)]
    calls = []

    def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        return verdict_response(body)

    reviewer = make_reviewer(upstream)
    await reviewer.prepare(claims)

    assert len(calls) == 1 and len(batch_of(calls[0])) == 3
    assert all([(await reviewer(item))['supported'] is True for item in claims])
    assert (await reviewer(claim('未审核的说法'))) == {'supported': False, 'method': 'model-entailment'}


async def test_incremental_prepare_reviews_only_uncovered_claims():
    early = [claim(f'早期说法{i}') for i in range(3)]
    prose = claim('整篇正文的改写', kind='inference')
    calls = []

    def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        return verdict_response(body)

    reviewer = make_reviewer(upstream)
    await reviewer.prepare(early)
    assert len(calls) == 1
    assert [item['text'] for item in batch_of(calls[0])] == [item['text'] for item in early]

    await reviewer.prepare([*early, prose])
    assert len(calls) == 2
    assert [item['text'] for item in batch_of(calls[1])] == [prose['text']]
    assert all([(await reviewer(item))['supported'] is True for item in [*early, prose]])

    # Repeating the same prepare no longer sends any review request.
    await reviewer.prepare([*early, prose])
    assert len(calls) == 2


async def test_concurrent_prepare_calls_do_not_duplicate_a_review():
    claims = [claim(f'说法{i}') for i in range(5)]
    calls = []

    def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        return verdict_response(body)

    reviewer = make_reviewer(upstream, review_shards=2, review_shard_min_claims=4)
    await asyncio.gather(reviewer.prepare(claims), reviewer.prepare(claims))

    assert len(calls) == 2  # one two-shard batch, not two duplicated reviews
    assert all([(await reviewer(item))['supported'] is True for item in claims])


async def test_one_failed_shard_leaves_only_its_own_claims_unverified():
    claims = [claim(f'说法{i}') for i in range(5)]
    calls = []

    async def upstream(request):
        body = json.loads(request.content)
        batch = batch_of(body)
        calls.append(batch)
        if '说法0' in [item['text'] for item in batch]:  # round-robin shard 0
            return httpx.Response(503)
        return verdict_response(body)

    reviewer = make_reviewer(upstream, review_shards=2, review_shard_min_claims=4)
    await reviewer.prepare(claims)  # no exception escapes a failed shard

    assert len(calls) == 2
    unverified = [item for item in claims if item['text'] in ('说法0', '说法2', '说法4')]
    reviewed = [item for item in claims if item['text'] in ('说法1', '说法3')]
    assert all([(await reviewer(item))['supported'] is False for item in unverified])
    assert all([(await reviewer(item))['supported'] is True for item in reviewed])


MALFORMED = [
    '{}',
    '[]',
    'not json',
    '{"verdicts": {}}',
    '{"verdicts": []}',
    '{"verdicts": [{"index": 0, "status": "supported"}, {"index": 1, "status": "supported"}]}',
    '{"verdicts": [{"index": 0, "status": "supported"}, {"index": 0, "status": "supported"},'
    ' {"index": 2, "status": "supported"}]}',
    '{"verdicts": [{"index": 0, "status": "supported"}, {"index": 1, "status": "supported"},'
    ' {"index": 3, "status": "supported"}]}',
    '{"verdicts": [{"index": true, "status": "supported"}, {"index": 1, "status": "supported"},'
    ' {"index": 2, "status": "supported"}]}',
    '{"verdicts": [{"index": 0, "status": "maybe"}, {"index": 1, "status": "supported"},'
    ' {"index": 2, "status": "supported"}]}',
    '{"verdicts": [{"index": 0, "status": "supported", "why": "x"},'
    ' {"index": 1, "status": "supported"}, {"index": 2, "status": "supported"}]}',
    '{"verdicts": [{"index": 0}, {"index": 1, "status": "supported"}, {"index": 2, "status": "supported"}]}',
    '{"verdicts": [{"index": 0, "status": "supported"}]}',
]


@pytest.mark.parametrize('content', MALFORMED)
async def test_malformed_verdict_batch_is_rejected_wholesale(content):
    claims = [claim(f'说法{i}') for i in range(3)]
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]})

    reviewer = make_reviewer(upstream)
    await reviewer.prepare(claims)

    assert len(calls) == 1
    assert reviewer.verdicts == {}
    assert all([(await reviewer(item))['supported'] is False for item in claims])


async def test_oversize_payload_makes_no_request():
    calls = []

    def upstream(request):
        calls.append(request)
        return verdict_response(json.loads(request.content))

    reviewer = make_reviewer(upstream)
    oversized = claim('x'*100000)
    await reviewer.prepare([oversized])

    assert calls == []
    assert reviewer.verdicts == {}
    assert (await reviewer(oversized))['supported'] is False
    assert reviewer.prepared is True


async def test_excerpts_and_more_than_twelve_pending_claims_are_not_reviewed():
    calls = []

    def upstream(request):
        calls.append(request)
        return verdict_response(json.loads(request.content))

    reviewer = make_reviewer(upstream)
    await reviewer.prepare([claim(f'原文{i}', kind='excerpt') for i in range(3)])
    assert calls == []

    # `prepared` no longer short-circuits: a later call still screens its claims.
    await reviewer.prepare([claim(f'说法{i}') for i in range(13)])
    assert calls == []
    assert reviewer.verdicts == {}


async def test_review_timing_counts_parallel_shard_calls():
    claims = [claim(f'说法{i}') for i in range(5)]

    def upstream(request):
        return verdict_response(json.loads(request.content))

    reviewer = make_reviewer(upstream, review_shards=2, review_shard_min_claims=4)
    timing = ResponseTiming()
    token = current_timing.set(timing)
    try:
        await reviewer.prepare(claims)
    finally:
        current_timing.reset(token)

    assert timing.review_calls == 2
    assert timing.model_calls == 2
    assert timing.phases['evidenceReview'] > 0


async def test_cancellation_during_shard_propagates_and_releases_lock():
    claims = [claim(f'说法{i}') for i in range(3)]
    entered, release, calls = asyncio.Event(), asyncio.Event(), []

    async def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        entered.set()
        await release.wait()
        return verdict_response(body)

    reviewer = make_reviewer(upstream)
    task = asyncio.create_task(reviewer.prepare(claims))
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(calls) == 1
    assert not reviewer._lock.locked()
    assert reviewer.verdicts == {} and reviewer.prepared is True

    # The lock and verdict state remain usable after cancellation.
    release.set()
    await reviewer.prepare(claims)
    assert len(calls) == 2
    assert all([(await reviewer(item))['supported'] is True for item in claims])
