"""Host-owned assistant facts and explicit failed-answer presentation."""
import re
from backend.agent.tasks import answer_unavailable


def assistant_identity_question(question, mode='ask'):
    if mode != 'ask':
        return False
    text = re.sub(r'[\s，,。.!！?？：:]+', '', question).lower()
    text = re.sub(r'^(?:请问|问一下|告诉我|我想知道)', '', text)
    patterns = (
        r'(?:你|您)(?:现在|目前|当前|到底|实际)?(?:的)?(?:大语言模型|语言模型|底层模型|基座模型|模型)(?:是|是什么|是哪一个|是哪个|是哪种|叫什么|名称|版本|是什么版本|呢|呀|啊|吗)*',
        r'(?:你|您)(?:现在|目前|当前|到底)?(?:是|在|正在)?(?:用|使用|调用|接入|基于)(?:的)?(?:是|什么|哪个|哪种|哪一款|什么版本|哪家的)*(?:大语言模型|语言模型|模型)(?:是|什么|哪个|哪种|版本|呢|呀|啊|吗)*',
        r'(?:你|您)(?:到底)?(?:是谁|是什么ai|是什么助手|是哪个ai)',
        r'(?:你|您)(?:是)?(?:chatgpt|gpt[0-9.\-]*|claude|gemini|mimo|小米mimo|小米模型|deepseek)(?:吗|么|嘛|还是.*)?',
        r'(?:what|which)(?:large)?(?:language)?(?:model|llm)(?:areyou|doyouuse|areyourunning|powersyou)',
        r'whoareyou',
    )
    return any(re.fullmatch(pattern, text, re.I) for pattern in patterns)


def assistant_identity_reply(config):
    model = getattr(config, 'model', '')
    if not model:
        return '我是学涯 Copilot。当前应用尚未配置文字问答模型。'
    name = '小米 MiMO 的 ' + model if model.startswith('mimo-') else model
    return '我是学涯 Copilot，当前文字问答使用的模型是' + name + '。这是应用当前的服务端配置。'


