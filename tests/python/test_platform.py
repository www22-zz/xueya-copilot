import asyncio
import copy
import hashlib
import json
import shutil
import sqlite3
import time
from contextlib import closing
from pathlib import Path
import pytest
from backend.xueya.actions import ActionAuthority
from backend.xueya.backup import create_backup, restore_backup
from backend.xueya.common import AppError, Scope, dumps
from backend.xueya.database import Database
from backend.xueya.learning import build_plan, memory_cards, wrong_questions
from backend.xueya.platform import Platform


def test_node_v3_snapshot_and_confirmations_are_compatible(tmp_path):
    source = Path(__file__).parents[1] / "fixtures/legacy-node-v3"
    data_dir = tmp_path / "legacy-copy"
    shutil.copytree(source, data_dir)
    expected = json.loads((data_dir / "expected.json").read_text(encoding="utf-8"))
    p = Platform(data_dir)
    try:
        # Freeze the authority clock inside the original five-minute approval window.
        p.authority.now = lambda: expected["pending"]["expiresAt"]-1000
        scope = p.scope()
        ws = p.repo.get_workspace(p.user_id)
        data = ws["data"]["courses"][0]["data"]
        # PRD 14.1: the old 作答记录 / 知识卡片 are cleared once; 问答记录 must survive untouched.
        assert "records" not in data and "cards" not in data
        assert len(data["messages"]) == 40
        assert p.db.one("PRAGMA user_version")["user_version"] == 3
        assert p.authority.apply(scope, expected["applied"]["actionId"]) == expected["receipt"]
        preview = p.authority.preview(scope, expected["pending"]["actionId"])
        assert preview["digest"] == expected["pending"]["digest"]
        receipt = p.authority.apply(scope, preview["actionId"])
        assert receipt["version"] == 1
        assert p.db.one("SELECT count(*) n FROM audits")["n"] == 2
        assert p.migration.backup(p.user_id, expected["importHash"])["raw"]["v2"] == "public legacy fixture"
    finally:
        asyncio.run(p.close())


def test_python_learning_rules_match_frozen_node_outputs():
    expected = json.loads((Path(__file__).parents[1] / "fixtures/legacy-node-v3/expected.json").read_text(encoding="utf-8"))
    assert wrong_questions(expected["records"]) == expected["wrong"]
    assert memory_cards(expected["records"], expected["base"]) == expected["memory"]
    assert build_plan("2026-10-20", 45, expected["records"], expected["base"]) == expected["plan"]


def test_repository_cas_pagination_scope_archives_and_rollback(platform):
    r, s = platform.repo, platform.scope()
    r.ensure_course(s.user_id, {"id": "other", "name": "另一门课"})
    other = platform.scope("other")
    for key in ("a", "b"):
        r.put(s, "note", key, {"title": key}, 0)
    first = r.list(s, "note", limit=1)
    assert first["items"][0]["id"] == "a"
    assert r.list(s, "note", first["nextCursor"])["items"][0]["id"] == "b"
    with pytest.raises(AppError, match="INVALID_CURSOR"):
        r.list(other, "note", first["nextCursor"])
    with pytest.raises(AppError, match="VERSION_CONFLICT"):
        r.put(s, "note", "a", {}, 0)
    with pytest.raises(RuntimeError):
        with platform.db.transaction():
            r.put(s, "note", "rollback", {})
            raise RuntimeError()
    assert r.read(s, "note", "rollback") is None
    assert platform.db.one("SELECT count(*) n FROM revisions WHERE id='rollback'")["n"] == 0
    r.ensure_course(s.user_id, {"id": "other", "name": "另一门课", "archived": True})
    assert r.all(other, "note") == []
    with pytest.raises(AppError, match="COURSE_ARCHIVED"):
        r.put(other, "note", "forbidden", {})


def test_migration_preserves_unbounded_history_and_raw_backup(platform, workspace):
    workspace["courses"][0]["data"]["records"] = [{"questionId": "q1", "correct": True} for _ in range(400)]
    p = platform.migration.preview(platform.user_id, {"workspace": workspace, "raw": {"v2": "literal bytes"}})
    assert p["counts"]["messages"] == 40 and p["counts"]["records"] == 400
    applied = platform.migration.apply(platform.user_id, p)
    assert platform.migration.apply(platform.user_id, p)["alreadyImported"]
    assert platform.migration.backup(platform.user_id, applied["backupId"])["raw"]["v2"] == "literal bytes"
    with pytest.raises(AppError, match="VERSION_CONFLICT"):
        platform.repo.save_workspace(platform.user_id, workspace, 0)


