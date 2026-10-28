"""Isolated Chrome acceptance. --live requires an explicit cumulative paid-call budget."""
import argparse
import asyncio
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
from types import SimpleNamespace

import uvicorn
from playwright.sync_api import sync_playwright, expect

from backend.xueya.app import create_app
from backend.xueya.common import require
from backend.xueya.config import Config, load_config
from backend.xueya.provider import MimoProvider
from backend.agent.data_structure_bank import PACKAGE_FILE, TEXTBOOK_HASH
from backend.xueya.curated_practice import CuratedPractice

CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
PRICING_SOURCE = 'https://mimo.mi.com/docs/en-US/price/pay-as-you-go'


class ControlledProvider:
    def __init__(self):
        self.calls = 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        await asyncio.sleep(.3)
        if kwargs.get('response_format'):
            snapshot = json.loads(messages[1]['content'])
            q = next(q for q in snapshot['questions'] if q['attempts'])
            value = {'title': '先把进程与线程练扎实', 'summary': '近期记录显示部分基础概念需要巩固。<img src=x onerror=alert(1)>',
                     'findings': [{'kind': 'weakness', 'title': '回到概念与边界', 'detail': '根据近期作答记录，建议通过不同题目核对理解。', 'questionIds': [q['id']]},
                                  {'kind': 'progress', 'title': '已开始主动回顾', 'detail': '你留下了练习记录和随手记，继续积累更多独立题目的证据。', 'questionIds': [q['id']]}],
                     'recommendations': [{'title': '先复述，再重新作答', 'reason': '解释关键概念的区别，再闭卷完成这道练习。', 'questionIds': [q['id']]}],
                     'limitations': ['当前记录较少，只能初步观察，不能据此确定真实能力。']}
            return {'content': json.dumps(value, ensure_ascii=False), 'model': 'controlled'}
        return {'content': '建议先用自己的话解释概念，再重新完成题目。只有对错记录时，错因仍需核实。', 'model': 'controlled'}


