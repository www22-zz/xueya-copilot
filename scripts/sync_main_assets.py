"""Import audited remote frontend/contracts/docs; preserve every replaced local file."""
import argparse
import subprocess
from pathlib import Path
from backend.config import ROOT
from backend.core import require


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(['git', 'rev-parse', args.revision], cwd=ROOT, text=True).strip()
    require(len(revision) == 40 and all(c in '0123456789abcdef' for c in revision), 'INVALID_REVISION')
    names = subprocess.check_output(['git', 'diff', '--name-only', '0a16b0e', revision], cwd=ROOT, text=True, encoding='utf-8').splitlines()
    # Disable git path quoting to safely handle Chinese task paths.
    names = subprocess.check_output(['git', '-c', 'core.quotepath=false', 'diff', '--name-only', '0a16b0e', revision], cwd=ROOT, text=True, encoding='utf-8').splitlines()
    backup = ROOT/'.migration-backup'/('main-'+revision[:8])
    for name in names:
        path = (ROOT/name).resolve()
        require(path.is_relative_to(ROOT), 'INVALID_PATH')
        data = subprocess.check_output(['git', 'show', revision+':'+name], cwd=ROOT)
        reference = backup/'remote'/name
        reference.parent.mkdir(parents=True, exist_ok=True)
        reference.write_bytes(data)
        # Keep our C chat routing changes and merge the remote course field explicitly.
        if name == 'frontend/js/services/chat-service.js':
            current = path.read_text(encoding='utf-8')
            marker = 'const request=C.normalizeChatRequest(input);'
            if "request.courseId=input.courseId" not in current:
                current = current.replace(marker, marker+"\n      if(typeof input.courseId==='string')request.courseId=input.courseId.slice(0,150);")
            old = backup/'local'/name
            old.parent.mkdir(parents=True, exist_ok=True)
            old.write_bytes(path.read_bytes())
            path.write_text(current, encoding='utf-8')
        elif name.startswith('frontend/') or name == 'shared/contracts/platform.js' or (name.startswith('docs/') and name not in ('docs/agent-mcp-guide.md',)):
            if path.exists():
                old = backup/'local'/name
                old.parent.mkdir(parents=True, exist_ok=True)
                old.write_bytes(path.read_bytes())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print('Audited main assets imported; Node backend/scripts/tests retained as ignored references only: '+revision)


if __name__ == '__main__':
    main()
