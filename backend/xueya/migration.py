"""Explicit, version-checked browser import with a recoverable raw snapshot."""
import copy
import json
import time
from uuid import uuid4
from .common import digest, dumps, require, utc_now, validate_workspace


class BrowserMigration:
    def __init__(self, repository):
        self.repo, self.previews = repository, {}

    def preview(self, user_id, args):
        workspace = copy.deepcopy(validate_workspace(args.get("workspace")))
        raw = args.get("raw") or {}
        require(len(dumps({"workspace": workspace, "raw": raw}).encode()) <= 24000000, "IMPORT_TOO_LARGE")
        from .practice_cleanup import strip_retired_payload
        cleaned = strip_retired_payload({'workspace': workspace, 'raw': raw})
        workspace, raw = cleaned['workspace'], cleaned['raw']
        value_hash = digest({"workspace": workspace, "raw": raw})
        now = int(time.time()*1000)
        self.previews = {k: p for k, p in self.previews.items() if p["expiresAt"] > now}
        require(len(self.previews) < 20, "IMPORT_CAPACITY")
        counts = {key: 0 for key in ("courses", "documents", "messages", "records", "cards")}
        for course in workspace["courses"]:
            data = course["data"]
            counts["courses"] += 1
            for key in ("documents", "records", "cards"):
                counts[key] += len(data.get(key, []))
            counts["messages"] += max(len(data.get("messages", [])), sum(len(s.get("messages", [])) for s in data.get("sessions", [])))
        old = self.repo.get_workspace(user_id)
        existing = self.repo.db.one("SELECT hash FROM imports WHERE user_id=? AND hash=?", (user_id, value_hash))
        preview = {"id": str(uuid4()), "hash": value_hash, "counts": counts, "expectedVersion": old["version"] if old else 0, "expiresAt": now+300000, "alreadyImported": bool(existing)}
        self.previews[preview["id"]] = {**preview, "userId": user_id, "workspace": workspace, "raw": copy.deepcopy(raw)}
        return preview

    def apply(self, user_id, args):
        p = self.previews.get(args.get("id"))
        require(p is not None and p["userId"] == user_id, "IMPORT_NOT_FOUND")
        require(p["expiresAt"] > int(time.time()*1000), "IMPORT_EXPIRED")
        require(p["hash"] == args.get("hash"), "IMPORT_CHANGED")
        with self.repo.db.transaction():
            old = self.repo.db.one("SELECT * FROM imports WHERE user_id=? AND hash=?", (user_id, p["hash"]))
            if old:
                return {"alreadyImported": True, "version": old["workspace_version"], "counts": p["counts"]}
            previous = self.repo.get_workspace(user_id)
            saved = self.repo.save_workspace(user_id, p["workspace"], p["expectedVersion"])
            self.repo.db.execute("INSERT INTO imports VALUES(?,?,?,?,?)", (user_id, p["hash"], dumps({"raw": p["raw"], "workspace": p["workspace"], "previous": previous}), saved["version"], utc_now()))
            return {"version": saved["version"], "counts": p["counts"], "backupId": p["hash"]}

    def backup(self, user_id, backup_id):
        row = self.repo.db.one("SELECT backup FROM imports WHERE user_id=? AND hash=?", (user_id, backup_id))
        require(row is not None, "IMPORT_NOT_FOUND")
        return json.loads(row["backup"])
