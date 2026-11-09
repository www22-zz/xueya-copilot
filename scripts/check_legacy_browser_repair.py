"""Run existing browser regressions with the installed Python Playwright's JS runtime.

Keeps test sources intact. Uses isolated legacy fixtures and no external API keys.
"""
import os
import argparse
from pathlib import Path
import subprocess
import sys

import playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('test',choices=('browser','workspace','platform'))
    parser.add_argument('--source-root',type=Path,default=ROOT)
    options=parser.parse_args()
    test,source=options.test,options.source_root.resolve()
    if not (source/'tests/e2e'/f'{test}.js').is_file():raise ValueError('Browser source is missing')
    runtime = Path(playwright.__file__).parent / 'driver' / 'package'
    env = os.environ.copy()
    for key in ('MIMO_API_KEY', 'RAG_OCR_API_KEY', 'RAG_EMBEDDING_API_KEY', 'RAG_RERANK_API_KEY', 'TAVILY_API_KEY'):
        env[key] = ''
    from .browser_runtime import browser_path
    env['CHROME_PATH'] = browser_path()
    env['XUEYA_PYTHON'] = sys.executable
    code = "const M=require('module'),resolve=M._resolveFilename;M._resolveFilename=function(name,...args){return resolve.call(this,name==='playwright'?process.argv[1]:name,...args)};require(process.argv[2]);"
    raise SystemExit(subprocess.run(['node', '-e', code, str(runtime), str(source / 'tests/e2e' / (test + '.js'))], cwd=source, env=env).returncode)


if __name__ == '__main__':
    main()
