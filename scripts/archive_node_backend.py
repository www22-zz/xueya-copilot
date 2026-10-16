"""One-time migration backup with verified bytes before moving legacy JS out of active paths."""
import argparse
import hashlib
from pathlib import Path
import zipfile
from backend.config import ROOT
from backend.core import require


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', action='store_true')
    args = parser.parse_args()
    require(args.archive, 'EXPLICIT_ARCHIVE_REQUIRED')
    root = ROOT.resolve()
    backup = (root/'.migration-backup').resolve()
    require(backup.is_relative_to(root) and backup != root, 'INVALID_BACKUP_PATH')
    backup.mkdir(exist_ok=True)
    targets = [*root.glob('backend/**/*.js'), *root.glob('tests/**/*.js'), *root.glob('scripts/*.js')]
    require(all(p.resolve().is_relative_to(root) and p.suffix == '.js' for p in targets), 'INVALID_ARCHIVE_TARGET')
    if not targets:
        print('No active Node backend or legacy JS test scripts remain.')
        return
    archive_path = backup/'node-backend-before-python.zip'
    require(not archive_path.exists(), 'BACKUP_ALREADY_EXISTS')
    # Include original startup docs and manifests before they are replaced.
    originals = [*targets, *[root/name for name in ('README.md', 'package.json', 'package-lock.json')]]
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in originals:
            archive.write(file, file.relative_to(root).as_posix())
    with zipfile.ZipFile(archive_path) as archive:
        require(archive.testzip() is None, 'BACKUP_CORRUPT')
        for file in originals:
            require(hashlib.sha256(file.read_bytes()).digest() == hashlib.sha256(archive.read(file.relative_to(root).as_posix())).digest(), 'BACKUP_VERIFY_FAILED')
    # Every destination is checked under this workspace before moving files.
    for file in targets:
        destination = (backup/'node-source'/file.relative_to(root)).resolve()
        require(destination.is_relative_to(backup) and destination != backup, 'INVALID_MOVE_TARGET')
        destination.parent.mkdir(parents=True, exist_ok=True)
        file.rename(destination)
    print(f'Verified backup and archived {len(targets)} legacy JavaScript files; frontend/shared browser scripts preserved.')


if __name__ == '__main__':
    main()
