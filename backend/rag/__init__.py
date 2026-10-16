"""Course extraction and deterministic retrieval; no duplicate database."""
import io
import json
import re
import zipfile
from pathlib import Path
from ..core import require, DomainError
from ..contracts import sanitize_sources, LIMITS


def catalog():
    return json.loads((Path(__file__).parent.parent / 'fixtures' / 'course.json').read_text(encoding='utf-8'))


def extract_chunks(text, document):
    text = str(text).replace('\r\n', '\n').strip()
    return [{'id': f"{document['id']}-chunk-{i}", 'documentId': document['id'], 'title': document['name'],
             'location': f'文本片段 {i+1}', 'quote': text[offset:offset+600], 'keywords': [], 'sample': False}
            for i, offset in enumerate(range(0, len(text), 520))]


def retrieve(question, sources):
    query = str(question).lower()
    latin = re.findall('[a-z0-9_]{2,}', query)
    grams = {word[i:i+2] for word in re.sub('[^\u4e00-\u9fff]', ' ', query).split() for i in range(len(word)-1)}
    hits = []
    for source in sources:
        hay = (source.get('title', '') + ' ' + source['quote']).lower()
        score = sum(5 for key in source.get('keywords', []) if key.lower() in query)
        score += sum(2 for word in latin if word in hay) + sum(1 for word in grams if word in hay)
        if score >= 2:
            hits.append((score, source))
    return [source for _, source in sorted(hits, key=lambda x: -x[0])[:4]]


def parse_document(buffer, kind):
    require(len(buffer) <= LIMITS['fileBytes'], 'FILE_TOO_LARGE')
    require(kind in ('pdf', 'docx'), 'UNSUPPORTED_DOCUMENT_TYPE')
    try:
        if kind == 'pdf':
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(buffer))
            require(not reader.is_encrypted, 'ENCRYPTED_DOCUMENT')
            pieces, count = [], 0
            for page in reader.pages:
                text = page.extract_text() or ''
                pieces.append(text[:LIMITS['parsedCharacters']-count])
                count += len(pieces[-1])
                if count >= LIMITS['parsedCharacters']:
                    break
            text = '\n'.join(pieces)
        else:
            with zipfile.ZipFile(io.BytesIO(buffer)) as archive:
                require(sum(x.file_size for x in archive.infolist()) <= 64*1024*1024, 'DOCUMENT_EXPANSION_LIMIT')
            from docx import Document
            document = Document(io.BytesIO(buffer))
            text = '\n'.join([p.text for p in document.paragraphs] + ['\t'.join(c.text for c in row.cells) for table in document.tables for row in table.rows])
        text = text[:LIMITS['parsedCharacters']].strip()
        return {'ok': True, 'text': text, 'kind': kind, **({'empty': True} if not text else {})}
    except DomainError:
        raise
    except Exception:
        raise DomainError('PARSE_FAILED') from None


class RagService:
    def __init__(self, sources=None):
        self.sources = catalog()['sources'] if sources is None else sources

    async def prepare_sources(self, sources):
        return sanitize_sources(sources, self.sources)

    async def retrieve(self, question, sources=None):
        return retrieve(question, self.sources if sources is None else sources)

    async def ingest(self, text, document):
        require(isinstance(text, str) and isinstance(document, dict) and document.get('id') and document.get('name'), 'INVALID_DOCUMENT')
        return {'document': document, 'sources': extract_chunks(text, document)}

    async def parse_document(self, buffer, kind):
        import asyncio
        return await asyncio.to_thread(parse_document, buffer, kind)
