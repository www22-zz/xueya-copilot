"""Bounded CPU extraction. Offsets address canonical text, never inferred PDF boxes."""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from xml.etree import ElementTree as ET

from pypdf import PdfReader

from .common import AppError, require
from .document_limits import document_limit

PARSER = "structured-v1"
MAX_TEXT = 1_200_000
KINDS = frozenset(("txt", "md", "pdf", "docx", "pptx"))
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


def safe_xml(archive, name):
    entry = archive.getinfo(name)
    require(entry.file_size <= 24_000_000, "DOCUMENT_XML_TOO_LARGE")
    xml = archive.read(entry)
    require(b"<!DOCTYPE" not in xml.upper() and b"<!ENTITY" not in xml.upper(), "UNSAFE_DOCUMENT_XML")
    return ET.fromstring(xml)


def quality(text):
    visible = [c for c in text if not c.isspace()]
    if not visible:
        return 0.0
    return round(sum(c.isprintable() and c != "\ufffd" for c in visible) / len(visible), 4)


def text_blocks(text, page=1, *, markdown=False, method="text", confidence=None):
    """Keep fenced code, display formulae and consecutive table rows indivisible."""
    blocks, lines = [], text.splitlines(keepends=True)
    offset, i = 0, 0
    while i < len(lines):
        start, line = offset, lines[i]
        if not line.strip():
            offset += len(line)
            i += 1
            continue
        kind, level = "paragraph", None
        fence = re.match(r"\s*(`{3,}|~{3,})", line) if markdown else None
        if fence or markdown and line.strip().startswith("$$"):
            kind = "code" if fence else "formula"
            marker = fence[1] if fence else "$$"
            end = i + 1
            if not (kind == "formula" and line.strip().endswith("$$") and len(line.strip()) > 4):
                while end < len(lines):
                    found = lines[end].strip().startswith(marker)
                    end += 1
                    if found:
                        break
        elif markdown and re.match(r"^#{1,6}\s", line):
            kind, level, end = "heading", len(line) - len(line.lstrip("#")), i + 1
        elif markdown and re.match(r"\s*!\[.*\]\(", line):
            kind, end = "image", i + 1
        elif markdown and "|" in line and i + 1 < len(lines) and re.match(r"\s*\|?\s*:?-{3,}", lines[i+1]):
            kind, end = "table", i + 2
            while end < len(lines) and "|" in lines[end] and lines[end].strip():
                end += 1
        else:
            kind = "list" if re.match(r"\s*(?:[-*+] |\d+[.)] )", line) else "paragraph"
            end = i + 1
            while end < len(lines) and lines[end].strip() and not re.match(r"\s*(?:#{1,6}\s|```|~~~|\$\$|[-*+] |\d+[.)] )", lines[end]):
                end += 1
        raw = "".join(lines[i:end])
        left, right = len(raw) - len(raw.lstrip()), len(raw.rstrip())
        if right > left:
            blocks.append({"type": kind, "text": raw[left:right], "start": start+left, "end": start+right,
                           "page": page, "bbox": None, "method": method, "confidence": confidence,
                           **({"level": level} if level else {})})
        offset += len(raw)
        i = end
    return blocks


def assemble(pages, kind, file_hash):
    text, blocks, position = [], [], 0
    for page in pages:
        part = page.pop("text", "")
        require(position + len(part) <= MAX_TEXT, "PARSED_TEXT_TOO_LARGE")
        page.update(start=position, end=position+len(part), quality=quality(part))
        page.setdefault("needsOcr", not part.strip() or quality(part) < .85)
        page.setdefault("bbox", None)
        page.setdefault("originalPage", page["number"])
        local = page.pop("blocks", None)
        if local is None:
            local = text_blocks(part, page["number"], markdown=kind == "md", method=page["method"])
        for block in local:
            blocks.append({**block, "id": f"block-{len(blocks)}", "start": block["start"]+position, "end": block["end"]+position})
        text.append(part)
        position += len(part)+1
    canonical = "\n".join(text)
    require(len(canonical) <= MAX_TEXT, "PARSED_TEXT_TOO_LARGE")
    return {"ok": True, "kind": kind, "text": canonical, "pages": pages, "blocks": blocks,
            "parserVersion": PARSER + ("-pptx-context-v1" if kind == "pptx" else ""), "fileHash": file_hash, "textHash": hashlib.sha256(canonical.encode()).hexdigest(),
            "empty": not bool(canonical.strip()), "warnings": ["OCR_REQUIRED"] if any(p["needsOcr"] for p in pages) else []}


