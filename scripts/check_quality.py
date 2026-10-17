"""F offline acceptance evaluation. Never reads .env or calls paid model APIs."""
import argparse
import asyncio
import csv
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform as system
import statistics
import subprocess
import tempfile
import time

from backend.xueya.platform import Platform
from backend.xueya.rag_eval import finish
from backend.xueya.rag_search import lexical, compress, rewrite_query, conflicts
from backend.xueya.rag_service import RagService
from scripts.build_quality_materials import ROOT, build


def score_case(case, sources, documents):
    gold = case['gold']
    matches = [any(s['documentId'] == documents[g['document']] and g['quote'] in s['quote'] for s in sources) for g in gold]
    rank = next((i+1 for i, s in enumerate(sources) if any(s['documentId'] == documents[g['document']] and g['quote'] in s['quote'] for g in gold)), None)
    return {'passed': all(matches) if gold else not sources, 'matchedGold': sum(matches), 'goldCount': len(gold),
            'reciprocalRank': 1/rank if rank else 0, 'returnedCount': len(sources)}


def summarize(rows):
    positives = [r for r in rows if r['goldCount']]
    negatives = [r for r in rows if not r['goldCount']]
    latency = sorted(ms for r in rows for ms in r['latencyMs'])
    return {'cases': len(rows), 'passed': sum(r['passed'] for r in rows),
            'allEvidenceRecallAt6': sum(r['passed'] for r in positives)/len(positives) if positives else None,
            'excerptRecallAt6': sum(r['matchedGold'] for r in positives)/sum(r['goldCount'] for r in positives) if positives else None,
            'mrrAt6': statistics.mean(r['reciprocalRank'] for r in positives) if positives else None,
            'noEvidenceRateOnUnanswerable': sum(r['passed'] for r in negatives)/len(negatives) if negatives else None,
            'p50Ms': statistics.median(latency) if latency else None,
            'p95Ms': latency[max(0, math.ceil(.95*len(latency))-1)] if latency else None,
            'invalidLocations': sum(not r['validLocations'] for r in rows),
            'overBudget': sum(r['usedBytes'] > r['budgetBytes'] for r in rows),
            'byCategory': {category: {'passed': sum(r['passed'] for r in rows if r['category'] == category),
                                    'count': sum(r['category'] == category for r in rows)} for category in sorted({r['category'] for r in rows})}}


