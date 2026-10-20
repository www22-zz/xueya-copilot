"""CPU-only media boundaries, evidence-backed rehearsal scripts and WAV exports."""
import io
import math
import wave

from backend.core import clone
from backend.xueya.common import AppError, require

MAX_ORIGINAL = 120 * 1024 * 1024
VOICES = ('mimo_default', '冰糖', '茉莉', '苏打', '白桦', 'Mia', 'Chloe', 'Milo', 'Dean')


def wav_info(raw):
    try:
        with wave.open(io.BytesIO(raw), 'rb') as audio:
            channels, width, rate, count = audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getnframes()
            require(audio.getcomptype() == 'NONE' and channels in (1, 2) and width in (1, 2, 3, 4)
                    and 8000 <= rate <= 96000 and 0 < count <= rate * 3600, 'INVALID_PCM_WAV')
            # A header claiming more samples than the file contains is not a timeline.
            require(len(audio.readframes(count)) == count * channels * width, 'TRUNCATED_WAV')
            return {'channels': channels, 'width': width, 'rate': rate, 'frames': count,
                    'durationMs': count * 1000 / rate}
    except (wave.Error, EOFError, ValueError) as error:
        raise AppError('INVALID_PCM_WAV') from error


def split_wav(raw, seconds=120):
    info = wav_info(raw)
    require(type(seconds) is int and 30 <= seconds <= 180, 'INVALID_SEGMENT_SECONDS')
    frames = min(seconds * info['rate'], 6_000_000 // (info['channels'] * info['width']))
    require(math.ceil(info['frames'] / frames) <= 120, 'TOO_MANY_AUDIO_SEGMENTS')
    parts = []
    with wave.open(io.BytesIO(raw), 'rb') as source:
        for start in range(0, info['frames'], frames):
            count = min(frames, info['frames'] - start)
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as clip:
                clip.setparams((info['channels'], info['width'], info['rate'], 0, 'NONE', 'not compressed'))
                clip.writeframes(source.readframes(count))
            parts.append({'startMs': start * 1000 / info['rate'], 'endMs': (start + count) * 1000 / info['rate'],
                          'bytes': buffer.getvalue()})
    return info, parts


def make_script(sources, style='solo', title='课程复习', card_ids=()):
    require(style in ('solo', 'dialogue') and sources and len(sources) <= 6, 'INVALID_SCRIPT_INPUT')
    segments = []
    def add(kind, text='', evidence=(), pause=0):
        segments.append({'id': 'part-'+str(len(segments)+1), 'kind': kind, 'speaker': 'B' if style == 'dialogue' and kind in ('recall', 'answer') else 'A',
                         'text': text, 'evidence': clone(list(evidence)), 'pauseSeconds': pause, 'reviewed': False})
    add('intro', '这次复习先核对资料，再闭卷回忆；听完不等于已经掌握。')
    for source in sources:
        quote = source['quote'][:600]
        refs = [{'sourceId': source['id'], 'documentId': source['documentId'], 'version': source['version'], 'quote': quote,
                 'title': source.get('title', '课程资料'), 'location': source.get('location')}]
        add('explain', quote, refs)
        add('pitfall', '核对这条原文中的适用条件，不把它扩展成资料没有说的结论。', refs)
        add('recall', '暂停看资料。请用自己的话复述刚才的要点。', refs)
        add('pause', pause=8)
        add('answer', quote, refs)
    add('review', '对照原文核对，再进入题库实际作答或对复习卡明确自评。')
    return {'title': title[:160], 'style': style, 'segments': segments, 'cardIds': list(card_ids),
            'origin': 'original-excerpt-template', 'masteryUpdated': False, 'verified': False}


def validate_script(value, sources):
    require(isinstance(value, dict) and value.get('style') in ('solo', 'dialogue') and isinstance(value.get('title'), str)
            and 0 < len(value['title'].strip()) <= 160, 'INVALID_REVIEW_SCRIPT')
    segments = value.get('segments')
    require(isinstance(segments, list) and 1 <= len(segments) <= 40, 'INVALID_REVIEW_SCRIPT')
    by_id, seen, total = {s['id']: s for s in sources}, set(), 0
    for part in segments:
        require(isinstance(part, dict) and isinstance(part.get('id'), str) and 0 < len(part['id']) <= 80 and part['id'] not in seen
                and part.get('speaker') in ('A', 'B') and part.get('kind') in ('intro', 'explain', 'pitfall', 'recall', 'pause', 'answer', 'review')
                and isinstance(part.get('text'), str) and len(part['text']) <= 800 and part.get('reviewed') is True, 'SCRIPT_REVIEW_REQUIRED')
        seen.add(part['id']); total += len(part['text'])
        if part['kind'] == 'pause':
            require(type(part.get('pauseSeconds')) is int and 1 <= part['pauseSeconds'] <= 30 and not part['text'], 'INVALID_RECALL_PAUSE')
        else:
            require(part['text'].strip(), 'INVALID_REVIEW_SCRIPT')
        refs = part.get('evidence')
        require(isinstance(refs, list) and len(refs) <= 6, 'INVALID_SCRIPT_EVIDENCE')
        require(refs or part['kind'] in ('intro', 'pause', 'review'), 'SCRIPT_EVIDENCE_REQUIRED')
        for ref in refs:
            require(isinstance(ref, dict), 'INVALID_SCRIPT_EVIDENCE')
            source = by_id.get(ref.get('sourceId'))
            require(source and ref.get('version') == source['version'] and isinstance(ref.get('quote'), str)
                    and ref['quote'].strip() and ref['quote'] in source['quote'], 'STALE_SCRIPT_EVIDENCE')
            ref.update(documentId=source['documentId'], title=source.get('title', '课程资料'), location=source.get('location'))
    require(total <= 20000, 'SCRIPT_TOO_LONG')
    require(isinstance(value.get('cardIds', []), list) and len(value.get('cardIds', [])) <= 20
            and all(isinstance(key, str) for key in value.get('cardIds', [])), 'INVALID_REVIEW_CARDS')
    parents = value.get('parents', [])
    require(isinstance(parents, list) and len(parents) <= 26 and all(isinstance(p, dict) and isinstance(p.get('id'), str)
            and type(p.get('revision')) is int and p['revision'] > 0 for p in parents), 'INVALID_SCRIPT_PARENT')
    return {**clone(value), 'verified': True, 'masteryUpdated': False, 'reviewMethod': 'explicit-user-review'}


def srt_timestamp(ms):
    ms = int(ms)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def assemble_wav(segments, read):
    """Actual PCM durations, including recall silence; no inferred word alignment."""
    first = next((p for p in segments if p.get('audioHash')), None)
    require(first, 'AUDIO_NOT_READY')
    info = wav_info(read(first['audioHash']))
    output, timeline, cursor, size = io.BytesIO(), [], 0, 0
    with wave.open(output, 'wb') as result:
        result.setparams((info['channels'], info['width'], info['rate'], 0, 'NONE', 'not compressed'))
        for part in segments:
            if part['kind'] == 'pause':
                frames = info['rate'] * part['pauseSeconds']
                pcm = (b'\x80' if info['width'] == 1 else b'\0') * (frames * info['channels'] * info['width'])
            else:
                require(part.get('audioHash'), 'AUDIO_NOT_READY')
                raw = read(part['audioHash']); current = wav_info(raw)
                require(all(current[k] == info[k] for k in ('channels', 'width', 'rate')), 'INCOMPATIBLE_AUDIO_FORMATS')
                with wave.open(io.BytesIO(raw), 'rb') as clip:
                    frames = clip.getnframes(); pcm = clip.readframes(frames)
            size += len(pcm)
            require(size <= MAX_ORIGINAL, 'AUDIO_EXPORT_TOO_LARGE')
            end = cursor + frames * 1000 / info['rate']
            timeline.append({'id': part['id'], 'startMs': cursor, 'endMs': end, 'text': part['text'], 'speaker': part['speaker'], 'kind': part['kind']})
            result.writeframesraw(pcm); cursor = end
    return output.getvalue(), timeline
