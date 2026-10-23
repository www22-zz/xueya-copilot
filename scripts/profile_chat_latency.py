"""Opt-in, bounded end-to-end latency profile using synthetic browser context."""
import argparse
import asyncio
from contextlib import asynccontextmanager, aclosing
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backend.xueya.agent as agent_module
from backend.xueya.agent import Agent
from backend.xueya.common import digest
from backend.xueya.config import load_config
from backend.xueya.execution_budget import budget_scope
from backend.xueya.learning import SOURCES
from backend.xueya.platform import Platform
from backend.xueya.provider import MimoProvider


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paid-budget-cny', required=True, type=Decimal)
    parser.add_argument('--previous-report', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--production-limits', action='store_true', help='Use production output cap and independent arithmetic/stack cases')
    args = parser.parse_args()
    if not args.paid_budget_cny.is_finite() or not 0 < args.paid_budget_cny <= 1 or args.output.exists():
        parser.error('Use a budget in (0, 1] and a new report path')
    previous = json.loads(args.previous_report.read_text(encoding='utf-8'))
    prior_cost = Decimal(previous.get('cumulative_cost_cny_upper', previous['estimated_cost_cny_upper']))
    if not prior_cost.is_finite() or prior_cost < 0:
        parser.error('Previous cumulative cost must be finite and nonnegative')
    remaining = args.paid_budget_cny-prior_cost
    if remaining <= 0:
        parser.error('Cumulative budget is exhausted')
    config = load_config()
    if config.model != 'mimo-v2.6-flash' or config.base_url.rstrip('/') != 'https://api.xiaomimimo.com/v1':
        parser.error('Only the official priced flash endpoint is supported')
    output_cap = config.max_output_tokens if args.production_limits else 512
    config = replace(config, run_budget_cny=str(remaining), input_cny_per_million='1',
                     output_cny_per_million='2', run_model_calls=8,
                     max_output_tokens=output_cap, run_output_tokens=8*output_cap, run_timeout=600)
    platform = Platform(config.data_dir, recover=False)
    results = []
    report = {'previous_cost_cny_upper': str(prior_cost), 'budget_cny': str(args.paid_budget_cny),
              'price_source': 'https://mimo.mi.com/models/zh-CN/mimo-v2.6-flash', 'results': results}
    report['output_token_limit'] = output_cap

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    class TracedProvider(MimoProvider):
        row = None

        def new_client(self, timeout):
            client = super().new_client(timeout)

            async def request_hook(request):
                row = self.row
                start = row['_start']
                row['request_ms'] = round((time.perf_counter()-row['_start'])*1000, 2)

                async def trace(name, info):
                    # Never store trace info, request headers or credentials.
                    entry = {'event': name, 'ms': round((time.perf_counter()-start)*1000, 2)}
                    if name.endswith('.failed'):
                        entry['error_type'] = type(info.get('exception')).__name__
                    row['network'].append(entry)

                request.extensions['trace'] = trace

            client.event_hooks['request'].append(request_hook)
            return client

        async def stream(self, messages, **options):
            self.row['model_start_ms'] = round((time.perf_counter()-self.row['_start'])*1000, 2)
            self.row['_hash'] = digest(messages)
            try:
                async with aclosing(super().stream(messages, **options)) as events:
                    async for event in events:
                        yield event
            except Exception as error:
                self.row['provider_error'] = getattr(error, 'code', type(error).__name__)
                raise

    baseline, optimized = TracedProvider(config, platform), TracedProvider(config, platform)
    real_session = agent_module.open_session

    @asynccontextmanager
    async def old_session(registry=None, **options):
        if registry is None:
            options['stdio'] = True
        async with real_session(registry, **options) as session:
            yield session

    try:
        with budget_scope(config, fresh=True) as budget:
            async with optimized.connection_pool():
                for round_number in range(2):
                    questions = ('1+1等于几', '用一句话解释什么是栈') if args.production_limits else ('今天星期几', '用一句话介绍雷锋')
                    for question in questions:
                        modes = ('baseline', 'optimized') if round_number == 0 else ('optimized', 'baseline')
                        for mode in modes:
                            provider = baseline if mode == 'baseline' else optimized
                            row = {'mode': mode, 'round': round_number+1, 'question': question,
                                   'network': [], 'stages': [], '_start': time.perf_counter()}
                            results.append(row)
                            provider.row = row
                            session = old_session if mode == 'baseline' else real_session
                            provisional = ''
                            try:
                                with patch.object(agent_module, 'open_session', session):
                                    async for event in Agent(provider, platform).workflow({
                                            'question': question, 'context': {'library': SOURCES}}):
                                        ms = round((time.perf_counter()-row['_start'])*1000, 2)
                                        if event['type'] == 'workflow':
                                            row['stages'].append({'stage': event['stage'], 'label': event['label'], 'ms': ms})
                                        elif event['type'] == 'content':
                                            row.setdefault('first_content_ms', ms)
                                            provisional += event.get('text', '')
                                        elif event['type'] == 'done':
                                            row.update(answer=event['answer'], done_ms=ms, ok=event['engine'] == 'general-chat')
                            except Exception as error:
                                row.update(ok=False, error=getattr(error, 'code', type(error).__name__))
                            row['total_ms'] = round((time.perf_counter()-row.pop('_start'))*1000, 2)
                            if not row.get('ok'):
                                row['rejected_content_length'] = len(provisional)
                                row['rejected_content_tail'] = provisional[-160:]
                            request_hash = row.pop('_hash', None)
                            ledger = platform.db.one('SELECT usage_json FROM invocations WHERE request_hash=? ORDER BY rowid DESC LIMIT 1', (request_hash,))
                            usage = json.loads(ledger['usage_json']) if ledger and ledger['usage_json'] else None
                            row['usage'] = usage
                            if usage:
                                row['estimated_cost_cny_upper'] = str((Decimal(usage['prompt_tokens'])+2*Decimal(usage['completion_tokens']))/1000000)
                            # Reserve conservatively even if a request's outcome is uncertain.
                            report['budget_reserved_cny'] = str(budget.money)
                            report['estimated_cost_cny_upper'] = str(sum(Decimal(r.get('estimated_cost_cny_upper', '0')) for r in results))
                            report['cumulative_cost_cny_upper'] = str(prior_cost+max(budget.money, Decimal(report['estimated_cost_cny_upper'])))
                            save()
                            print(json.dumps({k: v for k, v in row.items() if k not in ('network', 'stages')}, ensure_ascii=False), flush=True)
                            if not row.get('ok') or not usage:
                                return 1
    finally:
        await platform.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
