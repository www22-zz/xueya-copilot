"""Resolve this machine's installed browser; never inherit another PC's path."""
import os
from pathlib import Path
import shutil


def browser_path():
    candidates = [os.environ.get('CHROME_PATH'), os.environ.get('EDGE_PATH')]
    for directory in (os.environ.get('PROGRAMFILES'), os.environ.get('PROGRAMFILES(X86)'), os.environ.get('LOCALAPPDATA')):
        if directory:
            candidates += [str(Path(directory)/'Google/Chrome/Application/chrome.exe'),
                           str(Path(directory)/'Microsoft/Edge/Application/msedge.exe')]
    candidates += [shutil.which(name) for name in ('google-chrome', 'chromium', 'chromium-browser', 'msedge')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RuntimeError('No installed browser found; set CHROME_PATH or EDGE_PATH')
