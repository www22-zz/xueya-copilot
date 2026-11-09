"""HTTP smoke for the 2026-11 workbench endpoints against a local service.

Checks routing, auth and response shapes for the new code-runner and mind-map
endpoints plus static asset delivery. By default it never calls a paid model; the
AI analysis endpoint is only exercised when ``--ai`` is passed explicitly.

Usage:
    python -m scripts.check_workbench_http --base http://127.0.0.1:4199
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile

import httpx

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from backend.xueya.practice_bank import questions


def bootstrap(client, base):
    response = client.get(base + "/api/platform/bootstrap")
    response.raise_for_status()
    value = response.json()
    assert value.get("ok") and value.get("token"), value
    return {"X-Xueya-Token": value["token"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:4199")
    parser.add_argument("--login", default="", help="optional local account as user:password for a configured service")
    parser.add_argument("--ai", action="store_true", default=False,
                        help="also call the paid AI complexity endpoint once (explicit budget consent required)")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    report = {"base": base, "checks": [], "failures": []}

    def check(name, condition, detail=""):
        report["checks"].append({"name": name, "ok": bool(condition), "detail": str(detail)[:300]})
        if not condition:
            report["failures"].append(name)
        print(("PASS " if condition else "FAIL ") + name + ((" :: " + str(detail)[:200]) if detail and not condition else ""))

    with httpx.Client(timeout=30) as client:
        if args.login:
            username, _, password = args.login.partition(':')
            login = client.post(base + "/api/account/login", json={"username": username, "password": password})
            check("local account login", login.status_code == 200, login.text[:200])
        headers = bootstrap(client, base)

        page = client.get(base + "/")
        html = page.text
        for asset in ("css/exam-workbench.css", "css/plan-workbench.css", "css/library-workbench.css",
                      "css/code-workbench.css", "js/plan-workbench.js"):
            check("index links " + asset, asset in html)
        for asset in ("css/exam-workbench.css", "css/plan-workbench.css", "css/library-workbench.css",
                      "css/code-workbench.css", "js/plan-workbench.js", "js/exam-workspace.js",
                      "js/knowledge-base.js", "js/practice-view.js"):
            response = client.get(base + "/" + asset)
            check("asset 200 " + asset, response.status_code == 200, response.status_code)

        hot = {q["id"]: q for q in questions() if q["category"] == "hot100"}
        capabilities = client.get(base + "/api/learning/space/workbench/code/capabilities", headers=headers)
        capability_value = capabilities.json()
        check("capabilities 200", capabilities.status_code == 200 and capability_value.get("ok"), capability_value)
        languages = capability_value.get("languages") or []
        check("capabilities include python", "python" in languages, languages)
        check("capabilities detail", bool((capability_value.get("capabilities") or {}).get("python", {}).get("available")),
              capability_value.get("capabilities"))
        for language in ("python", "cpp", "java"):
            if language not in languages:
                check("code run skips missing " + language, True, "not detected")
                continue
            code = hot["h100-01"]["solutions"].get(language, "")
            run = client.post(base + "/api/learning/space/workbench/code/run",
                              headers=headers, json={"questionId": "h100-01", "language": language, "code": code})
            value = run.json()
            result = value.get("result") or {}
            check("code run passes " + language, run.status_code == 200 and result.get("supported") and result.get("passed"),
                  {k: result.get(k) for k in ("supported", "passed", "passedCases", "totalCases", "error")})
        broken = client.post(base + "/api/learning/space/workbench/code/run",
                             headers=headers, json={"questionId": "h100-01", "language": "python", "code": "def x("})
        broken_result = broken.json().get("result") or {}
        check("code run reports syntax error honestly",
              broken.status_code == 200 and broken_result.get("passed") is False and broken_result.get("error"),
              broken.json())
        missing = client.post(base + "/api/learning/space/workbench/code/run",
                              headers=headers, json={"questionId": "nope", "language": "python", "code": "x=1"})
        check("code run unknown question 404", missing.status_code == 404, missing.json())
        if "cpp" in languages:
            compile_error = client.post(base + "/api/learning/space/workbench/code/run",
                                        headers=headers, json={"questionId": "h100-01", "language": "cpp",
                                                               "code": "class Solution { public: int twoSum( };"})
            compile_result = compile_error.json().get("result") or {}
            check("cpp compile error reported", compile_result.get("passed") is False and "编译" in (compile_result.get("error") or ""),
                  compile_result)

        draft = {"title": "HTTP 冒烟学习路线", "goal": "验证思维导图导出", "startDate": "2026-11-10", "endDate": "2026-11-16",
                 "phases": [{"title": "第一阶段", "tasks": [
                     {"title": "线性表基础", "date": "2026-11-10", "minutes": 30, "difficulty": "基础"},
                     {"title": "栈与队列", "date": "2026-11-11", "minutes": 45, "difficulty": "进阶"}]}]}
        tree = client.post(base + "/api/learning/space/workbench/map/tree", headers=headers, json={"draft": draft})
        tree_value = tree.json()
        check("map tree 200", tree.status_code == 200 and tree_value.get("ok"), tree_value)
        check("map tree has root", bool((tree_value.get("tree") or {}).get("title")))

        export = client.post(base + "/api/learning/space/workbench/map/export", headers=headers, json={"draft": draft})
        check("map export 200", export.status_code == 200, export.status_code)
        check("map export disposition", "attachment" in export.headers.get("content-disposition", ""),
              export.headers.get("content-disposition"))
        try:
            archive = zipfile.ZipFile(io.BytesIO(export.content))
            names = set(archive.namelist())
            content = json.loads(archive.read("content.json").decode("utf-8"))
            check("xmind zip entries", {"content.json", "metadata.json", "manifest.json"} <= names, sorted(names))
            check("xmind content sheet", isinstance(content, list) and content and content[0].get("class") == "sheet",
                  str(content)[:200])
        except Exception as error:  # noqa: BLE001
            check("xmind zip entries", False, error)

        mm = client.post(base + "/api/learning/space/workbench/map/mm", headers=headers, json={"draft": draft})
        check("map mm 200", mm.status_code == 200 and b"<map" in mm.content, mm.status_code)

        no_plan = client.post(base + "/api/learning/space/workbench/map/tree", headers=headers, json={"planId": "plan-missing"})
        check("map missing plan 404", no_plan.status_code == 404, no_plan.json())

        if args.ai:
            analyze = client.post(base + "/api/learning/space/workbench/code/analyze", headers=headers,
                                  json={"questionId": "h100-01", "language": "python", "code": two_sum})
            body = analyze.json()
            check("code analyze responds", analyze.status_code in (200, 409, 503) and "analysis" in body or "error" in body,
                  body)

    out = __import__("pathlib").Path("test-results/workbench-http")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": len(report["checks"]), "failures": report["failures"]}, ensure_ascii=False))
    raise SystemExit(1 if report["failures"] else 0)


if __name__ == "__main__":
    main()
