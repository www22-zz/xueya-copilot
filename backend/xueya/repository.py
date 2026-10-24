"""Scoped entity/revision storage and browser workspace projection."""
from __future__ import annotations

import base64
import copy
import json
from uuid import uuid4

from .common import KINDS, Scope, digest, dumps, identifier, require, utc_now, validate_workspace
from .learning import QUESTIONS, SOURCES, wrong_questions


def encode_cursor(value):
    return base64.urlsafe_b64encode(dumps(value).encode()).decode().rstrip("=")


def decode_cursor(value):
    try:
        require(isinstance(value, str) and len(value) <= 2000, "INVALID_CURSOR")
        result = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        require(isinstance(result, dict), "INVALID_CURSOR")
        return result
    except Exception as error:
        from .common import AppError
        raise AppError("INVALID_CURSOR") from error


class Repository:
    def __init__(self, db):
        self.db = db

    def require_course(self, scope: Scope, *, archived=False):
        row = self.db.one("SELECT * FROM courses WHERE user_id=? AND id=?", (scope.user_id, scope.course_id))
        require(row is not None, "COURSE_NOT_FOUND")
        require(archived or not row["archived"], "COURSE_ARCHIVED")
        return row

    def ensure_course(self, user_id, course):
        identifier(user_id)
        identifier(course.get("id"))
        require(isinstance(course.get("name"), str) and 0 < len(course["name"]) <= 100, "INVALID_COURSE")
        self.db.execute("INSERT INTO courses(user_id,id,name,archived) VALUES(?,?,?,?) ON CONFLICT(user_id,id) DO UPDATE SET name=excluded.name,archived=excluded.archived,version=courses.version+1", (user_id, course["id"], course["name"], int(bool(course.get("archived")))))

    def courses(self, user_id):
        return [{**r, "archived": bool(r["archived"])} for r in self.db.all("SELECT id,name,archived,version FROM courses WHERE user_id=? ORDER BY id", (user_id,))]

    def read(self, scope, kind, entity_id, *, include_deleted=False):
        self.require_course(scope, archived=True)
        row = self.db.one("SELECT * FROM entities WHERE user_id=? AND course_id=? AND kind=? AND id=?", (scope.user_id, scope.course_id, kind, entity_id))
        if row is None or (row["deleted"] and not include_deleted):
            return None
        return {"id": row["id"], "version": row["version"], "value": json.loads(row["data"]), "createdAt": row["created_at"], "updatedAt": row["updated_at"], "deleted": bool(row["deleted"])}

    def put(self, scope, kind, entity_id, value, expected_version=None, *, deleted=False):
        with self.db.transaction():
            self.require_course(scope)
            require(kind in KINDS, "INVALID_KIND")
            identifier(entity_id)
            old = self.read(scope, kind, entity_id, include_deleted=True)
            version = old["version"] if old else 0
            require(expected_version is None or type(expected_version) is int and version == expected_version, "VERSION_CONFLICT")
            at, data = utc_now(), dumps(value)
            require(len(data.encode()) <= 16000000, "ENTITY_TOO_LARGE")
            self.db.execute("INSERT INTO entities VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,course_id,kind,id) DO UPDATE SET version=excluded.version,data=excluded.data,updated_at=excluded.updated_at,deleted=excluded.deleted", (scope.user_id, scope.course_id, kind, entity_id, version+1, data, old["createdAt"] if old else at, at, int(deleted)))
            self.db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?,?)", (scope.user_id, scope.course_id, kind, entity_id, version+1, data, at))
            return {"version": version+1, "value": copy.deepcopy(value)}

    def all(self, scope, kind):
        self.require_course(scope, archived=True)
        require(kind in KINDS, "INVALID_KIND")
        return [{"id": r["id"], **json.loads(r["data"]), "version": r["version"]} for r in self.db.all("SELECT * FROM entities WHERE user_id=? AND course_id=? AND kind=? AND deleted=0 ORDER BY id", (scope.user_id, scope.course_id, kind))]

    def list(self, scope, kind, cursor=None, limit=20):
        require(type(limit) is int and 1 <= limit <= 50, "INVALID_LIMIT")
        self.require_course(scope, archived=True)
        require(kind in KINDS, "INVALID_KIND")
        after = ""
        if cursor:
            c = decode_cursor(cursor)
            require(c.get("userId") == scope.user_id and c.get("courseId") == scope.course_id and c.get("kind") == kind and isinstance(c.get("after"), str), "INVALID_CURSOR")
            after = c["after"]
        rows = self.db.all("SELECT * FROM entities WHERE user_id=? AND course_id=? AND kind=? AND deleted=0 AND id>? ORDER BY id LIMIT ?", (scope.user_id, scope.course_id, kind, after, limit+1))
        items = [{"id": r["id"], **json.loads(r["data"]), "version": r["version"]} for r in rows[:limit]]
        return {"items": items, "nextCursor": encode_cursor({**scope.wire(), "kind": kind, "after": items[-1]["id"]}) if len(rows) > limit else None}

    def page_items(self, scope, items, label, cursor=None, limit=20):
        require(type(limit) is int and 1 <= limit <= 50, "INVALID_LIMIT")
        binding, after = digest({"scope": scope.wire(), "label": label}), ""
        if cursor:
            c = decode_cursor(cursor)
            require(c.get("binding") == binding and isinstance(c.get("after"), str), "INVALID_CURSOR")
            after = c["after"]
        remaining = sorted((i for i in items if str(i["id"]) > after), key=lambda i: str(i["id"]))
        page = remaining[:limit]
        return {"items": page, "nextCursor": encode_cursor({"binding": binding, "after": page[-1]["id"]}) if len(remaining) > limit else None}

    def get_workspace(self, user_id):
        row = self.db.one("SELECT * FROM workspaces WHERE user_id=?", (user_id,))
        return {"version": row["version"], "data": json.loads(row["data"]), "updatedAt": row["updated_at"]} if row else None

    def save_workspace(self, user_id, value, expected_version=0):
        validate_workspace(value)
        from .practice_cleanup import strip_retired_payload
        value = strip_retired_payload(value)
        require(type(expected_version) is int and expected_version >= 0, "INVALID_VERSION")
        with self.db.transaction():
            old = self.get_workspace(user_id)
            require((old["version"] if old else 0) == expected_version, "VERSION_CONFLICT")
            self.project(user_id, value)
            self.db.execute("INSERT INTO workspaces VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET version=excluded.version,data=excluded.data,updated_at=excluded.updated_at", (user_id, expected_version+1, dumps(value), utc_now()))
            return {"version": expected_version+1, "data": copy.deepcopy(value)}

    def project(self, user_id, workspace):
        for course in workspace["courses"]:
            self.ensure_course(user_id, {**course, "archived": False})
            scope, data = Scope(user_id=user_id, course_id=course["id"]), course["data"]
            sources = (SOURCES if course["id"] == "course-default" else []) + [s for d in data.get("documents", []) if not d.get("superseded") and not d.get("deleted") for s in d.get("chunks", [])]
            groups = {"source": sources, "session": data.get("sessions", [])}
            for kind, items in groups.items():
                seen = set()
                for i, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    entity_id = str(item.get("id") or f"{kind}-{digest(item)[:30]}-{i}")
                    seen.add(entity_id)
                    old = self.read(scope, kind, entity_id, include_deleted=True)
                    # Browser workspace snapshots do not own C-approved questions
                    # or B's authoritative, revision-bound evidence records.
                    if old and (old['value'].get('learningManaged') or kind == 'source' and old['value'].get('documentRevision') is not None):
                        continue
                    item = {k: v for k, v in item.items() if k != 'learningManaged'}
                    if not old or digest(old["value"]) != digest(item):
                        self.put(scope, kind, entity_id, item)
                for previous in self.all(scope, kind):
                    if previous["id"] not in seen and not previous.get('learningManaged') and not (kind == 'source' and previous.get('documentRevision') is not None):
                        self.put(scope, kind, previous["id"], previous, deleted=True)
            for document in data.get("documents", []):
                if document.get("remote") or not document.get("id"):
                    continue
                old = self.read(scope, "document", document["id"])
                value = {**(old["value"] if old else {}), **document}
                if old and old["value"].get("fileHash"):
                    value.update(fileHash=old["value"]["fileHash"], originalAvailable=True)
                if not old or digest(old["value"]) != digest(value):
                    self.put(scope, "document", document["id"], value)
            self.ensure_course(user_id, course)

    def read_source(self, scope, source_id):
        row = self.read(scope, "source", source_id)
        return {"id": source_id, **row["value"], "version": row["version"]} if row else None

    def patch_workspace(self, scope, kind, entity_id, value):
        ws = self.get_workspace(scope.user_id)
        course = next((c for c in ws["data"]["courses"] if c["id"] == scope.course_id), None) if ws else None
        if not course:
            return
        data = course["data"]
        if kind == "plan":
            data["plan"] = [{**day, "id": f"{entity_id}-day-{i}", "tasks": [{**t, "id": f"{entity_id}-task-{i}-{j}"} for j, t in enumerate(day["tasks"])]} for i, day in enumerate(value["days"])]
            data["planVersion"] = data.get("planVersion", 0)+1
        else:
            field = "cards" if kind == "note" else "bank"
            item = ({**value, "id": entity_id, "text": value["content"], "sources": [s for source_id in value.get("sourceIds", []) if (s := self.read_source(scope, source_id))], "createdAt": utc_now()} if kind == "note" else {**value, "id": entity_id, "type": "short", "answerText": value["answer"], "sourceId": value["sourceIds"][0], "topic": "课程练习", "version": 1})
            entries = data.setdefault(field, [])
            index = next((i for i, n in enumerate(entries) if n["id"] == entity_id), None)
            if index is None:
                entries.insert(0, item)
            else:
                entries[index] = item
        self.db.execute("UPDATE workspaces SET version=version+1,data=?,updated_at=? WHERE user_id=?", (dumps(ws["data"]), utc_now(), scope.user_id))

    def apply_confirmed(self, request):
        scope = Scope.model_validate(request["scope"])
        with self.db.transaction():
            self.require_course(scope)
            prior = self.db.one("SELECT receipt FROM receipts WHERE user_id=? AND course_id=? AND action_id=?", (scope.user_id, scope.course_id, request["actionId"]))
            if prior:
                return json.loads(prior["receipt"])
            for ref in request.get("references", []):
                source = self.read_source(scope, ref["sourceId"])
                require(source is not None and source["version"] == ref["version"] and digest(source["quote"]) == ref["quoteHash"], "SOURCE_VERSION_CONFLICT")
            saved = self.put(scope, request["kind"], request["entityId"], request["after"], request["expectedVersion"])
            audit_id = str(uuid4())
            self.db.execute("INSERT INTO audits VALUES(?,?,?,?,?,?)", (audit_id, scope.user_id, scope.course_id, request["actionId"], dumps(request["audit"]), utc_now()))
            receipt = {"actionId": request["actionId"], "version": saved["version"], "auditId": audit_id}
            self.db.execute("INSERT INTO receipts VALUES(?,?,?,?)", (scope.user_id, scope.course_id, request["actionId"], dumps(receipt)))
            self.patch_workspace(scope, request["kind"], request["entityId"], request["after"])
            return receipt
