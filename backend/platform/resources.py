import asyncio
from collections import deque

from ..core import DomainError, require


class Resources:
    def __init__(self, api_slots=2, cpu_slots=2):
        self.active, self.limits = {'api': 0, 'cpu': 0}, {'api': api_slots, 'cpu': cpu_slots}
        # Pending acquire_wait futures per resource. Diagnostics only: stats()
        # keeps its existing wire shape for the host bootstrap endpoint.
        self.waiters = {'api': deque(), 'cpu': deque()}

    def choose(self, resource):
        require(resource in self.limits, 'RESOURCE_UNSUPPORTED')
        return resource

    def _slot(self, resource):
        """Mark one slot busy and return an idempotent release callable."""
        self.active[resource] += 1
        released = False

        def release():
            nonlocal released
            if not released:
                released = True
                self.active[resource] -= 1
                self._wake(resource)
        return release

    def acquire(self, resource):
        self.choose(resource)
        if self.active[resource] >= self.limits[resource]:
            return None
        return self._slot(resource)

    def waiting(self, resource):
        """Number of queued acquire_wait callers (internal diagnostics only)."""
        self.choose(resource)
        return len(self.waiters[resource])

    def _wake(self, resource):
        """Wake the oldest waiter; the slot itself is only granted on retry."""
        waiters = self.waiters[resource]
        while waiters:
            future = waiters.popleft()
            if not future.done():
                future.set_result(True)
                return

    async def acquire_wait(self, resource, timeout=0):
        """Take an API/CPU slot now, or queue FIFO-ish for up to timeout seconds.

        ``timeout <= 0`` fails fast with API_BUSY, preserving the legacy
        contract. A timed-out or cancelled waiter is removed from the queue
        before anything is granted, so it can never leak an active slot.
        """
        self.choose(resource)
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = 0.0
        if not timeout > 0:  # zero, negative and NaN all mean fail fast
            if self.active[resource] >= self.limits[resource]:
                raise DomainError('API_BUSY')
            return self._slot(resource)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        waiters = self.waiters[resource]
        while True:
            if self.active[resource] < self.limits[resource]:
                return self._slot(resource)
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise DomainError('API_BUSY')
            future, expired = loop.create_future(), False

            def on_timeout(future=future):
                nonlocal expired
                expired = True
                future.cancel()

            handle = loop.call_later(remaining, on_timeout)
            waiters.append(future)
            try:
                await future
            except asyncio.CancelledError:
                woken = self._discard(waiters, future)
                if woken and not future.cancelled():
                    # A release already handed us the wakeup; pass it on so the
                    # remaining queue does not stall behind this cancelled task.
                    self._wake(resource)
                if expired:
                    raise DomainError('API_BUSY') from None
                raise
            except BaseException:
                self._discard(waiters, future)
                future.cancel()
                raise
            finally:
                handle.cancel()
            # Woken by a release: loop and claim the slot with a synchronous
            # check so a cancelled waiter can never hold a slot it never uses.

    @staticmethod
    def _discard(waiters, future):
        """Remove a pending waiter; True means a release already woke it."""
        try:
            waiters.remove(future)
            return False
        except ValueError:
            return True

    def stats(self):
        return {'active': dict(self.active), 'limits': dict(self.limits), 'inference': 'external-api-only'}
