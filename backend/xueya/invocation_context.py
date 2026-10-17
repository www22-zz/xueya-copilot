"""Associations for the existing ledger; no second usage or billing store."""
from contextvars import ContextVar
from .common import digest, dumps

active_job = ContextVar('xueya_active_job', default=None)


def configuration_identity(base_url, model, key):
    return digest({'base': base_url, 'model': model, 'credential': key}, canonical=True)


def attach_invocation(platform, scope, invocation_id, *, capability, model, base_url, key):
    context = active_job.get()
    if context and (context['userId'] != scope.user_id or context['courseId'] != scope.course_id):
        context = None
    metadata = {'capability': capability, 'model': model,
                'configurationIdentity': configuration_identity(base_url, model, key),
                'jobId': context['id'] if context else None}
    platform.db.execute('INSERT INTO meta(key,value) VALUES(?,?)',
                        ('invocation-context:'+invocation_id, dumps(metadata)))
