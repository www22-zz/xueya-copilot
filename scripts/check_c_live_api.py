"""Explicit paid smoke checks; same cumulative local budget as the pre-migration run."""
import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import struct
import zlib
from backend.config import load_config, ROOT
from backend.core import require, now_iso
from backend.providers import MimoProvider, MimoSpeech


def synthetic_image():
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    width, height = 320, 100
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            box = next((i for i in range(5) if 15+i*60 <= x < 55+i*60 and 30 <= y < 70), None)
            raw.extend((255, 255, 255) if box is None else (255, 0, 0) if box < 3 else (0, 0, 255))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))+chunk(b'IDAT', zlib.compress(raw))+chunk(b'IEND', b'')


async def checks(output):
    config = load_config()['ai']
    require(config['apiKey'], 'API_KEY_REQUIRED')
    require(config['baseURL'] == 'https://api.xiaomimimo.com/v1' and config['model'] == 'mimo-v2.6-flash', 'UNVERIFIED_PRICE_OR_ENDPOINT')
    ledger_file = output/'budget.json'
    ledger = json.loads(ledger_file.read_text(encoding='utf-8-sig')) if ledger_file.exists() else {'budgetCny': 10, 'reservations': []}
    report = {'runtime': 'python', 'startedAt': now_iso(), 'budgetCny': 10, 'syntheticInputs': True, 'results': [], 'notes': ['No retries. Each bounded tiny request reserves 0.1 CNY; historical reservations retained.', 'Actual invoice is not available; public domestic prices used for estimates only.']}
    model = MimoProvider({**config, 'thinking': {'type': 'disabled'}, 'maxOutputTokens': 512, 'maxRequests': 4})
    speech = MimoSpeech({**config, 'maxOutputTokens': 512, 'maxRequests': 1})
    stopped = False

    async def run(name, fn):
        nonlocal stopped
        if stopped:
            report['results'].append({'name': name, 'status': 'skipped', 'reason': 'Stopped after an error; no automatic retry'})
            return None
        reserved = sum(row['reservedCny'] for row in ledger['reservations'])
        require(reserved+.1 <= 10, 'CUMULATIVE_BUDGET_EXCEEDED')
        reservation = {'at': now_iso(), 'check': name, 'runtime': 'python', 'reservedCny': .1, 'state': 'outcome-unknown'}
        ledger['reservations'].append(reservation)
        ledger_file.write_text(json.dumps(ledger, indent=2), encoding='utf-8')
        try:
            result = await fn()
            reservation['state'] = 'response-received'
            row = {'name': name, 'status': 'passed', **result}
        except Exception as error:
            stopped = True
            row = {'name': name, 'status': 'failed', 'code': getattr(error, 'code', 'CHECK_FAILED')}
        report['results'].append(row)
        (output/'python-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        ledger_file.write_text(json.dumps(ledger, indent=2), encoding='utf-8')
        print(json.dumps(row, ensure_ascii=True))
        return row if row['status'] == 'passed' else None

    async def text():
        result = await model.generate({'responseFormat': {'type': 'json_object'}, 'messages': [{'role': 'user', 'content': '只返回JSON：{"answer":5}。'}]})
        require(json.loads(result['content'])['answer'] == 5, 'WRONG_ANSWER')
        return {k: result[k] for k in ('model', 'usage', 'finishReason', 'content')}
    await run('text-json', text)

    async def stream():
        content, usage = '', None
        async for event in model.stream({'messages': [{'role': 'user', 'content': '只输出：学习测试成功'}]}):
            if event['type'] == 'content':
                content += event['text']
            if event['type'] == 'usage':
                usage = event['usage']
        require('学习测试成功' in content, 'WRONG_STREAM')
        return {'model': model.model, 'content': content, 'usage': usage}
    await run('text-stream', stream)

    async def tool():
        result = await model.generate({'messages': [{'role': 'user', 'content': '必须调用 course_lookup 查询课程 math，不直接回答。'}], 'tools': [{'type': 'function', 'function': {'name': 'course_lookup', 'description': '查询课程', 'parameters': {'type': 'object', 'properties': {'courseId': {'type': 'string'}}, 'required': ['courseId']}}}]})
        call = next((c for c in result['toolCalls'] if c.get('function', {}).get('name') == 'course_lookup'), None)
        require(call and json.loads(call['function']['arguments'])['courseId'] == 'math', 'WRONG_TOOL_CALL')
        return {'model': result['model'], 'usage': result['usage'], 'finishReason': result['finishReason'], 'toolName': 'course_lookup'}
    await run('tool-call', tool)

    async def image():
        png = synthetic_image()
        (output/'python-synthetic-shapes.png').write_bytes(png)
        result = await model.generate({'responseFormat': {'type': 'json_object'}, 'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': '数出红色和蓝色方块数量，只返回JSON字段red和blue。'}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,'+base64.b64encode(png).decode()}}]}]})
        require(json.loads(result['content']) == {'red': 3, 'blue': 2}, 'WRONG_IMAGE_ANSWER')
        return {k: result[k] for k in ('model', 'usage', 'finishReason', 'content')}
    await run('image-understanding', image)

    audio = None
    async def synthesis():
        nonlocal audio
        audio = await speech.synthesize({'text': '三加二等于五。', 'voice': '冰糖'})
        data = base64.b64decode(audio['data'])
        require(data[:4] == b'RIFF' and data[8:12] == b'WAVE', 'INVALID_WAV')
        (output/'python-synthetic-speech.wav').write_bytes(data)
        return {'model': audio['model'], 'usage': audio['usage'], 'bytes': len(data)}
    await run('speech-synthesis', synthesis)
    async def recognition():
        require(audio, 'NO_TTS_SAMPLE')
        result = await speech.transcribe({'audio': 'data:audio/wav;base64,'+audio['data'], 'language': 'zh'})
        require('三加二等于五' in result['text'] or '3加2等于5' in result['text'], 'WRONG_TRANSCRIPTION')
        return {'model': result['model'], 'text': result['text'], 'usage': result['usage']}
    await run('speech-recognition', recognition)
    text_usage = [r['usage'] for r in report['results'] if r.get('model') == model.model and r.get('usage')]
    text_cny = sum(u.get('prompt_tokens', 0)+2*u.get('completion_tokens', 0) for u in text_usage)/1000000
    seconds = sum(r.get('usage', {}).get('seconds', 0) for r in report['results'] if r.get('name') == 'speech-recognition')
    report.update(finishedAt=now_iso(), providerUsage={'text': model.usage(), 'speech': speech.usage()},
                  costEstimate={'currency': 'CNY', 'textCny': text_cny, 'asrSeconds': seconds, 'ttsCny': 0, 'totalCny': text_cny+seconds*.5/3600, 'invoiceVerified': False, 'pricingSource': 'https://mimo.mi.com/docs/en-US/price/pay-as-you-go'})
    (output/'python-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 1 if stopped else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--budget-cny', type=float)
    args = parser.parse_args()
    require(args.live and args.budget_cny == 10, 'EXPLICIT_LIVE_BUDGET_REQUIRED')
    output = ROOT/'test-results/c-live-api'
    output.mkdir(parents=True, exist_ok=True)
    lock = output/'python-smoke.lock'
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        return asyncio.run(checks(output))
    finally:
        os.close(descriptor)
        lock.unlink()


if __name__ == '__main__':
    raise SystemExit(main())
