"""Local toolchain detection for the Hot100 code workbench.

Detects Python, a C++ compiler (g++) and a Java compiler/runtime (javac + java)
without trusting PATH alone: each candidate is version-probed and then exercised
with a tiny compile/run sample. Results are cached for a few minutes and can be
refreshed from the UI.

This is convenience detection for a local single-user app, not a sandbox.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROBE_TIMEOUT_SECONDS = 30
VERSION_TIMEOUT_SECONDS = 10
CACHE_TTL_SECONDS = 300
MAX_CAPTURE_BYTES = 16384

# Optional explicit overrides for hosts where PATH differs from the launcher.
ENV_OVERRIDES = {
    'cpp': ('XUEYA_GPP_PATH',),
    'javac': ('XUEYA_JAVAC_PATH',),
    'java': ('XUEYA_JAVA_PATH',),
}

_CACHE = {'at': 0.0, 'value': None}


def _run(command, *, cwd, timeout, env=None):
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {'ok': False, 'code': None, 'stdout': '', 'stderr': '执行超时'}
    except OSError as error:
        return {'ok': False, 'code': None, 'stdout': '', 'stderr': str(error)}
    return {
        'ok': completed.returncode == 0,
        'code': completed.returncode,
        'stdout': completed.stdout.decode('utf-8', errors='replace')[:MAX_CAPTURE_BYTES],
        'stderr': completed.stderr.decode('utf-8', errors='replace')[:MAX_CAPTURE_BYTES],
    }


def _first_line(*values):
    for value in values:
        for line in (value or '').splitlines():
            if line.strip():
                return line.strip()[:160]
    return ''


def _override_path(name):
    for key in ENV_OVERRIDES.get(name, ()):
        value = os.environ.get(key)
        if value and Path(value).is_file():
            return value
    return None


def _find(name, override):
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    if os.name == 'nt':
        candidates = {
            'g++': [r'C:\MinGW_c23\mingw64\bin\g++.exe', r'C:\mingw64\bin\g++.exe',
                    r'C:\Program Files\mingw64\bin\g++.exe', r'C:\msys64\mingw64\bin\g++.exe'],
            'javac': [r'C:\Program Files\Java\jdk-21\bin\javac.exe'],
            'java': [r'C:\Program Files\Java\jdk-21\bin\java.exe'],
        }.get(name, [])
        for candidate in candidates:
            if Path(candidate).is_file():
                return candidate
    return None


def _workspace():
    root = Path(tempfile.gettempdir()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='xueya-toolchain-', dir=str(root)))
    return directory


def _child_env(directory):
    env = {
        'TEMP': str(directory),
        'TMP': str(directory),
        'SYSTEMROOT': os.environ.get('SYSTEMROOT', ''),
    }
    # Compilers occasionally shell out to their own helper binaries; expose the
    # system PATH so an ordinary installation keeps working, but never secrets.
    path = os.environ.get('PATH')
    if path:
        env['PATH'] = path
    return env


def _version_number(text, fallback=''):
    match = re.search(r'(\d+\.\d+(?:\.\d+)?)', text or '')
    return match.group(1) if match else (fallback or '')


def _python_capability():
    version = sys.version.split()[0]
    return {
        'available': True,
        'path': sys.executable or 'python',
        'version': version,
        'label': 'Python ' + version,
        'reason': '',
    }


def _configured(name, executable, *, version_command, probe):
    if not executable:
        return None
    version_run = _run([executable, *version_command], cwd=str(Path(executable).parent), timeout=VERSION_TIMEOUT_SECONDS)
    version = _first_line(version_run.get('stdout'), version_run.get('stderr'))
    if not version:
        return {'available': False, 'path': executable, 'version': '',
                'reason': f'{name} 已找到但无法读取版本信息，可能安装不完整。'}
    return probe(executable, version)


def _probe_cpp(executable, version):
    short = _version_number(version, version)
    directory = _workspace()
    try:
        source = directory / 'probe.cpp'
        binary = directory / 'probe.exe' if os.name == 'nt' else directory / 'probe'
        source.write_text('#include <cstdio>\nint main(){int a=1,b=2;printf("%d\\n",a+b);return 0;}\n', encoding='utf-8')
        build = _run([executable, '-std=c++17', '-O0', '-o', str(binary), str(source)],
                     cwd=str(directory), timeout=PROBE_TIMEOUT_SECONDS, env=_child_env(directory))
        if not build['ok']:
            return {'available': False, 'path': executable, 'version': short,
                    'reason': '找到了 g++，但最小程序编译失败：' + _first_line(build.get('stderr'), build.get('stdout'))}
        run = _run([str(binary)], cwd=str(directory), timeout=VERSION_TIMEOUT_SECONDS, env=_child_env(directory))
        if not run['ok'] or run.get('stdout', '').strip() != '3':
            return {'available': False, 'path': executable, 'version': short,
                    'reason': 'g++ 可以编译，但生成的程序无法运行（可能缺少运行时 DLL）。'}
        return {'available': True, 'path': executable, 'version': short,
                'versionLine': version, 'label': 'g++ ' + short, 'reason': ''}
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _probe_java(executable, version, java_executable):
    short = _version_number(version, version)
    directory = _workspace()
    try:
        source = directory / 'Main.java'
        classes = directory / 'classes'
        classes.mkdir()
        source.write_text('public class Main { public static void main(String[] a){ System.out.println(1+2); } }\n',
                          encoding='utf-8')
        build = _run([executable, '-encoding', 'UTF-8', '-d', str(classes), str(source)],
                     cwd=str(directory), timeout=PROBE_TIMEOUT_SECONDS, env=_child_env(directory))
        if not build['ok']:
            return {'available': False, 'path': executable, 'version': short,
                    'reason': '找到了 javac，但最小程序编译失败：' + _first_line(build.get('stderr'), build.get('stdout'))}
        run = _run([java_executable, '-Dfile.encoding=UTF-8', '-cp', str(classes), 'Main'],
                   cwd=str(directory), timeout=PROBE_TIMEOUT_SECONDS, env=_child_env(directory))
        if not run['ok'] or run.get('stdout', '').strip() != '3':
            return {'available': False, 'path': executable, 'version': short,
                    'reason': 'javac 可以编译，但 java 无法运行生成的 class。'}
        return {'available': True, 'path': executable, 'javaPath': java_executable,
                'version': short, 'versionLine': version, 'label': 'JDK ' + short, 'reason': ''}
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _java_capability(javac_override, java_override):
    javac = _find('javac', javac_override)
    java = _find('java', java_override)
    if not javac:
        return {'available': False, 'path': '', 'javaPath': java or '', 'version': '',
                'reason': '未检测到 javac（JDK 编译器）。只安装 JRE 无法编译 Java，安装 JDK 后重试。'}
    if not java:
        return {'available': False, 'path': javac, 'javaPath': '', 'version': '',
                'reason': '检测到 javac，但未检测到 java 运行时。'}
    version_run = _run([javac, '-version'], cwd=str(Path(javac).parent), timeout=VERSION_TIMEOUT_SECONDS)
    version = _first_line(version_run.get('stdout'), version_run.get('stderr'))
    if not version:
        return {'available': False, 'path': javac, 'javaPath': java, 'version': '',
                'reason': 'javac 已找到但无法读取版本信息，可能安装不完整。'}
    return _probe_java(javac, version, java)


def detect(force=False) -> dict:
    """Return a capability snapshot for Python, C++ and Java."""
    now = time.time()
    if not force and _CACHE['value'] is not None and now - _CACHE['at'] < CACHE_TTL_SECONDS:
        return _CACHE['value']
    capabilities = {
        'python': _python_capability(),
        'cpp': _configured('g++', _find('g++', _override_path('cpp')),
                           version_command=['--version'], probe=_probe_cpp),
        'java': _java_capability(_override_path('javac'), _override_path('java')),
    }
    for name in ('cpp', 'java'):
        if capabilities[name] is None:
            capabilities[name] = {
                'available': False, 'path': '', 'version': '',
                'reason': '未检测到 g++ 编译器。' if name == 'cpp' else '未检测到 javac/java。',
            }
    value = {'capabilities': capabilities,
             'languages': [name for name in ('python', 'cpp', 'java') if capabilities[name]['available']],
             'detectedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    _CACHE['at'], _CACHE['value'] = now, value
    return value


def available_languages() -> list[str]:
    return list(detect().get('languages') or ['python'])


def reset_cache():
    _CACHE['at'], _CACHE['value'] = 0.0, None


def main(argv=None):
    """Print the capability snapshot as JSON (``--probe`` forces a fresh check)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ('--probe', '--json'):
        print('usage: python -m backend.xueya.judge_toolchain [--probe]')
        return 2
    print(json.dumps(detect(force='--probe' in argv), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':  # pragma: no cover - manual tool
    raise SystemExit(main())
