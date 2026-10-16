import asyncio
from ..core import fingerprint, require, clone, check_cancel


class ModelRouter:
    def __init__(self, providers, policy, cache=None, ledger=None):
        self.providers, self.policy, self.cache, self.ledger = providers, policy, cache, ledger

    async def generate(self, request):
        course, task = request.get('courseId'), request.get('task')
        name = self.policy.get(task, self.policy.get('default'))
        provider = self.providers.get(name)
        require(course and task and request.get('evidenceVersion') and request.get('promptVersion') and provider, 'INVALID_MODEL_ROUTE')
        signal = request.get('signal')
        check_cancel(signal)
        parameters = {k: v for k, v in request.items() if k not in ('signal', 'courseId', 'task', 'evidenceVersion', 'promptVersion')}
        identity = provider.capabilities().get('model')
        key = fingerprint({**{k: request[k] for k in ('courseId', 'task', 'evidenceVersion', 'promptVersion')}, 'provider': name, 'model': identity, 'parameters': parameters})
        cached = await self.cache.get(course, key) if self.cache and identity else None
        if cached:
            return {**clone(cached), 'execution': 'cache', 'cacheKey': key}
        reservation = await self.ledger.reserve({'courseId': course, 'task': task, 'provider': name, 'maxOutputTokens': request.get('maxOutputTokens', 4096)}) if self.ledger else None
        try:
            result = await provider.generate({**parameters, 'signal': signal})
            check_cancel(signal)
        except (Exception, asyncio.CancelledError) as error:
            if self.ledger:
                await self.ledger.settle(reservation, {'status': 'unknown' if isinstance(error, asyncio.CancelledError) or getattr(error, 'details', {}).get('outcomeUnknown') else 'failed', 'usage': None})
            raise
        if self.ledger:
            await self.ledger.settle(reservation, {'status': 'completed', 'usage': result.get('usage')})
        if self.cache and identity:
            await self.cache.put(course, key, clone(result))
        return {**result, 'execution': 'live', 'cacheKey': key}
