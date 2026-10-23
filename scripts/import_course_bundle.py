"""Validate or import a shared PPT course bundle through the existing local host.

No provider calls, database restore, document-ID assumptions or automatic retries.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import time
from urllib.parse import urlsplit

import httpx

from backend.xueya.common import digest
from backend.xueya.visual_review import IMAGE_REVIEW_KINDS, ppt_images, supplement_text
from .import_knowledge_base import checked


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def local_url(value):
    target = urlsplit(value)
    ensure(target.scheme == 'http' and target.hostname in ('127.0.0.1', 'localhost', '::1')
           and not target.username and not target.password and not target.query and not target.fragment
           and target.path in ('', '/'), 'LOCAL_HTTP_HOST_REQUIRED')
    return value.rstrip('/')


def bundle_file(root, name):
    ensure(isinstance(name, str) and '\\' not in name, 'INVALID_BUNDLE_PATH')
    relative = PurePosixPath(name)
    ensure(not relative.is_absolute() and bool(relative.parts) and not set(relative.parts) & {'..', '.'}, 'INVALID_BUNDLE_PATH')
    path = root.joinpath(*relative.parts)
    ensure(path.resolve().is_relative_to(root) and path.is_file() and not path.is_symlink(), 'INVALID_BUNDLE_PATH')
    return path


def load_bundle(directory):
    """Preflight every original, review and image location before any host write."""
    root = Path(directory).resolve(strict=True)
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    ensure(manifest.get('schemaVersion') == 1 and isinstance(manifest.get('documents'), list)
           and 0 < len(manifest['documents']) <= 100, 'INVALID_COURSE_BUNDLE')
    ensure(isinstance(manifest.get('name'), str) and 0 < len(manifest['name']) <= 60, 'INVALID_COURSE_BUNDLE')
    ref = manifest['visualReviews']
    review_bytes = bundle_file(root, ref['path']).read_bytes()
    ensure(len(review_bytes) <= 5_000_000 and hashlib.sha256(review_bytes).hexdigest() == ref['sha256'], 'BUNDLE_REVIEW_HASH_MISMATCH')
    reviews = json.loads(review_bytes)
    ensure(reviews.get('schemaVersion') == 1 and reviews.get('reviewer') in ('assistant-in-session', 'human')
           and isinstance(reviews.get('documents'), list), 'INVALID_BUNDLE_REVIEWS')
    by_hash = {d['fileHash']: d for d in reviews['documents']}
    ensure(len(by_hash) == len(reviews['documents']) == len(manifest['documents']), 'BUNDLE_DOCUMENT_MISMATCH')
    files, seen = [], set()
    for document in manifest['documents']:
        path = bundle_file(root, document['path'])
        ensure(path.name == document['name'] and path.suffix.lower() == '.pptx' and not path.name.startswith('~$'), 'INVALID_BUNDLE_ORIGINAL')
        ensure(0 < path.stat().st_size <= 10_485_760 and path.stat().st_size == document['size'], 'BUNDLE_SIZE_MISMATCH')
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        ensure(sha == document['sha256'] and sha not in seen and sha in by_hash, 'BUNDLE_ORIGINAL_HASH_MISMATCH')
        ensure(isinstance(document.get('chapter', ''), str) and len(document.get('chapter', '')) <= 200, 'INVALID_BUNDLE_CHAPTER')
        seen.add(sha)
        images, _ = ppt_images(raw)
        ensure(len(images) == document['pages'], 'BUNDLE_PAGE_MISMATCH')
        review = by_hash[sha]
        ensure(review['name'] == document['name'] and isinstance(review.get('pages'), list), 'BUNDLE_DOCUMENT_MISMATCH')
        seen_pages, seen_images = set(), set()
        for row in review['pages']:
            page, kind, hashes = row.get('page'), row.get('kind'), row.get('imageHashes')
            ensure(type(page) is int and page in images and isinstance(hashes, list) and all(isinstance(h, str) for h in hashes)
                   and len(hashes) == len(set(hashes)) and set(hashes) <= set(images[page]), 'BUNDLE_IMAGE_MISMATCH')
            ensure((page, kind) not in seen_pages, 'DUPLICATE_BUNDLE_REVIEW')
            seen_pages.add((page, kind))
            if kind == 'supplement':
                entries = row.get('imageReviews')
                ensure(isinstance(entries, list) and 0 < len(entries) <= 128 and not row.get('text'), 'INVALID_BUNDLE_REVIEW')
                for entry in entries:
                    ensure(set(entry) == {'imageHash', 'kind', 'text', 'partial'} and isinstance(entry['kind'], str)
                           and entry['kind'] in IMAGE_REVIEW_KINDS and isinstance(entry['text'], str)
                           and 0 < len(entry['text'].strip()) <= 12000 and type(entry['partial']) is bool, 'INVALID_BUNDLE_REVIEW')
                ensure(len(entries) == len(hashes) and {e['imageHash'] for e in entries} == set(hashes), 'BUNDLE_IMAGE_MISMATCH')
                ensure(sum(len(e['text']) for e in entries) <= 20000, 'BUNDLE_REVIEW_TOO_LARGE')
            else:
                text = row.get('text')
                ensure(kind in ('transcription', 'blank') and isinstance(text, str) and len(text) <= 20000, 'INVALID_BUNDLE_REVIEW')
                ensure((kind == 'blank' and not images[page] and not text.strip()) or
                       (kind == 'transcription' and hashes and sorted(hashes) == images[page] and text.strip()), 'INVALID_BUNDLE_REVIEW')
            for sha_image in hashes:
                ensure((page, sha_image) not in seen_images, 'DUPLICATE_BUNDLE_REVIEW')
                seen_images.add((page, sha_image))
        files.append((document, path, review['pages']))
    return manifest, reviews['reviewer'], files


def wait_job(http, job):
    deadline = time.monotonic()+300
    while job['status'] not in ('succeeded', 'failed', 'cancelled', 'unknown') and time.monotonic() < deadline:
        time.sleep(.1)
        job = checked(http.get('/api/platform/jobs/status', params={'id': job['id']}))['job']
    ensure(job['status'] == 'succeeded', 'COURSE_BUNDLE_JOB_'+job['status'].upper()+': '+str(job.get('error') or ''))
    return job


def pending_reviews(http, params, pack, rows):
    actual = {p['page']: p for p in pack['pages']}
    artifact = None
    pending = []
    for row in rows:
        page = actual[row['page']]
        if row['kind'] == 'supplement':
            existing = {e['imageHash']: e for e in page['imageReviews']}
            entries = []
            for entry in row['imageReviews']:
                sha = entry['imageHash']
                if sha in page['reviewedImageHashes']:
                    ensure(sha in existing and all(existing[sha].get(k) == v for k, v in entry.items()), 'COURSE_BUNDLE_REVIEW_CONFLICT')
                else:
                    entries.append(entry)
            if entries:
                pending.append({**row, 'imageReviews': entries, 'imageHashes': sorted(e['imageHash'] for e in entries)})
        elif page['review']:
            prior = page['review']
            ensure(prior['kind'] == row['kind'] and prior['imageHashes'] == row['imageHashes'], 'COURSE_BUNDLE_REVIEW_CONFLICT')
            if artifact is None:
                artifact = checked(http.get('/api/platform/library/read', params=params))['artifact']
            part = next(p for p in artifact['pages'] if p['number'] == row['page'])
            ensure(artifact['text'][part['start']:part['end']].startswith(row['text']), 'COURSE_BUNDLE_REVIEW_CONFLICT')
        else:
            ensure(not page['characters'] and not page['imageReviews'], 'COURSE_BUNDLE_REVIEW_CONFLICT')
            pending.append(row)
    return pending


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
                batch, weight, pages = [], 0, set()
                for row in pending:
                    cost = len(row.get('text', ''))
                    if row['kind'] == 'supplement':
                        cost = len(supplement_text(row['imageReviews'])) + sum(len(e['text']) for e in row['imageReviews'])
                    ensure(cost <= 50000, 'BUNDLE_REVIEW_TOO_LARGE')
                    if batch and (len(batch) >= 64 or weight+cost > 50000 or row['page'] in pages):
                        break
                    batch.append(row)
                    weight += cost
                    pages.add(row['page'])
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
