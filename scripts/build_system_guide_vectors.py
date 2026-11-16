r"""Build the system-guide embedding index used by the companion (桌宠小涯).

The guide lives in docs/guide/*.md. This script splits it into heading-aligned
chunks, adds metadata (docPath / title / module / sectionPath / feature /
route / steps / contentHash) and embeds every chunk with the SAME
EmbeddingProvider used by the course RAG (configured in .env). Vectors are
written to materials/system-guide/vectors.json next to a manifest.json that
records model identity, dimension, document hashes and content hashes.

Safety: the script builds a throw-away Platform in .tmp with its own SQLite
file; it never touches .xueya-data. Credentials are only read from the host
config and never printed. API failures retry a small, bounded number of times
with exponential backoff; there is no unbounded automatic spending.

Usage:
    .venv\Scripts\python.exe scripts/build_system_guide_vectors.py
    .venv\Scripts\python.exe scripts/build_system_guide_vectors.py --force
    .venv\Scripts\python.exe scripts/build_system_guide_vectors.py --check

--check validates the manifest/vectors against the current docs without any
network call (it only compares the configured embedding identity when available).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GUIDE_DIR = ROOT / "docs" / "guide"
OUT_DIR = ROOT / "materials" / "system-guide"
SCHEMA = "system-guide-vectors-v1"
VECTOR_FILE = "vectors.json"
MANIFEST_FILE = "manifest.json"
MIN_CHUNK = 260
MAX_CHUNK = 650
BATCH = 16
MAX_ATTEMPTS = 5

FRONT = re.compile(r"^---\s*$")
ROUTE_RE = re.compile(r"#space/[A-Za-z0-9][A-Za-z0-9/_-]*")
HEAD_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
NUMBERED = re.compile(r"^\s*(\d{1,2})[.、)]\s*(.+?)\s*$")
INLINE_STEPS = re.compile(r"操作步骤[：:]\s*(.+)")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_text(text: str) -> str:
    return " ".join(text.split())


def content_hash(text: str) -> str:
    return sha256_bytes(canonical_text(text).encode("utf-8"))


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Parse the tiny front-matter block (title/module/routes). Returns (meta, body)."""
    meta: dict = {}
    if not text.startswith("---"):
        return meta, text
    lines = text.splitlines()
    if not lines or not FRONT.match(lines[0]):
        return meta, text
    end = None
    for index in range(1, len(lines)):
        if FRONT.match(lines[index]):
            end = index
            break
    if end is None:
        return meta, text
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if not key:
            continue
        if value.startswith("["):
            try:
                meta[key] = json.loads(value)
            except ValueError:
                meta[key] = []
        else:
            meta[key] = value.strip('"\'')
    return meta, "\n".join(lines[end + 1:])


def extract_steps(text: str) -> list[str]:
    """Collect numbered steps from the document's 操作步骤 section."""
    lines = text.splitlines()
    steps: list[str] = []
    inside = False
    for line in lines:
        match = HEAD_RE.match(line)
        if match:
            title = match.group(2).strip()
            inside = "操作步骤" in title
            continue
        if not inside:
            continue
        numbered = NUMBERED.match(line)
        if numbered:
            steps.append(numbered.group(2).strip())
            if len(steps) >= 12:
                break
    return steps


def inline_steps(text: str) -> list[str]:
    match = INLINE_STEPS.search(text)
    if not match:
        return []
    raw = match.group(1).split("\n", 1)[0]
    parts = re.split(r"\s*\d{1,2}[.、)]\s*", " " + raw)
    return [part.strip(" 。；;") for part in parts if part.strip(" 。；;")][:12]


def route_of(text: str, fallback: list[str]) -> str:
    for match in ROUTE_RE.finditer(text):
        route = match.group(0).rstrip("/.,;，。；")
        if "{" not in route:
            return route
    candidates = [route for route in (fallback or [])
                  if isinstance(route, str) and route.startswith("#space/") and "{" not in route]
    # Only a document that represents a single page may inherit its page route.
    return candidates[0] if len(candidates) == 1 else ""


def split_paragraphs(lines: list[str], limit: int) -> list[list[str]]:
    """Split an over-long block on blank lines, then hard-wrap by characters."""
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    chunks: list[list[str]] = []
    for paragraph in paragraphs:
        text = "\n".join(paragraph)
        if len(text) <= limit:
            chunks.append([text])
            continue
        buffer = ""
        for line in paragraph:
            if len(buffer) + len(line) + 1 > limit and buffer:
                chunks.append([buffer])
                buffer = ""
            buffer = (buffer + "\n" + line).strip() if buffer else line
        if buffer:
            chunks.append([buffer])
    return chunks


