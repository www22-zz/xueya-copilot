"""Simple thinking UI acceptance: real MCP stays internal, controlled model only."""
import asyncio
import json
from pathlib import Path
import tempfile

import httpx

from scripts.check_learning_browser import Browser, server, upstream
from scripts.readonly_agent_fixture import planner_response
from backend.xueya.common import AppError
from backend.xueya.mcp_core import Session


def main():
    output = Path('test-results/chat-thinking')
    output.mkdir(parents=True, exist_ok=True)
    mode = {'fail': False}

    def controlled(request):
        value = json.loads(request.content)
        if 'xueya.readonly-agent.v1' in str(value['messages'][0]['content']):
            state = json.loads(value['messages'][-1]['content'])['state']
            if any(o.get('status') == 'failed' for o in state['observations']):
                return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({
                    'action': {'type': 'ask_user', 'question': '原文工具暂不可用，请稍后继续。'}}, ensure_ascii=False)}, 'finish_reason': 'stop'}]})
        return planner_response(value) or upstream(request)

    original = Session.call

    async def slow_call(self, name, args=None):
        await asyncio.sleep(.7)
        if mode['fail'] and name == 'read_source':
            raise AppError('MCP_BUSY')
        return await original(self, name, args)

    Session.call = slow_call
    try:
        with tempfile.TemporaryDirectory(prefix='xueya-mcp-trace-') as temporary:
            folder = Path(temporary)
            with server(folder, controlled) as (base, app):
                p = app.state.platform
                source = {'id': 'trace-queue', 'title': 'MCP 验收资料', 'location': '第一章 · 队列',
                          'quote': '队列遵循先进先出：先入队的元素先出队。', 'keywords': ['队列', '先进先出']}
                p.repo.put(p.scope(), 'source', source['id'], source, 0)
                browser = Browser(folder)
                try:
                    browser.call('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
                    browser.call('Page.navigate', url=base+'/#space/ask')
                    browser.wait('!!document.querySelector("#chatInput")')
                    material = folder/'MCP验收队列.txt'
                    material.write_text(source['quote'], encoding='utf-8')
                    browser.evaluate('''(()=>{const input=document.querySelector('#imageInput'),files=new DataTransfer();files.items.add(new File(['队列遵循先进先出：先入队的元素先出队。'],'MCP验收队列.txt',{type:'text/plain'}));input.files=files.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()''')
                    browser.wait('document.querySelector(".attachment-list")?.innerText.includes("MCP验收队列.txt")')
                    browser.fill('#chatInput', '根据课程资料解释队列的先进先出定义，先搜索再读取原文。')
                    browser.click('#chatForm .send-button')
                    browser.wait('document.querySelector(".loading-message .stream-text")?.textContent==="正在思考中"')
                    assert browser.evaluate('!document.querySelector(".mcp-trace,.workflow-details")')
                    browser.screenshot(output/'running.png')
                    browser.wait('!document.querySelector("#chatForm .stop-button")')
                    browser.wait('document.querySelector(".ai-message .rich-content")?.textContent.includes("先进先出")')
                    assert browser.evaluate('!document.querySelector(".mcp-trace,.workflow-details")')
                    runs = p.repo.all(p.scope(), 'run')
                    used = {o['tool'] for o in runs[-1]['result']['agent']['observations'] if o.get('status') == 'completed'}
                    assert {'search_materials', 'read_source'} <= used
                    browser.screenshot(output/'completed.png')
                    browser.reload()
                    browser.wait('document.querySelector(".ai-message .rich-content")?.textContent.includes("先进先出")')
                    assert browser.evaluate('!document.querySelector(".mcp-trace,.workflow-details")')
                    browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                    assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    browser.screenshot(output/'mobile.png')
                    browser.evaluate('document.documentElement.dataset.theme="dark"')
                    browser.screenshot(output/'mobile-dark.png')

                    # Renderer checks use adversarial metadata without executing it.
                    assert browser.evaluate('''(()=>{const t=XueyaMCPTrace,m={toolCalls:[{id:'1',tool:'read_source',status:'failed',arguments:{apiKey:'never-show-this'},data:{error:'<img src=x onerror=alert(1)>'}}]};const el=document.createElement('div');el.innerHTML=t.render(m);return !el.querySelector('img')&&!el.innerHTML.includes('never-show-this')&&el.textContent.includes('失败')})()''')
                    assert browser.evaluate('''(()=>{const t=XueyaMCPTrace;let calls=[];for(let i=1;i<=12;i++)calls=t.collect(calls,{status:'running',decisions:[{round:i,type:'call_tool',stepId:'search'+i,tool:'search_materials',arguments:{query:String(i)}}],observations:[{round:i,stepId:'search'+i,tool:'search_materials',status:'completed',data:{sources:[]}}]});return calls.length===12&&calls[0].arguments.query==='1'})()''')

                    mode['fail'] = True
                    browser.fill('#chatInput', '根据课程资料再次核对队列原文。')
                    browser.click('#chatForm .send-button')
                    browser.wait('!document.querySelector("#chatForm .stop-button")')
                    assert browser.evaluate('!document.querySelector(".mcp-trace,.workflow-details")')
                    browser.screenshot(output/'failed.png')
                    mode['fail'] = False
                    browser.fill('#chatInput', '根据课程资料再读取一次队列定义。')
                    browser.click('#chatForm .send-button')
                    browser.wait('document.querySelector(".ai-message:last-child .stream-text")?.textContent==="正在思考中"')
                    browser.click('[data-stop-chat]')
                    browser.wait('!document.querySelector("#chatForm .stop-button")')
                    assert browser.evaluate('document.querySelector(".ai-message:last-child").innerText.includes("已停止")')
                    browser.screenshot(output/'cancelled.png')
                    assert not browser.errors, browser.errors
                    print('Thinking UI browser passed: one thinking indicator, real MCP search/read kept internal, no tool/process panels, persisted answers, failure/cancellation, mobile and dark theme.')
                finally:
                    browser.close()
    finally:
        Session.call = original


if __name__ == '__main__':
    main()
