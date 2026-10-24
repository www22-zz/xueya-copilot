"""One-time destructive cleanup of the pre-refactor learning data (PRD 14).

Removes 独立笔记 / 章节学习 / 复习计划 / 知识图谱 / AI 出题 data so the new fixed bank
starts from zero, and keeps 账号、课程资料、问答记录 plus whatever those need.

Runs at most once per data directory: the 'cleanup:practice-v1' meta key is the gate.
It clears directly and writes no backup and migrates no old learning records, per PRD 14.3.
Old browser storage is shrunk separately by frontend/js/state/workspace-store.js, which
drops the deleted fields on every load so nothing can write them back.
"""
from __future__ import annotations
import json
from .common import dumps, utc_now

MARKER = 'cleanup:practice-v1'
DELETED_ENTITY_KINDS = ('note', 'question', 'attempt', 'plan', 'concept', 'session')
DELETED_ARTIFACT_KINDS = ('learning-package', 'chapter-summary', 'plan', 'concept-graph', 'note')
DELETED_META_PREFIXES = ('learning:', 'practice-legacy:', 'practice:op:', 'practice:note-draft:')
KEEP_META_PREFIXES = ('local-account-v1', 'account-v2:', 'invocation-context', MARKER)
WORKSPACE_KEEP = frozenset(('documents', 'messages', 'sessions', 'sessionId', 'courseId', 'libraryTags', 'mediaResults'))


def _stripped(data: dict) -> dict:
    return {k: v for k, v in (data or {}).items() if k in WORKSPACE_KEEP}


def cleanup(db, repo, *, dry_run: bool = False) -> dict:
    counts = {'entities': 0, 'artifacts': 0, 'meta': 0, 'workspaces': 0, 'jobs': 0}

    for kind in DELETED_ENTITY_KINDS:
        rows = db.all('SELECT user_id,course_id,id FROM entities WHERE kind=? AND deleted=0', (kind,))
        counts['entities'] += len(rows)
        if not dry_run:
            for row in rows:
                db.execute('UPDATE entities SET deleted=1 WHERE user_id=? AND course_id=? AND kind=? AND id=?',
                           (row['user_id'], row['course_id'], kind, row['id']))

    for row in db.all("SELECT user_id,course_id,id,data FROM entities WHERE kind='artifact' AND deleted=0"):
        try:
            value = json.loads(row['data'])
        except ValueError:
            continue
        if value.get('kind') in DELETED_ARTIFACT_KINDS:
            counts['artifacts'] += 1
            if not dry_run:
                db.execute("UPDATE entities SET deleted=1 WHERE user_id=? AND course_id=? AND kind='artifact' AND id=?",
                           (row['user_id'], row['course_id'], row['id']))

    for row in db.all('SELECT key FROM meta'):
        key = row['key']
        if any(key.startswith(prefix) for prefix in KEEP_META_PREFIXES):
            continue
        if any(key.startswith(prefix) for prefix in DELETED_META_PREFIXES):
            counts['meta'] += 1
            if not dry_run:
                db.execute('DELETE FROM meta WHERE key=?', (key,))

    for row in db.all('SELECT user_id,data FROM workspaces'):
        value = json.loads(row['data'])
        changed = False
        for course in value.get('courses', []):
            cleaned = _stripped(course.get('data'))
            if cleaned != course.get('data'):
                course['data'] = cleaned
                changed = True
        if changed:
            counts['workspaces'] += 1
            if not dry_run:
                db.execute('UPDATE workspaces SET data=? WHERE user_id=?',
                           (json.dumps(value, ensure_ascii=False), row['user_id']))

    rows = db.all("SELECT id FROM jobs WHERE type IN ('learning-chapter','study-session') "
                  "AND status NOT IN ('succeeded','failed','cancelled')")
    counts['jobs'] = len(rows)
    if not dry_run:
        for row in rows:
            db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (row['id'],))
    return counts


def already_done(db) -> bool:
    return db.one('SELECT value FROM meta WHERE key=?', (MARKER,)) is not None


def mark_done(db, counts, *, auto=False) -> None:
    db.execute('INSERT INTO meta(key,value) VALUES(?,?)',
               (MARKER, dumps({'doneAt': utc_now(), 'counts': counts, 'auto': bool(auto)})))
