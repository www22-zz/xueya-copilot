"""Immutable, content-addressed originals. Caller never supplies a filesystem path."""
import hashlib
import os
import re
from pathlib import Path
from uuid import uuid4
from .common import require


class FileStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, value):
        require(isinstance(value, str) and bool(re.fullmatch(r"[a-f0-9]{64}", value)), "INVALID_FILE_HASH")
        prefix = self.root / value[:2]
        target = prefix / value
        require(not prefix.is_symlink() and not target.is_symlink(), "UNSAFE_FILE_PATH")
        require(target.resolve().is_relative_to(self.root), "UNSAFE_FILE_PATH")
        return target

    def put(self, buffer):
        # Media originals may be larger; document HTTP/parse limits remain separate.
        require(isinstance(buffer, bytes) and 0 < len(buffer) <= 128*1024*1024, "FILE_TOO_LARGE")
        value = hashlib.sha256(buffer).hexdigest()
        target = self.path(value)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(".tmp-"+str(uuid4()))
            try:
                with temporary.open("xb") as file:
                    file.write(buffer)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            self.read(value)
        return {"hash": value, "size": len(buffer)}

    def read(self, value):
        target = self.path(value)
        require(target.is_file(), "ORIGINAL_NOT_FOUND")
        require(target.stat().st_size <= 128*1024*1024, "FILE_TOO_LARGE")
        buffer = target.read_bytes()
        require(hashlib.sha256(buffer).hexdigest() == value, "FILE_HASH_MISMATCH")
        return buffer
