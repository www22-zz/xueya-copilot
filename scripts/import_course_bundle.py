"""Validate or import a shared PPT course bundle through the existing local host.

No provider calls, database restore, document-ID assumptions or automatic retries.
"""
import argparse
import json
from pathlib import Path
import time

import httpx

from backend.xueya.common import digest
from backend.xueya.course_bundle import ensure, load_bundle, bundle_file, local_url, pending_visual_reviews, review_batch
from .import_knowledge_base import checked


def wait_job(http, job):
    deadline = time.monotonic()+300
    while job['status'] not in ('succeeded', 'failed', 'cancelled', 'unknown') and time.monotonic() < deadline:
        time.sleep(.1)
        job = checked(http.get('/api/platform/jobs/status', params={'id': job['id']}))['job']
    ensure(job['status'] == 'succeeded', 'COURSE_BUNDLE_JOB_'+job['status'].upper()+': '+str(job.get('error') or ''))
    return job


def pending_reviews(http, params, pack, rows):
    return pending_visual_reviews(pack, rows, lambda: checked(http.get('/api/platform/library/read', params=params))['artifact'])


def import_bundle(directory, base_url, *, existing_course_id=None):
    manifest, reviewer, files = load_bundle(directory)
    report = {'name': manifest['name'], 'providerRequests': 0, 'documents': []}
    with httpx.Client(base_url=local_url(base_url), trust_env=False, follow_redirects=False, timeout=90) as http:
        bootstrap = checked(http.get('/api/platform/bootstrap'))
        http.headers['X-Xueya-Token'] = bootstrap['token']
        course_id = existing_course_id
        if course_id:
            ensure(any(c['id'] == course_id and not c['archived'] for c in bootstrap['courses']), 'COURSE_NOT_FOUND')
        else:
            course_id = checked(http.post('/api/platform/knowledge/create', json={'name': manifest['name'],
                'description': '本机课程课件知识库；保留原件、页码、章节和引用版本。',
                'idempotencyKey': 'local-course-'+digest(manifest['name'])[:40]}))['base']['id']
        report['courseId'] = course_id
        for document, path, rows in files:
            chapter = document.get('chapter', '')
            signature = {'name': document['name'], 'sha256': document['sha256'], 'chapter': chapter}
            upload = checked(http.post('/api/platform/knowledge/upload', params={'courseId': course_id, 'name': document['name'], 'chapter': chapter},
                headers={'Idempotency-Key': 'import-'+digest(signature)[:48]}, content=path.read_bytes()))
            wait_job(http, upload['job'])
            params = {'courseId': course_id, 'documentId': upload['documentId']}
            jobs = []
            while True:
                pack = checked(http.get('/api/platform/knowledge/visual-pack', params=params))['pack']
                ensure(pack['fileHash'] == document['sha256'], 'BUNDLE_DOCUMENT_MISMATCH')
                pending = pending_reviews(http, params, pack, rows)
                if not pending:
                    break
                batch = review_batch(pending)
                preview = checked(http.post('/api/platform/knowledge/visual-preview', json={**params, 'version': pack['version'],
                    'fileHash': pack['fileHash'], 'reviewer': reviewer, 'pages': batch}))['preview']
                job = checked(http.post('/api/platform/knowledge/visual-apply', json={'courseId': course_id, 'previewId': preview['previewId'], 'confirmed': True}))['job']
                jobs.append(wait_job(http, job)['id'])
            read = checked(http.get('/api/platform/library/read', params=params))
            sources = len(read['document']['chunks'])
            ensure(sources == document['expectedSources'], 'BUNDLE_SOURCE_COUNT_DIFFERS')
            report['documents'].append({'name': document['name'], 'documentId': upload['documentId'], 'sources': sources, 'newReviewJobs': len(jobs)})
        report['summary'] = checked(http.get('/api/platform/knowledge/catalog', params={'courseId': course_id}))['summary']
    report['status'] = 'passed'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=Path('materials/data-structures-algorithms'))
    parser.add_argument('--base-url', default='http://127.0.0.1:4173')
    parser.add_argument('--existing-course-id')
    parser.add_argument('--apply', action='store_true', help='Import originals and explicitly adopt bundled visual reviews')
    parser.add_argument('--output', type=Path, default=Path('test-results/course-bundle/import.json'))
    args = parser.parse_args()
    if not args.apply:
        manifest, _, files = load_bundle(args.bundle)
        print(json.dumps({'status': 'validated-only', 'documents': len(files), 'name': manifest['name'], 'providerRequests': 0}, ensure_ascii=False))
        return
    report = import_bundle(args.bundle, args.base_url, existing_course_id=args.existing_course_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'courseId', 'summary', 'providerRequests')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
