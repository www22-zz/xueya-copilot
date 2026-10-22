"""Import real local files through the running host, with no model/API calls.

python -m scripts.import_knowledge_base --directory D:/course/PPT --name 数据结构与算法
Records only a local manifest; originals and parsed content stay in FileStore/SQLite.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import httpx

from backend.xueya.common import digest
from backend.xueya.config import load_config
from backend.xueya.knowledge_base import infer_chapter
from backend.xueya.rag_parse import KINDS


def checked(response):
    value = response.json()
    if not response.is_success or not value.get('ok'):
        raise RuntimeError(value.get('error', 'HTTP_'+str(response.status_code)))
    return value


def import_directory(directory, name, base_url, output, *, existing_course_id=None):
    directory = Path(directory).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError('DIRECTORY_REQUIRED')
    paths = sorted(directory.iterdir(), key=lambda p: p.name)
    files = [p for p in paths if p.is_file() and not p.name.startswith('~$') and p.suffix[1:].lower() in KINDS]
    if not files:
        raise ValueError('NO_SUPPORTED_FILES')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'name': name, 'paidApiCalls': 0, 'temporaryFilesSkipped': sum(p.name.startswith('~$') for p in paths), 'files': [], 'queries': []}

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    # Disable ambient proxies for loopback and do not follow redirects to other hosts.
    with httpx.Client(base_url=base_url.rstrip('/'), timeout=60, trust_env=False, follow_redirects=False) as http:
        bootstrap = checked(http.get('/api/platform/bootstrap'))
        http.headers['X-Xueya-Token'] = bootstrap['token']
        if existing_course_id:
            if not any(c['id'] == existing_course_id and not c['archived'] for c in bootstrap['courses']):
                raise ValueError('COURSE_NOT_FOUND')
            course_id = existing_course_id
        else:
            base = checked(http.post('/api/platform/knowledge/create', json={'name': name,
                'description': '本机课程课件知识库；保留原件、页码、章节和引用版本。',
                'idempotencyKey': 'local-course-'+digest(name)[:40]}))['base']
            course_id = base['id']
        report['courseId'] = course_id
        save()
        for path in files:
            # File size checked before reading. Original path is never sent to a model.
            if path.stat().st_size > (1_048_576 if path.suffix.lower() in ('.md', '.txt') else 10_485_760):
                report['files'].append({'name': path.name, 'status': 'too_large'})
                save()
                continue
            content = path.read_bytes()
            fingerprint = hashlib.sha256(content).hexdigest()
            chapter = infer_chapter(path.name)
            result = checked(http.post('/api/platform/knowledge/upload', params={'courseId': course_id, 'name': path.name, 'chapter': chapter},
                headers={'Idempotency-Key': 'import-'+digest({'name': path.name, 'sha256': fingerprint, 'chapter': chapter})[:48]}, content=content))
            job = result['job']
            deadline = time.monotonic()+300
            while job['status'] not in ('succeeded', 'failed', 'cancelled', 'unknown') and time.monotonic() < deadline:
                time.sleep(.2)
                job = checked(http.get('/api/platform/jobs/status', params={'id': job['id']}))['job']
            item = {'name': path.name, 'sha256': fingerprint, 'size': len(content), 'chapter': chapter, 'documentId': result['documentId'],
                    'jobId': job['id'], 'status': job['status'], 'error': job.get('error')}
            if job['status'] == 'succeeded':
                read = checked(http.get('/api/platform/library/read', params={'courseId': course_id, 'documentId': result['documentId']}))
                artifact = read['artifact']
                item.update({'sources': len(read['document']['chunks']), 'pages': len(artifact['pages']),
                             'textCharacters': len(artifact['text']), 'warnings': artifact['warnings'],
                             'emptyPages': sum(p['start'] == p['end'] for p in artifact['pages']),
                             'imagePages': sum(bool(p.get('hasImages')) for p in artifact['pages'])})
            report['files'].append(item)
            save()
            print(json.dumps({'file': path.name, 'status': item['status'], 'sources': item.get('sources')}, ensure_ascii=False), flush=True)
        # A repeatable smoke set, not an independent benchmark of answer quality.
        for query in ('顺序表', '链表', '栈', '队列', '哈夫曼', '最小生成树', '最短路径', '哈希', '排序'):
            evidence = checked(http.post('/api/platform/knowledge/search', json={'courseId': course_id, 'query': query, 'mode': 'lexical'}))['evidence']
            valid = all(checked(http.post('/api/platform/rag/validate', json={'courseId': course_id, 'citation': s}))['valid'] for s in evidence['sources'])
            report['queries'].append({'query': query, 'hits': len(evidence['sources']), 'citationsValid': valid,
                                     'documents': sorted({s['documentId'] for s in evidence['sources']}),
                                     'pages': sorted({s['page'] for s in evidence['sources'] if s.get('page') is not None})})
            save()
        report['summary'] = checked(http.get('/api/platform/knowledge/catalog', params={'courseId': course_id}))['summary']
        report['status'] = 'passed' if all(f['status'] == 'succeeded' for f in report['files']) and all(q['hits'] and q['citationsValid'] for q in report['queries']) else 'needs_review'
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--name', default='数据结构与算法')
    parser.add_argument('--base-url', default='http://127.0.0.1:'+str(load_config().port))
    parser.add_argument('--existing-course-id')
    parser.add_argument('--output', default='test-results/knowledge-base/import.json')
    args = parser.parse_args()
    # Never send bootstrap tokens or original course files to an arbitrary URL.
    from urllib.parse import urlsplit
    target = urlsplit(args.base_url)
    if target.scheme != 'http' or target.hostname not in ('127.0.0.1', 'localhost', '::1') or target.username or target.password or target.query or target.fragment or target.path not in ('', '/'):
        parser.error('--base-url must be a local HTTP host')
    report = import_directory(args.directory, args.name, args.base_url, args.output, existing_course_id=args.existing_course_id)
    print(json.dumps({k: report[k] for k in ('status', 'courseId', 'summary', 'paidApiCalls')}, ensure_ascii=False, indent=2))
    if report['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
