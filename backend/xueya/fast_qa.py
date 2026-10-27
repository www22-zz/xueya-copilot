"""Conservative ordinary-question routing and incremental evidence-only publication."""
import json
import re
from backend.agent.evidence import validate_claims
from backend.core import DomainError

COMPLEX = re.compile(r'跨章|跨文档|跨资料|跨文件|综合|整章|整门|所有章节|所有资料|全部资料|多步骤|多章节|多个(?:文件|文档|资料)|详细分析|全面分析|章节.{0,12}(?:对比|比较)|学习.{0,8}(?:计划|安排)|复习|备考|测验|出题|错题|学习包|思维导图|知识图谱|证明|推导|代码|编程|实现|算法设计|逐步|分步骤|分别|这一章|这章|总结|梳理|先.{1,80}(?:再|然后)|compare all|entire chapter|whole chapter|study plan|prove|derive|implement|across|multi.step', re.I)


def ordinary_question(request, intent):
    question = request['question']
    return (intent == 'ask' and request['mode'] == 'ask' and len(question) <= 500
            and len(re.findall(r'[?？]', question)) <= 2 and not COMPLEX.search(question))


def fast_messages(messages):
    messages[0] = {**messages[0], 'content': messages[0]['content'] +
        '这是普通资料问答，请直接简短回答，不要规划任务。请先输出 claims 数组，再输出 answer、sources、knowledgePoints。'
        '每个claim.text用自己的话讲清楚一个要点，kind使用paraphrase或inference，evidence优先只填写sourceId和quoteId，不重写OCR原文；兼容的quote字段必须逐字引用。先给直观结论再解释原因，最多6项，不要把原文重复粘贴成答案。'
        '不得为了提前输出而省略证据。'}
    return messages


class ClaimStream:
    """Parse complete top-level claim objects, never regex-match inside quoted text."""
    def __init__(self):
        self.buffer = ''
        self.pos = 0
        self.state = 'root'
        self.key = None
        self.decoder = json.JSONDecoder()
        self.claims = []
        self.accepted = []
        self.source_ids = []
        self.wait_for_review = False

    def feed(self, text):
        self.buffer += text
        completed = []
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos].isspace():
                self.pos += 1
            if self.pos >= len(self.buffer):
                break
            char = self.buffer[self.pos]
            if self.state == 'root':
                if char != '{':
                    break  # Markdown-wrapped responses retain final validation only.
                self.pos += 1
                self.state = 'key'
            elif self.state == 'key':
                if char == '}':
                    break
                try:
                    key, end = self.decoder.raw_decode(self.buffer, self.pos)
                except ValueError:
                    break
                if not isinstance(key, str):
                    break
                self.key, self.pos, self.state = key, end, 'colon'
            elif self.state == 'colon':
                if char != ':':
                    break
                self.pos += 1
                self.state = 'value'
            elif self.state == 'value':
                if self.key == 'claims' and char == '[':
                    self.pos += 1
                    self.state = 'claim'
                    continue
                try:
                    _, self.pos = self.decoder.raw_decode(self.buffer, self.pos)
                except ValueError:
                    break
                self.state = 'separator'
            elif self.state == 'claim':
                if char == ']':
                    self.pos += 1
                    self.state = 'separator'
                    continue
                try:
                    claim, end = self.decoder.raw_decode(self.buffer, self.pos)
                except ValueError:
                    break
                self.claims.append(claim)
                completed.append(claim)
                self.pos, self.state = end, 'claim-separator'
                if len(self.claims) > 100:
                    break
            elif self.state == 'claim-separator':
                if char not in ',]':
                    break
                self.pos += 1
                self.state = 'claim' if char == ',' else 'separator'
            elif self.state == 'separator':
                if char != ',':
                    break
                self.pos += 1
                self.state = 'key'
        return completed

    async def checked_text(self, claim, sources):
        try:
            checked = await validate_claims([claim], {'sources': sources})
        except (DomainError, ValueError, TypeError, KeyError, AttributeError):
            return None
        item = checked[0]
        if item['support'] != 'supported' or item['kind'] != 'excerpt':
            self.wait_for_review = True
            return None
        if self.wait_for_review:
            return None
        self.accepted.append(item)
        for ref in item['evidence']:
            if ref['sourceId'] not in self.source_ids:
                self.source_ids.append(ref['sourceId'])
        return item['text'] + ''.join(f" [{self.source_ids.index(r['sourceId'])+1}]" for r in item['evidence'])
