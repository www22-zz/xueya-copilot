"""Assisted image transcriptions over the existing document lifecycle.

This imports a review made outside the application; it is not a model endpoint.
No local inference, provider request, new database or automatic paid retry.
"""
import copy
import hashlib
import io
import posixpath
import time
import zipfile

from .common import digest, identifier, require, utc_now
from .rag_parse import A, assemble, safe_xml, text_blocks, quality

P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
IMAGE_REVIEW_KINDS = frozenset(('transcription', 'diagram', 'illustration', 'administrative', 'decorative', 'unreadable'))


def reviewed_images(page):
    """Include legacy empty-page transcriptions without re-appending their images."""
    return set(page.get('visualReview', {}).get('imageHashes', [])) | {r['imageHash'] for r in page.get('imageReviews', [])}


def supplement_text(reviews):
    # Non-course screenshots, decoration and unreadable content remain audit
    # metadata. They must not become evidence that overwhelms course retrieval.
    parts = []
    for row in reviews:
        if row['kind'] not in ('transcription', 'diagram'):
            continue
        label = '辅助视觉补录，未独立人审' + ('；部分转写，见限制说明' if row['partial'] else '')
        parts.append('【'+label+'；图片 '+row['imageHash'][:12]+'】\n'+row['text'])
    return '\n\n'.join(parts)


def ppt_images(buffer):
    """Map embedded image bytes to real presentation pages, including grouped shapes."""
    with zipfile.ZipFile(io.BytesIO(buffer)) as archive:
        entries = archive.infolist()
        require(len(entries) <= 10000 and sum(e.file_size for e in entries) <= 64_000_000, 'DOCUMENT_ARCHIVE_TOO_LARGE')
        names = {e.filename for e in entries}
        require(len(names) == len(entries), 'INVALID_DOCUMENT_ARCHIVE')
        rels = {r.get('Id'): r.get('Target') for r in safe_xml(archive, 'ppt/_rels/presentation.xml.rels') if r.get('TargetMode') != 'External'}
        pages, images = {}, {}
        for number, slide in enumerate(safe_xml(archive, 'ppt/presentation.xml').findall('.//'+P+'sldId'), 1):
            target = rels.get(slide.get(R+'id'), '')
            require(isinstance(target, str), 'INVALID_SLIDE_TARGET')
            part = target.lstrip('/') if target.startswith('/') else posixpath.normpath('ppt/'+target)
            require(part.startswith('ppt/slides/') and part.endswith('.xml') and part in names, 'INVALID_SLIDE_TARGET')
            root = safe_xml(archive, part)
            relation_file = posixpath.dirname(part)+'/_rels/'+posixpath.basename(part)+'.rels'
            image_rels = {r.get('Id'): r.get('Target') for r in safe_xml(archive, relation_file)
                          if r.get('Type', '').endswith('/image') and r.get('TargetMode') != 'External'} if relation_file in names else {}
            page_images = []
            for blip in root.iter(A+'blip'):
                target = image_rels.get(blip.get(R+'embed'))
                if target is None:
                    continue
                path = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.dirname(part)+'/'+target)
                require(path.startswith('ppt/media/') and path in names, 'INVALID_IMAGE_TARGET')
                info = archive.getinfo(path)
                require(info.file_size <= 10_485_760, 'IMAGE_TOO_LARGE')
                content = archive.read(path)
                sha = hashlib.sha256(content).hexdigest()
                images[sha] = {'content': content, 'extension': path.rsplit('.', 1)[-1].lower()}
                page_images.append(sha)
            pages[number] = sorted(set(page_images))
        return pages, images


