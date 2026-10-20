"""One browser acceptance of the actual durable job, confirmation and answer UI."""
from pathlib import Path
import tempfile
import httpx
from scripts.check_learning_browser import Browser, server, upstream
from scripts.readonly_agent_fixture import planner_response


def main():
    def controlled(request):
        import json
        return planner_response(json.loads(request.content)) or upstream(request)
    with tempfile.TemporaryDirectory(prefix='xueya-agent-runs-') as temp:
        folder = Path(temp)
        with server(folder, controlled) as (base, app):
            p = app.state.platform
            source = {'id': 'queue-source', 'title': '队列原文', 'location': '第一章', 'quote': '队列遵循先进先出。', 'keywords': ['队列']}
            p.repo.put(p.scope(), 'source', source['id'], source, 0)
            repo = app.state.learning.repo
            p.repo.put(p.scope(), 'artifact', repo.key('course-graph'), {'id': 'course-graph', 'courseId': 'course-default',
                'kind': 'concept-graph', 'revision': 1, 'content': {'courseId': 'course-default', 'edges': [], 'concepts': [
                    {'id': 'queue', 'name': '队列', 'courseId': 'course-default', 'status': 'confirmed',
                     'evidence': [{'sourceId': source['id'], 'version': '1', 'quote': source['quote']}]}]}}, 0)
            p.repo.put(p.scope(), 'question', 'queue-q', {'id': 'queue-q', 'courseId': 'course-default', 'version': '1',
                'sourceId': source['id'], 'sourceVersion': '1', 'evidenceQuote': source['quote'], 'topic': '队列',
                'type': 'boolean', 'prompt': '队列是否先进先出？', 'answer': True, 'status': 'approved', 'conceptIds': []}, 0)
            browser = Browser(folder)
            try:
                browser.call('Page.navigate', url=base+'/#space/chat')
                browser.wait('!!document.querySelector("#chatInput")')
                browser.fill('#chatInput', '请解释队列这一章')
                browser.click('#chatForm .send-button')
                browser.wait('!!document.querySelector("[data-agent-action=start-chapter]")')
                browser.click('[data-agent-action="start-chapter"]')
                browser.wait('!!document.querySelector("[data-agent-action=confirm]")')
                assert browser.evaluate('document.querySelector(".agent-run").innerText.includes("核对本轮练习")')
                browser.click('[data-agent-action=confirm]')
                browser.wait('!!document.querySelector("[data-agent-form=answer]")')
                browser.evaluate('document.querySelector("[data-agent-form=answer] select").value="false"')
                browser.click('[data-agent-form=answer] button[type=submit]')
                browser.wait('document.querySelector(".agent-run")?.innerText.includes("本次得分：0/1")')
                browser.call('Page.reload')
                browser.wait('document.querySelector(".agent-run")?.innerText.includes("本次得分：0/1")')
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                assert not browser.errors, browser.errors
                print('Durable Agent browser acceptance passed: real jobs, preview confirmation, actual answer, reload, mobile.')
            finally:
                browser.close()


if __name__ == '__main__':
    main()
