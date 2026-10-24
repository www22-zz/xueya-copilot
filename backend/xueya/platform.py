"""Composition root: repository, originals, jobs, action authority, migration."""
import hashlib
import json
from uuid import uuid4
from .actions import ActionAuthority
from .common import Scope, dumps, identifier, require, utc_now
from .database import Database
from .files import FileStore
from .jobs import JobQueue
from .migration import BrowserMigration
from .parse_worker import parse_artifact
from .rag import extract_chunks
from .repository import Repository
from .resources import Resources


class Platform:
    user_id = "local-user"

    def __init__(self, data_dir, api_slots=2, recover=True):
        self.data_dir = data_dir
        self.db = Database(data_dir / "workspace.sqlite")
        self.repo = Repository(self.db)
        self.files = FileStore(data_dir / "files")
        self.resources = Resources(api_slots=api_slots)
        if not self.repo.courses(self.user_id):
            self.repo.ensure_course(self.user_id, {"id": "course-default", "name": "数据结构"})
        if recover:
            self.db.execute("UPDATE invocations SET status='unknown' WHERE status='pending'")
            for course in self.repo.courses(self.user_id):
                if course["archived"]:
                    continue
                scope = self.scope(course["id"])
                for run in self.repo.all(scope, "run"):
                    if run.get("status") == "running":
                        self.repo.put(scope, "run", run["id"], {**run, "status": "interrupted", "recoveredAt": utc_now()})
        self.jobs = JobQueue(self.repo, self.resources)
        self.authority = ActionAuthority(self.repo, recover=recover)
        self.migration = BrowserMigration(self.repo)
        self.jobs.register("parse-document", self.parse_job)
        self._one_time_practice_cleanup()

    def _one_time_practice_cleanup(self):
        """PRD 14: drop the pre-refactor 笔记/题库/计划/图谱 data exactly once, never the new data."""
        from .practice_cleanup import already_done, cleanup, mark_done, purge_retired_learning
        with self.db.transaction():
            if not already_done(self.db):
                mark_done(self.db, cleanup(self.db, self.repo), auto=True)
            purge_retired_learning(self.db)

    def scope(self, course_id="course-default"):
        scope = Scope(user_id=self.user_id, course_id=course_id)
        self.repo.require_course(scope)
        return scope

    def document(self, scope, document_id):
        row = self.repo.read(scope, "document", document_id)
        require(row is not None, "DOCUMENT_NOT_FOUND")
        return {**row["value"], "id": document_id, "version": row["version"]}

    def upload(self, scope, buffer, name, key, previous_document_id=None):
        self.repo.require_course(scope)
        identifier(key)
        require(isinstance(name, str) and 1 <= len(name) <= 200, "INVALID_FILE_NAME")
        kind = name.rsplit(".", 1)[-1].lower()
        require(kind in ("txt", "md", "pdf", "docx"), "UNSUPPORTED_FILE_TYPE")
        require(kind not in ("txt", "md") or len(buffer) <= 1048576, "FILE_TOO_LARGE")
        value_hash = hashlib.sha256(buffer+dumps({"name": name, "previousDocumentId": previous_document_id or None}).encode()).hexdigest()
        prior = self.db.one("SELECT * FROM jobs WHERE user_id=? AND course_id=? AND type='parse-document' AND idempotency_key=?", (scope.user_id, scope.course_id, key))
        if prior:
            require(json.loads(prior["input"]).get("requestHash") == value_hash, "IDEMPOTENCY_CONFLICT")
            return self.jobs.get(prior["id"], self.user_id)
        file = self.files.put(buffer)
        document_id = "doc-"+str(uuid4())
        with self.db.transaction():
            if previous_document_id:
                previous = self.document(scope, previous_document_id)
                self.repo.put(scope, "document", previous["id"], {**previous, "superseded": True}, previous["version"])
                for source in self.repo.all(scope, "source"):
                    if source.get("documentId") == previous["id"]:
                        self.repo.put(scope, "source", source["id"], source, deleted=True)
            self.repo.put(scope, "document", document_id, {"id": document_id, "name": name, "kind": kind, "fileHash": file["hash"], "size": file["size"], "status": "等待解析", "chunks": [], "tags": [], "meta": "后台处理中", "originalAvailable": True, "remote": True}, 0)
            return self.jobs.submit(self.user_id, {"type": "parse-document", "courseId": scope.course_id, "input": {"documentId": document_id, "requestHash": value_hash}, "idempotencyKey": key, "resource": "cpu"})

    async def parse_job(self, scope, args, *, progress, checkpoint, commit):
        doc = self.document(scope, args["documentId"])
        if doc["status"] == "已解析，可检索":
            return {"documentId": doc["id"], "version": doc["version"]}
        progress({"percent": 10, "label": "正在读取原件"})
        buffer = self.files.read(doc["fileHash"])
        checkpoint({"documentId": doc["id"], "fileHash": doc["fileHash"]})
        parsed = await parse_artifact(buffer, doc["kind"])
        sources = extract_chunks(parsed["text"], doc)
        progress({"percent": 80, "label": "正在保存原文与检索记录"})

        def save():
            current = self.document(scope, doc["id"])
            if current["status"] == "已解析，可检索":
                return {"documentId": doc["id"], "version": current["version"]}
            require(current["version"] == doc["version"], "VERSION_CONFLICT")
            for source in sources:
                self.repo.put(scope, "source", source["id"], source)
            saved = self.repo.put(scope, "document", doc["id"], {**doc, "status": "已解析，可检索", "chunks": sources, "meta": str(len(sources))+"个原文片段", "originalAvailable": True}, doc["version"])
            return {"documentId": doc["id"], "version": saved["version"]}
        result = commit(save)
        progress({"percent": 100, "label": "原文与检索记录已保存"})
        return result

    async def close(self):
        await self.jobs.stop()
        self.db.close()
