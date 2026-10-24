"""Per-account practice storage: op log, derived status and per-question notes.

Rows live under user_id 'practice:<accountId>' so Repository.project() on the shared
'local-user' workspace never touches them. course_id is fixed: progress is cross-course.
Status is always re-derived from the ordered event log, so multi-browser merges stay
deterministic and a replayed op never double-counts (PRD 10.5).
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from .common import Scope, dumps, require, utc_now
from . import practice_rules as rules

COURSE_ID = 'practice-global'
COURSE_NAME = '练习'
MAX_OPS = 200
MAX_OP_BYTES = 1_000_000
MAX_NOTE_BYTES = 200_000
ACTIONS = ('answer', 'correct', 'master', 'conquer', 'fuzzy', 'mark-wrong', 'reset', 'note-save')


class PracticeState:
    def __init__(self, platform):
        self.platform = platform
        self.repo = platform.repo

    def scope(self, account_id: str) -> Scope:
        require(isinstance(account_id, str) and 1 <= len(account_id) <= 64, 'INVALID_ACCOUNT')
        user_id = 'practice:' + account_id
        scope = Scope(user_id=user_id, course_id=COURSE_ID)
        if self.platform.db.one('SELECT id FROM courses WHERE user_id=? AND id=?', (user_id, COURSE_ID)) is None:
            self.repo.ensure_course(user_id, {'id': COURSE_ID, 'name': COURSE_NAME})
        return scope

    def _key(self, account_id, name):
        return 'practice:' + name + ':' + account_id

    def sequence(self, account_id):
        row = self.platform.db.one('SELECT value FROM meta WHERE key=?', (self._key(account_id, 'seq'),))
        return int(json.loads(row['value'])) if row else 0

    def _bump_sequence(self, account_id):
        key = self._key(account_id, 'seq')
        value = self.sequence(account_id) + 1
        self.platform.db.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                                 (key, dumps(value)))
        return value

    def events(self, scope):
        rows = self.repo.all(scope, 'event')
        rows.sort(key=lambda r: (r.get('serverSeq', 0), r['id']))
        return rows

    def derive(self, account_id):
        """Rebuild statuses and notes from the ordered event log. Never patch fields one by one."""
        scope = self.scope(account_id)
        progress, notes = {}, {}
        events = self.events(scope)
        for event in events:
            action, question_id = event.get('action'), event.get('questionId')
            if action == 'note-save':
                previous_revision = notes.get(question_id, {}).get('revision', 0)
                notes[question_id] = rules.merge_note(notes.get(question_id), event.get('text', ''),
                                                      event.get('baseRevision'), at=event.get('at') or '',
                                                      device=event.get('deviceTag') or '')
                if event.get('resolve') and event.get('baseRevision') == previous_revision:
                    notes[question_id]['conflicts'] = []
                notes[question_id].pop('merged', None)
                continue
        ordered = sorted((event for event in events if event.get('action') != 'note-save'),
                         key=lambda event: (event.get('effectiveAt') or event.get('at') or '', event.get('serverSeq', 0), event['id']))
        for event in ordered:
            question_id = event['questionId']
            question = {'id': question_id, 'type': event.get('questionType')}
            try:
                self._apply(progress, question, event['action'],
                            {**(event.get('payload') or {}), 'at': event.get('effectiveAt') or event.get('at')},
                            concurrent=bool(event.get('clientTs')))
            except ValueError:
                continue
        return {'serverSeq': self.sequence(account_id), 'statuses': progress, 'notes': notes}

    @staticmethod
    def _apply(progress, question, action, payload, *, concurrent=False):
        # A lawful offline state choice remains valid when another browser changed the state meanwhile.
        if concurrent and action in ('master', 'conquer', 'fuzzy', 'reset'):
            row = rules.entry(progress, question['id'])
            row['status'] = 'wrong' if action == 'conquer' else 'mastered' if action == 'reset' else 'pending'
        return rules.apply(progress, question, action, payload)

    def accept(self, account_id, ops, *, device=''):
        require(isinstance(ops, list) and 1 <= len(ops) <= MAX_OPS, 'INVALID_OPS')
        scope = self.scope(account_id)
        accepted, duplicates, rejected = [], [], []
        with self.platform.db.transaction():
            snapshot = self.derive(account_id)
            progress, notes = snapshot['statuses'], snapshot['notes']
            for op in ops:
                try:
                    outcome = self._accept_one(account_id, scope, op, device, progress, notes)
                except ValueError as error:
                    rejected.append({'opId': (op or {}).get('opId') if isinstance(op, dict) else None, 'error': str(error)})
                    continue
                if outcome is None:
                    duplicates.append(op.get('opId'))
                else:
                    accepted.append(op.get('opId'))
        return {'accepted': accepted, 'duplicates': duplicates, 'rejected': rejected, **self.derive(account_id)}

    def _accept_one(self, account_id, scope, op, device, progress, notes):
        def guard(condition, code):
            if not condition:
                raise ValueError(code)
        guard(isinstance(op, dict), 'INVALID_OP')
        op_id = op.get('opId')
        guard(isinstance(op_id, str) and 1 <= len(op_id) <= 120, 'INVALID_OP_ID')
        if self.repo.read(scope, 'event', op_id):
            return None
        action = op.get('kind')
        guard(action in ACTIONS, 'INVALID_OP_KIND')
        question_id = op.get('questionId')
        guard(isinstance(question_id, str) and question_id, 'INVALID_QUESTION_ID')
        payload = op.get('payload') if isinstance(op.get('payload'), dict) else {}
        guard(len(dumps(op).encode()) <= MAX_OP_BYTES, 'OP_TOO_LARGE')
        at = utc_now()
        effective_at = at
        if op.get('clientTs'):
            try:
                parsed = datetime.fromisoformat(op['clientTs'].replace('Z', '+00:00'))
                guard(parsed.tzinfo is not None, 'INVALID_CLIENT_TIME')
                guard(parsed.timestamp() <= datetime.now(timezone.utc).timestamp() + 300, 'INVALID_CLIENT_TIME')
                effective_at = parsed.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            except (TypeError, AttributeError, ValueError):
                raise ValueError('INVALID_CLIENT_TIME')
        record = {'effectiveAt': effective_at, 'id': op_id, 'action': action, 'questionId': question_id, 'at': at,
                  'questionType': payload.get('questionType') or op.get('questionType'),
                  'deviceTag': op.get('deviceTag') or device, 'clientTs': op.get('clientTs')}
        if action == 'note-save':
            text = payload.get('text')
            guard(isinstance(text, str) and len(text.encode()) <= MAX_NOTE_BYTES, 'INVALID_NOTE')
            guard(type(payload.get('baseRevision')) is int and payload['baseRevision'] >= 0, 'INVALID_NOTE_REVISION')
            record.update(text=text, baseRevision=payload.get('baseRevision'), resolve=bool(payload.get('resolve')))
            merged = rules.merge_note(notes.get(question_id), text, payload.get('baseRevision'),
                                      at=at, device=record['deviceTag'])
            if payload.get('resolve') and payload.get('baseRevision') == notes.get(question_id, {}).get('revision', 0):
                merged['conflicts'] = []
            merged.pop('merged', None)
        else:
            if action == 'correct' and payload.get('attemptId'):
                guard(isinstance(payload['attemptId'], str) and len(payload['attemptId']) <= 120,
                      'INVALID_CORRECTION_ATTEMPT')
                target = self.repo.read(scope, 'event', payload['attemptId'])
                target = target['value'] if target else None
                guard(bool(target) and target.get('questionId') == question_id
                      and target.get('action') == 'answer' and target.get('questionType') == 'fill'
                      and (target.get('payload') or {}).get('result') == 'wrong', 'INVALID_CORRECTION_ATTEMPT')
            record['payload'] = payload
            question = {'id': question_id, 'type': record['questionType']}
            try:
                self._apply(progress, question, action, {**payload, 'at': effective_at}, concurrent=bool(op.get('clientTs')))
            except ValueError as error:
                raise ValueError(str(error))
            merged = None
        record['serverSeq'] = self._bump_sequence(account_id)
        self.repo.put(scope, 'event', op_id, record)
        if merged is not None:
            notes[question_id] = merged
        return record

    def state(self, account_id):
        return self.derive(account_id)

    def note(self, account_id, question_id):
        return self.derive(account_id)['notes'].get(question_id)
