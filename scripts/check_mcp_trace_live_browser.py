"""One authorized live browser flow; temporary data, capped cost, no retries."""
import argparse
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import socket
import tempfile
import threading
import time

import uvicorn

from backend.xueya.app import create_app
from backend.xueya.config import load_config
from scripts.check_learning_browser import Browser


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--authorized-budget-cny', required=True, type=Decimal)
    parser.add_argument('--output', type=Path, default=Path('test-results/mcp-trace-live'))
    args = parser.parse_args()
    assert 0 < args.authorized_budget_cny <= Decimal('1')
    output = args.output
    output.mkdir(parents=True, exist_ok=False)  # An existing run never silently repeats.
    config = load_config()
    assert config.api_key and config.model == 'mimo-v2.6-flash'
    assert config.base_url.rstrip('/') == 'https://api.xiaomimimo.com/v1'
    with tempfile.TemporaryDirectory(prefix='xueya-mcp-live-ui-') as temporary:
        folder = Path(temporary)
        config = replace(config, data_dir=folder/'data', run_budget_cny=str(args.authorized_budget_cny),
                         input_cny_per_million='10', output_cny_per_million='10', run_model_calls=5,
                         run_tool_calls=8, agent_max_rounds=5, max_output_tokens=3072,
                         agent_decision_tokens=3072, run_output_tokens=15360, run_timeout=150)
        app = create_app(config)
        host = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', log_level='error', access_log=False))
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        thread = threading.Thread(target=host.run, kwargs={'sockets': [sock]}, daemon=True)
        thread.start()
        browser = None
        summary = {'automaticRetries': 0, 'authorizedBudgetCny': str(args.authorized_budget_cny)}
        decisions = []
        try:
            for _ in range(200):
                if host.started:
                    break
                time.sleep(.03)
            assert host.started
            original = app.state.provider.generate

            async def record(*values, **options):
                result = await original(*values, **options)
                decisions.append({'content': result['content'], 'usage': result.get('usage')})
                return result

            app.state.provider.generate = record
            browser = Browser(folder)
            browser.call('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
            browser.call('Page.navigate', url=f'http://127.0.0.1:{port}/#space/chat')
            browser.wait('!!document.querySelector("#chatInput")')
            material = folder/'MCP真实体验示例.txt'
            material.write_text('队列遵循先进先出：先入队的元素先出队。', encoding='utf-8')
            browser.evaluate('''(()=>{const input=document.querySelector('#imageInput'),files=new DataTransfer();files.items.add(new File(['队列遵循先进先出：先入队的元素先出队。'],'MCP真实体验示例.txt',{type:'text/plain'}));input.files=files.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()''')
            browser.wait('document.querySelector(".attachment-list")?.innerText.includes("MCP真实体验示例.txt")')
            browser.fill('#chatInput', '只根据这份队列资料核对先进先出的定义，先搜索、再读取原文，最后引用原文回答。')
            browser.click('#chatForm .send-button')  # The only paid task submission.
            browser.wait('!!document.querySelector(".loading-message")', timeout=100)
            browser.wait('!document.querySelector("#chatForm .stop-button")', timeout=150)
            summary['pageTrace'] = browser.evaluate('document.querySelector(".mcp-trace")?.innerText')
            summary['pageAnswer'] = browser.evaluate('document.querySelector(".ai-message .rich-content")?.innerText')
            summary['pageStatuses'] = browser.evaluate('[...document.querySelectorAll(".mcp-call")].map(el=>({tool:el.dataset.tool,status:el.dataset.status}))')
            browser.screenshot(output/'completed.png')
            browser.reload()
            browser.wait('!!document.querySelector(".ai-message .rich-content")')
            summary['reloadRetained'] = browser.evaluate('!!document.querySelector(".ai-message .rich-content")&&!document.querySelector(".mcp-trace,.workflow-details")')
            assert not browser.errors, browser.errors
        except Exception as error:
            summary['error'] = type(error).__name__
            raise
        finally:
            p = app.state.platform
            runs = p.repo.all(p.scope(), 'run')
            summary['runs'] = runs
            summary['modelDecisions'] = decisions
            summary['invocations'] = [dict(row) for row in p.db.all('SELECT status,usage_json FROM invocations')]
            summary['modelCalls'] = len(summary['invocations'])
            (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({k: summary.get(k) for k in ('modelCalls','pageStatuses','pageAnswer','reloadRetained','error')}, ensure_ascii=False))
            if browser:
                browser.close()
            host.should_exit = True
            thread.join(8)
            sock.close()
        assert runs and runs[-1]['status'] == 'succeeded'
        assert runs[-1]['result']['agent']['status'] == 'completed'
        assert {'search_materials','read_source'} <= {row['tool'] for row in runs[-1]['result']['agent']['observations'] if row['status'] == 'completed'}
        assert not summary['pageStatuses']
        assert summary['reloadRetained']


if __name__ == '__main__':
    main()
