"""Current deterministic retrieval and ordinary document extraction; no local AI inference."""
from __future__ import annotations
import re
from .learning import SOURCES


def sanitize_sources(value, catalog=None, limit=6, quote_limit=3000):
    catalog, output = SOURCES if catalog is None else catalog, []
    for item in value[:limit] if isinstance(value, list) else []:
        source = next((s for s in catalog if s["id"] == item), None) if isinstance(item, str) else item
        if not isinstance(source, dict) or not isinstance(source.get("id"), str) or not isinstance(source.get("quote"), str):
            continue
        if any(s["id"] == source["id"][:150] for s in output):
            continue
        output.append({**source, "id": source["id"][:150], "title": str(source.get("title", "课程资料"))[:200], "location": str(source.get("location", "文本片段"))[:150], "quote": source["quote"][:quote_limit]})
    return output


def retrieve(question, library):
    query = str(question).lower()
    latin = re.findall(r"[a-z0-9_]{2,}", query)
    words = re.sub(r"[^\u4e00-\u9fff]", " ", query).split()
    grams = {word[i:i+2] for word in words for i in range(len(word)-1)}
    scored = []
    for source in library:
        hay = (source.get("title", "") + " " + source["quote"]).lower()
        score = sum(5 for k in source.get("keywords", []) if k.lower() in query)
        score += sum(2 for word in latin if word in hay) + sum(1 for word in grams if word in hay)
        if score >= 2:
            scored.append((score, source))
    return [source for _, source in sorted(scored, key=lambda row: -row[0])[:4]]


def extract_chunks(text, document):
    from .rag_parse import assemble, structured_chunks
    import hashlib
    text = text.replace("\r\n", "\n")
    parsed = assemble([{"number": None, "text": text, "method": "utf8", "needsOcr": False}], "md" if document.get("kind") == "md" or document["name"].endswith(".md") else "txt", document.get("fileHash") or hashlib.sha256(text.encode()).hexdigest())
    return structured_chunks(parsed, document)


def parse_document(buffer: bytes, kind: str):
    from .rag_parse import parse_structured
    return parse_structured(buffer, kind)
