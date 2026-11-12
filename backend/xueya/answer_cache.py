"""Evidence-versioned local answer cache for repeated questions.

Only successful, source-backed answers are stored, keyed by the authenticated
scope, the normalized question, the evidence snapshot and the model/prompt
version. A hit is used only after the caller re-checks that the evidence is
still current; any mismatch (or an expired entry) falls back to generation.
"""
from __future__ import annotations

import json
import time

from backend.core import fingerprint

PROMPT_VERSION = 'answer-cache-v1'
KEEP = ('answer', 'sources', 'sourceDetails', 'knowledgePoints', 'model', 'engine', 'verification')


class AnswerCache:
    def __init__(self, platform, ttl):
        self.platform = platform
        self.ttl = int(ttl or 0)

    @property
    def enabled(self):
        return bool(self.platform is not None and self.ttl > 0)

    def key(self, scope, question, mode, evidence_version, model, history=''):
        return 'answer-cache:'+fingerprint([scope.user_id, scope.course_id, PROMPT_VERSION,
                                            question, mode, evidence_version, model, history])

    def get(self, scope, question, mode, evidence_version, model, history=''):
        if not self.enabled:
            return None
        row = self.platform.db.one('SELECT value FROM meta WHERE key=?',
                                   (self.key(scope, question, mode, evidence_version, model, history),))
        if not row:
            return None
        try:
            stored = json.loads(row['value'])
        except (ValueError, TypeError):
            return None
        if not isinstance(stored, dict) or not isinstance(stored.get('value'), dict):
            return None
        if self.ttl and time.time()-stored.get('at', 0) > self.ttl:
            return None
        return stored['value']

    def put(self, scope, question, mode, evidence_version, model, result, history=''):
        if not self.enabled or not isinstance(result, dict):
            return
        if result.get('answerStatus') == 'unavailable' or not result.get('answer'):
            return
        if not result.get('sources'):
            return
        value = {key: result[key] for key in KEEP if key in result}
        self.platform.db.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                                 (self.key(scope, question, mode, evidence_version, model, history),
                                  json.dumps({'at': time.time(), 'value': value}, ensure_ascii=False)))
