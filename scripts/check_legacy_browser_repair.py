"""Run existing browser regressions with the installed Python Playwright's JS runtime.

Keeps test sources intact. Uses isolated legacy fixtures and no external API keys.
"""
import os
from pathlib import Path
import subprocess
import sys

import playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    test = sys.argv[1]
    if test not in ('browser', 'workspace', 'platform'):
        raise ValueError('Unknown browser check')
    runtime = Path(playwright.__file__).parent / 'driver' / 'package'
    env = os.environ.copy()
    for key in ('MIMO_API_KEY', 'RAG_OCR_API_KEY', 'RAG_EMBEDDING_API_KEY', 'RAG_RERANK_API_KEY', 'TAVILY_API_KEY'):
        env[key] = ''
    env['CHROME_PATH'] = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
    code = "const M=require('module'),resolve=M._resolveFilename;M._resolveFilename=function(name,...args){return resolve.call(this,name==='playwright'?process.argv[1]:name,...args)};require(process.argv[2]);"
    raise SystemExit(subprocess.run(['node', '-e', code, str(runtime), str(ROOT / 'tests/e2e' / (test + '.js'))], cwd=ROOT, env=env).returncode)


if __name__ == '__main__':
    main()