def office_pages(buffer, kind):
    with zipfile.ZipFile(io.BytesIO(buffer)) as archive:
        entries = archive.infolist()
        require(len(entries) <= 10_000 and sum(e.file_size for e in entries) <= 64_000_000, "DOCUMENT_ARCHIVE_TOO_LARGE")
        names = [e.filename for e in entries]
        require(len(names) == len(set(names)), "INVALID_DOCUMENT_ARCHIVE")
        if kind == "docx":
            root = safe_xml(archive, "word/document.xml")
            body = root.find(W+"body")
            require(body is not None, "PARSE_FAILED")
            blocks, parts, position = [], [], 0
            for node in body:
                block_type, level = "paragraph", None
                if node.tag == W+"tbl":
                    block_type = "table"
                    rows = [["".join(n.text or "" for n in cell.iter(W+"t")) for cell in row.findall(W+"tc")] for row in node.findall(W+"tr")]
                    part = "\n".join(" | ".join(row) for row in rows)
                else:
                    # Only text nodes: itertext() over the whole paragraph duplicates fields/tails.
                    part = "".join(n.text or "" for n in node.iter() if n.tag in (W+"t", M+"t"))
                    style = node.find(f"{W}pPr/{W}pStyle")
                    style_name = style.get(W+"val", "") if style is not None else ""
                    heading = re.search(r"(?:Heading|标题)([1-6])", style_name, re.I)
                    if heading:
                        block_type, level = "heading", int(heading[1])
                    elif node.find(f".//{W}numPr") is not None:
                        block_type = "list"
                    elif node.find(f".//{M}oMath") is not None:
                        block_type = "formula"
                    elif "code" in style_name.lower():
                        block_type = "code"
                if not part:
                    continue
                math_nodes = list(node.iter(M+"oMath"))
                blocks.append({"type": block_type, "text": part, "start": position, "end": position+len(part), "page": None,
                               "bbox": None, "method": "ooxml", "confidence": None, **({"level": level} if level else {}),
                               **({"mathXml": [ET.tostring(n, encoding="unicode") for n in math_nodes], "mathRepresentation": "ooxml-original; text-is-linearized"} if math_nodes else {})})
                parts.append(part)
                position += len(part)+1
            # DOCX has no stable rendered page numbers. Use section/offset, never guessed pages.
            return [{"number": None, "method": "ooxml", "needsOcr": False, "text": "\n".join(parts), "blocks": blocks}]
        presentation = safe_xml(archive, "ppt/presentation.xml")
        relationships = safe_xml(archive, "ppt/_rels/presentation.xml.rels")
        targets = {n.get("Id"): n.get("Target") for n in relationships if n.get("TargetMode") != "External"}
        pages = []
        for slide in presentation.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId"):
            target = targets.get(slide.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"), "")
            require(bool(re.fullmatch(r"(?:/ppt/)?slides/slide\d+\.xml", target)), "INVALID_SLIDE_TARGET")
            root = safe_xml(archive, target.lstrip("/") if target.startswith("/") else "ppt/"+target)
            shape_tree = root.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}spTree")
            blocks, parts, position = [], [], 0
            # OOXML shape order is retained; it is not a claim about arbitrary visual columns.
            for shape in list(shape_tree) if shape_tree is not None else [root]:
                table = shape.find(".//"+A+"tbl")
                if table is not None:
                    rows = [["".join(n.text or "" for n in cell.iter(A+"t")) for cell in row.findall(A+"tc")] for row in table.findall(A+"tr")]
                    values = [("table", "\n".join(" | ".join(row) for row in rows))]
                else:
                    values = [("paragraph", "".join(n.text or "" for n in p.iter(A+"t"))) for p in shape.iter(A+"p")]
                for block_type, part in values:
                    if not part:
                        continue
                    blocks.append({"type": block_type, "text": part, "start": position, "end": position+len(part), "page": len(pages)+1,
                                   "bbox": None, "method": "ooxml-slide-order", "confidence": None})
                    parts.append(part)
                    position += len(part)+1
            # A slide often encodes one sentence as many separate text boxes or
            # paragraphs. Preserve contiguous prose on this slide as one parent
            # so retrieval does not return a lone word/number without its context.
            # Tables remain atomic; canonical text, slide order and offsets stay exact.
            merged = []
            for block in blocks:
                if merged and block['type'] == merged[-1]['type'] == 'paragraph':
                    parent = merged[-1]
                    parent['text'] += '\n' + block['text']
                    parent['end'] = block['end']
                else:
                    merged.append(dict(block))
            pages.append({"number": len(pages)+1, "method": "ooxml-slide-order", "text": "\n".join(parts), "blocks": merged,
                          "hasImages": root.find('.//{http://schemas.openxmlformats.org/presentationml/2006/main}pic') is not None})
            require(len(pages) <= 3000, "DOCUMENT_TOO_MANY_PAGES")
        return pages


