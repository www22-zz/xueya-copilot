"""Python port of E's SQLite/files/jobs platform at remote main f149b5d."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import sys
import uuid
from ..core import require, dumps, now_iso, fingerprint
from ..rag import RagService
from .database import Database
from .repository import Repository
from .files import FileStore
from .resources import Resources
from .jobs import JobQueue
from .migration import BrowserMigration


class Platform:
    def __init__(self, data_dir, rag=None, user_id='local-user', api_slots=2, recover=True):
        from ..mcp.actions import ActionAuthority
        self.data_dir, self.user_id = Path(data_dir).resolve(), user_id
        self.db = Database(self.data_dir/'workspace.sqlite')
        self.repository, self.files, self.resources = Repository(self.db), FileStore(self.data_dir/'files'), Resources(api_slots)
        self.rag = rag or RagService()
        if not self.repository.courses(user_id):
            self.repository.ensure_course(user_id, {'id': 'course-default', 'name': '数据结构'})
        if recover:
            for course in self.repository.courses(user_id):
                if not course['archived']:
                    scope = self.scope(course['id'])
                    for run in self.repository.all(scope, 'run'):
                        if run.get('status') == 'running':
                            self.repository.put(scope, 'run', run['id'], {**run, 'status': 'interrupted', 'recoveredAt': now_iso()})
            self.db.execute("UPDATE invocations SET status='unknown',billing_status='unknown' WHERE status='pending'")
        self.jobs = JobQueue(self.repository, self.resources)
        self.authority, self.migration = ActionAuthority(self.repository, recover=recover), BrowserMigration(self.repository)
        self.jobs.register('parse-document', self._parse)

    def scope(self, course):
        scope = {'userId': self.user_id, 'courseId': course}
        self.repository.require_course(scope)
        return scope

    def document(self, scope, key):
        row = self.repository.read(scope, 'document', key)
        require(row, 'DOCUMENT_NOT_FOUND')
        return {**row['value'], 'id': key, 'version': row['version']}

    def upload(self, scope, name, binary, idempotency_key, previous_document_id=None):
        self.repository.require_course(scope)
        kind = name.rsplit('.', 1)[-1].lower()
        require(kind in ('txt', 'md', 'pdf', 'docx'), 'UNSUPPORTED_FILE_TYPE')
        require(0 < len(name) <= 200, 'INVALID_FILE_NAME')
        require(kind not in ('txt', 'md') or len(binary) <= 1048576, 'FILE_TOO_LARGE')
        request_hash = hashlib.sha256(binary+dumps({'name': name, 'previousDocumentId': previous_document_id}).encode()).hexdigest()
        prior = self.db.one("SELECT * FROM jobs WHERE user_id=? AND course_id=? AND type='parse-document' AND idempotency_key=?", (scope['userId'], scope['courseId'], idempotency_key))
        if prior:
            require(json.loads(prior['input'])['requestHash'] == request_hash, 'IDEMPOTENCY_CONFLICT')
            return self.jobs.get(prior['id'], scope['userId'])
        file, key = self.files.put(binary), 'doc-'+str(uuid.uuid4())
        with self.db.transaction():
            if previous_document_id:
                old = self.document(scope, previous_document_id)
                self.repository.put(scope, 'document', old['id'], {**old, 'superseded': True}, old['version'])
                for source in self.repository.all(scope, 'source'):
                    if source.get('documentId') == old['id']:
                        self.repository.put(scope, 'source', source['id'], source, deleted=True)
            self.repository.put(scope, 'document', key, {'id': key, 'name': name, 'kind': kind, 'fileHash': file['hash'], 'size': file['size'], 'status': '等待解析', 'chunks': [], 'tags': [], 'meta': '后台处理中', 'originalAvailable': True, 'remote': True}, 0)
            return self.jobs.submit(scope['userId'], {'type': 'parse-document', 'courseId': scope['courseId'], 'input': {'documentId': key, 'requestHash': request_hash}, 'idempotencyKey': idempotency_key, 'resource': 'cpu'})

    async def _parse(self, job, progress, checkpoint, commit):
        scope, key = job['scope'], job['input']['documentId']
        document = self.document(scope, key)
        if document['status'] == '已解析，可检索':
            return {'documentId': key, 'version': document['version']}
        progress({'percent': 10, 'label': '正在读取原件'})
        binary = self.files.read(document['fileHash'])
        checkpoint({'documentId': key, 'fileHash': document['fileHash']})
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'backend.platform.parse_worker', stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=Path(__file__).resolve().parents[2])
        try:
            stdout, _ = await process.communicate(dumps({'data': base64.b64encode(binary).decode(), 'kind': document['kind'], 'document': {'id': key, 'name': document['name']}}).encode())
            require(process.returncode == 0 and len(stdout) <= 16000000, 'PARSE_FAILED')
            ingested = json.loads(stdout)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        progress({'percent': 80, 'label': '正在保存原文与检索记录'})
        def save():
            current = self.document(scope, key)
            if current['status'] == '已解析，可检索':
                return {'documentId': key, 'version': current['version']}
            require(current['version'] == document['version'], 'VERSION_CONFLICT')
            for source in ingested['sources']:
                self.repository.put(scope, 'source', source['id'], {**source, 'documentId': key})
            saved = self.repository.put(scope, 'document', key, {**document, 'status': '已解析，可检索', 'chunks': ingested['sources'], 'meta': str(len(ingested['sources']))+'个原文片段', 'originalAvailable': True}, document['version'])
            return {'documentId': key, 'version': saved['version']}
        result = commit(save)
        progress({'percent': 100, 'label': '原文与检索记录已保存'})
        return result

    async def close(self):
        await self.jobs.stop()
        self.db.close()
