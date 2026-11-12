const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../../shared/contracts/index.js');
const { createChatService } = require('../../frontend/js/services/chat-service.js');

const done = { type: 'done', ok: true, engine: 'xiaomi-mimo', answer: '回答。', sources: [], knowledgePoints: [] };

function streamBody(text) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } });
}

function serviceCapturing(sent) {
  return createChatService({
    fetchImpl: async (url, options) => {
      sent.push({ url, body: JSON.parse(options.body) });
      return new Response(streamBody('data: ' + JSON.stringify(done) + '\n\n'), { headers: { 'Content-Type': 'text/event-stream' } });
    }
  });
}

test('fastMode is a client-requested enum and survives contract normalization', () => {
  assert.equal(C.normalizeChatRequest({ question: '队列是什么？', fastMode: true }).fastMode, true);
  assert.ok(!('fastMode' in C.normalizeChatRequest({ question: '队列是什么？' })));
  assert.ok(!('fastMode' in C.normalizeChatRequest({ question: '队列是什么？', fastMode: 'yes' })));
});

test('chat service forwards fastMode only when enabled', async () => {
  const sent = [];
  const service = serviceCapturing(sent);
  await service.stream({ question: '队列是什么？', sources: [], fastMode: true }, {});
  await service.stream({ question: '队列是什么？', sources: [] }, {});
  assert.equal(sent[0].body.fastMode, true);
  assert.ok(!('fastMode' in sent[1].body));
});