def parse_structured(buffer: bytes, kind: str):
    require(kind in KINDS, "UNSUPPORTED_DOCUMENT_TYPE")
    require(isinstance(buffer, bytes) and 0 < len(buffer) <= document_limit(kind), "FILE_TOO_LARGE")
    try:
        if kind in ("txt", "md"):
            require(len(buffer) <= 1_048_576, "FILE_TOO_LARGE")
            text = buffer.decode("utf-8-sig", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
            pages = [{"number": None, "method": "utf8", "needsOcr": False, "text": text}]
        elif kind in ("docx", "pptx"):
            pages = office_pages(buffer, kind)
        else:
            reader = PdfReader(io.BytesIO(buffer), strict=False)
            require(not reader.is_encrypted, "DOCUMENT_ENCRYPTED")
            require(0 < len(reader.pages) <= 3000, "DOCUMENT_TOO_MANY_PAGES")
            pages, size = [], 0
            for number, page in enumerate(reader.pages, 1):
                part = (page.extract_text(extraction_mode="layout") or "") if "/Contents" in page else ""
                size += len(part)+1
                require(size <= MAX_TEXT, "PARSED_TEXT_TOO_LARGE")
                resources = page.get("/Resources", {})
                resources = resources.get_object() if hasattr(resources, "get_object") else resources
                objects = resources.get("/XObject", {})
                objects = objects.get_object() if hasattr(objects, "get_object") else objects
                has_image = any(obj.get_object().get("/Subtype") == "/Image" for obj in objects.values())
                pages.append({"number": number, "method": "pypdf-layout", "text": part,
                              "hasImages": has_image, "readingOrder": "layout-heuristic",
                              "needsOcr": not part.strip() or quality(part) < .85 or has_image and len(part.strip()) < 40,
                              "width": float(page.mediabox.width), "height": float(page.mediabox.height)})
        return assemble(pages, kind, hashlib.sha256(buffer).hexdigest())
    except AppError:
        raise
    except UnicodeError as error:
        raise AppError("INVALID_TEXT_ENCODING") from error
    except Exception as error:
        raise AppError("PARSE_FAILED") from error


def structured_chunks(parsed, document, *, size=600, overlap=80):
    require(type(size) is int and 100 <= size <= 4000 and type(overlap) is int and 0 <= overlap < size//2, "INVALID_CHUNK_OPTIONS")
    text, chunks, path = parsed["text"], [], []
    revision = document.get("contentRevision", 1)
    for block in parsed["blocks"]:
        if block["type"] == "image":
            # An image reference is location metadata, not recognized textual evidence.
            continue
        if block["type"] == "heading":
            level = block.get("level", 1)
            path = path[:level-1] + [re.sub(r"^#+\s*", "", block["text"])]
        atomic = block["type"] in ("table", "code", "formula", "image")
        # Oversize atomic blocks remain intact and are omitted from embedding if over budget.
        starts = [block["start"]] if atomic else range(block["start"], block["end"], size-overlap)
        parent = "parent-"+hashlib.sha256(f"{document['id']}:{revision}:{block['id']}".encode()).hexdigest()[:32]
        for start in starts:
            end = block["end"] if atomic else min(start+size, block["end"])
            quote = text[start:end]
            if not quote.strip():
                continue
            token = f"{document['id']}:{revision}:{parsed['textHash']}:{start}:{end}"
            chunks.append({"id": "chunk-"+hashlib.sha256(token.encode()).hexdigest()[:40], "documentId": document["id"],
                           "documentRevision": revision, "fileHash": parsed["fileHash"], "textHash": parsed["textHash"],
                           "title": document["name"], "quote": quote, "start": start, "end": end,
                           "page": block["page"], "bbox": block.get("bbox"), "blockId": block["id"], "blockType": block["type"],
                           "parentId": parent, "sectionPath": list(path), "parserVersion": parsed["parserVersion"],
                           "method": block["method"], "confidence": block.get("confidence"), "keywords": [], "sample": False,
                           "location": (f"第 {block['page']} 页" if block["page"] is not None else
                                        (" > ".join(path[-2:])+" · " if parsed['kind'] == 'md' and path else "")+f"字符 {start}–{end}")})
    return chunks
