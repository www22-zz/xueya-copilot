"""Browser regression against a controlled Python server and real Python MCP."""
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
from playwright.sync_api import sync_playwright, expect
from backend.config import ROOT


def main():
    output = ROOT/'test-results/browser-python'
    output.mkdir(parents=True, exist_ok=True)
    marker = output/'model-cancelled.txt'
    if marker.exists():
        marker.unlink()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    with (output/'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'scripts.browser_fixture_server', '--port', str(port)], cwd=ROOT, stdout=log, stderr=log, env={**os.environ, 'PYTHONUTF8': '1'})
        try:
            for _ in range(100):
                try:
                    if httpx.get(base+'/api/health', timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Controlled Python server did not start')
            with sync_playwright() as playwright:
                executable = os.environ.get('CHROME_PATH') or (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' if os.name == 'nt' else None)
                browser = playwright.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base+'/')
                expect(page.locator('.hero h1')).to_contain_text('资料，读得懂。')
                page.get_by_role('link', name='进入学习空间', exact=True).click()
                page.get_by_role('link', name='资料问答', exact=True).click()
                def ask(question):
                    page.locator('#chatInput').fill(question)
                    page.get_by_role('button', name='发送问题', exact=True).click()
                    page.get_by_role('button', name='发送问题', exact=True).wait_for(timeout=30000)
                    return page.locator('.ai-message').last
                expect(ask('你好')).to_contain_text('你好')
                expect(ask('怎样养成早睡习惯？')).to_contain_text('MiMo 通用问答')
                page.get_by_role('link', name='课程资料', exact=False).first.click()
                quote = '拓扑排序每轮选择入度为零的顶点，移除该顶点和出边，再更新相邻顶点的入度。'
                page.locator('#fileInput').set_input_files({'name': '协作验证.md', 'mimeType': 'text/markdown', 'buffer': quote.encode()})
                expect(page.locator('#documentList')).to_contain_text('协作验证.md')
                page.get_by_role('link', name='资料问答', exact=True).click()
                expect(ask('拓扑排序如何选择顶点？')).to_contain_text('入度为零')
                message = page.locator('.ai-message').last
                message.locator('.workflow-details summary').click()
                expect(message.locator('.workflow-details')).to_contain_text('原文和引用位置已核对')
                message.locator('.citation-chip').first.click()
                expect(page.locator('#sourceContent')).to_contain_text('协作验证.md')
                page.locator('#sourceSave').click()
                page.get_by_role('button', name='关闭原文', exact=True).click()
                page.get_by_role('link', name='知识卡片', exact=True).click()
                expect(page.locator('#cardList')).to_contain_text('拓扑排序')
                page.reload()
                expect(page.locator('#cardList')).to_contain_text('拓扑排序')
                page.get_by_role('link', name='资料问答', exact=True).click()
                expect(ask('再解释一下')).to_contain_text('入度为零')
                page.locator('#chatInput').fill('请慢一点解释拓扑排序')
                page.get_by_role('button', name='发送问题', exact=True).click()
                expect(page.locator('.ai-message').last).to_contain_text('尚未校验', timeout=30000)
                page.get_by_role('button', name='停止生成', exact=True).click()
                expect(page.locator('.ai-message').last).to_contain_text('已停止生成')
                for _ in range(50):
                    if marker.exists():
                        break
                    time.sleep(.1)
                assert marker.exists(), 'Disconnect did not cancel Python model task'
                expect(ask('拓扑排序如何选择顶点？')).to_contain_text('入度为零')
                page.get_by_role('link', name='练习与错题', exact=True).click()
                page.locator('[data-option="0"]').click()
                page.get_by_role('button', name='提交答案', exact=True).click()
                expect(page.locator('.quiz-feedback')).to_contain_text('再学一次')
                page.get_by_role('button', name='AI 题库', exact=False).click()
                page.locator('.quiz-panel [data-open-bank-dialog]').click()
                page.locator('#bankTopics input[data-topic="拓扑排序"]').check()
                page.get_by_role('button', name='生成 1 个知识点的题目', exact=True).click()
                expect(page.locator('.quiz-panel h2')).to_contain_text('拓扑排序', timeout=30000)
                page.locator('[data-option="0"]').click()
                page.get_by_role('button', name='提交答案', exact=True).click()
                expect(page.locator('.quiz-feedback')).to_contain_text('回答正确')
                from docx import Document
                document, stream = Document(), io.BytesIO()
                document.add_paragraph('光合作用发生在叶绿体。')
                document.save(stream)
                page.get_by_role('link', name='课程资料', exact=False).first.click()
                page.locator('#fileInput').set_input_files({'name': '生物.docx', 'mimeType': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'buffer': stream.getvalue()})
                expect(page.locator('.document-row').filter(has_text='生物.docx')).to_contain_text('已解析，可检索', timeout=10000)
                for width in (1440, 768, 375):
                    page.set_viewport_size({'width': width, 'height': 900})
                    for view in ('overview', 'chat', 'library', 'cards', 'practice', 'memory', 'plan'):
                        page.goto(base+'/#space/'+view)
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, view)
                page.goto(base+'/#space/ask')
                page.screenshot(path=str(output/'chat-mobile.png'), full_page=True)
                assert not errors, errors
                browser.close()
                print('Browser passed: Python MCP, greetings/general/course Q&A, source confirmation, follow-ups, cancellation, notes, question bank, DOCX and responsive views. No paid models.')
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == '__main__':
    main()
