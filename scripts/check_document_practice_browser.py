"""Real Chrome upload/200-question/answering acceptance with a controlled model and isolated data."""
import asyncio
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time

import uvicorn
from playwright.sync_api import sync_playwright, expect
from backend.xueya.app import create_app
from backend.xueya.config import Config

OUTPUT = Path('test-results/document-practice')
CHROME = os.environ.get('CHROME_PATH', 'C:/Users/571/AppData/Local/Google/Chrome/Application/chrome.exe')
MATERIAL = '\n'.join(f'第{i}节：光合作用把光能转化为化学能，叶绿体是主要场所；细胞呼吸分解有机物释放能量。' for i in range(80))


class ControlledModel:
    def __init__(self):
        self.calls = 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        batch = self.calls
        await asyncio.sleep(.06)
        args = json.loads(messages[-1]['content'])
        source, kind = args['materials'][0], args['types'][0]
        questions = []
        for i in range(args['count']):
            q = dict(type=kind, prompt=f'练习{batch}-{i+1}：判断光合作用与细胞呼吸的关系。',
                     explanation='光合作用储存能量，细胞呼吸分解有机物释放能量。',
                     sourceId=source['id'], evidenceQuote=source['quote'][:80], difficulty='easy', conceptIds=[])
            if kind in ('single', 'multiple'):
                q.update(options=['光合作用储存能量', '光合作用释放所有能量', '细胞呼吸释放能量', '两者完全相同'], answer=0 if kind == 'single' else [0, 2])
            elif kind == 'boolean':
                q['answer'] = True
            elif kind == 'fill':
                q['answers'] = [['叶绿体']]
            else:
                q.update(solutions={'python': 'def solve(x):\n    return x'}, samples=[{'input': '1', 'output': '1'}])
            questions.append(q)
        return {'content': json.dumps({'questions': questions}, ensure_ascii=False), 'model': 'controlled'}


def main():
    expect.set_options(timeout=20000)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    errors, checks = [], []
    model = ControlledModel()
    with tempfile.TemporaryDirectory(prefix='xueya-document-practice-', ignore_cleanup_errors=True) as directory:
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        base = 'http://127.0.0.1:' + str(sock.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(create_app(Config(data_dir=Path(directory), api_key='controlled'), provider=model), log_level='error'))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        while not server.started:
            time.sleep(.03)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=CHROME, headless=True)
                context = browser.new_context(viewport={'width':1440, 'height':1000}, service_workers='block')
                context.add_init_script("localStorage.setItem('xueya-theme','dark')")
                context.request.post(base+'/api/account/register', data={'username':'doclearner','password':'DocLearn12345','confirmPassword':'DocLearn12345'})
                page = context.new_page()
                page.set_default_timeout(20000)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base+'/#space/practice')
                expect(page.get_by_text('上传课程资料后，将自动生成', exact=False).first).to_be_visible()
                assert page.get_by_role('tab', name='面试题').count() == 0
                checks.append('empty document bank and two categories')
                page.goto(base+'/#space/knowledge')
                page.locator('[data-kb=toggle-upload]').click()
                page.locator('#kbFiles').set_input_files({'name':'生物课程.md', 'mimeType':'text/markdown', 'buffer':MATERIAL.encode()})
                expect(page.locator('#kbPracticeGeneration')).to_contain_text('/200')
                page.screenshot(path=str(OUTPUT/'upload-progress.png'))
                page.goto(base+'/#space/practice/foundation')
                expect(page.locator('.practice-row')).to_have_count(100)
                expect(page.locator('.practice-generation')).to_contain_text('200/200')
                assert model.calls == 40
                checks.append('upload automatically generates and publishes 100+100')

                def choose(kind):
                    field = page.locator('select[data-filter=type]')
                    label = field.locator(f'option[value="{kind}"]').inner_text()
                    field.locator('..').get_by_role('combobox').click()
                    expect(page.locator('.practice-select-menu')).to_be_visible()
                    page.locator('.practice-select-menu').get_by_role('option', name=label, exact=True).click()

                choose('multiple')
                expect(page.locator('.practice-row')).to_have_count(25)
                page.locator('[data-action=pick][data-index="0"]').click()
                page.locator('[data-action=submit-single]').click()
                expect(page.locator('.practice-result')).to_contain_text('回答错误')
                page.locator('[data-action=re-answer]').click()
                for i in (0,2):
                    page.locator(f'[data-action=pick][data-index="{i}"]').click()
                page.locator('[data-action=submit-single]').click()
                expect(page.locator('.practice-result')).to_contain_text('回答正确')
                expect(page.locator('.practice-detail-head .chip')).to_contain_text('错题本')
                page.locator('.practice-evidence summary').click()
                expect(page.locator('.practice-evidence blockquote')).to_contain_text('光合作用')
                page.screenshot(path=str(OUTPUT/'multiple-answer-dark.png'))
                checks.append('multiple selection, exact grading, wrong book and source evidence')
                choose('boolean')
                page.locator('[data-action=pick][data-index="1"]').click()
                page.locator('[data-action=submit-single]').click()
                expect(page.locator('.practice-result')).to_contain_text('回答错误')
                page.locator('[data-action=re-answer]').click()
                page.locator('[data-action=pick][data-index="0"]').click()
                page.locator('[data-action=submit-single]').click()
                expect(page.locator('.practice-result')).to_contain_text('回答正确')
                checks.append('boolean true/false are graded as booleans')
                page.reload()
                expect(page.locator('.practice-row')).to_have_count(24)
                checks.append('bank and progress survive reload')
                page.locator('[data-action=category][data-category=hot100]').click()
                expect(page.locator('.practice-row')).to_have_count(100)
                assert page.locator('.practice-code').count() == 0
                assert page.locator('select[data-filter=type] option[value=code]').count() == 0
                page.evaluate("window.XueyaPreferences.applyTheme('light')")
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.locator('.practice-row').first.click()
                expect(page.locator('.practice-detail-pane')).to_be_visible()
                page.screenshot(path=str(OUTPUT/'hot-mobile-light.png'))
                checks.append('mixed Hot100, no code for biology; mobile/light layout')
                page.set_viewport_size({'width':1440,'height':1000})
                page.goto(base+'/#space/knowledge')
                if not page.locator('#kbFiles').is_visible():
                    page.locator('[data-kb=toggle-upload]').click()
                programming = MATERIAL + '\n程序设计和算法实现：```python\ndef solve(x):\n    return x\n```'
                page.locator('#kbFiles').set_input_files({'name':'程序设计.md','mimeType':'text/markdown','buffer':programming.encode()})
                page.goto(base+'/#space/practice/hot100')
                expect(page.locator('select[data-filter=type] option[value=code]')).to_have_count(1)
                choose('code')
                page.locator('.practice-row').first.click()
                page.locator('[data-action=reveal]').click()
                expect(page.locator('.practice-code')).to_contain_text('def solve')
                page.screenshot(path=str(OUTPUT/'code-answer-light.png'))
                checks.append('programming evidence permits code and actual-language reference solutions render')
                assert not errors, errors
                report = {'status':'passed','checks':checks,'pageErrors':errors,'controlledModelCalls':model.calls,'paidApiCalls':0}
                (OUTPUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps(report, ensure_ascii=False))
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
