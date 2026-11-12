"""Conservative ordinary-question routing and incremental evidence-only publication."""
import json
import re
from backend.agent.evidence import validate_claims
from backend.core import DomainError

COMPLEX = re.compile(r'跨章|跨文档|跨资料|跨文件|综合|整章|整门|所有章节|所有资料|全部资料|多步骤|多章节|多个(?:文件|文档|资料)|详细分析|全面分析|章节.{0,12}(?:对比|比较)|学习.{0,8}(?:计划|安排)|复习|备考|测验|出题|错题|学习包|思维导图|知识图谱|证明|推导|代码|编程|实现|算法设计|逐步|分步骤|这一章|这章|总结|梳理|先.{1,80}(?:再|然后)|compare all|entire chapter|whole chapter|study plan|prove|derive|implement|across|multi.step', re.I)


def ordinary_question(request, intent):
    question = request['question']
    routing_question = question
    if ('代码' in question and re.search(r'解释|说明|含义|为什么|区别', question)
            and not re.search(r'编写|生成|写.{0,20}代码|修改|重构', question)):
        # Reading an existing snippet needs evidence, not a multi-round plan.
        # Other complexity markers (proof, implementation, cross-document) remain.
        routing_question = question.replace('代码', '')
    return (intent == 'ask' and request['mode'] == 'ask' and len(question) <= 500
            and len(re.findall(r'[?？]', question)) <= 2 and not COMPLEX.search(routing_question))


def fast_messages(messages):
    messages[0] = {**messages[0], 'content': messages[0]['content'] +
        '这是资料教学问答，请结合相关片段组织完整、通俗且有依据的讲解，不要规划任务或堆砌原文。除非用户要求简答，先给结论，再解释机制和原因，结合题设给出具体例子或逐步推导，最后澄清易混淆点；不为凑长度重复内容。'
        '除非用户明确要求详细展开，answer 控制在 150–350 字，claims 最多 4 项且不要重复同一事实。请先输出 claims 数组，再输出 answer、sources、knowledgePoints。'
        'claims 必须全部使用逐字原文整句（kind 设为 excerpt，text 必须与所选 quoteId 的 quoteSpans 原文完全一致），不要写改写型 claims；自己的解释全部写在 answer 里。这样服务端可以立即核对，回答也更快。'
        '给定材料只是参考资料，请不要机械照抄原文，要用自己的话组织自然、完整的 answer；资料与问题无关或不足时设 answerable=false。'
        'suggestedQuestions 根据本轮问题和回答预测 3 个用户可能追问的问题，每条不超过 40 字，不要重复原问题。'
        '最多给出一项与问题直接相关且语义完整的原文摘录，优先选s开头的完整句编号。OCR噪声或断行使原句不清楚时，不要逐行粘贴，直接用paraphrase解释并提供依据；'
        '随后的段落再用自己的话展开通俗解释或推导（kind 设为 paraphrase 或 inference，evidence.quote 必须逐字引用资料）。先直观结论再解释原因，按需要给出完整的解释，各项保持语义连贯。'
        'evidence可以只填写sourceId与quoteId，由服务端恢复所选原文，避免重抄OCR字形；直接摘录的text仍需与原文完全一致。不得为了提前输出而编造证据。'
        '标题用于定位，不能拿只有主题名称的标题当作解释依据。不要把资料中另一个数值例子的答案放到当前题目的答案前；'
        '只解释当前输入，示例与题设不同必须明确区分。不要用原文未定义的括号别名把两个不同概念说成同义词。'
        '用户明确要求一句话、只给结果或限定格式时，遵守该要求，可只输出一项paraphrase或inference，不必额外附摘录；事实依据仍须完整且通过核对。'}
    try:
        question = json.loads(messages[-1]['content']).get('question', '')
    except (ValueError, TypeError, AttributeError):
        question = ''
    if re.search(r'\d|一句话|只用|^(?:那|它|这样)|\b(?:front|rear|GetHead)\b', question):
        messages[0]['content'] += ('本题需要明确结果、位置或连续推理。只输出直接回答问题的paraphrase或inference，不额外摘录；'
            '不要用相关的定义或判空条件代替实际询问的结果。推理用“按题设”明确给定数值或操作序列；'
            '证据优先选相关来源的q0完整片段；不同规则来自不同片段时必须全部列入evidence，不能只引用含主题词的句子。')
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
        self.claims_closed = False

    def feed(self, text):
        self.buffer += text
        completed = []
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos].isspace():
                self.pos += 1
            if self.pos >= len(self.buffer):
                break
            if self.state == 'root':
                if self.buffer[self.pos:].startswith('```'):
                    nl = self.buffer.find('\n', self.pos)
                    if nl == -1:
                        break
                    self.pos = nl + 1
                    while self.pos < len(self.buffer) and self.buffer[self.pos].isspace():
                        self.pos += 1
                if self.pos >= len(self.buffer):
                    break
            char = self.buffer[self.pos]
            if self.state == 'root':
                if char != '{':
                    break
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
                    self.claims_closed = True
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
                if char == ']':
                    self.claims_closed = True
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
        return item['text'] + ''.join(f" [{self.source_ids.index(source_id)+1}]" for source_id in dict.fromkeys(r['sourceId'] for r in item['evidence']))


