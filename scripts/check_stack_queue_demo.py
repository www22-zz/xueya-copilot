"""Verify demo calculations and heading evidence with zero model requests."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile

from backend.xueya.agent import Agent
from backend.xueya.config import Config
from backend.xueya.platform import Platform
from backend.xueya.rag_service import RagService
from scripts.import_prepared_pdf import finish

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT/'evals/rag/stack-queue-demo.json'


async def evaluate():
    spec = json.loads(SPEC.read_text(encoding='utf-8'))
    content = (ROOT/spec['material']).read_bytes()
    assert hashlib.sha256(content).hexdigest() == spec['materialSha256'], 'Material changed; revalidate before demonstrating'
    with tempfile.TemporaryDirectory(prefix='xueya-demo-check-') as folder:
        p = Platform(Path(folder), recover=False, preserve_legacy_data=True)
        try:
            rag, scope = RagService(p), p.scope()
            p.jobs.stopped = False
            done = await finish(p, rag.upload(scope, content, '栈与队列知识库.md', 'demo'))
            doc = done['result']['documentId']
            class NoAPI:
                config = Config()
                async def stream(self, *args, **kwargs):
                    raise AssertionError('A local calculation must not call a model')
                    yield
            agent = Agent(NoAPI(), p);agent.rag = rag
            calculations = []
            for q in spec['localRule']:
                final = [e async for e in agent.workflow({'question': q['question'], 'documentIds': [doc]})][-1]
                assert final.get('verification') == 'calculated-from-cited-rules', q['id']
                for key, value in q['expected'].items():
                    assert final['calculation'][key] == value, (q['id'], key)
                assert final['timings']['modelCalls'] == 0
                assert all(rag.validate(scope, s) for s in final['sourceDetails'])
                calculations.append({'id': q['id'], 'passed': True, 'answer': final['answer'],
                    'calculation': final['calculation'], 'locations': [s['location'] for s in final['sourceDetails']],
                    'modelCalls': 0, 'elapsedMs': final['timings']['totalMs']})
            evidence = []
            for q in spec['historicalLive']:
                found = await rag.search(scope, q['question'], document_ids=[doc], mode='lexical', budget=9000)
                hit = any(any(part.startswith(section+' ') for part in s['sectionPath'])
                          for section in q['sections'] for s in found['sources'])
                assert hit and all(rag.validate(scope, s) for s in found['sources']), q['id']
                evidence.append({'id': q['id'], 'evidenceFound': True, 'answerRegenerated': False})
            assert not p.db.one('SELECT id FROM invocations')
            return {'materialSha256': spec['materialSha256'], 'localCalculations': calculations,
                    'historicalQuestionEvidence': evidence, 'newModelRequests': 0,
                    'note': '本轮只本地复核公式题及历史题的证据位置，不冒充重新在线验证9道生成回答。'}
        finally:
            await p.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'test-results/rag-fallback/demo-check.json')
    args = parser.parse_args()
    result = asyncio.run(evaluate())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'localCalculations': len(result['localCalculations']),
                      'historicalEvidenceChecks': len(result['historicalQuestionEvidence']), 'newModelRequests': 0}))


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