async def evaluate(dataset, output, split='test', budget=2000, repeats=3):
    value = json.loads(dataset.read_text(encoding='utf-8'))
    assert len({c['id'] for c in value['cases']}) == len(value['cases'])
    documents = {d['name']: d for d in value['documents']}
    for case in value['cases']:
        for gold in case['gold']:
            assert gold['quote'] in documents[gold['document']]['text'], case['id']
    cases = [c for c in value['cases'] if split == 'all' or c['split'] == split]
    assert cases, 'No cases selected'
    results = {'fixed-lexical': [], 'structured-lexical': []}
    with tempfile.TemporaryDirectory(prefix='xueya-f-eval-') as folder:
        p = Platform(Path(folder)); rag = RagService(p)
        try:
            scope, ids, canonical, baseline = p.scope(), {}, {}, []
            start = time.perf_counter()
            for i, doc in enumerate(value['documents']):
                completed = await finish(p, rag.upload(scope, doc['text'].encode(), doc['name'], 'f-'+str(i)))
                key = completed['documentId']; ids[doc['name']] = key
                text = rag.artifact(scope, rag.document(scope, key))['text']; canonical[key] = text
                for offset in range(0, len(text), 520):
                    baseline.append({'id': f'fixed-{i}-{offset}', 'documentId': key, 'title': doc['name'],
                        'start': offset, 'end': min(offset+600, len(text)), 'quote': text[offset:offset+600], 'blockType': 'paragraph'})
            import_ms = (time.perf_counter()-start)*1000
            for index, case in enumerate(cases):
                query = rewrite_query(case['query'], case.get('history', []))
                # Alternating order reduces a constant first/second-method timing bias.
                methods = list(results) if index % 2 == 0 else list(reversed(results))
                for method in methods:
                    times, result = [], None
                    for _ in range(repeats):
                        start = time.perf_counter()
                        if method == 'fixed-lexical':
                            sources, used = compress(query, lexical(query, baseline), budget=budget, limit=6)
                            result = {'sources': sources, 'budget': {'used': used}, 'conflicts': conflicts(sources)}
                        else:
                            result = await rag.search(scope, case['query'], history=case.get('history', []), mode='lexical', budget=budget, limit=6)
                        times.append((time.perf_counter()-start)*1000)
                    sources = result['sources']
                    valid = all(canonical.get(s['documentId'], '')[s['start']:s['end']] == s['quote'] for s in sources)
                    metrics = score_case(case, sources, ids)
                    results[method].append({'id': case['id'], 'group': case['group'], 'category': case['category'],
                        'query': case['query'], **metrics, 'budgetBytes': budget, 'usedBytes': result['budget']['used'],
                        'validLocations': valid, 'conflictFlag': bool(result['conflicts']), 'latencyMs': times,
                        'returned': [{'document': next(name for name, key in ids.items() if key == s['documentId']), 'quote': s['quote'], 'start': s['start'], 'end': s['end']} for s in sources]})
            invocation_count = p.db.one('SELECT count(*) n FROM invocations')['n']
            assert invocation_count == 0
        finally:
            await p.close()
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = 'unavailable', None
    report = {'schema': 'f-quality-1', 'datasetVersion': value['version'], 'datasetSha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
        'split': split, 'totalDatasetCases': len(value['cases']), 'evaluatedCases': len(cases), 'repeats': repeats,
        'sourceCommit': commit, 'workingTreeChanged': dirty, 'python': system.python_version(), 'os': system.system(),
        'dependencies': {name: importlib.metadata.version(name) for name in ['fastapi', 'mcp', 'pypdf', 'fsrs']},
        'budget': {'unit': 'utf8Bytes', 'limit': budget, 'topK': 6}, 'importMs': import_ms, 'apiInvocations': invocation_count,
        'modelQuality': 'not_evaluated', 'humanReview': 'not_performed', 'cost': 'no_provider_calls',
        'notes': ['Original AI-assisted fixtures, not a human-labelled real-course benchmark.',
                  'Paraphrase pairs are correlated; no statistical superiority claim.',
                  'No-evidence rate measures retrieval abstention, not generated-answer refusal.',
                  'Fixed baseline does not include the structured service database/version checks. Latencies are not isolated algorithm comparisons.',
                  'CPU document import time includes spawned parser processes; query timings are local warm queries.'],
        'results': {method: {'status': 'evaluated', 'summary': summarize(rows), 'rows': rows} for method, rows in results.items()},
        'unmeasured': {'vector': 'API credentials/budget not authorized', 'hybrid': 'no real embedding evaluation', 'rerank': 'no real rerank evaluation',
                       'ocr': 'image-only fixture verifies no fabricated text, not OCR accuracy', 'multimodal': 'real model quality not tested'}}
    output.mkdir(parents=True, exist_ok=True)
    (output/'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['# F 离线验收实测', '', f"数据版本：{report['datasetVersion']}；SHA256：`{report['datasetSha256']}`。", '',
        f"分组：{split}；本次 {len(cases)} 问；每次重复 {repeats} 轮；预算 {budget} UTF-8 bytes，top-k=6。", '',
        '| 方法 | 通过 | 全部证据召回 | 摘录召回 | MRR | 不可答无检索证据 | P50/P95 ms |', '| --- | --- | --- | --- | --- | --- | --- |']
    for method, item in report['results'].items():
        s = item['summary']
        lines.append(f"| {method} | {s['passed']}/{s['cases']} | {s['allEvidenceRecallAt6']:.3f} | {s['excerptRecallAt6']:.3f} | {s['mrrAt6']:.3f} | {s['noEvidenceRateOnUnanswerable']:.3f} | {s['p50Ms']:.2f}/{s['p95Ms']:.2f} |")
    lines += ['', '这是原创验收集的实际结果，不代表真实模型质量或真实学习收益；没有新增付费调用。', '', '## 失败条目', '']
    for method, item in report['results'].items():
        lines += [f"- {method} / {r['id']}：{r['query']}（命中 {r['matchedGold']}/{r['goldCount']}，返回 {r['returnedCount']} 段）" for r in item['rows'] if not r['passed']]
    (output/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    with (output/'human-review.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file); writer.writerow(['caseId', 'query', 'referenceAnswer', 'goldEvidence', 'reviewer', 'decision', 'reason'])
        for case in cases:
            writer.writerow([case['id'], case['query'], case['referenceAnswer'], json.dumps(case['gold'], ensure_ascii=False), '', 'pending', ''])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'test-results/f-quality')
    parser.add_argument('--split', choices=['dev', 'test', 'all'], default='test')
    parser.add_argument('--budget', type=int, default=2000)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args(); output = args.output.resolve()
    if not output.is_relative_to(ROOT/'test-results') or not 32 <= args.budget <= 16000 or not 1 <= args.repeats <= 10:
        raise SystemExit('Output must be in test-results; budget 32..16000; repeats 1..10.')
    build(output/'materials')
    result = asyncio.run(evaluate(output/'materials/dataset.json', output, args.split, args.budget, args.repeats))
    print(json.dumps({m: v['summary'] for m, v in result['results'].items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
