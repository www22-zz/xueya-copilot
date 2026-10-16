import asyncio
import pytest
from backend.core import DomainError, Cancellation
from backend.agent.run_service import RunService


async def test_confirmation_resume_restart_and_atomic_double_execution(repository):
    calls = []
    async def handler(step):
        calls.append(step['step']['id'])
        await asyncio.sleep(.01)
        return {'value': step['step']['id']}
    service = RunService(repository, {'step': handler}, lambda c, s: s == 'v1')
    run = await service.create({'courseId': 'c', 'id': 'r', 'input': {}, 'snapshot': 'v1', 'steps': [{'id': 'read', 'type': 'step', 'effect': 'read'}, {'id': 'write', 'type': 'step', 'effect': 'write'}]})
    waiting = await service.execute('c', 'r')
    assert waiting['status'] == 'awaiting_confirmation' and calls == ['read']
    # Fresh service object reads the same persisted checkpoints.
    restarted = RunService(repository, {'step': handler}, lambda c, s: True)
    with pytest.raises(DomainError, match='CONFIRMATION_REQUIRED'):
        await restarted.resume('c', 'r', {'revision': waiting['revision']})
    await restarted.resume('c', 'r', {'revision': waiting['revision'], 'confirmation': True})
    results = await asyncio.gather(restarted.execute('c', 'r'), restarted.execute('c', 'r'), return_exceptions=True)
    assert any(isinstance(r, dict) and r['status'] == 'completed' for r in results)
    assert calls == ['read', 'write']


@pytest.mark.parametrize('effect,status', [('read', 'failed'), ('remote', 'unknown'), ('write', 'unknown')])
async def test_timeout_unknown_outcome_is_not_automatic_retry(repository, effect, status):
    async def slow(step):
        await asyncio.sleep(10)
        return {'late': True}
    service = RunService(repository, {'step': slow}, lambda c, s: True)
    await service.create({'courseId': 'c', 'id': 'r', 'input': {}, 'snapshot': 'v', 'timeoutMs': 10, 'steps': [{'id': 'one', 'type': 'step', 'effect': effect, 'confirmed': True}]})
    result = await service.execute('c', 'r')
    assert result['status'] == status
    assert 'output' not in result['steps'][0]
    if status == 'unknown':
        with pytest.raises(DomainError, match='UNKNOWN_OUTCOME_REQUIRES_REVIEW'):
            await service.resume('c', 'r', {'revision': result['revision']})


async def test_cancel_running_and_stale_snapshot(repository):
    entered = asyncio.Event()
    async def slow(step):
        entered.set()
        await asyncio.sleep(10)
    service = RunService(repository, {'step': slow}, lambda c, s: True)
    await service.create({'courseId': 'c', 'id': 'r', 'input': {}, 'snapshot': 'v', 'steps': [{'id': 'one', 'type': 'step', 'effect': 'remote'}]})
    task = asyncio.create_task(service.execute('c', 'r'))
    await entered.wait()
    cancelled = await service.cancel('c', 'r')
    assert cancelled['status'] == 'cancelled'
    await task
    stale = RunService(repository, {'step': slow}, lambda c, s: False)
    await stale.create({'courseId': 'c', 'id': 'stale', 'input': {}, 'snapshot': 'v', 'steps': [{'id': 'one', 'type': 'step', 'effect': 'read'}]})
    with pytest.raises(DomainError, match='STALE_EVIDENCE'):
        await stale.execute('c', 'stale')


async def test_crash_recovery_requires_expired_lease_and_acknowledgement(repository):
    service = RunService(repository, {'step': lambda value: None}, lambda c, s: True)
    run = await service.create({'courseId': 'c', 'id': 'r', 'input': {}, 'snapshot': 'v', 'steps': [{'id': 'one', 'type': 'step', 'effect': 'remote'}]})
    run['status'], run['steps'][0]['status'] = 'running', 'running'
    repository.rows['c', 'r'] = run
    with pytest.raises(DomainError, match='ACTIVE_RUN'):
        await service.recover('c', 'r')
    recovered = await service.recover('c', 'r', lease_expired=True)
    assert recovered['status'] == 'unknown'
