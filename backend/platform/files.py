import hashlib
import os
from pathlib import Path
import re
import uuid
from ..core import require


class FileStore:
    def __init__(self, root, max_bytes=10485760):
        self.root, self.max_bytes = Path(root).resolve(), max_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def location(self, digest):
        require(isinstance(digest, str) and re.fullmatch('[a-f0-9]{64}', digest), 'INVALID_FILE_HASH')
        file = self.root/digest[:2]/digest
        require(not file.parent.is_symlink() and not file.is_symlink(), 'UNSAFE_FILE_PATH')
        return file

    def read(self, digest):
        file = self.location(digest)
        require(file.is_file(), 'FILE_NOT_FOUND')
        data = file.read_bytes()
        require(hashlib.sha256(data).hexdigest() == digest, 'FILE_HASH_MISMATCH')
        return data

    def put(self, data):
        require(isinstance(data, bytes) and data, 'EMPTY_FILE')
        require(len(data) <= self.max_bytes, 'FILE_TOO_LARGE')
        digest = hashlib.sha256(data).hexdigest()
        file = self.location(digest)
        file.parent.mkdir(parents=True, exist_ok=True)
        if file.exists():
            self.read(digest)
        else:
            temp = file.with_suffix('.'+str(uuid.uuid4())+'.tmp')
            try:
                with temp.open('xb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                temp.replace(file)
            finally:
                temp.unlink(missing_ok=True)
        return {'hash': digest, 'size': len(data)}

    def inventory(self):
        return [{'hash': p.name, 'size': p.stat().st_size} for p in self.root.glob('*/*') if re.fullmatch('[a-f0-9]{64}', p.name) and not p.is_symlink() and not p.parent.is_symlink()]

    def remove_unreferenced(self, digest, referenced):
        require(digest not in referenced, 'FILE_STILL_REFERENCED')
        self.location(digest).unlink(missing_ok=True)