class MeteredProvider(MimoProvider):
    def __init__(self, config, ledger):
        super().__init__(config)
        self.ledger = ledger
        self.data = json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {'reservations': []}
        self.calls = 0

    async def generate(self, *args, **kwargs):
        # Reserve ¥1 before every outbound attempt; the provider enforces that upper bound too.
        require(len(self.data['reservations']) < 5, 'LIVE_CALL_BUDGET_EXCEEDED')
        require(sum(Decimal(row['reservedCny']) for row in self.data['reservations']) + 1 <= 5, 'LIVE_COST_BUDGET_EXCEEDED')
        row = {'reservedCny': '1', 'status': 'unknown'}
        self.data['reservations'].append(row)
        self.ledger.write_text(json.dumps(self.data, indent=2), encoding='utf-8')
        self.calls += 1
        try:
            result = await super().generate(*args, **kwargs)
        except Exception as error:
            row['error'] = getattr(error, 'code', None) or type(error).__name__
            self.ledger.write_text(json.dumps(self.data, indent=2), encoding='utf-8')
            raise
        row.update(status='succeeded', usage=result.get('usage'), model=result.get('model'))
        self.ledger.write_text(json.dumps(self.data, indent=2), encoding='utf-8')
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--budget-cny', type=int, default=0)
    parser.add_argument('--max-calls', type=int, default=0)
    args = parser.parse_args()
    if args.live:
        require(args.budget_cny == 5 and args.max_calls == 5, 'EXPLICIT_LIVE_BUDGET_REQUIRED')
    output = Path('test-results/analysis-live' if args.live else 'test-results/analysis-browser')
    output.mkdir(parents=True, exist_ok=True)
    checks, page_errors = [], []
    with tempfile.TemporaryDirectory(prefix='xueya-analysis-', ignore_cleanup_errors=True) as directory:
        if args.live:
            configured = load_config()
            require(configured.api_key and configured.model == 'mimo-v2.6-flash', 'LIVE_CONFIG_UNSUPPORTED')
            config = replace(configured, data_dir=Path(directory), auto_import_demo=False, api_slots=1,
                             run_budget_cny='1', input_cny_per_million='1', output_cny_per_million='2', run_model_calls=1)
            provider = MeteredProvider(config, output / 'budget.json')
        else:
            config = Config(data_dir=Path(directory), api_key='controlled', api_slots=1)
            provider = ControlledProvider()
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        base = 'http://127.0.0.1:' + str(sock.getsockname()[1])
        app = create_app(config, provider=provider)
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started:
            require(time.monotonic() < deadline, 'TEST_SERVER_TIMEOUT')
            time.sleep(.05)
        # Use the actual course catalog now shown by the practice page, with isolated evidence bindings.
        package = json.loads(PACKAGE_FILE.read_text(encoding='utf-8'))
        platform = app.state.platform
        scope = platform.scope('course-default')
        platform.repo.put(scope, 'document', 'analysis-textbook-fixture', {
            'id': 'analysis-textbook-fixture', 'name': '数据结构教材.pdf', 'kind': 'pdf',
            'fileHash': TEXTBOOK_HASH, 'contentRevision': 2, 'archived': False, 'status': '已解析', 'chunks': []})
        sources = [{'id': 'analysis-source-' + str(i), 'quote': q['evidenceQuote'],
                    'page': q['references'][0]['page'], 'location': '第 ' + str(q['references'][0]['page']) + ' 页'}
                   for i, q in enumerate(package['questions'])]
        CuratedPractice(platform, SimpleNamespace(sources=lambda *args, **kwargs: sources)).install(scope, package)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=CHROME, headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1050})
            page = context.new_page()
            page.set_default_timeout(20000)
            page.on('pageerror', lambda error: page_errors.append(str(error)))
            try:
                response = page.request.post(base + '/api/account/register', data={
                    'username': 'analysisuser', 'password': 'Analysis123', 'confirmPassword': 'Analysis123'})
                assert response.ok, response.text()
                boot = page.request.get(base + '/api/platform/bootstrap').json()
                headers = {'X-Xueya-Token': boot['token']}
                course_bank = app.state.practice_generation.catalog('analysisuser', 'course-default')['questions']
                questions = [q for q in course_bank if q['type'] == 'single' and q['category'] == 'basic'][:6]
                assert len(questions) == 6
                ops = [{'opId': 'sample-' + str(i), 'kind': 'answer', 'questionId': q['id'],
                        'payload': {'questionType': 'single', 'result': 'wrong' if i < 3 else 'correct', 'selected': 0}}
                       for i, q in enumerate(questions)]
                ops.append({'opId': 'sample-note', 'kind': 'note-save', 'questionId': questions[0]['id'],
                            'payload': {'text': '这里容易把适用条件混淆，需要先理解概念。', 'baseRevision': 0}})
                assert page.request.post(base + '/api/practice/ops', headers=headers, data={'ops': ops}).json()['accepted']
                page.goto(base + '/#space/analysis')
                expect(page.locator('#analysisModule')).to_be_visible()
                expect(page.locator('[data-analysis-action=generate]')).to_be_enabled()
                for name, value in (('category', 'basic'), ('days', '30')):
                    field = page.locator(f'[data-analysis-filter={name}]')
                    label = field.locator(f'option[value="{value}"]').inner_text()
                    field.locator('..').get_by_role('combobox').click()
                    page.locator('.practice-select-menu').get_by_role('option', name=label, exact=True).click()
                page.click('[data-analysis-action=generate]')
                expect(page.locator('.analysis-status')).to_contain_text('AI', timeout=20000)
                page.reload()
                expect(page.locator('.analysis-report')).to_be_visible(timeout=90000)
                assert page.locator('.analysis-stats').inner_text().find('50%') >= 0
                assert page.locator('.analysis-summary img').count() == 0
                checks.append('generate-and-refresh-resume-safe-report')
                page.screenshot(path=str(output / 'desktop.png'), full_page=True)
                page.locator('#analysisQuestion').fill('为什么先练这些题？请给出具体的练习方法。')
                page.locator('[data-analysis-chat] button').click()
                expect(page.locator('.analysis-message')).to_have_count(2, timeout=90000)
                page.reload()
                expect(page.locator('.analysis-message')).to_have_count(2)
                checks.append('follow-up-and-history-persist-after-refresh')
                link = page.locator('.analysis-next [data-analysis-action=practice]').first
                target = link.get_attribute('data-id')
                link.click()
                expect(page.locator(f'.practice-row[data-id="{target}"]')).to_have_class('practice-row is-active')
                expected_title = next(q['title'] for q in course_bank if q['id'] == target)
                expect(page.locator('.practice-detail h2')).to_have_text(expected_title)
                checks.append('recommendation-opens-exact-question')
                page.goto(base + '/#space/analysis')
                expect(page.locator('.analysis-report')).to_be_visible()
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.screenshot(path=str(output / 'mobile.png'), full_page=True)
                page.evaluate("document.documentElement.dataset.theme='dark'")
                page.screenshot(path=str(output / 'dark-mobile.png'), full_page=True)
                checks.append('mobile-and-dark-layout-no-horizontal-overflow')
                other = browser.new_context()
                response = other.request.post(base + '/api/account/register', data={
                    'username': 'otheruser', 'password': 'Other12345', 'confirmPassword': 'Other12345'})
                assert response.ok
                token = other.request.get(base + '/api/platform/bootstrap').json()['token']
                other_headers = {'X-Xueya-Token': token}
                listing = other.request.get(base + '/api/practice/analysis', headers=other_headers).json()
                assert listing['reports'] == [] and listing['jobs'] == []
                original = page.request.get(base + '/api/practice/analysis', headers=headers).json()['reports'][0]
                assert other.request.get(base + '/api/practice/analysis/reports/' + original['id'], headers=other_headers).status == 404
                empty = other.request.post(base + '/api/practice/analysis', headers=other_headers,
                    data={'idempotencyKey': 'empty-other'}).json()
                assert empty.get('error') == 'ANALYSIS_NO_RECORDS', empty
                other.close()
                checks.append('account-isolation-and-empty-range-without-ai-call')
                assert provider.calls == 2
                assert not page_errors, page_errors
                ledger = app.state.platform.db.all('SELECT status,usage_json FROM invocations')
                usage = [json.loads(row['usage_json']) for row in ledger if row['usage_json']]
                estimate = sum((u.get('prompt_tokens', 0) + 2*u.get('completion_tokens', 0))/1_000_000 for u in usage)
                report = {'status': 'passed', 'paidApiCalls': provider.calls if args.live else 0,
                          'checks': checks, 'pageErrors': page_errors, 'syntheticInputs': True,
                          'usage': usage, 'estimatedCny': estimate if args.live else 0,
                          'invoiceVerified': False, 'pricingSource': PRICING_SOURCE if args.live else None}
                (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps(report, ensure_ascii=False), flush=True)
            except BaseException:
                page.screenshot(path=str(output / 'failure.png'), full_page=True)
                jobs = app.state.practice_analysis.listing('analysisuser')['jobs']
                (output / 'failure.json').write_text(json.dumps({'checks': checks, 'pageErrors': page_errors,
                    'paidApiCalls': provider.calls if args.live else 0, 'jobs': jobs}, ensure_ascii=False), encoding='utf-8')
                raise
            finally:
                browser.close()
                server.should_exit = True
                thread.join(timeout=5)


if __name__ == '__main__':
    main()
