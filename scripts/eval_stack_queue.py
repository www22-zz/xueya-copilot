"""Offline chapter evidence coverage. No credentials, providers or external calls."""
import argparse
import json
from pathlib import Path

from backend.xueya.rag_parse import assemble, structured_chunks, text_blocks
from backend.xueya.rag_search import compress, lexical

ROOT = Path(__file__).resolve().parents[1]


def chapter_sources(*, corrected=False):
    spec = json.loads((ROOT/'evals/rag/stack-queue.json').read_text(encoding='utf-8'))
    bundle = json.loads((ROOT/spec['source']).read_text(encoding='utf-8'))
    low, high = spec['pdfPages']
    pages = [{'number': p['page'], 'text': p['text'], 'method': 'prepared-ocr', 'needsOcr': False}
             for p in bundle['pages'] if low <= p['page'] <= high]
    if corrected:
        corrections = json.loads((ROOT/'evals/rag/stack-queue-corrections.json').read_text(encoding='utf-8'))
        assert corrections['sourceFileHash'] == bundle['sourceFileHash']
        for patch in corrections['patches']:
            page = next(p for p in pages if p['number'] == patch['page'])
            assert page['text'].count(patch['before']) == 1, 'Correction anchor changed; inspect the original again'
            page['text'] = page['text'].replace(patch['before'], patch['after'], 1)
            page['method'] = 'ai-visual-correction'
        for page in pages:
            if page['method'] == 'ai-visual-correction' and '```' in page['text']:
                page['blocks'] = text_blocks(page['text'], page['number'], markdown=True, method=page['method'])
    parsed = assemble(pages, 'pdf', bundle['sourceFileHash'])
    if corrected:
        parsed['preparation'] = {'humanReviewed': False, 'notice': corrections['reviewMethod'],
                                 'correctionFile': 'evals/rag/stack-queue-corrections.json'}
    document = {'id': 'eval-stack-queue', 'name': '栈和队列（原OCR，公式待核对）', 'contentRevision': 1}
    return spec, parsed, document, structured_chunks(parsed, document)


def coverage(question, sources):
    return [any(s.get('page') in gold['pages'] and gold['contains'] in s['quote'] for s in sources)
            for gold in question.get('evidence', [])]


def evaluate():
    spec, _, _, sources = chapter_sources()
    rows = []
    for q in spec['questions']:
        ranked = lexical(q['query'], sources)
        selected, used = compress(q['query'], ranked, budget=9000, limit=6)
        rows.append({'id': q['id'], 'query': q['query'], 'split': q['split'],
                     'top3Coverage': coverage(q, selected[:3]), 'top6Coverage': coverage(q, selected),
                     'pages': [s['page'] for s in selected], 'usedBytes': used,
                     'negativeHasCandidates': bool(selected) if q.get('unanswerable') else None})
    return {'description': spec['description'], 'sourceCount': len(sources), 'apiCalls': 0,
            'note': '页码加原文锚点仅衡量检索覆盖；候选非空不能代表可回答，回答准确性另验收。', 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'test-results/chapter-qa/offline-baseline.json')
    args = parser.parse_args()
    result = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
