"""Double-click launcher: bootstrap Python, reuse the host, open the real HTTP page."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def run(command):
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise RuntimeError('环境准备失败，请查看上方提示。')


def ready(base, instance=None):
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(base+'/api/health', timeout=1) as response:
            value = json.load(response)
        return value.get('ok') is True and (not instance or value.get('instanceId') == instance)
    except (OSError, ValueError):
        return False


def main():
    os.chdir(ROOT)
    if sys.version_info < (3, 11):
        raise RuntimeError('请先安装 Python 3.11 或更新版本，再双击启动文件。')
    python = ROOT/'.venv/Scripts/python.exe'
    if python.exists():
        probe = subprocess.run([str(python), '-c', 'import sys'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode:
            backup = ROOT/'.migration-backup'/('unusable-venv-'+str(time.time_ns()))
            backup.parent.mkdir(parents=True, exist_ok=True)
            source = (ROOT/'.venv').resolve()
            if not source.is_relative_to(ROOT.resolve()) or not backup.resolve().is_relative_to(ROOT.resolve()):
                raise RuntimeError('环境备份路径不正确。')
            source.rename(backup)
    if not python.exists():
        print('首次启动：正在创建 Python 环境…', flush=True)
        run([sys.executable, '-m', 'venv', str(ROOT/'.venv')])
    lockfile = ROOT/'requirements.lock'
    digest = hashlib.sha256(lockfile.read_bytes()).hexdigest()
    marker = ROOT/'.venv/xueya-launch-dependencies.txt'
    if not marker.exists() or marker.read_text(encoding='utf-8') != digest:
        probe = subprocess.run([str(python), '-X', 'utf8', '-c',
            "import importlib.metadata as m,pathlib,sys; rows=[s.strip().split('==',1) for s in pathlib.Path('requirements.lock').read_text().splitlines() if '==' in s and not s.lstrip().startswith('#')]; sys.exit(any(m.version(name)!=version for name,version in rows))"], cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # On first use the existing project environment can already be prepared.
        if marker.exists() or probe.returncode:
            print('首次启动或依赖有更新：正在安装项目依赖，请稍候…', flush=True)
            run([str(python), '-m', 'pip', 'install', '-r', str(lockfile)])
        marker.write_text(digest, encoding='utf-8')
    if Path(sys.executable).resolve() != python.resolve():
        run([str(python), '-X', 'utf8', str(Path(__file__).resolve())])
        return
    sys.path.insert(0, str(ROOT))
    from backend.xueya.config import load_config
    config = load_config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    metadata = config.data_dir/'server.json'
    if metadata.exists():
        try:
            identity = json.loads(metadata.read_text(encoding='utf-8'))
            base = 'http://127.0.0.1:'+str(int(identity['port']))
            if ready(base, identity['instanceId']):
                print('本地服务已经运行，正在打开星球首页。', flush=True)
                webbrowser.open(base+'/#home')
                return
        except (OSError, ValueError, KeyError, TypeError):
            pass
    env = {**os.environ, 'PYTHONUTF8': '1'}
    stdout = (config.data_dir/'launcher.out.log').open('ab')
    stderr = (config.data_dir/'launcher.err.log').open('ab')
    print('正在启动本地服务…', flush=True)
    try:
        process = subprocess.Popen([str(python), '-X', 'utf8', '-m', 'backend.xueya.server'], cwd=ROOT,
            env=env, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    finally:
        stdout.close()
        stderr.close()
    for _ in range(150):
        if metadata.exists():
            try:
                identity = json.loads(metadata.read_text(encoding='utf-8'))
                base = 'http://127.0.0.1:'+str(int(identity['port']))
                if ready(base, identity['instanceId']):
                    print('启动完成，正在打开星球首页。关闭此窗口不会停止服务。', flush=True)
                    webbrowser.open(base+'/#home')
                    return
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if process.poll() is not None:
            break
        time.sleep(.2)
    raise RuntimeError('服务未能启动。请查看 '+str(config.data_dir/'launcher.err.log')+'；可能有其他程序占用了端口。')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('\n启动失败：'+str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
