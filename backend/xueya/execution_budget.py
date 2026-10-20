"""Host-owned, shared request/job limits; reservations precede outbound calls."""
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation
import time

from .common import require, dumps

current_budget = ContextVar('xueya_execution_budget', default=None)


def decimal_setting(value):
    try:
        result = Decimal(str(value))
        require(result.is_finite() and result >= 0, 'AI_INVALID_BUDGET_CONFIG')
        return result
    except InvalidOperation:
        require(False, 'AI_INVALID_BUDGET_CONFIG')


class ExecutionBudget:
    def __init__(self, config=None):
        self.model_limit = getattr(config, 'run_model_calls', 10)
        self.tool_limit = getattr(config, 'run_tool_calls', 12)
        self.output_limit = getattr(config, 'run_output_tokens', 32768)
        self.deadline = time.monotonic()+getattr(config, 'run_timeout', 300)
        self.money_limit = decimal_setting(getattr(config, 'run_budget_cny', '0'))
        self.input_price = decimal_setting(getattr(config, 'input_cny_per_million', '0'))
        self.output_price = decimal_setting(getattr(config, 'output_cny_per_million', '0'))
        self.priced_model = getattr(config, 'model', None)
        self.models = self.tools = self.output = 0
        self.money = Decimal(0)
        self.changed = None

    def snapshot(self):
        return {'models': self.models, 'tools': self.tools, 'output': self.output, 'money': str(self.money),
                'seconds': max(0, self.deadline-time.monotonic())}

    def restore(self, value):
        self.models, self.tools, self.output = (value[k] for k in ('models', 'tools', 'output'))
        self.money = decimal_setting(value['money'])
        self.deadline = time.monotonic()+value['seconds']

    def persist(self):
        if self.changed:
            self.changed(self.snapshot())

    def remaining(self):
        seconds = self.deadline-time.monotonic()
        require(seconds > 0, 'AI_RUN_TIMEOUT')
        return seconds

    def model(self, messages, output_tokens, *, capability='text', model=None):
        self.remaining()
        require(self.models < self.model_limit, 'AI_MODEL_BUDGET_EXCEEDED')
        require(self.output+output_tokens <= self.output_limit, 'AI_OUTPUT_BUDGET_EXCEEDED')
        cost = Decimal(0)
        if self.money_limit:
            require(capability == 'text' and model == self.priced_model and self.input_price > 0 and self.output_price > 0,
                    'AI_PRICING_REQUIRED')
            # Deliberately conservative text estimate; provider billing is still authoritative.
            input_upper = len(dumps(messages).encode('utf-8'))+256*(len(messages)+1)
            cost = (input_upper*self.input_price+output_tokens*self.output_price)/1000000
            require(self.money+cost <= self.money_limit, 'AI_COST_BUDGET_EXCEEDED')
        # Synchronous reservation: child tasks share this object and cannot oversubscribe it.
        self.models += 1
        self.output += output_tokens
        self.money += cost
        self.persist()
        return cost

    def observe(self, usage, reserved_cost, output_tokens):
        """Never refund uncertain reservations; stop if reported usage exceeds them."""
        if not isinstance(usage, dict):
            return reserved_cost
        prompt, completion = usage.get('prompt_tokens'), usage.get('completion_tokens')
        if type(completion) is int and completion > output_tokens:
            self.output += completion-output_tokens
        if self.money_limit and type(prompt) is int and prompt >= 0 and type(completion) is int and completion >= 0:
            actual = (prompt*self.input_price+completion*self.output_price)/1000000
            self.money += max(Decimal(0), actual-reserved_cost)
            reserved_cost = max(reserved_cost, actual)
        self.persist()
        require(type(completion) is not int or completion <= output_tokens, 'AI_OUTPUT_BUDGET_EXCEEDED')
        require(not self.money_limit or self.money <= self.money_limit, 'AI_COST_BUDGET_EXCEEDED')
        return reserved_cost

    def tool(self):
        self.remaining()
        require(self.tools < self.tool_limit, 'AI_TOOL_BUDGET_EXCEEDED')
        self.tools += 1
        self.persist()


@contextmanager
def budget_scope(config=None, *, fresh=False):
    existing = current_budget.get()
    if existing is not None and not fresh:
        yield existing
        return
    token = current_budget.set(ExecutionBudget(config))
    try:
        yield current_budget.get()
    finally:
        current_budget.reset(token)


class BudgetMiddleware:
    """ASGI lifetime includes StreamingResponse; no context reset at response headers."""
    def __init__(self, app, config):
        self.app, self.config = app, config

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope.get('path', '').startswith('/api/'):
            with budget_scope(self.config, fresh=True):
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)
