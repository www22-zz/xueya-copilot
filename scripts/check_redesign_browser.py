"""Capture 2026-11 workbench screens and report console errors / horizontal overflow.

Local verification helper for the 408 / personalized-learning / library / Hot100
redesign. Needs a running local service (default http://127.0.0.1:4173) and an
installed Chromium-family browser (see scripts/browser_runtime.py). It only opens
routes and toggles local UI; it never submits model requests.

Usage:
    python -m scripts.check_redesign_browser --out test-results/redesign-shots
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from scripts.browser_runtime import browser_path

ROUTES = [
    ("exams", "#space/exams", "viewport"),
    ("video-catalog", "#space/materials/video", "viewport"),
    ("personalized-plan", "#space/materials/plan", "viewport"),
    ("library-manage", "#space/knowledge", "viewport"),
    ("hot100", "#space/practice/hot100", "viewport"),
    ("exams-mobile", "#space/exams", "mobile"),
    ("video-catalog-mobile", "#space/materials/video", "mobile"),
    ("personalized-plan-mobile", "#space/materials/plan", "mobile"),
    ("library-manage-mobile", "#space/knowledge", "mobile"),
    ("hot100-mobile", "#space/practice/hot100", "mobile"),
]


def probe(page):
    return page.evaluate(
        """() => ({
            title: document.title,
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            text: (document.querySelector('#spaceContent')?.innerText || '').replace(/\\s+/g, ' ').slice(0, 400)
        })"""
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:4173")
    parser.add_argument("--out", default="test-results/redesign-shots")
    parser.add_argument("--timeout", type=int, default=20000)
    parser.add_argument("--cookie", default="", help="optional xueya_session value for a configured local account")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {"base": args.base, "pages": [], "consoleErrors": [], "pageErrors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_path(), headless=True, args=["--no-sandbox"])
        try:
            for name, route, mode in ROUTES:
                context = browser.new_context(viewport={"width": 390, "height": 844} if mode == "mobile" else {"width": 1440, "height": 960})
                if args.cookie:
                    host = args.base.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
                    context.add_cookies([{"name": "xueya_session", "value": args.cookie, "domain": host, "path": "/"}])
                page = context.new_page()
                console, page_errors = [], []
                page.on("console", lambda message, bucket=console: bucket.append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error, bucket=page_errors: bucket.append(str(error)))
                try:
                    page.goto(args.base + "/" + route, wait_until="networkidle", timeout=args.timeout)
                    time.sleep(0.8)
                    shot = out / f"{name}.png"
                    page.screenshot(path=str(shot), full_page=True)
                    state = probe(page)
                    overflow = state["scrollWidth"] - state["clientWidth"] > 2
                    report["pages"].append({"name": name, "route": route, "mode": mode,
                                            "screenshot": shot.name, "overflow": overflow, **state})
                except Exception as error:  # noqa: BLE001 - report instead of aborting the batch
                    report["pages"].append({"name": name, "route": route, "mode": mode, "error": str(error)[:500]})
                finally:
                    for message in console:
                        report["consoleErrors"].append({"page": name, "message": message[:500]})
                    for message in page_errors:
                        report["pageErrors"].append({"page": name, "message": message[:500]})
                    page.close()
                    context.close()
        finally:
            browser.close()
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bad = [row for row in report["pages"] if row.get("error") or row.get("overflow")]
    print(json.dumps({"pages": len(report["pages"]), "problems": len(bad) + len(report["consoleErrors"]) + len(report["pageErrors"]),
                      "report": str(out / "report.json")}, ensure_ascii=False))
    for row in bad:
        print("PROBLEM", row.get("name"), row.get("error") or ("horizontal overflow" if row.get("overflow") else ""))


if __name__ == "__main__":
    main()