def hard_split(text: str, limit: int) -> list[str]:
    """Split text that has no paragraph breaks (lists or markdown tables)."""
    lines = text.splitlines()
    table = len(lines) >= 3 and lines[0].lstrip().startswith("|") and bool(re.fullmatch(r"\s*\|(?:\s*:?-{2,}:?\s*\|)+\s*", lines[1]))
    header = lines[:2] if table else []
    body = lines[2:] if table else lines
    parts: list[str] = []
    buffer: list[str] = []
    size = 0
    for line in body:
        if buffer and size + len(line) + 1 > limit:
            parts.append("\n".join(buffer))
            buffer, size = [], 0
        buffer.append(line)
        size += len(line) + 1
    if buffer:
        parts.append("\n".join(buffer))
    if table and header:
        prefix = "\n".join(header)
        return [prefix + "\n" + part for part in parts] if parts else [prefix]
    return parts or ([text] if text else [])


def ensure_limit(parts: list[str], limit: int) -> list[str]:
    """Final guard: every returned chunk respects the size budget."""
    output: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        output.extend(hard_split(part, limit) if len(part) > limit else [part])
    return output


def _section_to_chunks(text_lines: list[str]) -> list[str]:
    """Return chunk bodies (at most MAX_CHUNK) for one h2 section body."""
    joined = "\n".join(text_lines).strip()
    if not joined:
        return []
    if len(joined) <= MAX_CHUNK:
        return [joined]
    buckets: list[list[str]] = []
    current: list[str] = []
    for line in text_lines:
        match = HEAD_RE.match(line)
        if match and len(match.group(1)) == 3 and current:
            buckets.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        buckets.append(current)
    if len(buckets) == 1:
        body = "\n".join(buckets[0])
        return ensure_limit([part for part in (p.strip() for p in re.split(r"\n{2,}", body)) if part], MAX_CHUNK)
    merged: list[list[str]] = []
    pending: list[str] = []
    for bucket in buckets:
        candidate = pending + bucket
        if pending and len("\n".join(candidate)) > MAX_CHUNK:
            merged.append(pending)
            pending = list(bucket)
        else:
            pending = candidate
        if len("\n".join(pending)) >= MIN_CHUNK:
            continue
    if pending:
        merged.append(pending)
    result: list[str] = []
    for bucket in merged:
        text = "\n".join(bucket).strip()
        if not text:
            continue
        if len(text) <= MAX_CHUNK:
            result.append(text)
            continue
        result.extend("\n".join(part).strip() for part in split_paragraphs(bucket, MAX_CHUNK) if "\n".join(part).strip())
    return ensure_limit(result, MAX_CHUNK)


