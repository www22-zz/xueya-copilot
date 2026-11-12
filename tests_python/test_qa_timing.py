"""ResponseTiming token/counter accrual and one-per-call provider wiring."""
import asyncio

import httpx
import pytest

from backend.xueya.config import Config
from backend.xueya.platform import Platform
from backend.xueya.provider import MimoProvider
from backend.xueya.qa_latency import ResponseTiming, current_timing

LEGACY_KEYS = {"route", "totalMs", "firstContentMs", "firstModelTokenMs", "modelMs", "modelCalls", "phasesMs"}


@pytest.fixture
def platform(tmp_path):
    value = Platform(tmp_path / "timing")
    yield value
    asyncio.run(value.close())


def test_note_usage_accumulates_ints_and_ignores_other_values():
    timing = ResponseTiming()
    timing.note_usage({"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14})
    timing.note_usage({"prompt_tokens": 2, "completion_tokens": 1, "promptTokens": 1, "outputTokens": 1,
                       "repairs": 1, "review_calls": 3, "cache_hits": 2})
    # Non-integer values (including bool, floats and numeric strings) are ignored.
    timing.note_usage({"prompt_tokens": "9", "completion_tokens": True, "repairs": None,
                       "review_calls": 2.5, "cache_hits": "4"})
    timing.note_usage(None)
    timing.note_usage([])
    timing.note_usage({})
    snapshot = timing.snapshot()
    assert snapshot["promptTokens"] == 13
    assert snapshot["outputTokens"] == 6
    assert snapshot["repairs"] == 1
    assert snapshot["reviewCalls"] == 3
    assert snapshot["cacheHits"] == 2


def test_snapshot_keeps_existing_keys_and_adds_zero_defaults():
    timing = ResponseTiming()
    snapshot = timing.snapshot()
    assert LEGACY_KEYS <= set(snapshot)
    assert snapshot["modelCalls"] == 0
    assert snapshot["promptTokens"] == snapshot["outputTokens"] == 0
    assert snapshot["repairs"] == snapshot["reviewCalls"] == snapshot["cacheHits"] == 0
    assert snapshot["firstContentMs"] is None and snapshot["firstModelTokenMs"] is None
    timing.phase({"type": "content", "text": "x"})
    assert timing.snapshot()["firstContentMs"] is not None


async def test_provider_accrues_usage_exactly_once_for_generate(platform):
    def upstream(request):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12}})

    provider = MimoProvider(Config(api_key="test-only"), platform, httpx.MockTransport(upstream))
    timing = ResponseTiming()
    token = current_timing.set(timing)
    try:
        await provider.generate([], scope=platform.scope())
    finally:
        current_timing.reset(token)
    snapshot = timing.snapshot()
    assert timing.model_calls == 1
    assert snapshot["promptTokens"] == 7
    assert snapshot["outputTokens"] == 5
    assert platform.resources.stats()["active"]["api"] == 0


async def test_provider_counts_failures_without_accruing_unknown_usage(platform):
    def broken(request):
        raise httpx.ReadError("controlled network failure")

    provider = MimoProvider(Config(api_key="test-only"), platform, httpx.MockTransport(broken))
    timing = ResponseTiming()
    token = current_timing.set(timing)
    try:
        with pytest.raises(httpx.ReadError):
            await provider.generate([], scope=platform.scope())
    finally:
        current_timing.reset(token)
    assert timing.model_calls == 1
    assert timing.prompt_tokens == 0 and timing.output_tokens == 0
    assert timing.snapshot()["reviewCalls"] == 0
    assert platform.resources.stats()["active"]["api"] == 0


async def test_provider_accrues_usage_for_streamed_calls(platform):
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":2}}\n\n'
            yield b'data: [DONE]\n\n'

    provider = MimoProvider(Config(api_key="test-only"), platform,
                            httpx.MockTransport(lambda request: httpx.Response(200, stream=Body())))
    timing = ResponseTiming()
    token = current_timing.set(timing)
    try:
        events = [event async for event in provider.stream([], scope=platform.scope())]
    finally:
        current_timing.reset(token)
    assert any(event["type"] == "content" for event in events)
    assert timing.model_calls == 1
    assert timing.prompt_tokens == 3 and timing.output_tokens == 2
