"""First-run offline course preparation over the platform's existing CPU jobs."""
import asyncio
import hashlib
import logging
from contextlib import suppress

from .common import digest, require
from .course_bundle import ensure, load_bundle, pending_visual_reviews, review_batch
from .jobs import TERMINAL

log = logging.getLogger(__name__)
MARKER = 'first-run-course-import-v1'
ACTIVE = frozenset(('preparing', 'running'))


class DemoImport:
    def __init__(self, knowledge, config):
        self.kb, self.p, self.config = knowledge, knowledge.p, config
        self.directory = config.root/'materials/data-structures-algorithms'
        self.task = None
        self.retry_jobs = False

    def status(self):
        row = self.p.repo.read(self.p.scope(), 'artifact', MARKER)
        return row['value'] if row else None

    def save(self, **changes):
        scope = self.p.scope()
        row = self.p.repo.read(scope, 'artifact', MARKER)
        value = {**(row['value'] if row else {}), **changes, 'courseId': scope.course_id}
        self.p.repo.put(scope, 'artifact', MARKER, value, row['version'] if row else 0)
        return value

    def start(self, *, retry=False):
        if not self.config.auto_import_demo or self.p.jobs.stopped:
            return None
        default = next((c for c in self.p.repo.courses(self.p.user_id) if c['id'] == 'course-default'), None)
        if not default or default['archived']:
            return None
        prior = self.status()
        if self.task and not self.task.done():
            return prior
        if retry:
            require(prior and prior['status'] in ('failed', 'interrupted'), 'DEMO_IMPORT_NOT_RETRYABLE')
        elif prior and prior['status'] in ('completed', 'failed'):
            return prior
        elif not prior and self.p.db.one("SELECT 1 FROM entities WHERE user_id=? AND kind='document' LIMIT 1", (self.p.user_id,)):
            return None  # Includes archived/deleted documents: never repopulate a used workspace.
        self.retry_jobs = bool(retry or prior)
        state = self.save(status='preparing', completed=prior.get('completed', 0) if prior else 0,
                          total=prior.get('total', 17) if prior else 17, currentFile='', error=None)
        self.task = asyncio.create_task(self.run(), name='first-run-course-import')
        return state

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    async def wait(self, job):
        if job['status'] in ('failed', 'cancelled') and self.retry_jobs:
            require(job['resource'] == 'cpu' and job['type'] in ('rag-parse', 'rag-visual-apply'), 'PAID_RETRY_FORBIDDEN')
            if job['type'] == 'rag-visual-apply':
                job = self.kb.task(self.p.scope(), {'id': job['id'], 'action': 'retry'})
            else:
                job = self.p.jobs.retry(job['id'], self.p.user_id)
        deadline = asyncio.get_running_loop().time()+300
        while job['status'] not in TERMINAL:
            ensure(asyncio.get_running_loop().time() < deadline, 'DEMO_IMPORT_JOB_TIMEOUT')
            await asyncio.sleep(.1)
            job = self.p.jobs.get(job['id'], self.p.user_id)
        ensure(job['status'] == 'succeeded', 'DEMO_IMPORT_JOB_'+job['status'].upper())
        return job

    async def run(self):
        try:
            # All originals/reviews are checked before any document is written.
            manifest, reviewer, files = await asyncio.to_thread(load_bundle, self.directory)
            fingerprint = hashlib.sha256((self.directory/'manifest.json').read_bytes()).hexdigest()
            state = self.status()
            ensure(not state.get('bundleHash') or state['bundleHash'] == fingerprint, 'DEMO_IMPORT_BUNDLE_CHANGED')
            self.save(status='running', total=len(files), bundleHash=fingerprint)
            scope = self.p.scope()
            for index, (document, path, rows) in enumerate(files):
                self.save(currentFile=document['name'])
                signature = {'name': document['name'], 'sha256': document['sha256'], 'chapter': document.get('chapter', '')}
                raw = await asyncio.to_thread(path.read_bytes)
                upload = self.kb.upload(scope, raw, document['name'], signature['chapter'], 'import-'+digest(signature)[:48])
                await self.wait(upload['job'])
                document_id = upload['documentId']
                while True:
                    pack = self.kb.visual.pack(scope, document_id)
                    ensure(pack['fileHash'] == document['sha256'], 'BUNDLE_DOCUMENT_MISMATCH')
                    def artifact():
                        return self.kb.rag.artifact(scope, self.kb.rag.document(scope, document_id))
                    pending = pending_visual_reviews(pack, rows, artifact)
                    if not pending:
                        break
                    preview = self.kb.visual.preview(scope, {'documentId': document_id, 'version': pack['version'],
                        'fileHash': pack['fileHash'], 'reviewer': reviewer, 'pages': review_batch(pending)})
                    job = self.kb.visual.submit(scope, {'previewId': preview['previewId'], 'confirmed': True})
                    await self.wait(job)
                current = self.kb.rag.document(scope, document_id)
                ensure(len(current['chunks']) == document['expectedSources'], 'BUNDLE_SOURCE_COUNT_DIFFERS')
                self.save(completed=max(self.status().get('completed', 0), index+1))
                await asyncio.sleep(0)
            self.save(status='completed', currentFile='', error=None)
        except asyncio.CancelledError:
            self.save(status='interrupted', currentFile='', error=None)
            raise
        except Exception as error:
            code = getattr(error, 'code', None)
            if not code:
                code = str(error) if isinstance(error, ValueError) and str(error).replace('_', '').isalnum() else 'DEMO_IMPORT_MATERIALS_UNAVAILABLE' if isinstance(error, OSError) else 'DEMO_IMPORT_FAILED'
            self.save(status='failed', error=code[:100])
            log.warning('Demo course import stopped: %s', code[:100])
