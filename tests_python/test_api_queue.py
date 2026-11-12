"""API permit wait queue: bounded waiting, fail-fast, cancellation, provider wiring."""
import asyncio

import httpx
import pytest

from backend.core import DomainError
from backend.platform.resources import Resources as PlatformResources
from backend.xueya.common import AppError
from backend.xueya.config import Config
from backend.xueya.platform import Platform
from backend.xueya.provider import MimoProvider
from backend.xueya.resources import Resources


@pytest.fixture
def platform(tmp_path):
    value = Platform(tmp_path / "queue", api_slots=1)
    yield value
    asyncio.run(value.close())


async def test_acquire_wait_takes_free_slot_and_releases_idempotently():
    resources = Resources(api_slots=1, cpu_slots=1)
    release = await resources.acquire_wait("api", 1)
    assert resources.active["api"] == 1
    assert resources.stats()["active"]["api"] == 1
    assert set(resources.stats()) == {"active", "limits", "inference"}
    release()
    release()
    assert resources.active["api"] == 0
    # A zero timeout still succeeds when a slot is free; it only fails fast when full.
    release = await resources.acquire_wait("api", 0)
    assert resources.active["api"] == 1
    release()
    assert resources.active["api"] == 0


async def test_second_concurrent_call_waits_and_succeeds_after_first_finishes():
    resources = Resources(api_slots=1, cpu_slots=1)
    first = await resources.acquire_wait("api", 1)
    acquired = []

    async def second():
        release = await resources.acquire_wait("api", 2)
        acquired.append("second")
        release()

    task = asyncio.create_task(second())
    await asyncio.sleep(.05)
    assert resources.active["api"] == 1 and not acquired
    assert resources.waiting("api") == 1
    first()
    await asyncio.wait_for(task, 2)
    assert acquired == ["second"]
    assert resources.active["api"] == 0
    assert resources.waiting("api") == 0


async def test_bounded_wait_timeout_raises_api_busy_and_leaves_active_zero():
    resources = Resources(api_slots=1, cpu_slots=1)
    release = await resources.acquire_wait("api", 1)
    with pytest.raises(AppError, match="API_BUSY"):
        await resources.acquire_wait("api", .05)
    assert resources.active["api"] == 1 and resources.waiting("api") == 0
    release()
    assert resources.active["api"] == 0


async def test_cancelling_a_waiter_leaves_no_active_slot_or_stuck_waiter():
    resources = Resources(api_slots=1, cpu_slots=1)
    first = await resources.acquire_wait("api", 1)
    waiter = asyncio.create_task(resources.acquire_wait("api", 5))
    await asyncio.sleep(.05)
    assert resources.waiting("api") == 1
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert resources.active["api"] == 1
    assert resources.waiting("api") == 0
    first()
    assert resources.active["api"] == 0
    # The queue keeps working after the cancelled waiter.
    release = await resources.acquire_wait("api", .5)
    release()
    assert resources.active["api"] == 0


async def test_release_wakes_a_surviving_waiter_after_peer_cancellation():
    resources = Resources(api_slots=1, cpu_slots=1)
    first = await resources.acquire_wait("api", 1)
    cancelled = asyncio.create_task(resources.acquire_wait("api", 2))
    surviving = asyncio.create_task(resources.acquire_wait("api", 2))
    await asyncio.sleep(.05)
    assert resources.waiting("api") == 2
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    first()
    release = await asyncio.wait_for(surviving, 1)
    release()
    assert resources.active["api"] == 0 and resources.waiting("api") == 0


async def test_platform_resources_wait_queue_parity():
    resources = PlatformResources(api_slots=1, cpu_slots=1)
    first = await resources.acquire_wait("api", 1)
    with pytest.raises(DomainError, match="API_BUSY"):
        await resources.acquire_wait("api", .05)
    waiter = asyncio.create_task(resources.acquire_wait("api", 2))
    await asyncio.sleep(.05)
    assert resources.waiting("api") == 1
    first()
    release = await asyncio.wait_for(waiter, 1)
    release()
    assert resources.active["api"] == 0 and resources.waiting("api") == 0


async def test_provider_queues_instead_of_failing_when_slot_is_busy(platform):
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []

    async def upstream(request):
        calls.append(request)
        if len(calls) == 1:
            started.set()
            await finish.wait()
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}],
                                         "usage": {"prompt_tokens": 3, "completion_tokens": 2}})

    provider = MimoProvider(Config(api_key="test-only", api_slots=1, api_queue_timeout=1),
                            platform, httpx.MockTransport(upstream))
    first = asyncio.create_task(provider.generate([], scope=platform.scope()))
    await started.wait()
    second = asyncio.create_task(provider.generate([], scope=platform.scope()))
    await asyncio.sleep(.05)
    assert len(calls) == 1
    assert platform.resources.stats()["active"]["api"] == 1
    assert platform.resources.waiting("api") == 1
    finish.set()
    results = await asyncio.gather(first, second)
    assert [result["content"] for result in results] == ["ok", "ok"]
    assert len(calls) == 2
    assert platform.resources.stats()["active"]["api"] == 0
    assert platform.resources.waiting("api") == 0


async def test_provider_queue_timeout_returns_api_busy_without_ledger_row(platform):
    calls = []
    provider = MimoProvider(Config(api_key="test-only", api_slots=1, api_queue_timeout=.05),
                            platform, httpx.MockTransport(lambda request: calls.append(request)))
    held = platform.resources.acquire("api")
    try:
        with pytest.raises(AppError, match="API_BUSY"):
            await provider.generate([], scope=platform.scope())
        assert calls == []
        assert platform.resources.stats()["active"]["api"] == 1
        assert platform.resources.waiting("api") == 0
        assert platform.db.one("SELECT count(*) n FROM invocations")["n"] == 0
    finally:
        held()
    assert platform.resources.stats()["active"]["api"] == 0


async def test_provider_keeps_legacy_fail_fast_with_zero_queue_timeout(platform):
    calls = []
    provider = MimoProvider(Config(api_key="test-only", api_slots=1, api_queue_timeout=0),
                            platform, httpx.MockTransport(lambda request: calls.append(request)))
    held = platform.resources.acquire("api")
    try:
        with pytest.raises(AppError, match="API_BUSY"):
            await provider.generate([], scope=platform.scope())
        assert calls == []
    finally:
        held()
    assert platform.resources.stats()["active"]["api"] == 0
