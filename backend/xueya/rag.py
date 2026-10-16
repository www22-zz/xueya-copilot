"""Current deterministic retrieval and ordinary document extraction; no local AI inference."""
from __future__ import annotations
import io
import re
import zipfile
from xml.etree import ElementTree
from pypdf import PdfReader
from .common import AppError, require
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
    text = text.replace("\r\n", "\n").strip()
    return [{"id": f"{document['id']}-chunk-{i}", "documentId": document["id"], "title": document["name"], "location": f"文本片段 {i+1}", "quote": text[offset:offset+600], "keywords": [], "sample": False} for i, offset in enumerate(range(0, len(text), 520))]


def parse_document(buffer: bytes, kind: str):
    require(kind in ("pdf", "docx", "txt", "md"), "UNSUPPORTED_DOCUMENT_TYPE")
    require(0 < len(buffer) <= 10485760, "FILE_TOO_LARGE")
    try:
        if kind in ("txt", "md"):
            require(len(buffer) <= 1048576, "FILE_TOO_LARGE")
            text = buffer.decode("utf-8", errors="strict")
        elif kind == "docx":
            with zipfile.ZipFile(io.BytesIO(buffer)) as archive:
                entry = archive.getinfo("word/document.xml")
                require(entry.file_size <= 24000000, "DOCUMENT_XML_TOO_LARGE")
                xml = archive.read(entry)
                require(b"<!DOCTYPE" not in xml.upper() and b"<!ENTITY" not in xml.upper(), "UNSAFE_DOCUMENT_XML")
                root = ElementTree.fromstring(xml)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                text = "\n".join("".join(p.itertext()) for p in root.findall(".//w:p", ns))
        else:
            reader = PdfReader(io.BytesIO(buffer), strict=False)
            require(len(reader.pages) <= 3000, "DOCUMENT_TOO_MANY_PAGES")
            parts, size = [], 0
            for page in reader.pages:
                part = page.extract_text() or ""
                parts.append(part)
                size += len(part)
                if size >= 1200000:
                    break
            text = "\n".join(parts)
        text = text[:1200000]
        return {"ok": True, "text": text, "kind": kind, **({"empty": True} if not text.strip() else {})}
    except AppError:
        raise
    except UnicodeError as error:
        raise AppError("INVALID_TEXT_ENCODING") from error
    except Exception as error:
        raise AppError("PARSE_FAILED") from error
