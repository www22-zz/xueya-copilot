"""Controlled Python server used only by the browser regression, never paid APIs."""
import argparse
import asyncio
import json
import uvicorn
from backend.app import create_app
from backend.config import ROOT
from backend.core import dumps


class ControlledModel:
    async def generate(self, request):
        system, raw = request['messages'][0]['content'], request['messages'][-1]['content']
        if '通用问答' in system:
            return {'model': 'controlled', 'content': dumps({'answer': '可以固定起床时间，逐步调整作息。'})}
        materials = json.loads(raw)['materials']
        source = next((s for s in materials if s['title'] == '协作验证.md'), materials[0])
        if '知识点整理助手' in system:
            content = [{'name': '拓扑排序', 'sourceId': source['id']}, {'name': '入度', 'sourceId': source['id']}]
        elif '出题助手' in system:
            content = [{'topic': '拓扑排序', 'prompt': '拓扑排序首先选择哪类顶点？', 'options': ['入度为零的顶点', '任意顶点'], 'answer': 0, 'explanation': '每轮选择入度为零的顶点。', 'sourceId': source['id']}]
        else:
            content = {'answer': source['quote'], 'sources': [source['id']], 'knowledgePoints': [], 'claims': [{'text': source['quote'], 'evidence': [{'sourceId': source['id'], 'quote': source['quote']}]}]}
        return {'model': 'controlled', 'content': dumps(content)}

    async def stream(self, request):
        raw = request['messages'][-1]['content']
        if '慢一点' in raw:
            try:
                yield {'type': 'content', 'text': '{"answer":"尚未校验的半段答案', 'model': 'controlled'}
                await asyncio.sleep(120)
            except asyncio.CancelledError:
                output = ROOT/'test-results/browser-python'
                output.mkdir(parents=True, exist_ok=True)
                (output/'model-cancelled.txt').write_text('cancelled', encoding='utf-8')
                raise
            return
        result = await self.generate(request)
        for i in range(0, len(result['content']), 12):
            yield {'type': 'content', 'text': result['content'][i:i+12], 'model': 'controlled'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--platform-data')
    args = parser.parse_args()
    config = {'root': ROOT, 'ai': {'apiKey': 'controlled-only', 'model': 'controlled'}}
    if args.platform_data:
        config['platform'] = {'enabled': True, 'dataDir': args.platform_data}
    uvicorn.run(create_app(config, model=ControlledModel()), host='127.0.0.1', port=args.port, log_level='warning')
