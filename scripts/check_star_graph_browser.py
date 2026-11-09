"""Isolated visual and navigation check using real fixed-bank question metadata."""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright
from backend.xueya.graph_practice import attach_practice
from .browser_runtime import browser_path

ROOT = Path(__file__).resolve().parents[1]


def check_hover_positions(page):
    # Keep :hover active even if a regression moves the node away from the pointer.
    page.mouse.move(0, 0)
    session = page.context.new_cdp_session(page)
    session.send('DOM.enable')
    session.send('CSS.enable')
    root_id = session.send('DOM.getDocument')['root']['nodeId']
    for motion in ('no-preference', 'reduce'):
        page.emulate_media(reduced_motion=motion)
        for selector in ('.cg-chapter.is-active', '.cg-leaf'):
            node = page.locator(selector).first
            node_id = session.send('DOM.querySelector', {'nodeId': root_id, 'selector': selector})['nodeId']
            before = node.evaluate('node => node.getBoundingClientRect().toJSON()')
            session.send('CSS.forcePseudoState', {'nodeId': node_id, 'forcedPseudoClasses': ['hover']})
            after = node.evaluate('''async node => {
                node.getBoundingClientRect();
                await Promise.all(node.getAnimations().map(animation => animation.finished));
                return node.getBoundingClientRect().toJSON();
            }''')
            assert before == after, f'{selector} moved on hover ({motion}): {before} -> {after}'
            session.send('CSS.forcePseudoState', {'nodeId': node_id, 'forcedPseudoClasses': []})
    session.detach()
    page.emulate_media(reduced_motion='no-preference')


def main():
    bank = json.loads((ROOT/'backend/xueya/data/data_structures_practice.json').read_text(encoding='utf-8'))
    docs = [{'id': str(i), 'name': name, 'subject': '数据结构', 'ready': True} for i, name in enumerate(
        ['第1章 绪论', '第2章 线性表(1) 顺序表', '第2章 线性表(2) 链表', '第3章 栈和队列', '第4章 数组'])]
    nodes, edges = {}, []
    attach_practice(docs, nodes, edges, [dict(q, bankSource='legacy') for q in bank['questions']])
    graph = dict(documents=docs, nodes=list(nodes.values()), edges=edges, blocked=[], available=False,
                 coverage=dict(completedRanges=0,totalRanges=0,pendingJobs=0,questions=0,unreadyDocuments=0,remainingCalls=0))
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT/'frontend')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    output = ROOT/'test-results/star-graph'; output.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_path(), headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
            base = f'http://127.0.0.1:{server.server_port}'
            page.route('**/*', lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
            page.goto(base+'/css/course-star-map.css')
            page.set_content('<html><head></head><body><main id="graph"></main></body></html>')
            for css in ['styles.css', 'workspace.css', 'learning.css', 'stitch-theme.css', 'course-star-map.css']:
                page.add_style_tag(path=str(ROOT/'frontend/css'/css))
            page.evaluate('''data => {window.fixture=data;window.XueyaRich={escape:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};window.XueyaPlatform={spaceFetch:async url=>({ok:true,json:async()=>url.includes('course-graph')?{ok:true,...window.fixture}:{ok:true,courses:[]}})};}''', graph)
            page.add_script_tag(path=str(ROOT/'frontend/js/course-graph.js'))
            page.evaluate("XueyaCourseGraph.mount(document.querySelector('#graph'),'course-default')")
            page.locator('[data-cg-book]').click()
            topic = page.get_by_role('img', name='数据结构与算法', exact=True)
            topic.click()
            assert page.locator('.cg-root-rail').count() == page.locator('[data-star-doc]').count() == len(docs)
            page.locator('[data-star-doc="3"]').click()
            assert topic.is_visible() and page.locator('[data-star-doc]').count() == len(docs)
            canvas = page.locator('.cg-star-map')
            fitted_view = canvas.get_attribute('viewBox')
            page.locator('[data-cg-zoom="0.8"]').click()
            assert canvas.get_attribute('viewBox') != fitted_view
            page.locator('[data-cg-fit]').click()
            assert canvas.get_attribute('viewBox') == fitted_view
            assert page.locator('.cg-leaf').count() == len(nodes)
            check_hover_positions(page)
            page.locator('.cg-leaf').first.click()
            link = page.locator('.cg-fixed-question').first
            assert link.get_attribute('href').startswith('#space/practice/legacy/ds-')
            page.screenshot(path=str(output/'desktop.png'), full_page=True)
            link.click()
            assert '#space/practice/legacy/ds-' in page.url
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'mobile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            browser.close()
            print('PASS: always-visible topic and chapter branches, zoom/fit, stable hover, fixed links, desktop/mobile')
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    main()
