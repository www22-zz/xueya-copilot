"""Consistent SQLite backup and checksummed originals; restoration never overwrites."""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
from pathlib import Path
from uuid import uuid4
from .common import require, utc_now
from .files import FileStore


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(files):
    output = []
    for directory in files.root.iterdir():
        if re.fullmatch(r"[a-f0-9]{2}", directory.name):
            require(not directory.is_symlink() and directory.is_dir(), "UNSAFE_FILE_PATH")
            for entry in directory.iterdir():
                if re.fullmatch(r"[a-f0-9]{64}", entry.name):
                    target = files.path(entry.name)
                    output.append({"hash": entry.name, "size": target.stat().st_size})
    return output


def create_backup(data_dir, destination):
    data_dir, destination = Path(data_dir).resolve(), Path(destination).resolve()
    require(not destination.exists(), "BACKUP_DESTINATION_EXISTS")
    require((data_dir / "workspace.sqlite").is_file(), "DATABASE_NOT_FOUND")
    destination.mkdir(parents=True, exist_ok=False)
    source = sqlite3.connect((data_dir / "workspace.sqlite").as_uri()+"?mode=ro", uri=True)
    target = sqlite3.connect(destination / "workspace.sqlite")
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    entries = [{"path": "workspace.sqlite", "sha256": checksum(destination / "workspace.sqlite")}]
    files = FileStore(data_dir / "files")
    for file in inventory(files):
        relative = "files/"+file["hash"][:2]+"/"+file["hash"]
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(files.read(file["hash"]))
        entries.append({"path": relative, "sha256": checksum(target)})
    manifest = {"version": 1, "createdAt": utc_now(), "entries": entries}
    with (destination / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return {"destination": str(destination), "files": len(entries)}


def restore_backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    require(not destination.exists(), "RESTORE_REQUIRES_NEW_DIRECTORY")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("version") == 1 and isinstance(manifest.get("entries"), list), "INVALID_BACKUP")
    paths = set()
    for entry in manifest["entries"]:
        relative = entry.get("path")
        require(isinstance(relative, str) and bool(re.fullmatch(r"workspace\.sqlite|files/[a-f0-9]{2}/[a-f0-9]{64}", relative)) and relative not in paths, "UNSAFE_BACKUP_PATH")
        paths.add(relative)
        file = source / relative
        require(not file.is_symlink() and file.resolve().is_relative_to(source), "UNSAFE_BACKUP_PATH")
        if relative.startswith("files/"):
            require(not file.parent.is_symlink() and relative.split("/")[1] == file.name[:2], "UNSAFE_BACKUP_PATH")
        require(file.is_file() and checksum(file) == entry.get("sha256"), "BACKUP_CHECKSUM_MISMATCH")
    require("workspace.sqlite" in paths, "INVALID_BACKUP")
    probe = sqlite3.connect((source / "workspace.sqlite").as_uri()+"?mode=ro", uri=True)
    try:
        require(probe.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "DATABASE_INTEGRITY_FAILED")
    finally:
        probe.close()
    staging = destination.with_name(destination.name+".restore-"+str(uuid4()))
    staging.mkdir(parents=True, exist_ok=False)
    for relative in paths:
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream, (source / relative).open("rb") as original:
            shutil.copyfileobj(original, stream)
    for attempt in range(6):
        try:
            require(not destination.exists(), "RESTORE_REQUIRES_NEW_DIRECTORY")
            staging.rename(destination)
            break
        except PermissionError:
            if attempt == 5 or destination.exists():
                raise
            time.sleep(.02*2**attempt)
    return {"destination": str(destination), "files": len(paths)}
