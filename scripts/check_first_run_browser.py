"""Fresh real server: automatic bundled course, progress, search and restart; free."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

import httpx

from .check_learning_browser import Browser
from .import_knowledge_base import checked

ROOT = Path(__file__).resolve().parents[1]


def launch(directory, logs):
    env = {**os.environ, 'XUEYA_DATA_DIR': str(directory/'data'), 'PORT': '0',
           'XUEYA_PLATFORM_ENABLED': '1', 'PYTHONUTF8': '1', 'XUEYA_AUTO_IMPORT_DEMO': '1',
           'MIMO_API_KEY': '', 'RAG_EMBEDDING_API_KEY': '', 'RAG_RERANK_API_KEY': '', 'RAG_OCR_API_KEY': ''}
    process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'backend.xueya.server'],
        cwd=ROOT, env=env, stdout=logs, stderr=logs,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    lock = directory/'data/server.json'
    started = time.monotonic()
    while time.monotonic()-started < 30:
        assert process.poll() is None, 'host stopped during startup'
        try:
            info = json.loads(lock.read_text(encoding='utf-8'))
            base = 'http://127.0.0.1:'+str(info['port'])
            with httpx.Client(base_url=base, trust_env=False, timeout=1) as http:
                if http.get('/api/health').status_code == 200:
                    return process, base, info, round(time.monotonic()-started, 2)
        except (OSError, ValueError, httpx.HTTPError):
            pass
        time.sleep(.1)
    process.terminate()
    process.wait(10)
    raise AssertionError('host was not ready within 30 seconds')


def stop(process, base, info):
    if process.poll() is None:
        try:
            with httpx.Client(base_url=base, trust_env=False, timeout=3) as http:
                http.post('/api/platform/shutdown', headers={'X-Xueya-Stop': info['stopToken']}).raise_for_status()
            process.wait(15)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(10)
    assert process.returncode == 0


def counts(directory):
    path = (directory/'data/workspace.sqlite').resolve()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
        return {table: db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                for table in ('jobs', 'revisions', 'invocations')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('test-results/first-run-course'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'paidApiCalls': 0}
    with tempfile.TemporaryDirectory(prefix='xueya-first-run-') as temporary, (args.output/'server.log').open('wb') as logs:
        directory = Path(temporary)
        process, base, info, ready_seconds = launch(directory, logs)
        browser = None
        try:
            with httpx.Client(base_url=base, trust_env=False, timeout=30) as http:
                http.headers['X-Xueya-Token'] = checked(http.get('/api/platform/bootstrap'))['token']
                initial = checked(http.get('/api/platform/knowledge/catalog'))
                assert initial['demoImport']['status'] in ('preparing', 'running')
                browser = Browser(directory)
                browser.call('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
                browser.call('Page.navigate', url=base+'/#space/knowledge')
                browser.wait('!!document.querySelector(".kb-demo-import progress")')
                browser.screenshot(args.output/'preparing.png')
                print('Fresh host ready; browser shows automatic preparation progress.', flush=True)
                deadline = time.monotonic()+600
                while time.monotonic() < deadline:
                    value = checked(http.get('/api/platform/knowledge/catalog'))
                    state = value['demoImport']
                    assert state['status'] != 'failed', state
                    if state['status'] == 'completed':
                        break
                    time.sleep(.5)
                else:
                    raise AssertionError('automatic import timed out')
                assert value['summary']['documents'] == 17 and value['summary']['sources'] == 1495
                assert value['summary']['processing'] == 0
                browser.wait('document.querySelectorAll(".kb-document").length===17 && !!document.querySelector("[data-demo-status=completed]")')
                queries = []
                for query in ('栈和队列', '最短路径', '哈夫曼树'):
                    evidence = checked(http.post('/api/platform/knowledge/search', json={'query': query, 'mode': 'lexical'}))['evidence']
                    assert evidence['sources']
                    for source in evidence['sources']:
                        assert checked(http.post('/api/platform/rag/validate', json={'citation': source}))['valid']
                    queries.append({'query': query, 'hits': len(evidence['sources'])})
                browser.fill('#kbQuery', '最短路径')
                browser.click('#kbSearch button')
                browser.wait('!!document.querySelector(".kb-result")')
                browser.click('[data-kb=source]')
                browser.wait('document.querySelector("#kbDialog[open]")?.innerText.includes("实际第")')
                browser.screenshot(args.output/'original-page.png')
                browser.click('#kbDialog [data-kb=close]')
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                browser.screenshot(args.output/'mobile-ready.png')
                assert not browser.errors, browser.errors
                browser.close()
                browser = None
                report.update(status='passed', readySeconds=ready_seconds, documents=17, sources=1495,
                              queries=queries, progressVisible=True)
        finally:
            if browser:
                browser.close()
            stop(process, base, info)
        before = counts(directory)
        assert before['invocations'] == 0
        process, base, info, _ = launch(directory, logs)
        try:
            with httpx.Client(base_url=base, trust_env=False, timeout=30) as http:
                http.headers['X-Xueya-Token'] = checked(http.get('/api/platform/bootstrap'))['token']
                value = checked(http.get('/api/platform/knowledge/catalog'))
                assert value['demoImport']['status'] == 'completed'
                assert value['summary']['documents'] == 17 and value['summary']['sources'] == 1495
        finally:
            stop(process, base, info)
        assert counts(directory) == before
        report['restartCreatedJobsOrRevisions'] = False
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
