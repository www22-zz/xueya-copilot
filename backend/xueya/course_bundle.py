"""Shared, offline validation and review planning for a bundled course."""
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .visual_review import IMAGE_REVIEW_KINDS, ppt_images, supplement_text


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


def pending_visual_reviews(pack, rows, artifact_loader):
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
                artifact = artifact_loader()
            part = next(p for p in artifact['pages'] if p['number'] == row['page'])
            ensure(artifact['text'][part['start']:part['end']].startswith(row['text']), 'COURSE_BUNDLE_REVIEW_CONFLICT')
        else:
            ensure(not page['characters'] and not page['imageReviews'], 'COURSE_BUNDLE_REVIEW_CONFLICT')
            pending.append(row)
    return pending


def review_batch(pending):
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
    return batch
