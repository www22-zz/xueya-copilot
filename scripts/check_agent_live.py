"""Explicitly authorized live smoke: one isolated run, no retries, <=1 CNY reserve."""
import argparse
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--authorized-budget-cny', required=True, type=Decimal)
    parser.add_argument('--env', required=True, type=Path)
    args = parser.parse_args()
    assert 0 < args.authorized_budget_cny <= Decimal('1')
    target = Path('test-results/agent-live-summary.json')
    previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    prior = Decimal(previous.get('cumulativeReservedCny', previous.get('reservedCny', '0')))
    remaining = args.authorized_budget_cny-prior
    assert remaining > 0, 'Authorized cumulative test budget is exhausted.'
    # Values stay in process memory, never echo keys or write another credentials file.
    import os
    for line in args.env.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('\"\''))
    config = load_config()
    assert config.api_key and config.model == 'mimo-v2.6-flash'
    assert config.base_url.rstrip('/') == 'https://api.xiaomimimo.com/v1'
    # 2026-10-21 official domestic realtime list: 1 CNY input / 2 output per million.
    # Use 10/10 to over-reserve and include hidden reasoning in the output cap.
    with tempfile.TemporaryDirectory(prefix='xueya-agent-live-') as directory:
        config = replace(config, data_dir=Path(directory), run_budget_cny=str(remaining),
            input_cny_per_million='10', output_cny_per_million='10', run_model_calls=5,
            agent_max_rounds=5, max_output_tokens=3072, agent_decision_tokens=3072,
            run_output_tokens=15360, run_timeout=180)
        app = create_app(config, start_jobs=False)
        decisions = []
        with TestClient(app, base_url='http://127.0.0.1') as client:
            original = app.state.provider.generate
            async def record(*values, **options):
                result = await original(*values, **options)
                decisions.append(result['content'][:6000])
                return result
            app.state.provider.generate = record
            client.headers['x-xueya-token'] = app.state.token
            p = app.state.platform
            source = {'id': 'live-queue', 'title': '队列第一章', 'location': '定义',
                'quote': '队列遵循先进先出：先入队的元素先出队。', 'keywords': ['队列', '先进先出']}
            p.repo.put(p.scope(), 'source', source['id'], source, 0)
            r = client.post('/api/learning/agent-runs', json={'id': 'live-smoke',
                'question': '只核对队列的先进先出定义，查找资料后读取原文，再给出来源支持的简短解释。', 'scenario': 'prepare'})
            assert r.status_code == 200
            for _ in range(5):
                run = client.portal.call(app.state.learning.dynamic.execute, p.scope(), {'runId': 'live-smoke'})
                if run['status'] != 'queued':
                    break
            invocations = [dict(row) for row in p.db.all('SELECT status,usage_json FROM invocations')]
            summary = {'status': run['status'], 'stopReason': run['state'].get('stopReason'),
                'modelCalls': run['budget']['models'] if run['budget'] else 0,
                'reservedCny': run['budget']['money'] if run['budget'] else '0',
                'tools': [o.get('tool') for o in run['state'].get('observations', []) if o.get('tool')],
                'sources': (run.get('result') or {}).get('sources', []), 'invocations': invocations}
            summary.update(previousReservedCny=str(prior), cumulativeReservedCny=str(prior+Decimal(summary['reservedCny'])), decisions=decisions)
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(summary, ensure_ascii=False))
            assert Decimal(summary['cumulativeReservedCny']) <= args.authorized_budget_cny
            assert run['status'] == 'completed', 'Live run did not complete; no automatic paid retry.'


if __name__ == '__main__':
    main()