def parse_document(path: Path, root: Path) -> dict:
    """Parse one guide document into h2 sections with h3 children."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    meta, body = parse_front_matter(text)
    doc_path = path.relative_to(root).as_posix()
    title = str(meta.get("title") or "").strip()
    module = str(meta.get("module") or "").strip()
    routes = meta.get("routes") if isinstance(meta.get("routes"), list) else []
    doc_steps = extract_steps(body)
    lines = body.splitlines()
    sections: list[dict] = []
    current: dict | None = None
    for line in lines:
        match = HEAD_RE.match(line)
        if match:
            level = len(match.group(1))
            heading = match.group(2).strip()
            if level == 1:
                title = title or heading
                current = None
                continue
            if level == 2:
                current = {"heading": heading, "lines": [], "children": []}
                sections.append(current)
                continue
            if level == 3 and current is not None:
                current["children"].append({"heading": heading, "lines": []})
                continue
        if current is not None:
            if current["children"]:
                current["children"][-1]["lines"].append(line)
            else:
                current["lines"].append(line)
    if not title:
        title = path.stem
    return {
        "docPath": doc_path,
        "docHash": sha256_bytes(raw),
        "title": title,
        "module": module,
        "routes": routes,
        "steps": doc_steps,
        "sections": sections,
    }


def chunk_document(document: dict) -> list[dict]:
    """Split one parsed document into retrieval chunks with metadata."""
    chunks: list[dict] = []
    ordered = 0
    for section in document["sections"]:
        heading = section["heading"]
        if section["children"]:
            bodies = []
            for child in section["children"]:
                text = "\n".join(child["lines"]).strip()
                if not text:
                    continue
                bodies.append((child["heading"], text))
            merged: list[tuple[list[str], str]] = []
            pending: list[str] = []
            pending_text = ""
            for child_heading, text in bodies:
                candidate = (pending_text + "\n\n" + text).strip()
                if pending and len(candidate) > MAX_CHUNK:
                    merged.append((pending, pending_text))
                    pending, pending_text = [child_heading], text
                else:
                    pending.append(child_heading)
                    pending_text = candidate
            if pending:
                merged.append((pending, pending_text))
            for headings, text in merged:
                if len(text) > MAX_CHUNK:
                    parts = ensure_limit([p.strip() for p in re.split(r"\n{2,}", text) if p.strip()], MAX_CHUNK)
                    for part_index, part in enumerate(parts):
                        chunks.append(_make_chunk(document, section["heading"], list(headings), part.strip(), ordered, part_index))
                        ordered += 1
                else:
                    chunks.append(_make_chunk(document, section["heading"], list(headings), text, ordered, 0))
                    ordered += 1
        else:
            text = "\n".join(section["lines"]).strip()
            if not text:
                continue
            for part_index, part in enumerate(_section_to_chunks(section["lines"])):
                chunks.append(_make_chunk(document, heading, [], part.strip(), ordered, part_index))
                ordered += 1
    return chunks


GENERIC_HEADINGS = frozenset("""
功能名与作用 作用 所属模块 进入路径 操作步骤 涉及路由 涉及路由（接口与页面） 常见问题
代码依据 功能总览 功能名 操作步骤与限制 常见问题与限制清单 本篇涉及的后端接口
""".split())


def _feature_name(document: dict, h2: str, h3s: list[str]) -> str:
    """Pick a human feature name: explicit 功能： heading first, document title otherwise."""
    for candidate in reversed(h3s):
        cleaned = re.sub(r"^功能[：:]\s*", "", candidate).strip()
        if cleaned and cleaned not in GENERIC_HEADINGS:
            return cleaned
    cleaned = re.sub(r"^功能[：:]\s*", "", h2).strip()
    if cleaned and cleaned not in GENERIC_HEADINGS:
        return cleaned
    return document["title"]


def _make_chunk(document: dict, h2: str, h3s: list[str], text: str, order: int, part: int) -> dict:
    body = text.strip()
    section_path = [h2] + [h for h in h3s if h]
    heading_lines = [f"## {h2}"] + [f"### {h}" for h in h3s if h]
    full_text = "\n".join(heading_lines + [body]) if heading_lines else body
    feature = _feature_name(document, h2, h3s)
    steps = inline_steps(body) or document["steps"]
    routes = []
    for match in ROUTE_RE.finditer(full_text):
        candidate = match.group(0).rstrip("/.,;，。；")
        if "{" not in candidate and candidate not in routes:
            routes.append(candidate)
    route = routes[0] if routes else route_of(full_text, document["routes"])
    return {
        "id": "",
        "docPath": document["docPath"],
        "docHash": document["docHash"],
        "title": document["title"],
        "module": document["module"],
        "feature": feature,
        "sectionPath": section_path,
        "route": route,
        "routes": routes,
        "steps": steps[:12],
        "text": full_text,
        "contentHash": content_hash(full_text),
        "order": order * 100 + part,
    }


def chunk_documents(guide_dir: Path = GUIDE_DIR) -> tuple[list[dict], list[dict], list[str]]:
    """Return (chunks, documents, duplicates) for every *.md guide file."""
    if not guide_dir.is_dir():
        raise SystemExit(f"guide directory missing: {guide_dir}")
    documents: list[dict] = []
    chunks: list[dict] = []
    for path in sorted(guide_dir.glob("*.md")):
        document = parse_document(path, guide_dir)
        documents.append({"path": document["docPath"], "title": document["title"],
                          "sha256": document["docHash"]})
        chunks.extend(chunk_document(document))
    duplicates: list[str] = []
    seen: dict[str, str] = {}
    unique: list[dict] = []
    for chunk in chunks:
        chunk_id = "guide-" + sha256_bytes((chunk["docPath"] + "|" + "|".join(chunk["sectionPath"]) + "|" + chunk["contentHash"]).encode("utf-8"))[:20]
        chunk["id"] = chunk_id
        if chunk["contentHash"] in seen:
            duplicates.append(chunk_id)
            continue
        seen[chunk["contentHash"]] = chunk_id
        unique.append(chunk)
    unique.sort(key=lambda item: (item["docPath"], item["order"], item["id"]))
    for index, chunk in enumerate(unique):
        chunk["order"] = index
    return unique, documents, duplicates


def _load_prior(out_dir: Path, identity: dict) -> dict[str, list[float]]:
    path = out_dir / VECTOR_FILE
    if not path.is_file():
        return {}
    try:
        prior = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if prior.get("schema") != SCHEMA or prior.get("identity") != identity:
        return {}
    dimension = int(identity.get("dimension") or 0)
    reused: dict[str, list[float]] = {}
    for row in prior.get("chunks") or []:
        vector = row.get("embedding")
        if isinstance(vector, list) and len(vector) == dimension and isinstance(row.get("contentHash"), str):
            reused[row["contentHash"]] = vector
    return reused


def _temp_embedding_service(root: Path):
    """Create an isolated Platform + RagService just to borrow the embedding provider."""
    from backend.xueya.platform import Platform
    from backend.xueya.rag_http import configured_service

    base = ROOT / ".tmp" / "system-guide-build"
    base.mkdir(parents=True, exist_ok=True)
    data_dir = Path(tempfile.mkdtemp(prefix="build-", dir=str(base)))
    platform = Platform(data_dir, api_slots=2, recover=False, preserve_legacy_data=True)
    service = configured_service(platform, root)
    return platform, service, data_dir


async def _embed_batches(embedding, scope, texts: list[str], label: str = "") -> list[list[float]]:
    results: list[list[float]] = []
    for start in range(0, len(texts), BATCH):
        batch = texts[start:start + BATCH]
        for attempt in range(MAX_ATTEMPTS):
            try:
                vectors = await embedding.embed(scope, batch)
                results.extend(vectors)
                print(f"  embedded {min(start + BATCH, len(texts))}/{len(texts)} chunks{label}", flush=True)
                break
            except Exception as error:  # noqa: BLE001 - converted into a stable code below
                code = getattr(error, "code", None) or type(error).__name__
                retryable = code in {"RAG_API_REJECTED", "ConnectError", "ReadTimeout", "TimeoutException",
                                     "TransportError", "RemoteProtocolError", "AI_TIMEOUT"} or isinstance(error, (TimeoutError, asyncio.TimeoutError))
                if not retryable or attempt == MAX_ATTEMPTS - 1:
                    raise
                delay = min(30, 2 ** attempt)
                print(f"  embedding attempt {attempt + 1} failed ({code}); retrying in {delay}s", flush=True)
                await asyncio.sleep(delay)
        else:
            raise SystemExit("embedding failed after retries")
    return results


def _validate_vectors(vectors: list[list[float]], dimension: int) -> None:
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != dimension:
            raise SystemExit(f"INVALID_DIMENSION: expected {dimension}, got {len(vector) if isinstance(vector, list) else type(vector).__name__}")
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if not math.isfinite(norm) or norm <= 0:
            raise SystemExit("INVALID_VECTOR_NORM")
        if any(not math.isfinite(float(value)) for value in vector):
            raise SystemExit("INVALID_VECTOR_VALUE")


def _write_json(path: Path, value: dict, *, pretty: bool) -> bytes:
    if pretty:
        data = json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
    else:
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    return data


async def build(guide_dir: Path, out_dir: Path, *, force: bool = False) -> int:
    chunks, documents, duplicates = chunk_documents(guide_dir)
    if not chunks:
        raise SystemExit("no guide chunks found")
    platform, service, data_dir = _temp_embedding_service(ROOT)
    try:
        embedding = getattr(service, "embedding", None)
        if embedding is None or not getattr(embedding.settings, "key", ""):
            raise SystemExit("EMBEDDING_NOT_CONFIGURED: set RAG_EMBEDDING_* in the local .env")
        identity = embedding.identity
        dimension = int(identity.get("dimension") or 0)
        if dimension <= 0:
            raise SystemExit("INVALID_EMBEDDING_DIMENSION")
        prior = {} if force else _load_prior(out_dir, identity)
        missing = [chunk for chunk in chunks if chunk["contentHash"] not in prior]
        reused = len(chunks) - len(missing)
        print(f"guide chunks: {len(chunks)} | documents: {len(documents)} | reused vectors: {reused} | to embed: {len(missing)}")
        if missing:
            new_vectors = await _embed_batches(embedding, platform.scope("course-default"), [chunk["text"] for chunk in missing])
            for chunk, vector in zip(missing, new_vectors):
                prior[chunk["contentHash"]] = vector
        vectors = [prior[chunk["contentHash"]] for chunk in chunks]
        _validate_vectors(vectors, dimension)
        from datetime import datetime, timezone
        built_at = datetime.now(timezone.utc).isoformat()
        active = [{**chunk, "embedding": prior[chunk["contentHash"]]} for chunk in chunks]
        index_content = sha256_bytes(json.dumps([[row["id"], row["contentHash"]] for row in active], ensure_ascii=False).encode("utf-8"))
        out_dir.mkdir(parents=True, exist_ok=True)
        vectors_payload = {
            "schema": SCHEMA,
            "builtAt": built_at,
            "model": identity.get("model"),
            "dimension": dimension,
            "adapter": identity.get("adapter", ""),
            "identity": identity,
            "chunks": active,
        }
        vector_bytes = _write_json(out_dir / VECTOR_FILE, vectors_payload, pretty=False)
        manifest = {
            "schema": SCHEMA,
            "builtAt": built_at,
            "model": identity.get("model"),
            "dimension": dimension,
            "adapter": identity.get("adapter", ""),
            "identity": identity,
            "vectorFile": VECTOR_FILE,
            "vectorsSha256": sha256_bytes(vector_bytes),
            "vectorsBytes": len(vector_bytes),
            "contentHash": index_content,
            "chunkCount": len(chunks),
            "duplicateChunks": duplicates,
            "documentCount": len(documents),
            "documents": sorted(
                [{"path": doc["path"], "title": doc["title"], "sha256": doc["sha256"],
                  "chunkCount": len([c for c in chunks if c["docPath"] == doc["path"]])} for doc in documents],
                key=lambda item: item["path"]),
            "newEmbeddingRequests": len(missing),
            "reusedChunks": reused,
            "builder": "scripts/build_system_guide_vectors.py",
        }
        _write_json(out_dir / MANIFEST_FILE, manifest, pretty=True)
        print(f"wrote {out_dir / MANIFEST_FILE}")
        print(f"wrote {out_dir / VECTOR_FILE} ({len(vector_bytes)} bytes)")
        print(f"identity: model={identity.get('model')} dimension={dimension} adapter={identity.get('adapter', '')}")
        print(f"build ok: {len(chunks)} chunks, {len(documents)} documents, new requests {len(missing)}, reused {reused}")
        return 0
    finally:
        await platform.close()
        shutil.rmtree(data_dir, ignore_errors=True)


def _configured_identity() -> tuple[dict | None, str]:
    """Return the configured embedding identity without contacting any API."""
    from backend.xueya.rag_http import read_env_file

    env = {**read_env_file(ROOT / ".env"), **os.environ}
    key = env.get("RAG_EMBEDDING_API_KEY", "")
    model = env.get("RAG_EMBEDDING_MODEL", "")
    if not key or not model:
        return None, "EMBEDDING_NOT_CONFIGURED"
    provider = env.get("RAG_EMBEDDING_PROVIDER", "jina")
    base = env.get("RAG_EMBEDDING_BASE_URL", "https://api.moark.com/v1" if provider == "moark-qwen" else "https://api.jina.ai/v1")
    if provider == "moark-qwen":
        default_dimension = "4096" if "8B" in model else "2048"
        dimension = int(env.get("RAG_EMBEDDING_DIMENSION", default_dimension))
        identity = {"provider": base, "model": model, "revision": env.get("RAG_EMBEDDING_REVISION", "1"),
                    "adapter": "moark-qwen-text-v2", "dimension": dimension, "normalized": True,
                    "documentTask": "text", "queryTask": "text"}
    else:
        dimension = int(env.get("RAG_EMBEDDING_DIMENSION", "1024"))
        identity = {"provider": base, "model": model, "revision": env.get("RAG_EMBEDDING_REVISION", "1"),
                    "dimension": dimension, "normalized": True,
                    "documentTask": "retrieval.passage", "queryTask": "retrieval.query"}
    return identity, "ok"


def check(guide_dir: Path, out_dir: Path) -> int:
    problems: list[str] = []
    manifest_path = out_dir / MANIFEST_FILE
    vector_path = out_dir / VECTOR_FILE
    if not manifest_path.is_file():
        print(f"FAIL manifest missing: {manifest_path}")
        return 1
    if not vector_path.is_file():
        print(f"FAIL vectors missing: {vector_path}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    vector_bytes = vector_path.read_bytes()
    vectors_doc = json.loads(vector_bytes.decode("utf-8"))
    dimension = manifest.get("dimension")
    if manifest.get("schema") != SCHEMA or vectors_doc.get("schema") != SCHEMA:
        problems.append("schema_mismatch")
    if sha256_bytes(vector_bytes) != manifest.get("vectorsSha256"):
        problems.append("vectors_sha256_mismatch")
    if vectors_doc.get("identity") != manifest.get("identity"):
        problems.append("identity_mismatch_between_files")
    configured, note = _configured_identity()
    if configured:
        for key in ("model", "dimension", "adapter"):
            if configured.get(key) != manifest.get(key):
                problems.append(f"configured_identity_mismatch:{key}")
    else:
        print(f"note: configured embedding identity unavailable ({note}); skipping identity comparison")
    docs = sorted(guide_dir.glob("*.md"))
    expected = {path.relative_to(guide_dir).as_posix(): sha256_bytes(path.read_bytes()) for path in docs}
    recorded = {row.get("path"): row.get("sha256") for row in manifest.get("documents") or []}
    if set(expected) != set(recorded):
        problems.append("document_coverage_mismatch")
    for path, digest in expected.items():
        if recorded.get(path) != digest:
            problems.append(f"document_changed:{path}")
    chunks = vectors_doc.get("chunks") or []
    if len(chunks) != manifest.get("chunkCount"):
        problems.append("chunk_count_mismatch")
    seen_hashes: set[str] = set()
    for row in chunks:
        if not isinstance(row.get("embedding"), list) or len(row["embedding"]) != dimension:
            problems.append(f"invalid_dimension:{row.get('id')}")
            break
        if any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in row["embedding"]):
            problems.append(f"non_finite_vector:{row.get('id')}")
            break
        normalized = math.sqrt(sum(float(value) ** 2 for value in row["embedding"]))
        if abs(normalized - 1.0) > 1e-3:
            problems.append(f"unnormalized_vector:{row.get('id')}")
            break
        if content_hash(row.get("text", "")) != row.get("contentHash"):
            problems.append(f"content_hash_mismatch:{row.get('id')}")
            break
        if row.get("contentHash") in seen_hashes:
            problems.append(f"duplicate_content_hash:{row.get('id')}")
            break
        seen_hashes.add(row.get("contentHash"))
        if row.get("docPath") not in expected:
            problems.append(f"unknown_doc_path:{row.get('docPath')}")
            break
    for row in manifest.get("documents") or []:
        if not any(chunk.get("docPath") == row.get("path") for chunk in chunks):
            problems.append(f"document_without_chunks:{row.get('path')}")
    recomputed = sha256_bytes(json.dumps([[row.get("id"), row.get("contentHash")] for row in chunks], ensure_ascii=False).encode("utf-8"))
    if recomputed != manifest.get("contentHash"):
        problems.append("content_hash_mismatch")
    print(f"manifest: model={manifest.get('model')} dimension={dimension} adapter={manifest.get('adapter', '')} builtAt={manifest.get('builtAt')}")
    print(f"documents: {len(expected)} | chunks: {len(chunks)} | vectors: {vector_path.stat().st_size} bytes")
    if problems:
        for problem in dict.fromkeys(problems):
            print(f"FAIL {problem}")
        return 1
    print("check ok: manifest, identity, dimension, vectors, content hashes and docs coverage all match")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build/check the companion system-guide vector index")
    parser.add_argument("--guide-dir", default=str(GUIDE_DIR))
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--check", action="store_true", help="validate existing index without embedding")
    parser.add_argument("--force", action="store_true", help="re-embed every chunk instead of reusing vectors")
    options = parser.parse_args(argv)
    guide_dir, out_dir = Path(options.guide_dir), Path(options.out)
    if options.check:
        return check(guide_dir, out_dir)
    return asyncio.run(build(guide_dir, out_dir, force=options.force))


if __name__ == "__main__":
    raise SystemExit(main())
