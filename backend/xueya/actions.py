"""Durable prepare -> host confirmation -> atomic application. Never a confirm tool."""
from __future__ import annotations
import copy
import json
import time
from uuid import uuid4
from .common import Scope, digest, dumps, identifier, require, utc_now
from .learning import valid_date


def validate_after(kind, value):
    require(isinstance(value, dict), "INVALID_ACTION")
    allowed = {"note": {"title", "content", "sourceIds"}, "question": {"prompt", "answer", "sourceIds"}, "plan": {"title", "days"}}
    require(kind in allowed and not set(value)-allowed[kind], "INVALID_ACTION")
    value = copy.deepcopy(value)

    def text(key, minimum, maximum):
        require(isinstance(value.get(key), str) and minimum <= len(value[key]) <= maximum, "INVALID_ACTION")

    if kind == "note":
        text("title", 1, 200)
        text("content", 0, 30000)
        value.setdefault("sourceIds", [])
    elif kind == "question":
        text("prompt", 1, 5000)
        text("answer", 1, 10000)
    else:
        text("title", 1, 200)
        require(isinstance(value.get("days"), list) and len(value["days"]) <= 90, "INVALID_ACTION")
        for day in value["days"]:
            require(isinstance(day, dict) and set(day) == {"date", "tasks"} and valid_date(day["date"]) and isinstance(day["tasks"], list) and len(day["tasks"]) <= 30, "INVALID_ACTION")
            for task in day["tasks"]:
                require(isinstance(task, dict) and set(task) == {"title", "minutes"} and isinstance(task["title"], str) and 1 <= len(task["title"]) <= 300 and type(task["minutes"]) is int and 1 <= task["minutes"] <= 480, "INVALID_ACTION")
    if kind in ("note", "question"):
        ids = value.get("sourceIds")
        require(isinstance(ids, list) and (0 if kind == "note" else 1) <= len(ids) <= (100 if kind == "note" else 30), "INVALID_ACTION")
        for item in ids:
            identifier(item)
    require(len(dumps(value).encode()) <= 48000, "ACTION_TOO_LARGE")
    return value


class ActionAuthority:
    def __init__(self, repository, *, recover=True, now=None, ttl_ms=300000, max_pending=100):
        self.repo, self.db = repository, repository.db
        self.now = now or (lambda: int(time.time()*1000))
        self.ttl_ms, self.max_pending = ttl_ms, max_pending
        if recover:
            for row in self.db.all("SELECT * FROM confirmations"):
                a = json.loads(row["data"])
                if a["state"] in ("executing", "uncertain"):
                    prior = self.db.one("SELECT receipt FROM receipts WHERE action_id=? AND user_id=? AND course_id=?", (a["actionId"], a["scope"]["userId"], a["scope"]["courseId"]))
                    a["state"] = "applied" if prior else "uncertain"
                    if prior:
                        a["receipt"] = json.loads(prior["receipt"])
                    self.store(a)

    def store(self, action):
        self.db.execute("INSERT INTO confirmations VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (action["actionId"], dumps(action)))

    def get(self, scope, action_id):
        row = self.db.one("SELECT data FROM confirmations WHERE id=?", (action_id,))
        action = json.loads(row["data"]) if row else None
        require(action is not None and action["scope"] == scope.wire(), "ACTION_NOT_FOUND")
        return action

    def live(self, action):
        require(action["expiresAt"] > self.now(), "ACTION_EXPIRED")
        require(action["state"] in ("preview", "confirmed"), "ACTION_NOT_PENDING")

    def prepare(self, scope, args):
        require(isinstance(args, dict) and set(args) == {"kind", "entityId", "expectedVersion", "after"}, "INVALID_ACTION")
        kind, entity_id, expected = args["kind"], identifier(args["entityId"]), args["expectedVersion"]
        require(type(expected) is int and expected >= 0, "INVALID_VERSION")
        after = validate_after(kind, args["after"])
        with self.db.transaction():
            for row in self.db.all("SELECT * FROM confirmations"):
                a = json.loads(row["data"])
                if a["expiresAt"] <= self.now() and a["state"] not in ("executing", "uncertain"):
                    self.db.execute("DELETE FROM confirmations WHERE id=?", (row["id"],))
            require(self.db.one("SELECT count(*) n FROM confirmations")["n"] < self.max_pending, "ACTION_CAPACITY")
            current = self.repo.read(scope, kind, entity_id)
            require((current["version"] if current else 0) == expected, "VERSION_CONFLICT")
            references = []
            for source_id in after.get("sourceIds", []):
                source = self.repo.read_source(scope, source_id)
                require(source is not None and isinstance(source.get("quote"), str), "SOURCE_NOT_FOUND")
                references.append({"sourceId": source_id, "version": source["version"], "quoteHash": digest(source["quote"])})
            preview = {"actionId": str(uuid4()), "scope": scope.wire(), "kind": kind, "entityId": entity_id, "expectedVersion": expected, "before": current["value"] if current else None, "after": after, "references": references, "expiresAt": self.now()+self.ttl_ms}
            preview["digest"] = digest(preview, canonical=True)
            self.store({**preview, "state": "preview"})
            return preview

    def preview(self, scope, action_id):
        action = self.get(scope, action_id)
        self.live(action)
        return {k: v for k, v in action.items() if k != "state"}

    def confirm(self, scope, args):
        with self.db.transaction():
            action = self.get(scope, args.get("actionId"))
            self.live(action)
            require(action["state"] == "preview", "ACTION_ALREADY_CONFIRMED")
            require(action["digest"] == args.get("digest"), "ACTION_CHANGED")
            action["state"] = "confirmed"
            self.store(action)
        return {"actionId": action["actionId"], "state": "confirmed"}

    def cancel(self, scope, action_id):
        with self.db.transaction():
            action = self.get(scope, action_id)
            self.live(action)
            action["state"] = "cancelled"
            self.store(action)
        return {"actionId": action_id, "state": "cancelled"}

    def apply(self, scope, action_id):
        with self.db.transaction():
            action = self.get(scope, action_id)
            if action["state"] == "applied":
                return action["receipt"]
            self.live(action)
            require(action["state"] == "confirmed", "ACTION_CONFIRMATION_REQUIRED")
            action["state"] = "executing"
            self.store(action)
        try:
            receipt = self.repo.apply_confirmed({**action, "audit": {"actionId": action_id, "digest": action["digest"], "actor": scope.user_id, "courseId": scope.course_id, "kind": action["kind"], "entityId": action["entityId"], "at": utc_now()}})
            require(receipt.get("actionId") == action_id and receipt.get("version") == action["expectedVersion"]+1 and receipt.get("auditId") is not None, "INVALID_WRITE_RECEIPT")
            action.update(state="applied", receipt=receipt)
            self.store(action)
            return receipt
        except BaseException:
            action["state"] = "uncertain"
            self.store(action)
            raise