class VisualReview:
    def __init__(self, platform, rag):
        self.p, self.rag = platform, rag
        platform.jobs.register('rag-visual-apply', self.execute)

    def pack(self, scope, document_id):
        doc = self.rag.document(scope, document_id, active=True)
        require(doc['kind'] == 'pptx', 'VISUAL_PPTX_REQUIRED')
        artifact = self.rag.artifact(scope, doc)
        page_images, _ = ppt_images(self.p.files.read(doc['fileHash']))
        return {'documentId': doc['id'], 'name': doc['name'], 'version': doc['version'], 'fileHash': doc['fileHash'],
                'contentRevision': doc['contentRevision'], 'pages': [
                    {'page': page['number'], 'characters': page['end']-page['start'], 'needsOcr': page.get('needsOcr', False),
                     'review': page.get('visualReview'), 'imageReviews': page.get('imageReviews', []),
                     'reviewedImageHashes': sorted(reviewed_images(page)),
                     'imageHashes': page_images.get(page['number'], [])}
                    for page in artifact['pages']],
                'scope': 'empty-page-transcription-or-append-only-image-supplement', 'automaticOcr': False, 'pdfOcrConfigured': bool(self.rag.ocr),
                'note': '本接口导入已核对的图片转写，不调用聊天助手或任何模型 API。'}

    def preview(self, scope, value):
        pack = self.pack(scope, value.get('documentId'))
        require(type(value.get('version')) is int and pack['version'] == value['version'] and pack['fileHash'] == value.get('fileHash'), 'VERSION_CONFLICT')
        reviewer = value.get('reviewer')
        require(reviewer in ('assistant-in-session', 'human'), 'INVALID_VISUAL_REVIEWER')
        rows = value.get('pages')
        require(isinstance(rows, list) and 0 < len(rows) <= 64, 'INVALID_VISUAL_PAGES')
        actual = {p['page']: p for p in pack['pages']}
        seen, checked = set(), []
        for row in rows:
            require(isinstance(row, dict) and not set(row)-{'page', 'kind', 'text', 'imageHashes', 'imageReviews'}, 'INVALID_VISUAL_PAGE')
            page = row.get('page')
            require(type(page) is int and page in actual and page not in seen, 'INVALID_VISUAL_PAGE')
            seen.add(page)
            text, kind, hashes = row.get('text', ''), row.get('kind'), row.get('imageHashes')
            if kind == 'supplement':
                require(not text, 'INVALID_VISUAL_TEXT')
                entries = row.get('imageReviews')
                require(isinstance(entries, list) and 0 < len(entries) <= 128, 'INVALID_IMAGE_REVIEWS')
                clean, sha_seen = [], set()
                for entry in entries:
                    require(isinstance(entry, dict) and not set(entry)-{'imageHash', 'kind', 'text', 'partial'}, 'INVALID_IMAGE_REVIEW')
                    sha, label, caption = entry.get('imageHash'), entry.get('kind'), entry.get('text', '')
                    require(isinstance(sha, str) and sha in actual[page]['imageHashes'] and sha not in sha_seen, 'VISUAL_IMAGE_MISMATCH')
                    require(sha not in actual[page]['reviewedImageHashes'], 'VISUAL_IMAGE_ALREADY_REVIEWED')
                    require(isinstance(label, str) and label in IMAGE_REVIEW_KINDS and isinstance(caption, str) and len(caption) <= 12000
                            and caption.strip() and quality(caption) >= .85 and type(entry.get('partial', False)) is bool, 'INVALID_IMAGE_REVIEW')
                    sha_seen.add(sha)
                    clean.append({'imageHash': sha, 'kind': label, 'text': caption.strip(), 'partial': entry.get('partial', False)})
                require(isinstance(hashes, list) and all(isinstance(h, str) for h in hashes)
                        and len(hashes) == len(sha_seen) and set(hashes) == sha_seen, 'VISUAL_IMAGE_MISMATCH')
                require(sum(len(e['text']) for e in clean) <= 20000, 'VISUAL_TEXT_TOO_LARGE')
                checked.append({'page': page, 'kind': kind, 'text': supplement_text(clean), 'imageHashes': sorted(hashes), 'imageReviews': clean})
                continue
            require(actual[page]['characters'] == 0 and not actual[page]['review'] and not actual[page]['imageReviews'], 'VISUAL_PAGE_NOT_EMPTY')
            require('imageReviews' not in row, 'INVALID_VISUAL_PAGE')
            require(kind in ('transcription', 'blank') and isinstance(text, str) and len(text) <= 20000, 'INVALID_VISUAL_TEXT')
            require(isinstance(hashes, list) and all(isinstance(h, str) for h in hashes)
                    and len(hashes) == len(set(hashes)) and sorted(hashes) == actual[page]['imageHashes'], 'VISUAL_IMAGE_MISMATCH')
            require((kind == 'blank' and not hashes and not text.strip()) or
                    (kind == 'transcription' and bool(hashes) and bool(text.strip()) and quality(text) >= .85), 'INVALID_VISUAL_TEXT')
            checked.append({'page': page, 'kind': kind, 'text': text.strip(), 'imageHashes': sorted(hashes)})
        require(sum(len(p['text']) + sum(len(e['text']) for e in p.get('imageReviews', [])) for p in checked) <= 50000, 'VISUAL_TEXT_TOO_LARGE')
        payload = {'documentId': pack['documentId'], 'documentVersion': pack['version'], 'fileHash': pack['fileHash'],
                   'contentRevision': pack['contentRevision'], 'reviewer': reviewer, 'pages': sorted(checked, key=lambda p: p['page'])}
        key = 'visual-preview-'+digest(payload, canonical=True)[:40]
        prior = self.p.repo.read(scope, 'artifact', key)
        if not prior:
            self.p.repo.put(scope, 'artifact', key, {'kind': 'visual-review-preview', **payload, 'createdAt': utc_now(), 'expiresAt': time.time()+86400}, 0)
        saved = prior['value'] if prior else self.p.repo.read(scope, 'artifact', key)['value']
        return {'previewId': key, **saved, 'expired': saved['expiresAt'] < time.time(),
                'warning': '这是外部提交的视觉转写；来源页码/图片已校验，转写语义没有独立人工审核。'}

    def submit(self, scope, value):
        require(value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
        key = identifier(value.get('previewId'))
        row = self.p.repo.read(scope, 'artifact', key)
        require(row and row['value'].get('kind') == 'visual-review-preview', 'VISUAL_PREVIEW_NOT_FOUND')
        # Acknowledgement lost after submission must return the original job even
        # after that job has published the next document version.
        prior = self.p.db.one("SELECT id FROM jobs WHERE user_id=? AND course_id=? AND type='rag-visual-apply' AND idempotency_key=?", (scope.user_id, scope.course_id, key))
        if prior:
            return self.p.jobs.get(prior['id'], scope.user_id)
        self.current(scope, row['value'])
        require(row['value']['expiresAt'] >= time.time(), 'VISUAL_PREVIEW_EXPIRED')
        with self.p.db.transaction():
            job = self.p.jobs.submit(scope.user_id, {'type': 'rag-visual-apply', 'courseId': scope.course_id,
                        'resource': 'cpu', 'maxAttempts': 1, 'idempotencyKey': key, 'input': {'previewId': key}})
            self.p.repo.put(scope, 'artifact', key, {**row['value'], 'confirmedJobId': job['id']}, row['version'])
        return job

    def current(self, scope, preview):
        doc = self.rag.document(scope, preview['documentId'], active=True)
        require(doc['version'] == preview['documentVersion'] and doc['fileHash'] == preview['fileHash']
                and doc.get('contentRevision') == preview['contentRevision'], 'VERSION_CONFLICT')
        return doc

    async def execute(self, scope, args, *, progress, checkpoint, commit):
        require(isinstance(args, dict) and set(args) == {'previewId'}, 'INVALID_JOB')
        row = self.p.repo.read(scope, 'artifact', identifier(args['previewId']))
        require(row and row['value'].get('kind') == 'visual-review-preview', 'VISUAL_PREVIEW_NOT_FOUND')
        preview = row['value']
        job = self.p.jobs.get(preview.get('confirmedJobId', ''), scope.user_id)
        require(job and job['courseId'] == scope.course_id and job['type'] == 'rag-visual-apply'
                and job['status'] == 'running' and job['resource'] == 'cpu', 'VISUAL_CONFIRMATION_REQUIRED')
        require(preview['expiresAt'] >= time.time(), 'VISUAL_PREVIEW_EXPIRED')
        doc = self.current(scope, preview)
        old = self.rag.artifact(scope, doc)
        page_images, _ = ppt_images(self.p.files.read(doc['fileHash']))
        reviews = {p['page']: p for p in preview['pages']}
        method = 'assisted-visual-transcription' if preview['reviewer'] == 'assistant-in-session' else 'human-visual-transcription'
        pages = []
        progress({'percent': 20, 'label': '核对图片与原始资料版本'})
        for original in old['pages']:
            page = copy.deepcopy(original)
            number = page['number']
            replacement = reviews.get(number)
            text = old['text'][page['start']:page['end']]
            # assemble consumes page-local block offsets, unlike stored artifacts.
            blocks = [{**b, 'start': b['start']-page['start'], 'end': b['end']-page['start']} for b in old['blocks'] if b['page'] == number]
            if replacement:
                if replacement['kind'] == 'supplement':
                    hashes = set(replacement['imageHashes'])
                    require(hashes <= set(page_images[number]) and not hashes & reviewed_images(page), 'VISUAL_IMAGE_MISMATCH')
                    extra = supplement_text(replacement['imageReviews'])
                    if extra:
                        offset = len(text) + (2 if text else 0)
                        text += ('\n\n' if text else '') + extra
                        blocks += [{**b, 'start': b['start']+offset, 'end': b['end']+offset}
                                   for b in text_blocks(extra, number, method=method)]
                    page['imageReviews'] = page.get('imageReviews', []) + [
                        {**entry, 'reviewer': preview['reviewer'], 'method': method, 'sourceFileHash': doc['fileHash'],
                         'reviewedAt': utc_now(), 'independentSemanticReview': False}
                        for entry in replacement['imageReviews']]
                    if extra:
                        page['needsOcr'] = False
                    pages.append({**page, 'text': text, 'blocks': blocks})
                    continue
                require(not text and not page.get('visualReview') and not page.get('imageReviews') and replacement['imageHashes'] == page_images[number], 'VISUAL_IMAGE_MISMATCH')
                text = replacement['text']
                page['method'] = method if replacement['kind'] == 'transcription' else 'confirmed-empty-slide'
                page['needsOcr'] = False
                page['visualReview'] = {'kind': replacement['kind'], 'reviewer': preview['reviewer'], 'method': page['method'],
                    'sourceFileHash': doc['fileHash'], 'imageHashes': replacement['imageHashes'], 'reviewedAt': utc_now(),
                    'independentSemanticReview': False}
                blocks = text_blocks(text, number, method=page['method'])
            pages.append({**page, 'text': text, 'blocks': blocks})
        parsed = assemble(pages, doc['kind'], doc['fileHash'])
        parsed['visualReviewScope'] = 'per-image-status-and-limitations; reviewed-is-not-independent-semantic-certification'
        checkpoint({'documentId': doc['id'], 'pages': sorted(reviews), 'stage': 'visual-review-ready'})
        result = commit(lambda: self.rag._publish(scope, doc, parsed, correction={'type': 'visual-transcription-import', 'previewId': row['id'], 'pages': sorted(reviews)}))
        progress({'percent': 100, 'label': '图片转写已发布，知识库片段已重建'})
        return result
