"""Shared lab harness for the unattended overhaul: isolated server + Playwright.

Only local, isolated data dirs. The production .xueya-data is never modified by
these helpers; pass --base to target an already running server if needed.

Usage (as a library):
    from scripts.agent_lab import Server, browser_page
    with Server(port=4199) as server:
        with browser_page(server.base) as (page, context):
            page.goto(server.base + '/#space/practice/hot100')
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Playwright creates artifacts through tempfile; the system temp dir is locked down
# on this host, so keep every temp artifact inside the workspace.
_TMP = ROOT / '.tmp' / 'playwright'
_TMP.mkdir(parents=True, exist_ok=True)
os.environ['TMP'] = str(_TMP)
os.environ['TEMP'] = str(_TMP)
tempfile.tempdir = str(_TMP)
PYTHON = ROOT / '.venv' / 'Scripts' / 'python.exe'
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def http_json(url, *, method='GET', body=None, headers=None, timeout=20):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8')), response.headers


class Server:
    """An isolated backend process under .tmp/agent-lab-data/<name>."""

    def __init__(self, *, port=None, data_dir=None, env=None, fresh=False, name=None):
        self.port = port or free_port()
        self.name = name or f'lab-{self.port}'
        self.data_dir = Path(data_dir) if data_dir else ROOT / '.tmp' / 'agent-lab-data' / self.name
        if fresh and self.data_dir.exists():
            shutil.rmtree(self.data_dir, ignore_errors=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.extra_env = dict(env or {})
        self.process = None

    @property
    def base(self):
        return f'http://127.0.0.1:{self.port}'

    def start(self, timeout=90):
        env = {**os.environ}
        env.update({'PORT': str(self.port), 'XUEYA_DATA_DIR': str(self.data_dir), 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'})
        env.update(self.extra_env)
        log_dir = ROOT / 'test-results' / 'agent-lab'
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout = open(log_dir / f'{self.name}.out.log', 'ab')
        stderr = open(log_dir / f'{self.name}.err.log', 'ab')
        self.process = subprocess.Popen([str(PYTHON), '-m', 'backend.xueya.server'], cwd=str(ROOT), env=env,
                                        stdout=stdout, stderr=stderr,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'server exited: {(log_dir / (self.name + ".err.log")).read_text(errors="replace")[-3000:]}')
            try:
                value, _ = http_json(self.base + '/api/health', timeout=3)
                if value.get('ok'):
                    return self
            except Exception:
                time.sleep(0.2)
        raise RuntimeError('server did not become healthy')

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        self.process = None

    def warm(self, cookie, timeout=180):
        """First bootstrap installs the shipped corpus (seconds to tens of seconds).

        Frontend practice-client uses a 3s bootstrap timeout, so an isolated
        lab must warm this once before driving the UI.
        """
        value, _ = http_json(self.base + '/api/platform/bootstrap', headers={'Cookie': cookie}, timeout=timeout)
        return value

    def register(self, username='agent-lab', password='AgentLab123'):
        for action in ('register', 'login'):
            try:
                value, headers = http_json(self.base + '/api/account/' + action, method='POST',
                                           body={'username': username, 'password': password, 'confirmPassword': password})
                if value.get('ok'):
                    cookie = headers.get('Set-Cookie', '').split(';', 1)[0]
                    boot = self.warm(cookie)
                    return {'value': value, 'cookie': cookie, 'token': boot.get('token'), 'username': username, 'password': password}
            except urllib.error.HTTPError:
                continue
        raise RuntimeError('account register/login failed')

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False


@contextlib.contextmanager
def browser_page(base, *, session=None, viewport=None, headless=True, storage_state=None):
    """Playwright page authenticated with a local account (register once per data dir)."""
    tmp = ROOT / '.tmp' / 'playwright'
    tmp.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('TMP', str(tmp))
    os.environ.setdefault('TEMP', str(tmp))
    from playwright.sync_api import sync_playwright
    from scripts.browser_runtime import browser_path
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_path(), headless=headless, args=['--no-sandbox'])
        context = browser.new_context(viewport=viewport or {'width': 1440, 'height': 960})
        if session and session.get('cookie'):
            name, value = session['cookie'].split('=', 1)
            host = base.split('//', 1)[-1].split('/', 1)[0].split(':')[0]
            context.add_cookies([{'name': name, 'value': value, 'domain': host, 'path': '/'}])
        page = context.new_page()
        errors = []
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        page.on('pageerror', lambda error: errors.append('PAGEERROR ' + str(error)))
        try:
            yield page, context, errors
        finally:
            context.close()
            browser.close()


def wait_ui(page, text=None, selector=None, timeout=30000):
    if selector:
        page.wait_for_selector(selector, timeout=timeout)
    if text:
        page.wait_for_function("t => (document.body.innerText||'').includes(t)", arg=text, timeout=timeout)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--probe', default='')
    parser.add_argument('--screenshot', default='')
    options = parser.parse_args()
    with Server(port=options.port or free_port(), fresh=options.fresh) as server:
        session = server.register()
        print('server', server.base, 'data', server.data_dir)
        with browser_page(server.base, session=session) as (page, context, errors):
            if options.probe:
                page.goto(server.base + '/' + options.probe, wait_until='networkidle', timeout=60000)
                time.sleep(1.5)
            if options.screenshot:
                page.screenshot(path=options.screenshot, full_page=True)
            print(json.dumps({'url': page.url, 'title': page.title(), 'errors': errors[:20]}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
