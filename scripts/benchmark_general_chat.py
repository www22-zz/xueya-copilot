"""Explicitly budgeted MiMo latency comparison; never retries paid requests."""
import argparse
import asyncio
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.xueya.agent import Agent, normalize_request
from backend.xueya.common import digest
from backend.xueya.config import load_config
from backend.xueya.execution_budget import budget_scope
from backend.xueya.platform import Platform
from backend.xueya.provider import MimoProvider


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paid-budget-cny', required=True, type=Decimal)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not args.paid_budget_cny.is_finite() or not 0 < args.paid_budget_cny <= 1:
        parser.error('Budget must be greater than zero and at most CNY 1')
    config = load_config()
    if config.model != 'mimo-v2.6-flash' or config.base_url.rstrip('/') != 'https://api.xiaomimimo.com/v1':
        parser.error('This benchmark is priced only for the official mimo-v2.6-flash endpoint')
    if not config.api_key:
        parser.error('API credential is not configured')
    # Official CNY prices: input cache miss 1 / output 2 per million tokens.
    # Cached input is conservatively counted at the cache-miss rate.
    config = replace(config, run_budget_cny=str(args.paid_budget_cny),
                     input_cny_per_million='1', output_cny_per_million='2',
                     run_model_calls=4, max_output_tokens=512, run_output_tokens=2048,
                     run_timeout=240)
    platform = Platform(config.data_dir, recover=False)
    provider = MimoProvider(config, platform)
    results = []
    report = {'model': config.model, 'budget_cny': str(args.paid_budget_cny),
              'price_source': 'https://mimo.mi.com/models/zh-CN/mimo-v2.6-flash',
              'results': results}

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    class Capture:
        config = provider.config

        async def stream(self, messages, **options):
            self.messages = messages
            yield {'type': 'content', 'text': '{"answer":"offline prompt capture"}'}

    try:
        with budget_scope(config, fresh=True) as budget:
            # Alternate order to reduce systematic warm-up/cache advantage.
            cases = [('今天星期几', ('enabled', 'disabled')),
                     ('用一句话解释什么是二叉搜索树', ('disabled', 'enabled'))]
            for question, modes in cases:
                capture = Capture()
                _ = [e async for e in Agent(capture).general(normalize_request({'question': question}), None)]
                for mode in modes:
                    row = {'question': question, 'thinking': mode}
                    results.append(row)
                    start = time.perf_counter()
                    content = ''
                    try:
                        async for event in provider.stream(capture.messages, scope=platform.scope(),
                                thinking={'type': mode}):
                            if event['type'] == 'content':
                                row.setdefault('first_content_seconds', round(time.perf_counter()-start, 3))
                                content += event['text']
                        row['answer'] = content.strip()
                        row['ok'] = isinstance(row['answer'], str) and bool(row['answer'].strip())
                    except Exception as error:
                        row['ok'] = False
                        row['error'] = getattr(error, 'code', type(error).__name__)
                    row['total_seconds'] = round(time.perf_counter()-start, 3)
                    invocation = platform.db.one('SELECT usage_json FROM invocations WHERE request_hash=? ORDER BY rowid DESC LIMIT 1',
                                                 (digest(capture.messages),))
                    row['usage'] = json.loads(invocation['usage_json']) if invocation and invocation['usage_json'] else None
                    if row['usage']:
                        usage = row['usage']
                        row['estimated_cost_cny_upper'] = str((Decimal(usage['prompt_tokens'])+2*Decimal(usage['completion_tokens']))/1000000)
                    report['budget_reserved_cny'] = str(budget.money)
                    save()
                    print(json.dumps(row, ensure_ascii=False), flush=True)
                    if not row['ok']:
                        return 1  # Stop rather than retrying or spending on more cases.
            report['estimated_cost_cny_upper'] = str(sum(Decimal(r['estimated_cost_cny_upper']) for r in results))
            save()
    finally:
        await platform.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