class DraftStream:
    """Extract the top-level `answer` string from a streaming JSON response.

    This is a display-only preview: content is never validated, stored or
    forwarded as a final answer. The authoritative answer remains the `done`
    event. Callers must label the emitted fragments as unverified.
    """
    def __init__(self):
        self.buffer = ''
        self.pos = 0
        self.state = 'root'
        self.key = None
        self.decoder = json.JSONDecoder()
        self.quoted = False
        self.finished = False
        self.started = False

    def feed(self, text):
        if self.finished or not isinstance(text, str) or not text:
            return ''
        self.buffer += text
        out = []
        while not self.finished:
            if self.quoted:
                chunk, done = self._read_string()
                if chunk:
                    out.append(chunk)
                if done:
                    self.finished = True
                break
            while self.pos < len(self.buffer):
                while self.pos < len(self.buffer) and self.buffer[self.pos].isspace():
                    self.pos += 1
                if self.pos >= len(self.buffer):
                    return ''.join(out)
                char = self.buffer[self.pos]
                if self.state == 'root':
                    if self.buffer.startswith('```', self.pos):
                        newline = self.buffer.find('\n', self.pos)
                        if newline == -1:
                            return ''.join(out)
                        self.pos = newline+1
                        continue
                    if char != '{':
                        return ''.join(out)
                    self.pos += 1
                    self.state = 'key'
                    continue
                if self.state == 'key':
                    if char == '}':
                        return ''.join(out)
                    try:
                        key, end = self.decoder.raw_decode(self.buffer, self.pos)
                    except ValueError:
                        return ''.join(out)
                    if not isinstance(key, str):
                        return ''.join(out)
                    self.key, self.pos, self.state = key, end, 'colon'
                    continue
                if self.state == 'colon':
                    if char != ':':
                        return ''.join(out)
                    self.pos += 1
                    self.state = 'value'
                    continue
                if self.state == 'value':
                    if self.key == 'answer' and char == '"':
                        self.pos += 1
                        self.quoted = self.started = True
                        break
                    try:
                        _, self.pos = self.decoder.raw_decode(self.buffer, self.pos)
                    except ValueError:
                        return ''.join(out)
                    self.state = 'separator'
                    continue
                if self.state == 'separator':
                    if char != ',':
                        return ''.join(out)
                    self.pos += 1
                    self.state = 'key'
                    continue
                return ''.join(out)
            else:
                # Buffer exhausted without reaching a complete value: wait for more.
                return ''.join(out)
        return ''.join(out)
    def _read_string(self):
        raw, i, out = self.buffer, self.pos, []
        escapes = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}
        while i < len(raw):
            char = raw[i]
            if char == '\\':
                if i+1 >= len(raw):
                    break
                escape = raw[i+1]
                if escape == 'u':
                    if i+6 > len(raw):
                        break
                    try:
                        out.append(json.loads('"'+raw[i:i+6]+'"'))
                    except ValueError:
                        self.finished = True
                        break
                    i += 6
                    continue
                if escape in escapes:
                    out.append(escapes[escape])
                    i += 2
                    continue
                self.finished = True
                break
            if char == '"':
                self.pos = i+1
                return ''.join(out), True
            end = i
            while end < len(raw) and raw[end] not in '\\"':
                end += 1
            out.append(raw[i:end])
            i = end
        self.pos = i
        return ''.join(out), False
