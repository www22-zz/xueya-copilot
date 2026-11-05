import asyncio
from types import SimpleNamespace
import pytest
from backend.xueya.common import AppError
from backend.xueya.platform import Platform


@pytest.mark.parametrize('override,global_limit,expected',[(None,1,'unknown'),(.4,1,'succeeded'),(.4,.025,'unknown')])
async def test_handler_deadline_is_opt_in_and_cannot_exceed_shared_budget(tmp_path,override,global_limit,expected):
    platform=Platform(tmp_path,preserve_legacy_data=True)
    try:
        queue=platform.jobs;queue.timeout=.025;queue.budget_config=SimpleNamespace(run_timeout=global_limit)
        calls=[]
        async def slow(scope,args,**callbacks):
            calls.append(1);await asyncio.sleep(.08);return {'saved':True}
        queue.register('deadline-test',slow,timeout=override)
        job=queue.submit(platform.user_id,{'type':'deadline-test','courseId':'course-default','resource':'api','maxAttempts':1,'idempotencyKey':'one'})
        queue.stopped=False
        await queue.tick()
        await asyncio.gather(*list(queue.active.values()))
        result=queue.get(job['id'],platform.user_id)
        assert result['status']==expected and result['attempts']==1 and calls==[1]
        if expected=='unknown':assert result['error']=='JOB_TIMEOUT'
        await queue.tick()
        assert calls==[1]  # Unknown work is never replayed.
    finally:
        await platform.close()


async def test_handler_timeout_cannot_be_supplied_in_client_job_args(tmp_path):
    platform=Platform(tmp_path,preserve_legacy_data=True)
    try:
        async def handler(*args,**kwargs):return {}
        for value in (True,0,-1,float('nan'),601):
            with pytest.raises(AppError,match='INVALID_JOB_TIMEOUT'):
                platform.jobs.register('bad',handler,timeout=value)
        platform.jobs.register('valid',handler)
        with pytest.raises(AppError,match='INVALID_JOB'):
            platform.jobs.submit(platform.user_id,{'type':'valid','courseId':'course-default','idempotencyKey':'bad','timeout':600})
    finally:
        await platform.close()
