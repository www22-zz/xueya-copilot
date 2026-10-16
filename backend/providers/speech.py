import base64
import re
from .mimo import MimoProvider
from ..core import require


class MimoSpeech:
    def __init__(self, config, transport=None):
        self.recognition = MimoProvider({**config, 'model': config.get('asrModel', 'mimo-v2.5-asr')}, transport=transport)
        self.synthesis = MimoProvider({**config, 'model': config.get('ttsModel', 'mimo-v2.5-tts')}, transport=transport)

    async def transcribe(self, request):
        audio, language = request.get('audio'), request.get('language', 'auto')
        require(isinstance(audio, str) and len(audio) <= 10*1024*1024 and re.fullmatch(r'data:audio/(wav|mpeg|mp3);base64,[A-Za-z0-9+/]+=*', audio) and language in ('auto', 'zh', 'en'), 'INVALID_AUDIO')
        result = await self.recognition.generate({'signal': request.get('signal'), 'asrOptions': {'language': language},
                    'messages': [{'role': 'user', 'content': [{'type': 'input_audio', 'input_audio': {'data': audio}}]}]})
        return {'text': result['content'], 'model': self.recognition.model, 'usage': result['usage'], 'wordAlignment': False}

    async def synthesize(self, request):
        text, voice = request.get('text'), request.get('voice', 'mimo_default')
        require(isinstance(text, str) and text.strip() and len(text) <= 1000 and voice in ('mimo_default', '冰糖', '茉莉', '苏打', '白桦', 'Mia', 'Chloe', 'Milo', 'Dean'), 'INVALID_SPEECH_REQUEST')
        result = await self.synthesis.generate({'signal': request.get('signal'), 'audio': {'format': 'wav', 'voice': voice}, 'messages': [{'role': 'assistant', 'content': text}]})
        encoded = (result.get('audio') or {}).get('data')
        require(isinstance(encoded, str) and 0 < len(encoded) <= 20*1024*1024, 'INVALID_SPEECH_RESPONSE')
        try:
            base64.b64decode(encoded, validate=True)
        except ValueError:
            require(False, 'INVALID_SPEECH_RESPONSE')
        return {'data': encoded, 'mime': 'audio/wav', 'model': self.synthesis.model, 'usage': result['usage'], 'synthetic': True}

    def usage(self):
        return {'asr': self.recognition.usage(), 'tts': self.synthesis.usage()}