def prepare(p, kind="note", entity_id="note-1", after=None):
    return p.authority.prepare(p.scope(), {"kind": kind, "entityId": entity_id, "expectedVersion": 0, "after": after or {"title": "重点", "content": "原文内容", "sourceIds": []}})


def test_confirmation_atomic_idempotent_and_cas_fences_old_browser(platform, workspace):
    p = platform
    p.repo.save_workspace(p.user_id, workspace, 0)
    preview = prepare(p)
    with pytest.raises(AppError, match="ACTION_CONFIRMATION_REQUIRED"):
        p.authority.apply(p.scope(), preview["actionId"])
    assert p.repo.all(p.scope(), "note") == []
    p.authority.confirm(p.scope(), preview)
    receipt = p.authority.apply(p.scope(), preview["actionId"])
    assert p.authority.apply(p.scope(), preview["actionId"]) == receipt
    assert p.db.one("SELECT count(*) n FROM audits")["n"] == 1
    assert p.repo.get_workspace(p.user_id)["data"]["courses"][0]["data"]["cards"][0]["text"] == "原文内容"
    with pytest.raises(AppError, match="VERSION_CONFLICT"):
        p.repo.save_workspace(p.user_id, workspace, 1)


@pytest.mark.parametrize("kind,after", [("question", {"prompt": "问题", "answer": "答案", "sourceIds": ["source-1"]}), ("plan", {"title": "计划", "days": [{"date": "2026-10-20", "tasks": [{"title": "复习", "minutes": 30}]}]})])
def test_question_and_plan_share_confirmation_pipeline(platform, workspace, kind, after):
    p = platform
    p.repo.save_workspace(p.user_id, workspace)
    preview = prepare(p, kind, "item-1", after)
    p.authority.confirm(p.scope(), preview)
    assert p.authority.apply(p.scope(), preview["actionId"])["version"] == 1
    data = p.repo.get_workspace(p.user_id)["data"]["courses"][0]["data"]
    assert data["bank"] if kind == "question" else data["plan"][0]["tasks"][0]["minutes"] == 30


def test_changed_source_expiry_cancel_scope_and_uncertainty(platform, workspace):
    p = platform
    p.repo.save_workspace(p.user_id, workspace)
    preview = prepare(p, after={"title": "引用", "content": "原文内容", "sourceIds": ["source-1"]})
    p.authority.confirm(p.scope(), preview)
    old = p.repo.read(p.scope(), "source", "source-1")
    p.repo.put(p.scope(), "source", "source-1", {**old["value"], "quote": "新的原文"}, old["version"])
    with pytest.raises(AppError, match="SOURCE_VERSION_CONFLICT"):
        p.authority.apply(p.scope(), preview["actionId"])
    assert p.authority.get(p.scope(), preview["actionId"])["state"] == "uncertain"
    assert p.db.one("SELECT count(*) n FROM audits")["n"] == 0
    with pytest.raises(AppError, match="ACTION_NOT_PENDING"):
        p.authority.apply(p.scope(), preview["actionId"])
    cancelled = prepare(p, entity_id="cancel")
    p.authority.cancel(p.scope(), cancelled["actionId"])
    with pytest.raises(AppError, match="ACTION_NOT_PENDING"):
        p.authority.confirm(p.scope(), cancelled)
    expired = prepare(p, entity_id="expired")
    p.authority.now = lambda: expired["expiresAt"]+1
    with pytest.raises(AppError, match="ACTION_EXPIRED"):
        p.authority.confirm(p.scope(), expired)
    with pytest.raises(AppError, match="ACTION_NOT_FOUND"):
        p.authority.preview(Scope(user_id="another-user", course_id="course-default"), expired["actionId"])


def test_confirmation_restart_recovers_receipt_without_replaying(platform):
    p = platform
    preview = prepare(p)
    recovered = ActionAuthority(p.repo)
    assert recovered.preview(p.scope(), preview["actionId"])["digest"] == preview["digest"]
    recovered.confirm(p.scope(), preview)
    receipt = recovered.apply(p.scope(), preview["actionId"])
    action = recovered.get(p.scope(), preview["actionId"])
    action["state"] = "executing"
    action.pop("receipt")
    recovered.store(action)
    again = ActionAuthority(p.repo)
    assert again.apply(p.scope(), preview["actionId"]) == receipt
    assert p.db.one("SELECT count(*) n FROM audits")["n"] == 1


