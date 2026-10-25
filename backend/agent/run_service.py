"""Durable CAS state machine. Repository must provide atomic compare_and_set."""
import asyncio
import time
from ..core import require, clone, fingerprint, Cancellation, check_cancel, DomainError, resolve

ALLOWED = {
    'queued': ['running', 'cancelled'],
    'running': ['running', 'completed', 'failed', 'cancelled', 'unknown', 'awaiting_user', 'awaiting_confirmation'],
    'failed': ['queued', 'cancelled'],
    'unknown': ['queued', 'cancelled'],
    'awaiting_user': ['queued', 'cancelled'],
    'awaiting_confirmation': ['queued', 'cancelled'],
}


class RunService:
    def __init__(
        self,
        repository,
        handlers,
        verify_snapshot,
        clock=lambda: int(time.time() * 1000),
    ):
        require(
            (hasattr(repository, 'get') and hasattr(repository, 'compare_and_set')),
            'RUN_REPOSITORY_REQUIRED',
        )
        require(callable(verify_snapshot), 'SNAPSHOT_VALIDATOR_REQUIRED')
        self.repository, self.handlers, self.verify_snapshot, self.clock = (
            repository,
            handlers,
            verify_snapshot,
            clock,
        )
        self.executing = {}

    async def get(self, course, key):
        run = await self.repository.get(course, key)
        require(run and run['courseId'] == course, 'RUN_NOT_FOUND')
        return clone(run)

    async def _save(self, run, status, **patch):
        require(status in ALLOWED.get(run['status'], []), 'INVALID_RUN_TRANSITION')
        result = {**run, **clone(patch), 'status': status, 'revision': run['revision'] + 1, 'updatedAt': self.clock()}
        require(
            await self.repository.compare_and_set(run['courseId'], run['id'], run['revision'], result),
            'RUN_CONFLICT',
        )
        return result

    async def create(self, value):
        course, key, steps = value.get('courseId'), value.get('id'), value.get('steps')
        maximum, timeout = value.get('maxSteps', 64), value.get('timeoutMs', 120000)
        require(
            course
            and key
            and value.get('snapshot')
            and isinstance(steps, list)
            and 0 < len(steps) <= maximum <= 256
            and 1 <= timeout <= 3600000,
            'INVALID_RUN',
        )
        ids = set()
        for step in steps:
            require(
                step.get('id')
                and step['id'] not in ids
                and step.get('type') in self.handlers
                and step.get('effect') in ('read', 'remote', 'write'),
                'INVALID_RUN_STEP',
            )
            ids.add(step['id'])
        digest = fingerprint(
            {k: value[k] for k in ('input', 'snapshot', 'steps')} | {'maxSteps': maximum, 'timeoutMs': timeout},
        )
        old = await self.repository.get(course, key)
        if old:
            require(old['courseId'] == course, 'COURSE_MISMATCH')
            require(old['requestHash'] == digest, 'IDEMPOTENCY_CONFLICT')
            return clone(old)
        run = {
            'id': key,
            'courseId': course,
            'input': clone(value['input']),
            'snapshot': value['snapshot'],
            'requestHash': digest,
            'steps': [{**clone(s), 'status': 'pending', 'attempts': 0} for s in steps],
            'status': 'queued',
            'revision': 1,
            'createdAt': self.clock(),
            'updatedAt': self.clock(),
            'maxSteps': maximum,
            'timeoutMs': timeout,
            'executions': 0,
        }
        require(await self.repository.compare_and_set(course, key, 0, run), 'RUN_CONFLICT')
        return clone(run)

    async def execute(self, course, key, signal=None):
        check_cancel(signal)
        run = await self.get(course, key)
        if run['status'] != 'queued':
            return run
        require(await resolve(self.verify_snapshot(course, run['snapshot'])), 'STALE_EVIDENCE')
        run = await self._save(run, 'running')
        controller, finished = Cancellation(), asyncio.Event()
        self.executing[(course, key)] = controller, finished
        deadline = asyncio.get_running_loop().time() + run['timeoutMs'] / 1000
        try:
            for index in range(len(run['steps'])):
                check_cancel(signal)
                controller.check()
                step = run['steps'][index]
                if step['status'] == 'completed':
                    continue
                if step['effect'] == 'write' and step.get('confirmed') is not True:
                    return await self._save(run, 'awaiting_confirmation', waitingStep=step['id'])
                require(run['executions'] < run['maxSteps'], 'RUN_STEP_BUDGET')
                step['status'], step['attempts'] = 'running', step['attempts'] + 1
                run = await self._save(run, 'running', steps=run['steps'], executions=run['executions'] + 1)
                async def invoke():
                    return await resolve(
                        self.handlers[step['type']](
                            {
                                'courseId': course,
                                'runId': key,
                                'input': clone(run['input']),
                                'step': clone(step),
                                'previous': clone([s for s in run['steps'] if s['status'] == 'completed']),
                                'snapshot': run['snapshot'],
                                'idempotencyKey': fingerprint([course, key, step['id']]),
                                'signal': controller,
                            },
                        ),
                    )
                task = asyncio.create_task(invoke())
                waiters = [asyncio.create_task(controller.event.wait())]
                if signal:
                    waiters.append(asyncio.create_task(signal.event.wait()))
                try:
                    done, _ = await asyncio.wait(
                        [task, *waiters],
                        timeout=max(0, deadline - asyncio.get_running_loop().time()),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if task not in done:
                        if controller.aborted or signal and signal.aborted:
                            raise asyncio.CancelledError()
                        raise DomainError('RUN_TIMEOUT')
                    output = task.result()
                    check_cancel(signal)
                    controller.check()
                finally:
                    for future in [task, *waiters]:
                        if not future.done():
                            future.cancel()
                    # 即使处理函数忽略取消，也不能提交取消之后才返回的结果。
                    for waiter in waiters:
                        try:
                            await waiter
                        except asyncio.CancelledError:
                            pass
                if isinstance(output, dict) and output.get('awaitingUser'):
                    return await self._save(run, 'awaiting_user', waitingStep=step['id'], prompt=output.get('prompt'))
                run['steps'][index] = {**run['steps'][index], 'status': 'completed', 'output': clone(output), 'completedAt': self.clock()}
                run = await self._save(run, 'running', steps=run['steps'])
            return await self._save(run, 'completed')
        except (Exception, asyncio.CancelledError) as error:
            active = next((s for s in run['steps'] if s['status'] == 'running'), None)
            uncertain = bool(active and active['effect'] != 'read')
            cancelled = isinstance(error, asyncio.CancelledError)
            return await self._save(
                run,
                ('cancelled' if cancelled else 'unknown' if uncertain else 'failed'),
                error={
                    'code': ('RUN_CANCELLED' if cancelled else getattr(error, 'code', 'RUN_FAILED')),
                    'outcomeUnknown': uncertain,
                },
            )
        finally:
            self.executing.pop((course, key), None)
            finished.set()

    async def resume(self, course, key, options):
        run = await self.get(course, key)
        require(run['status'] not in ('completed', 'cancelled', 'queued', 'running'), 'RUN_NOT_RESUMABLE')
        require(run['revision'] == options.get('revision'), 'RUN_CONFLICT')
        require(await resolve(self.verify_snapshot(course, run['snapshot'])), 'STALE_EVIDENCE')
        require(
            (run['status'] != 'unknown' or options.get('acknowledgeUnknown') is True),
            'UNKNOWN_OUTCOME_REQUIRES_REVIEW',
        )
        require(
            (run['status'] != 'awaiting_confirmation' or options.get('confirmation') is True),
            'CONFIRMATION_REQUIRED',
        )
        require(run['status'] != 'awaiting_user' or 'userInput' in options, 'USER_INPUT_REQUIRED')
        steps = clone(run['steps'])
        for step in steps:
            if step['status'] == 'completed':
                continue
            step['status'] = 'pending'
            if step['id'] != run.get('waitingStep'):
                continue
            if options.get('confirmation') is True:
                step['confirmed'] = True
            if 'userInput' in options:
                step['userInput'] = clone(options['userInput'])
        return await self._save(run, 'queued', steps=steps, error=None, waitingStep=None, prompt=None)

    async def recover(self, course, key, lease_expired=False):
        run = await self.get(course, key)
        if run['status'] != 'running':
            return run
        require(lease_expired and (course, key) not in self.executing, 'ACTIVE_RUN')
        active = next((s for s in run['steps'] if s['status'] == 'running'), None)
        uncertain = bool(active and active['effect'] != 'read')
        return await self._save(
            run,
            ('unknown' if uncertain else 'failed'),
            error={'code': 'RUN_INTERRUPTED', 'outcomeUnknown': uncertain},
        )

    async def cancel(self, course, key):
        run = await self.get(course, key)
        if run['status'] in ('completed', 'cancelled'):
            return run
        if run['status'] == 'running':
            require((course, key) in self.executing, 'CANCEL_VIA_EXECUTION_SIGNAL')
            controller, finished = self.executing[(course, key)]
            controller.cancel()
            await finished.wait()
            return await self.get(course, key)
        return await self._save(run, 'cancelled')
