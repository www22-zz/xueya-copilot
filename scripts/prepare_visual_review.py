"""Export PPT image review packs without calling any OCR/model API.

Optional --render uses installed Windows PowerPoint, opening copies without windows.
The script does not install PowerPoint, OCR models or local inference runtimes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import httpx

from backend.xueya.visual_review import ppt_images
from .import_knowledge_base import checked


def render_copy(source, pages, output):
    # This opt-in is a maintenance tool, not a server accepting arbitrary paths.
    # Export in a bounded child so a stuck Office automation cannot hang the host.
    code = r'''
import sys,json
import pythoncom
import win32com.client
from pathlib import Path
pythoncom.CoInitialize()
app=win32com.client.DispatchEx('PowerPoint.Application')
previous=app.Presentations.Count
presentation=None
try:
 presentation=app.Presentations.Open(str(Path(sys.argv[1]).resolve()),ReadOnly=True,Untitled=False,WithWindow=False)
 for page in json.loads(sys.argv[2]):
  presentation.Slides(page).Export(str(Path(sys.argv[3]).resolve()/('page-'+str(page)+'.png')),'PNG',1600,1200)
finally:
 if presentation is not None:presentation.Close()
 if previous==0 and app.Presentations.Count==0:app.Quit()
 pythoncom.CoUninitialize()
'''
    subprocess.run([sys.executable, '-c', code, str(source), json.dumps(pages), str(output)],
                   timeout=120, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course-id', required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:4173')
    parser.add_argument('--output', type=Path, default=Path('test-results/visual-review/packs'))
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--all-images', action='store_true', help='Include images on pages that already have text; preserve legacy reviews')
    parser.add_argument('--max-pages', type=int, default=64, choices=range(1,65), metavar='1..64', help='Export one bounded batch per document; re-export after publishing')
    args = parser.parse_args()
    from urllib.parse import urlsplit
    url = urlsplit(args.base_url)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost', '::1') or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
        parser.error('Only a local HTTP host is allowed')
    args.output.mkdir(parents=True, exist_ok=True)
    count = 0
    with httpx.Client(base_url=args.base_url, trust_env=False, timeout=60) as http:
        http.headers['X-Xueya-Token'] = checked(http.get('/api/platform/bootstrap'))['token']
        docs = checked(http.get('/api/platform/knowledge/catalog', params={'courseId': args.course_id}))['documents']
        for doc in docs:
            if doc['kind'] != 'pptx' or doc.get('archived') or not doc.get('contentRevision'):
                continue
            pack = checked(http.get('/api/platform/knowledge/visual-pack', params={'courseId': args.course_id, 'documentId': doc['id']}))['pack']
            pages = ([p for p in pack['pages'] if set(p['imageHashes'])-set(p['reviewedImageHashes'])] if args.all_images else
                     [p for p in pack['pages'] if p['needsOcr'] and not p['review'] and not p.get('imageReviews')])
            if not pages:
                continue
            remaining_pages = len(pages)
            pages = pages[:args.max_pages]
            directory = args.output/doc['id']
            directory.mkdir(exist_ok=True)
            (directory/'pack.json').write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding='utf-8')
            # A draft deliberately cannot be applied until each page is reviewed.
            draft_pages = []
            for page in pages:
                hashes = sorted(set(page['imageHashes'])-set(page['reviewedImageHashes'])) if args.all_images else page['imageHashes']
                draft_pages.append({'page': page['page'], 'kind': 'supplement' if args.all_images else 'review-required', 'text': '',
                                    'imageHashes': hashes, **({'imageReviews': [{'imageHash': sha, 'kind': 'review-required', 'text': '', 'partial': False} for sha in hashes]} if args.all_images else {})})
            draft = {'courseId': args.course_id, 'documentId': doc['id'], 'version': pack['version'], 'fileHash': pack['fileHash'],
                     'reviewer': 'human', 'pages': draft_pages}
            draft_path = directory/(('all-images-draft-v'+str(pack['version'])+'.json') if args.all_images else 'review-draft.json')
            if not draft_path.exists():
                draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')
            response = http.get('/api/platform/rag/original', params={'courseId': args.course_id, 'documentId': doc['id']})
            response.raise_for_status()
            original = response.content
            if hashlib.sha256(original).hexdigest() != pack['fileHash']:
                raise ValueError('ORIGINAL_HASH_MISMATCH')
            source = directory/'original.pptx'
            if not source.exists():
                source.write_bytes(original)
            image_pages, images = ppt_images(original)
            for page in pages:
                for sha in image_pages[page['page']]:
                    image = images[sha]
                    (directory/(sha+'.'+image['extension'])).write_bytes(image['content'])
            if args.render:
                render_copy(source, [p['page'] for p in pages], directory)
            count += len(pages)
            print(json.dumps({'document': doc['name'], 'pendingPages': [p['page'] for p in pages], 'remainingAfterBatch': remaining_pages-len(pages), 'directory': str(directory)}, ensure_ascii=False))
    print(json.dumps({'exportedPages': count, 'providerRequests': 0}))


if __name__ == '__main__':
    main()