def test_backup_restore_files_and_checksum(platform, workspace, tmp_path):
    p = platform
    p.repo.save_workspace(p.user_id, workspace)
    original = p.files.put(b"recoverable original")
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    create_backup(p.data_dir, backup)
    restore_backup(backup, restored)
    other = Platform(restored, recover=False)
    try:
        assert other.files.read(original["hash"]) == b"recoverable original"
        assert len(other.repo.get_workspace(p.user_id)["data"]["courses"][0]["data"]["messages"]) == 40
    finally:
        asyncio.run(other.close())
    with pytest.raises(AppError, match="RESTORE_REQUIRES_NEW_DIRECTORY"):
        restore_backup(backup, restored)
    with (backup / "workspace.sqlite").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(AppError, match="BACKUP_CHECKSUM_MISMATCH"):
        restore_backup(backup, tmp_path / "bad")
    with pytest.raises(AppError, match="INVALID_FILE_HASH"):
        p.files.read("../../.env")


def test_future_database_is_rejected_and_not_modified(tmp_path):
    target = tmp_path / "future.sqlite"
    with closing(sqlite3.connect(target)) as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(AppError, match="DATABASE_NEWER_THAN_APP"):
        Database(target)
    with closing(sqlite3.connect(target)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 999


def test_durable_jobs_retries_cancel_leases_idempotency_and_api_unknown(platform):
    p = platform

    async def run():
        calls = 0

        async def cpu(scope, args, **ctx):
            nonlocal calls
            calls += 1
            ctx["checkpoint"]({"phase": calls})
            if calls == 1:
                raise AppError("RETRYABLE")
            return {"ok": True}

        async def paid(scope, args, **ctx):
            raise AppError("RESULT_UNKNOWN")

        async def wait(job):
            for _ in range(200):
                await p.jobs.tick()
                state = p.jobs.get(job["id"], p.user_id)
                if state["status"] in ("succeeded", "failed", "cancelled", "unknown"):
                    return state
                await asyncio.sleep(.02)
            pytest.fail("job did not finish")
        p.jobs.stopped = False
        p.jobs.register("test-cpu", cpu)
        p.jobs.register("test-paid", paid)
        args = {"type": "test-cpu", "courseId": "course-default", "idempotencyKey": "cpu"}
        job = p.jobs.submit(p.user_id, args)
        assert p.jobs.submit(p.user_id, args)["id"] == job["id"]
        with pytest.raises(AppError, match="IDEMPOTENCY_CONFLICT"):
            p.jobs.submit(p.user_id, {**args, "input": {"different": True}})
        assert (await wait(job))["status"] == "succeeded" and calls == 2
        paid_job = p.jobs.submit(p.user_id, {"type": "test-paid", "courseId": "course-default", "idempotencyKey": "api", "resource": "api"})
        assert (await wait(paid_job))["status"] == "unknown"
        with pytest.raises(AppError, match="JOB_NOT_RETRYABLE"):
            p.jobs.retry(paid_job["id"], p.user_id)
        stale = p.jobs.submit(p.user_id, {**args, "idempotencyKey": "stale"})
        p.db.execute("UPDATE jobs SET status='running',lease_owner='dead',lease_until=0,attempts=1 WHERE id=?", (stale["id"],))
        assert p.jobs.recover() == 1
        assert p.jobs.get(stale["id"], p.user_id)["status"] == "queued"
        p.jobs.cancel(stale["id"], p.user_id)
        assert p.jobs.get(stale["id"], p.user_id)["status"] == "cancelled"
        assert p.jobs.events(job["id"], p.user_id)[-1]["status"] == "succeeded"
        ready, blocked = asyncio.Event(), asyncio.Event()

        async def active(scope, args, **ctx):
            ready.set()
            await blocked.wait()
            return ctx["commit"](lambda: p.repo.put(scope, "note", "forbidden", {}))
        p.jobs.register("test-cancel", active)
        cancel = p.jobs.submit(p.user_id, {"type": "test-cancel", "courseId": "course-default", "idempotencyKey": "cancel"})
        await p.jobs.tick()
        await ready.wait()
        p.jobs.cancel(cancel["id"], p.user_id)
        blocked.set()
        assert (await wait(cancel))["status"] == "cancelled"
        assert p.repo.read(p.scope(), "note", "forbidden") is None
        await p.jobs.stop()
    asyncio.run(run())
