"""MoArk adapters. Credentials stay on the host; never replay unknown submissions.

MinerU's public segments are semantic segments, not guaranteed page numbers.
Submit single-page PDFs inside the user's selected batch to retain exact provenance.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import re

from .common import digest, dumps, require
from .document_limits import PDF_MAX_BYTES, OFFICE_MAX_BYTES
from .rag_api import ApiClient, EmbeddingProvider
from .rag_search import normalize


class QwenEmbeddingProvider(EmbeddingProvider):
    @property
    def identity(self):
        return {"provider": self.settings.base_url, "model": self.settings.model, "revision": self.settings.revision,
                "adapter": "moark-qwen-text-v2",
                "dimension": self.settings.dimension, "normalized": True,
                "documentTask": "text", "queryTask": "text"}

    async def embed(self, scope, texts, *, query=False):
        require(isinstance(texts, list) and 1 <= len(texts) <= 32
                and all(isinstance(t, str) and 0 < len(t.encode()) <= 24_000 for t in texts), "INVALID_EMBEDDING_INPUT")
        # Do not send Jina-specific task/normalized fields to another provider.
        # Use native model dimensions, verified against every response below.
        data = await self.post(scope, "/embeddings", {"input": [{"text": t} for t in texts],
                                                     "dimensions": self.settings.dimension, "encoding_format": "float"})
        require(data.get("model", self.settings.model) == self.settings.model, "EMBEDDING_MODEL_MISMATCH")
        rows = data.get("data")
        require(isinstance(rows, list) and len(rows) == len(texts), "INVALID_EMBEDDING")
        require(all(isinstance(r, dict) and type(r.get("index")) is int for r in rows), "INVALID_EMBEDDING")
        require({r["index"] for r in rows} == set(range(len(texts))), "INVALID_EMBEDDING")
        return [normalize(r.get("embedding"), self.settings.dimension) for r in sorted(rows, key=lambda r: r["index"])]


def single_pdf_page(buffer, page):
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(io.BytesIO(buffer), strict=False)
    require(not reader.is_encrypted and 1 <= page <= len(reader.pages), "INVALID_OCR_PAGES")
    writer, target = PdfWriter(), io.BytesIO()
    writer.add_page(reader.pages[page-1])
    writer.write(target)
    raw = target.getvalue()
    require(len(raw) <= OFFICE_MAX_BYTES, "OCR_BATCH_TOO_LARGE")
    return raw


class MinerUProvider(ApiClient):
    def __init__(self, *args, poll_interval=1.5, **kwargs):
        super().__init__(*args, **kwargs)
        self.poll_interval = poll_interval

    @property
    def identity(self):
        return {**super().identity, "adapter": "moark-mineru-single-page-v1",
                "ocr": True, "formula": True, "table": True, "images": False}

    @staticmethod
    def markdown(value):
        output = value.get("output")
        require(isinstance(output, dict), "INVALID_OCR_RESPONSE")
        segments = output.get("segments")
        if isinstance(segments, list):
            require(all(isinstance(s, dict) and isinstance(s.get("content"), str) for s in segments), "INVALID_OCR_RESPONSE")
            text = "\n\n".join(s["content"] for s in segments)
        else:
            text = output.get("markdown")
        require(isinstance(text, str) and len(text) <= 1_200_000, "INVALID_OCR_RESPONSE")
        return MinerUProvider.clean_text(text)

    @staticmethod
    def clean_text(text):
        # Pro may append generated diagram descriptions and signed image URLs.
        # Retain the raw response separately; these are not verbatim text evidence.
        text = re.sub(r'<details\b[^>]*>.*?</details>', '', text, flags=re.S | re.I)
        text = re.sub(r'!\[[^\]]*\]\([^\n]*\)', '', text)
        return text

    async def recognize(self, scope, buffer, pages):
        require(isinstance(buffer, bytes) and 0 < len(buffer) <= PDF_MAX_BYTES and isinstance(pages, list)
                and 0 < len(pages) <= 20 and all(type(p) is int and p > 0 for p in pages)
                and len(set(pages)) == len(pages), "INVALID_OCR_PAGES")
        result, file_hash = {}, hashlib.sha256(buffer).hexdigest()
        for page in pages:
            key = "mineru-page-" + digest({"file": file_hash, "page": page, "provider": self.identity})[:40]
            row = self.platform.repo.read(scope, "artifact", key)
            receipt = row["value"] if row else None
            if receipt and receipt.get("result"):
                result[page] = {**receipt["result"], "text": self.clean_text(receipt["result"]["text"])}
                continue
            require(not receipt or receipt.get("taskId"), "OCR_SUBMISSION_UNKNOWN")
            raw = await asyncio.to_thread(single_pdf_page, buffer, page)

            async def operation(client, request_id):
                nonlocal receipt
                if not receipt:
                    receipt = {"kind": "mineru-page-receipt", "page": page, "provider": self.identity,
                               "invocationId": request_id, "state": "submitting"}
                    self.platform.repo.put(scope, "artifact", key, receipt, 0)
                    data = await self.exchange(client, "POST", "/async/documents/parse",
                        data={"model": self.settings.model, "is_ocr": "true", "formula_enable": "true",
                              "table_enable": "true", "include_image_base64": "false", "layout_model": "doclayout_yolo"},
                        files={"file": (f"page-{page}.pdf", raw, "application/pdf")})
                    task_id = data.get("task_id")
                    require(isinstance(task_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task_id), "INVALID_OCR_TASK")
                    receipt.update(taskId=task_id, state="submitted")
                    self.platform.repo.put(scope, "artifact", key, receipt)
                while True:
                    # Ignore provider-supplied URLs; use the configured host and validated ID.
                    data = await self.exchange(client, "GET", "/task/"+receipt["taskId"])
                    status = data.get("status")
                    require(status not in ("failed", "error", "cancelled", "canceled"), "OCR_REMOTE_FAILED")
                    if status in ("success", "succeeded", "completed"):
                        raw_file = self.platform.files.put(dumps(data).encode())
                        receipt['rawResultHash'] = raw_file['hash']
                        self.platform.repo.put(scope, 'artifact', key, receipt)
                        text = self.markdown(data)
                        resolved = {"text": text, "method": "ocr-api:"+self.settings.model,
                                    "confidence": None, "bbox": None, "images": [], "dimensions": {},
                                    "rawResultHash": raw_file["hash"]}
                        receipt.update(state="completed", result=resolved)
                        self.platform.repo.put(scope, "artifact", key, receipt)
                        result[page] = resolved
                        return data
                    require(status in ("waiting", "queued", "pending", "processing", "running", "in_progress"), "INVALID_OCR_TASK_STATUS")
                    await asyncio.sleep(self.poll_interval)

            await self.invoke(scope, {"page": page, "fileHash": file_hash}, operation,
                              request_id=receipt["invocationId"] if receipt else None)
        return result
