"""Reproducible author smoke evaluation. No paid APIs unless --live-api is explicit."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import statistics
import tempfile
import time
import tracemalloc

from .common import dumps, require
from .platform import Platform
from .rag_http import configured_service
from .rag_search import compress, conflicts, lexical, rewrite_query
from .rag_service import RagService


async def finish(platform, job):
    platform.jobs.stopped = False
    async with asyncio.timeout(120):
        while True:
            await platform.jobs.tick()
            row = platform.jobs.get(job["id"], platform.user_id)
            if row["status"] in ("succeeded", "failed", "unknown", "cancelled"):
                task = platform.jobs.active.get(job["id"])
                if task:
                    await task
                require(row["status"] == "succeeded", "EVAL_JOB_"+row["status"].upper())
                return row["result"]
            await asyncio.sleep(.02)


async def evaluate(dataset, *, live_api=False, budget=2000):
    root = Path(__file__).resolve().parents[2]
    data = json.loads(Path(dataset).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="xueya-rag-eval-") as folder:
        platform = Platform(Path(folder))
        tracemalloc.start()
        try:
            rag = configured_service(platform, root) if live_api else RagService(platform)
            scope, ids, fixed = platform.scope(), {}, []
            for index, doc in enumerate(data["documents"]):
                result = await finish(platform, rag.upload(scope, doc["text"].encode(), doc["name"], f"eval-{index}"))
                document_id = result["documentId"]
                ids[doc["name"]] = document_id
                text = doc["text"]
                for offset in range(0, len(text), 520):
                    fixed.append({"id": f"fixed-{index}-{offset}", "documentId": document_id, "title": doc["name"], "start": offset, "end": min(offset+600, len(text)), "quote": text[offset:offset+600], "blockType": "paragraph"})
                if rag.embedding:
                    await finish(platform, rag.submit(scope, "rag-index", document_id, f"index-{index}"))
            modes = ["fixed-lexical", "lexical", "vector", "hybrid", "rerank"]
            output = {"dataset": str(Path(dataset).name), "description": data["description"], "budget": {"unit": "utf8Bytes", "limit": budget},
                      "liveApi": live_api, "results": {}, "inference": "external-api-only", "humanSupportReview": "not_performed"}
            for mode in modes:
                if mode in ("vector", "hybrid", "rerank") and not rag.embedding or mode == "rerank" and not rag.rerank:
                    output["results"][mode] = {"status": "not_evaluated", "reason": "API provider not configured; no fabricated vectors or scores"}
                    continue
                rows, latency = [], []
                for question in data["questions"]:
                    started = time.perf_counter()
                    if mode == "fixed-lexical":
                        query = rewrite_query(question["query"], question.get("history", []))
                        sources, used = compress(query, lexical(query, fixed), budget=budget)
                        result = {"sources": sources, "conflicts": conflicts(sources), "warnings": [], "budget": {"used": used}}
                    else:
                        result = await rag.search(scope, question["query"], history=question.get("history", []), mode=mode, budget=budget)
                    latency.append((time.perf_counter()-started)*1000)
                    if question.get("unanswerable"):
                        passed = not result["sources"]
                    elif question.get("conflict"):
                        passed = bool(result["conflicts"]) and all(any(q in s["quote"] for s in result["sources"]) for q in question["quotes"])
                    else:
                        passed = any(s["documentId"] == ids[question["document"]] and question["quote"] in s["quote"] for s in result["sources"])
                    rows.append({"query": question["query"], "passed": passed, "sourceCount": len(result["sources"]), "warnings": result["warnings"], "usedBytes": result["budget"]["used"]})
                positive = [r for r, q in zip(rows, data["questions"]) if not q.get("unanswerable") and not q.get("conflict")]
                negatives = [r for r, q in zip(rows, data["questions"]) if q.get("unanswerable")]
                output["results"][mode] = {"status": "evaluated", "passed": sum(r["passed"] for r in rows), "count": len(rows),
                                           "goldExcerptRecallAt6": sum(r["passed"] for r in positive)/max(1, len(positive)),
                                           "unanswerableAccuracy": sum(r["passed"] for r in negatives)/max(1, len(negatives)),
                                           "p50Ms": round(statistics.median(latency), 3), "p95Ms": round(sorted(latency)[max(0, int(.95*len(latency))-1)], 3), "rows": rows}
            _, peak = tracemalloc.get_traced_memory()
            output.update(pythonTracemallocPeakBytes=peak, apiInvocations=platform.db.one("SELECT count(*) n FROM invocations")["n"],
                          usage=[json.loads(r["usage_json"]) for r in platform.db.all("SELECT usage_json FROM invocations WHERE usage_json IS NOT NULL")],
                          cost="not_reported", apiConcurrentLimit=platform.resources.limits["api"], approximateIndex="not_evaluated; exact SQLite entity baseline only")
            return output
        finally:
            tracemalloc.stop()
            await platform.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parents[2]/"evals/rag/golden.json")
    parser.add_argument("--output", type=Path, default=Path("test-results/rag-eval.json"))
    parser.add_argument("--live-api", action="store_true", help="Explicitly enable configured external API requests (may incur costs)")
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.dataset, live_api=args.live_api))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dumps(result), encoding="utf-8")
    print(dumps({"output": str(args.output), "modes": {mode: {k: v for k, v in r.items() if k != "rows"} for mode, r in result["results"].items()}}))


if __name__ == "__main__":
    main()
