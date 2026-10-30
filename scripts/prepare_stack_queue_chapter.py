"""Build the local text/code chapter draft; original files are never rewritten."""
import argparse
import json
from pathlib import Path

from scripts.eval_stack_queue import chapter_sources


def bundle():
    _, parsed, _, _ = chapter_sources(corrected=True)
    return {'schema': 'prepared-pdf-ocr-v1', 'sourceFileHash': parsed['fileHash'],
            'engine': 'prepared-ocr-with-source-checked-corrections-v1',
            'selectedPages': [p['number'] for p in parsed['pages']],
            'humanReviewed': False, 'correctionFile': 'evals/rag/stack-queue-corrections.json',
            'pages': [{'page': p['number'], 'text': parsed['text'][p['start']:p['end']],
                       'textFormat': 'markdown' if any(b['page'] == p['number'] and b['type'] == 'code' for b in parsed['blocks']) else 'text'}
                      for p in parsed['pages']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = bundle()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'pages': len(value['pages']), 'providerRequests': 0, 'humanReviewed': False}))


if __name__ == '__main__':
    main()
