"""Prepare the local host; Windows opens the user's default browser."""
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import sys
from urllib.request import ProxyHandler, build_opener
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import launch


def save_target(url, *args, **kwargs):
    parts = urlsplit(url)
    if parts.scheme != 'http' or parts.hostname != '127.0.0.1':
        raise RuntimeError('启动地址必须是本机 HTTP 服务')
    query = dict(parse_qsl(parts.query))
    query['theme'] = 'dark'
    state = ROOT / '.xueya-data'
    state.mkdir(parents=True, exist_ok=True)
    (state / 'launch-url.txt').write_text(urlunsplit(parts._replace(query=urlencode(query))), encoding='ascii')
    return True


def main():
    os.chdir(ROOT)
    print('学涯启动器：默认浏览器 / 深色界面', flush=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else '--prepare'
    if mode == '--prepare':
        original = launch.webbrowser.open
        try:
            launch.webbrowser.open = save_target
            launch.main()
        finally:
            launch.webbrowser.open = original
        return
    if mode != '--verify':
        raise RuntimeError('未知启动参数')
    from backend.xueya.config import load_config
    config = load_config()
    identity = json.loads((config.data_dir / 'server.json').read_text(encoding='utf-8'))
    base = 'http://127.0.0.1:' + str(int(identity['port']))
    if not launch.ready(base, identity['instanceId']):
        raise RuntimeError('本地服务健康检查失败')
    with build_opener(ProxyHandler({})).open(base + '/', timeout=5) as response:
        if response.status != 200:
            raise RuntimeError('首页无法访问')
    print('本地服务与首页检查通过，已请求 Windows 默认浏览器打开。', flush=True)


class Tee:
    def __init__(self, console, log):
        self.console, self.log = console, log

    def write(self, text):
        self.console.write(text)
        self.log.write(text)
        self.log.flush()

    def flush(self):
        self.console.flush()
        self.log.flush()


def run():
    try:
        main()
        return 0
    except Exception as error:
        message = '启动失败：' + str(error)
        print(message, file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    directory = ROOT / '.xueya-data'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'quick-start.log').open('a', encoding='utf-8') as log:
        log.write('\n=== ' + datetime.now().isoformat() + ' ===\n')
        with redirect_stdout(Tee(sys.stdout, log)), redirect_stderr(Tee(sys.stderr, log)):
            raise SystemExit(run())
