"""Compile browser-only utilities into the local stylesheet shipped with the app.

Install the locked frontend dependencies with npm ci before running this module.
The Python server never needs Node or a network connection to serve these assets.
"""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    node = shutil.which('node')
    compiler = ROOT / 'node_modules/tailwindcss/lib/cli.js'
    if not node or not compiler.is_file():
        raise SystemExit('Frontend build needs Node >=20 and npm ci; existing local CSS remains usable.')
    subprocess.run([node, str(compiler), '--config', 'tailwind.config.cjs',
                    '--input', 'frontend/css/utility-source.css',
                    '--output', 'frontend/css/utilities.css', '--minify'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
