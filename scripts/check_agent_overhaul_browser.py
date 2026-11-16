"""End-to-end acceptance checks for the unattended overhaul (T1/T2/T3/T4).

One command runs an isolated backend (scripts.agent_lab.Server), an isolated
Playwright profile and every acceptance item from the overhaul plan:

  * T1  overview "提问" -> #space/ask with correct chat payload
  * T2  system-guide docs + vectors + companion API/browser answers
  * T3  web-search toggle copy/default/payload + SSE event gating
  * T4.1 no "返回算法学习" button; T4.2 icon centering at 3 viewports
  * T4.3 100 Hot100 rows / 17 official topics / h100-53 reachable & scrolled
  * T4.5 starter-code skeleton + full solution reveal + saved code priority
  * T4.4 demo registry / coverage / API schema / browser playback
  * broad page regression (console errors + horizontal overflow)

The production server on 4173 and the production .xueya-data are never touched.
Outputs: test-results/agent-lab/overhaul-report.json + screenshots in
test-results/agent-lab/overhaul/.

Usage:
  .venv/Scripts/python.exe scripts/check_agent_overhaul_browser.py
  ... --only t1,t3            # subset (prefix match on check ids)
  ... --strict                # SKIP also fails the run
  ... --data-dir overhaul-dev # reuse an isolated data dir (faster iterations)
  ... --skip-model            # skip checks that need the paid model
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('PYTHONUTF8', '1')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
# Environment variables only help child processes; the console that launched us
# may still be a legacy GBK code page where emoji (e.g. the 🌐 toggle label)
# raise UnicodeEncodeError and abort the whole run. Reconfigure the live streams
# once so a check can never fail just because it printed a non-GBK character.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001 - non-standard streams (pytest capture) may refuse
        pass

from scripts.agent_lab import Server, browser_page, http_json  # noqa: E402

OUT = ROOT / 'test-results' / 'agent-lab'
SHOTS = OUT / 'overhaul'
PRACTICE_BANK = ROOT / 'backend' / 'xueya' / 'data' / 'practice_bank.json'
OFFICIAL_BANK = ROOT / 'backend' / 'xueya' / 'data' / 'hot100_official.json'
STARTERS = ROOT / 'backend' / 'xueya' / 'data' / 'hot100_starters.json'
REGISTRY = ROOT / 'frontend' / 'js' / 'algorithm-demo-registry.js'
GUIDE_DIR = ROOT / 'docs' / 'guide'
SYSTEM_VECTORS = ROOT / 'materials' / 'system-guide'

# Views accepted by app.js#route (titles map) plus their real sub-routes.
KNOWN_VIEWS = {'overview', 'ask', 'knowledge', 'practice', 'review', 'materials',
               'algorithms', 'exams', 'analysis', 'courses', 'frameworks'}
KNOWN_ROUTES = {
    '#space/overview', '#space/ask', '#space/courses', '#space/practice',
    '#space/practice/hot100', '#space/exams', '#space/knowledge', '#space/analysis',
    '#space/review', '#space/materials', '#space/algorithms', '#space/frameworks',
    '#space/analysis/plans', '#space/materials/plan', '#space/materials/reading',
    '#space/materials/corpus', '#space/materials/video', '#space/practice/ai',
    '#space/review/materials', '#space/review/algorithms', '#space/review/exams',
    '#space/practice/foundation', '#space/practice/interview', '#space/practice/legacy',
    '#space/practice/exam408',
}
# Legacy/renamed hashes that docs may mention only with an explanation.
EXPLAINED_ALIASES = {'#space/library', '#space/graph', '#space/media'}
EXPLAIN_WORDS = ('旧', '历史', '已改', '迁移', '不再', '兼容', '已移除', '限制', '历史路由', '替换')


class Skip(Exception):
    """The item cannot be verified yet (feature/file missing) - not a crash."""


class Checker:
    def __init__(self):
        self.rows = []
        self.current = None

    def run(self, cid, title, fn):
        self.current = {'id': cid, 'title': title, 'screenshots': []}
        started = time.monotonic()
        try:
            detail = fn() or ''
            status = 'PASS'
        except Skip as error:
            status, detail = 'SKIP', str(error)
        except Exception as error:  # noqa: BLE001 - a failing check must not kill the run
            status = 'FAIL'
            detail = f'{type(error).__name__}: {error}'
            self.current['traceback'] = traceback.format_exc(limit=6)
        self.current.update(status=status, detail=str(detail)[:4000],
                           seconds=round(time.monotonic() - started, 2))
        self.rows.append(self.current)
        mark = {'PASS': 'PASS', 'FAIL': 'FAIL', 'SKIP': 'SKIP'}[status]
        print(f'[{mark}] {cid} - {title}' + (f' :: {str(detail)[:220]}' if detail else ''), flush=True)
        self.current = None
        return status

    def add_shot(self, path):
        if self.current is not None and path:
            relative = str(Path(path).relative_to(OUT)).replace('\\', '/')
            self.current['screenshots'].append(relative)
            return relative
        return str(path)

    def summary(self):
        counts = {'PASS': 0, 'FAIL': 0, 'SKIP': 0}
        for row in self.rows:
            counts[row['status']] = counts.get(row['status'], 0) + 1
        return counts


class Harness:
    """Server + Playwright plumbing shared by the checks."""

    def __init__(self, page, context, errors, session, server):
        self.page = page
        self.context = context
        self.errors = errors
        self.session = session
        self.server = server
        self.bad_responses = []
        self.request_failures = []
        self.network = []
        self.api_bodies = []
        page.on('request', self._on_request)
        page.on('response', self._on_response)
        page.on('requestfailed', self._on_requestfailed)
        # A service worker would bypass Playwright route interception and may serve
        # stale cached JS; these checks always run against the current files.
        try:
            page.add_init_script(
                "try { navigator.serviceWorker.register = () => Promise.reject(new Error('SW_DISABLED_FOR_TESTS')); } catch (error) {}")
            # Observable fetch log: makes "no request reached the app" failures diagnosable.
            page.add_init_script(
                "window.__fetchLog=[];try{const __origFetch=window.fetch.bind(window);"
                "window.fetch=(...args)=>{try{const input=args[0];const url=String(input);"
                "let body=null;try{const init=args[1]||{};if(typeof init.body==='string')body=init.body.slice(0,200000);"
                "else if(typeof input==='object'&&input&&typeof input.body==='string')body=input.body.slice(0,200000);}catch(e){}"
                "window.__fetchLog.push({url:url,body:body});}catch(e){}return __origFetch(...args)};}catch(e){}")
        except Exception:  # noqa: BLE001
            pass

    def _on_request(self, request):
        try:
            if '/api/' in request.url:
                self.network.append((request.method, request.url, bool(request.post_data)))
                raw = request.post_data
                if raw:
                    try:
                        self.api_bodies.append({'url': request.url, 'method': request.method,
                                                'body': json.loads(raw)})
                    except (json.JSONDecodeError, TypeError):
                        pass
        except Exception:  # noqa: BLE001
            pass

    def _on_response(self, response):
        try:
            if response.status >= 400:
                self.bad_responses.append((response.status, response.url))
        except Exception:  # noqa: BLE001
            pass

    def _on_requestfailed(self, request):
        try:
            self.request_failures.append((request.url, request.failure))
        except Exception:  # noqa: BLE001
            pass

    def api(self, path, method='GET', body=None, timeout=90):
        headers = {'X-Xueya-Token': self.session.get('token') or '', 'Cookie': self.session.get('cookie') or ''}
        value, _ = http_json(self.server.base + path, method=method, body=body, headers=headers, timeout=timeout)
        return value

    def reset_diagnostics(self):
        self.errors.clear()
        self.bad_responses.clear()
        self.request_failures.clear()
        self.network.clear()
        self.api_bodies.clear()

    def body_mark(self):
        return len(self.api_bodies)

    def clear_fetch_log(self):
        try:
            self.page.evaluate('window.__fetchLog = []')
        except Exception:  # noqa: BLE001
            pass

    def wait_api_body(self, url_suffix, *, start=0, timeout=40, message='request not captured'):
        def find():
            for row in self.api_bodies[start:]:
                if row['url'].split('?', 1)[0].endswith(url_suffix):
                    return row['body']
            # Fallback: the page-side fetch wrapper is authoritative for app calls
            # even if the automation layer misses the network event.
            try:
                payload = self.page.evaluate("""(suffix) => {
                    const rows = window.__fetchLog || [];
                    for (let i = rows.length - 1; i >= 0; i -= 1) {
                        const row = rows[i] || {};
                        if (typeof row.url === 'string' && row.url.split('?')[0].endsWith(suffix) && row.body) {
                            try { return JSON.parse(row.body); } catch (error) { return null; }
                        }
                    }
                    return null;
                }""", url_suffix)
            except Exception:  # noqa: BLE001
                payload = None
            return payload
        return poll_until(find, timeout=timeout,
                          message=f'{message}; network={self.recent_network()}, fetch={self.fetch_log()}, '
                                  f'errors={self.real_errors()[:3]}')

    def recent_network(self, limit=18):
        return [f'{method} {url}' for method, url, _ in self.network[-limit:]]

    def fetch_log(self):
        try:
            rows = self.page.evaluate('window.__fetchLog || []')
            return [str(row.get('url')) if isinstance(row, dict) else str(row) for row in rows[-14:]]
        except Exception:  # noqa: BLE001
            return []

    def real_errors(self):
        """Console/page errors minus favicon/optional-resource 404 noise."""
        noise = re.compile(r"Failed to load resource: the server responded with a status of (?:404|409)", re.I)
        bad = [(code, url) for code, url in self.bad_responses
               if 'favicon' not in url.lower()
               and not (code == 409 and '/api/platform/workspace' in url)]
        pending = list(self.errors)
        if bad:
            # keep the console 404 lines only when they point at something real
            return [e for e in pending if not noise.search(e)] + [f'HTTP {code} {url}' for code, url in bad]
        return [e for e in pending if not noise.search(e)]

    def shot(self, checker, name, full=False):
        SHOTS.mkdir(parents=True, exist_ok=True)
        path = SHOTS / f'{name}.png'
        try:
            self.page.screenshot(path=str(path), full_page=full)
        except Exception:  # noqa: BLE001 - screenshots are evidence, not the check
            return ''
        return checker.add_shot(path)

    def goto(self, route, wait_selector=None, timeout=45000):
        # A hash-only navigation would keep the old JS context (and its in-flight
        # chat); always load a fresh document for deterministic checks.
        self._nav_token = getattr(self, '_nav_token', 0) + 1
        url = f'{self.server.base}/?check={self._nav_token}{route}'
        self.page.goto(url, wait_until='domcontentloaded', timeout=timeout)
        if wait_selector:
            self.page.wait_for_selector(wait_selector, state='attached', timeout=timeout)
        return url

    def wait_text(self, text, timeout=30000):
        self.page.wait_for_function(
            'text => (document.body.innerText || "").includes(text)', arg=text, timeout=timeout)

    def sse(self, path, body, timeout=180):
        url = self.server.base + path
        request = urllib.request.Request(
            url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), method='POST',
            headers={'Content-Type': 'application/json', 'Accept': 'text/event-stream',
                     'X-Xueya-Token': self.session.get('token') or '',
                     'Cookie': self.session.get('cookie') or ''})
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            return {'error': f'HTTP {error.code}', 'events': []}
        kind = response.headers.get('content-type') or ''
        if 'text/event-stream' not in kind:
            return {'error': 'NOT_SSE: ' + response.read(400).decode('utf-8', 'replace'), 'events': []}
        events = []
        try:
            for raw in response:
                line = raw.decode('utf-8', 'replace').strip()
                if line.startswith('data:'):
                    try:
                        events.append(json.loads(line[5:].strip()))
                    except json.JSONDecodeError:
                        pass
                if len(events) > 4000:
                    break
        finally:
            response.close()
        return {'error': None, 'events': events}


class ApiClient:
    """Token+cookie authenticated JSON client for the isolated server."""

    def __init__(self, server, session):
        self.server = server
        self.session = session

    def api(self, path, method='GET', body=None, timeout=90):
        headers = {'X-Xueya-Token': self.session.get('token') or '',
                   'Cookie': self.session.get('cookie') or ''}
        value, _ = http_json(self.server.base + path, method=method, body=body,
                             headers=headers, timeout=timeout)
        return value


# --------------------------------------------------------------------------- #
# pure data / filesystem audits
# --------------------------------------------------------------------------- #

def load_practice_data():
    bank = json.loads(PRACTICE_BANK.read_text(encoding='utf-8'))
    hot = [q for q in bank['questions'] if q.get('category') == 'hot100']
    official = json.loads(OFFICIAL_BANK.read_text(encoding='utf-8'))
    topics = {}
    for row in official['questions']:
        topics.setdefault(row['topic'], []).append(row['number'])
    return bank, hot, topics


def audit_practice_bank(checker):
    def run():
        bank, hot, official_topics = load_practice_data()
        expect(len(hot) == 100, f'Hot100 count {len(hot)} != 100')
        expect(len(official_topics) == 17, f'official topics {len(official_topics)} != 17')
        missing = [q['id'] for q in hot if not q.get('topic')]
        expect(not missing, f'questions without official topic: {missing[:8]}')
        bank_topics = {}
        for question in hot:
            bank_topics.setdefault(question['topic'], set()).add(question['id'])
        expect(set(bank_topics) == set(official_topics),
               f'bank topics != official topics: {sorted(set(bank_topics) ^ set(official_topics))}')
        union = set().union(*bank_topics.values())
        expect(len(union) == 100, f'topic union {len(union)} != 100')
        for topic, numbers in official_topics.items():
            expect(len(bank_topics[topic]) == len(numbers),
                   f'topic {topic}: bank {len(bank_topics[topic])} vs official {len(numbers)}')
        h53 = next((q for q in hot if q['id'] == 'h100-53'), None)
        expect(h53 is not None, 'h100-53 missing from Hot100 bank')
        expect(str(h53.get('leetcodeNumber') or h53.get('number') or '') in ('200', '200.0') or h53.get('title') == '岛屿数量',
               f'h100-53 is not #200 岛屿数量: {h53.get("leetcodeNumber")} {h53.get("title")}')
        per_topic = {topic: len(ids) for topic, ids in bank_topics.items()}
        return f'Hot100=100, official topics=17, union=100, per-topic={json.dumps(per_topic, ensure_ascii=False)}; h100-53 topic={h53["topic"]}'
    return checker.run('audit.practice-bank', '题库与 17 官方专题数据完整性', run)


def audit_starter_file(checker):
    def run():
        if not STARTERS.exists():
            raise Skip(f'{STARTERS.relative_to(ROOT)} 不存在（T4.5 未完成）')
        data = json.loads(STARTERS.read_text(encoding='utf-8'))
        questions = data.get('questions') or {}
        expect(isinstance(questions, dict) and len(questions) == 100, f'starter entries {len(questions)} != 100')
        _bank, hot, _topics = load_practice_data()
        bank_by_id = {q['id']: q for q in hot}
        checked = 0
        for qid, languages in questions.items():
            expect(qid in bank_by_id, f'starter for unknown question {qid}')
            expect(set(languages.keys()) >= {'python', 'cpp', 'java'}, f'{qid} languages {list(languages)}')
            for language in ('python', 'cpp', 'java'):
                starter = (languages.get(language) or '').strip()
                full = ((bank_by_id[qid].get('solutions') or {}).get(language) or '').strip()
                expect(len(starter) > 20, f'{qid}/{language} starter too short')
                expect(starter != full, f'{qid}/{language} starter equals full solution')
                expect(len(starter) < len(full), f'{qid}/{language} starter longer than solution')
            checked += 1
        return f'starters for {checked}/100 questions, three languages, all shorter than official solutions'
    return checker.run('audit.startup-starters', 'T4.5 hot100_starters.json 数据校验', run)


def audit_docs_guide(checker):
    def run():
        if not GUIDE_DIR.exists():
            raise Skip('docs/guide/ 不存在（T2 文档未完成）')
        files = sorted(GUIDE_DIR.rglob('*.md'))
        expect(len(files) >= 10, f'docs/guide markdown files {len(files)} < 10')
        file_texts = [(path.name, path.read_text(encoding='utf-8', errors='replace')) for path in files]
        text = '\n'.join(content for _name, content in file_texts)
        routes = set(re.findall(r'#space/[a-zA-Z0-9/_-]+', text))
        unexplained = []
        for route in routes:
            normalized = route.rstrip('/')
            if normalized in KNOWN_ROUTES:
                continue
            head = normalized.split('/')[2] if len(normalized.split('/')) > 2 else ''
            mentions = [content for _name, content in file_texts if normalized in content]
            if not mentions:
                continue
            if normalized in EXPLAINED_ALIASES or head not in KNOWN_VIEWS:
                # legacy/renamed hashes are fine when the mentioning document explains it
                if all(any(word in content for word in EXPLAIN_WORDS) for content in mentions):
                    continue
            unexplained.append(normalized)
        expect(not unexplained, f'docs reference unknown/unexplained routes: {sorted(set(unexplained))[:6]}')
        required_topics = ['算法', '408', '资料库', '问答', '计划', '分析', '练习', '错题', '设置', '账号', '限制']
        missing = [topic for topic in required_topics if topic not in text]
        expect(not missing, f'docs missing required topics: {missing}')
        total_chars = sum(len(path.read_text(encoding='utf-8', errors='replace')) for path in files)
        expect(total_chars >= 8000, f'docs total {total_chars} chars < 8000')
        return f'{len(files)} docs, {total_chars} chars, {len(routes)} distinct #space routes, all routes known'
    return checker.run('audit.docs-guide', 'T2 系统百科文档（≥10 篇、真实路由、覆盖主题）', run)


def audit_system_vectors(checker):
    def run():
        if not SYSTEM_VECTORS.exists():
            raise Skip('materials/system-guide/ 不存在（T2 向量未构建）')
        manifests = [path for path in SYSTEM_VECTORS.rglob('*.json')
                     if 'manifest' in path.name.lower() or path.name == 'vectors.json']
        expect(manifests, f'no manifest/vectors json under {SYSTEM_VECTORS.relative_to(ROOT)}')
        manifest = None
        for path in manifests:
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and (value.get('dimension') or value.get('dim')):
                manifest = (path, value)
                break
        expect(manifest is not None, f'no manifest with dimension found in {[p.name for p in manifests]}')
        path, value = manifest
        dimension = int(value.get('dimension') or value.get('dim') or 0)
        expect(dimension == 4096, f'embedding dimension {dimension} != 4096')
        chunks = value.get('chunks') or value.get('items') or value.get('entries')
        chunks = chunks if isinstance(chunks, list) else []
        count = len(chunks) or int(value.get('count') or value.get('chunkCount') or 0)
        expect(count >= 20, f'vector chunk count {count} < 20')
        # vector payload file: find vectors and inspect
        vector_file = None
        for candidate in SYSTEM_VECTORS.rglob('*.json'):
            if candidate == path:
                continue
            try:
                data = json.loads(candidate.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                continue
            rows = data if isinstance(data, list) else (data.get('chunks') or data.get('vectors') or data.get('items') or [])
            if isinstance(rows, list) and rows and isinstance(rows[0], dict) and (
                    isinstance(rows[0].get('vector'), list) or isinstance(rows[0].get('embedding'), list)):
                vector_file = (candidate, rows)
                break
        expect(vector_file is not None, 'no vectors payload file found under materials/system-guide')
        vector_path, rows = vector_file
        expect(len(rows) >= 20, f'vector rows {len(rows)} < 20')
        for row in rows[:5]:
            vector = row.get('vector') or row.get('embedding')
            expect(len(vector) == 4096, f'{vector_path.name}: vector length {len(vector)} != 4096')
        texts = []
        for row in rows:
            for key in ('text', 'content', 'chunk', 'excerpt'):
                if isinstance(row.get(key), str):
                    texts.append(row[key])
                    break
        joined = '\n'.join(texts)
        expect('算法练习' in joined or '算法学习' in joined, 'system-guide vectors do not contain an algorithm-practice chunk')
        hashes = [row.get('hash') or row.get('contentHash') for row in rows if row.get('hash') or row.get('contentHash')]
        expect(len(hashes) == len(set(hashes)), 'duplicate content hashes in vector rows')
        return (f'{vector_path.name}: {len(rows)} vectors x {len(rows[0].get("vector") or rows[0].get("embedding"))} dim, '
                f'{len(texts)} chunks with text, 算法练习 chunk present, hashes unique')
    return checker.run('audit.system-vectors', 'T2 系统百科向量文件（4096 维/数量/内容哈希）', run)


def audit_demo_coverage(checker):
    def run():
        coverage_path = ROOT / 'test-results' / 'algorithm-demo-coverage.json'
        alternative = OUT / 'algorithm-demo-coverage.json'
        if not coverage_path.exists() and alternative.exists():
            coverage_path = alternative
        if not coverage_path.exists():
            raise Skip('test-results/algorithm-demo-coverage.json 不存在（T4.4 引擎未完成）')
        value = json.loads(coverage_path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise AssertionError('coverage json is not an object')
        summary = value.get('summary') or {}
        questions = value.get('questions') or value.get('results') or []
        if isinstance(questions, dict):
            questions = list(questions.values())
        expect(isinstance(questions, list) and len(questions) >= 80,
               f'coverage rows {len(questions) if isinstance(questions, list) else "?"} < 80')
        total = int(summary.get('totalQuestions') or len(questions))
        ok_questions = int(summary.get('okQuestions') or sum(1 for row in questions
                                                              if isinstance(row, dict) and row.get('ok')))
        total_samples = int(summary.get('totalSamples') or 0)
        ok_samples = int(summary.get('okSamples') or 0)
        failed_samples = int(summary.get('failedSamples') or 0)
        expect(total >= 80, f'total demo questions {total} < 80')
        expect(ok_questions >= 80, f'ok questions {ok_questions} < 80')
        failures = value.get('failures') or []
        expect(not failures, f'coverage lists failures: {list(failures)[:3]}')
        if total_samples:
            expect(failed_samples == 0 and ok_samples == total_samples,
                   f'samples ok {ok_samples}/{total_samples}, failed {failed_samples}')
        # every row must be a real trace with steps
        for row in questions[:5]:
            if not isinstance(row, dict):
                continue
            for sample in (row.get('samples') or [])[:2]:
                expect(sample.get('ok') is True and int(sample.get('steps') or 0) >= 2,
                       f'{row.get("questionId")}: sample {sample.get("sampleIndex")} has no real steps')
        schema = str(summary.get('schemaVersion') or '')
        return (f'{ok_questions}/{total} questions, {ok_samples}/{total_samples} samples, '
                f'{len(failures)} failures, schema={schema or "n/a"}')

    return checker.run('audit.demo-coverage', 'T4.4 演示覆盖率文件（真实统计）', run)


def registry_ids():
    if not REGISTRY.exists():
        return None, {}
    text = REGISTRY.read_text(encoding='utf-8', errors='replace')
    match = re.search(r'XueyaAlgorithmDemoIds\s*=\s*(\[[^\]]*\])', text, re.S)
    ids = []
    if match:
        try:
            ids = json.loads(match.group(1).replace("'", '"'))
        except json.JSONDecodeError:
            ids = re.findall(r'"([^"]+)"', match.group(1)) or re.findall(r"'([^']+)'", match.group(1))
    meta = {}
    meta_match = re.search(r'XueyaAlgorithmDemoMeta\s*=\s*(\{.*?\})\s*;?\s*$', text, re.S | re.M)
    if not meta_match:
        meta_match = re.search(r'XueyaAlgorithmDemoMeta\s*=\s*(\{.*?\})\s*;', text, re.S)
    if meta_match:
        try:
            meta = json.loads(meta_match.group(1).replace("'", '"'))
        except json.JSONDecodeError:
            meta = {}
    return ids, meta


def expect(condition, message=''):
    if not condition:
        raise AssertionError(message or 'assertion failed')


def normalize_output(value):
    if isinstance(value, str):
        text = value.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return value


def _numbers(value):
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, (int, float)):
        text = str(value)
        return [text[:-2] if text.endswith('.0') else text]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_numbers(item))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_numbers(item))
        return out
    return []


def outputs_match(result, expected):
    """JSON-aware comparison: list/dict results vs official sample text.

    Design questions return an operation-result array while the official sample
    output is a human sentence (e.g. "get 的返回值依次为 1、-1、-1、3、4"); fall back
    to comparing the ordered numeric sequence in that case.
    """
    if normalize_output(result) == normalize_output(expected):
        return True
    if isinstance(expected, str):
        expected_numbers = re.findall(r'-?\d+(?:\.\d+)?', expected)
        actual_numbers = _numbers(result)
        if expected_numbers and [value.rstrip('0').rstrip('.') if '.' in value else value
                                 for value in expected_numbers] == actual_numbers:
            return True
        if expected_numbers:
            expected_clean = [str(float(value)).rstrip('0').rstrip('.') if '.' in value else value
                              for value in expected_numbers]
            if expected_clean == actual_numbers:
                return True
    return False


# --------------------------------------------------------------------------- #
# shared browser helpers
# --------------------------------------------------------------------------- #

def wait_for(page, script, timeout=30000, arg=None):
    page.wait_for_function(script, arg=arg, timeout=timeout)


def poll_until(fn, timeout=30, interval=0.15, message='condition not met'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = fn()
            if value:
                return value
        except Exception:  # noqa: BLE001
            pass
        time.sleep(interval)
    raise AssertionError(message)


def open_hot100(harness, timeout=90000):
    """Open Hot100 and clear any filter persisted by a previous check/run."""
    page = harness.page
    harness.goto('#space/practice/hot100', wait_selector='#practiceModule')
    deadline = time.monotonic() + timeout / 1000
    cleared = False
    while time.monotonic() < deadline:
        rows = page.locator('.practice-row').count()
        if rows >= 100:
            time.sleep(0.6)  # let the list paint/layout settle
            return page
        if not cleared:
            cleared = True
            try:
                page.evaluate("""() => {
                    const clear = document.querySelector('[data-action="clear-filters"]');
                    if (clear) clear.click();
                    const all = document.querySelector('[data-action="hot-topic"][data-topic=""]');
                    if (all && !all.classList.contains('is-active')) all.click();
                }""")
            except Exception:  # noqa: BLE001
                pass
            retry = page.locator('[data-action="retry-sync"]')
            if retry.count() and retry.first.is_visible():
                try:
                    retry.first.click()
                except Exception:  # noqa: BLE001
                    pass
        time.sleep(0.8)
    errors = harness.real_errors()
    module_text = page.evaluate("() => (document.querySelector('#practiceModule')?.innerText || '').slice(0, 240)")
    raise AssertionError(f'Hot100 list did not reach 100 rows; module={module_text!r}; errors={errors[:3]}')


def visible_rows(page):
    return page.locator('.practice-row:visible').count()


def tag_topic_button(page, topic):
    return page.evaluate(
        """(topic) => {
            const buttons = [...document.querySelectorAll('button,[role=button],a')];
            const matches = buttons.filter(button => (button.innerText || '').replace(/\\s+/g, '').includes(topic));
            matches.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
            const target = matches.find(button => button.closest('.practice-units,.hot100-dock,.stitch-capsules-bar,#practiceModule')) || matches[0];
            if (!target) return false;
            document.querySelectorAll('[data-verifier-topic]').forEach(node => delete node.dataset.verifierTopic);
            target.dataset.verifierTopic = topic;
            return true;
        }""", topic)


def tag_button_by_text(page, texts):
    return page.evaluate(
        """(texts) => {
            const buttons = [...document.querySelectorAll('button,a,[role=button]')];
            for (const text of texts) {
                const match = buttons.find(button => (button.innerText || '').replace(/\\s+/g, '').includes(text.replace(/\\s+/g, '')));
                if (match) {
                    document.querySelectorAll('[data-verifier-click]').forEach(node => delete node.dataset.verifierClick);
                    match.dataset.verifierClick = text;
                    return text;
                }
            }
            return null;
        }""", texts)


def send_composer_question(page, question):
    page.wait_for_selector('#chatInput', state='visible', timeout=30000)
    page.fill('#chatInput', question)
    page.press('#chatInput', 'Enter')
    wait_for(page, "() => document.querySelectorAll('#chatThread .message').length > 0", timeout=30000)


# --------------------------------------------------------------------------- #
# isolated server start/stop with stale-lock recovery
# --------------------------------------------------------------------------- #


def _pid_alive(pid):
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def cleanup_stale_lock(data_dir):
    """Remove a server.json left behind by a hard-killed lab server."""
    if data_dir is None:
        return
    lock = Path(data_dir) / 'server.json'
    if not lock.exists():
        return
    try:
        identity = json.loads(lock.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        try:
            lock.unlink()
        except OSError:
            pass
        return
    if not _pid_alive(identity.get('pid') or 0):
        try:
            lock.unlink()
            print(f'[lab] removed stale server lock ({identity.get("pid")})', flush=True)
        except OSError:
            pass


def start_lab_server(name, data_dir, fresh):
    cleanup_stale_lock(data_dir)
    server = Server(fresh=fresh, name=name, data_dir=data_dir)
    try:
        return server.start()
    except RuntimeError as error:
        if 'ANOTHER_PLATFORM_INSTANCE_RUNNING' not in str(error):
            raise
        cleanup_stale_lock(data_dir)
        raise RuntimeError(
            f'{name}: another lab server is still running on {data_dir}; '
            f'wait for it to exit or remove {Path(data_dir) / "server.json"} after verifying the process is gone') from error


# --------------------------------------------------------------------------- #
# isolated workspace fixture (server-backed document so chat payloads carry ids)
# --------------------------------------------------------------------------- #

SEED_DOC_ID = 'doc-verifier-seed'
SEED_CHUNK_ID = 'src-verifier-seed'
SEED_QUOTE = '二叉搜索树的查找复杂度是 O(log n)；中序遍历可以得到递增序列。'


def seed_workspace_document(api):
    """Store one server-backed course document in the isolated account workspace.

    A brand-new lab account has no uploaded materials, so chat requests would carry
    no documentIds. The production account has uploaded documents; this fixture
    recreates that state (document record + chunk) through the public workspace API
    so the end-to-end payload assertions exercise the real client code path.
    """
    seed_doc = {
        'id': SEED_DOC_ID, 'name': '验收资料.md', 'status': '已索引', 'fileHash': 'verifier-seed-hash',
        'remote': True, 'version': 1, 'sourceCount': 1,
        'chunks': [{'id': SEED_CHUNK_ID, 'documentId': SEED_DOC_ID, 'title': '验收资料.md',
                    'location': '资料依据 · 二叉搜索树', 'quote': SEED_QUOTE, 'sample': False}],
    }
    for attempt in range(3):
        value = api.api('/api/platform/workspace')
        workspace = value.get('workspace') or {}
        version = int(workspace.get('version') or 0)
        data = workspace.get('data') or {}
        courses = data.get('courses')
        if not isinstance(courses, list) or not courses:
            data = {'version': 3, 'activeId': 'course-default', 'courses': [
                {'id': 'course-default', 'name': '数据结构', 'archived': False,
                 'data': {'documents': [seed_doc]}}]}
            courses = data['courses']
        else:
            data.setdefault('activeId', courses[0].get('id'))
        changed = False
        for course in courses:
            if not isinstance(course, dict):
                continue
            course_data = course.get('data')
            if not isinstance(course_data, dict):
                course_data = course['data'] = {}
            documents = course_data.get('documents')
            if not isinstance(documents, list):
                documents = course_data['documents'] = []
            documents[:] = [doc for doc in documents if isinstance(doc, dict)
                            and doc.get('id') != SEED_DOC_ID]
            documents.insert(0, seed_doc)
            changed = True
        if not changed:
            raise AssertionError('workspace fixture has no course to attach the document to')
        try:
            saved = api.api('/api/platform/workspace', method='PUT', body={
                'workspace': data, 'expectedVersion': version})
            return int((saved.get('workspace') or {}).get('version') or 0)
        except urllib.error.HTTPError as error:
            if error.code == 409 or attempt == 2:
                raise
            time.sleep(0.2)
    return 0


# --------------------------------------------------------------------------- #
# T1 - overview ask navigation
# --------------------------------------------------------------------------- #

def _require_harness(harness):
    if harness is None:
        raise Skip('no isolated no-model server available for the zero-cost UI flow')


def check_t1(checker, harness):
    def run():
        _require_harness(harness)
        page = harness.page
        harness.reset_diagnostics()
        harness.goto('#space/overview', wait_selector='#overviewPromptInput')
        time.sleep(0.4)

        # empty input must not navigate
        hash_before = page.evaluate('location.hash')
        page.click('#overviewSubmitPromptBtn')
        time.sleep(0.5)
        expect(page.evaluate('location.hash') == hash_before,
               f'empty overview submit navigated to {page.evaluate("location.hash")}')

        # filled input -> #space/ask + question in thread + payload
        question = '二叉搜索树查找的时间复杂度为什么是 O(log n)？'
        before_messages = page.evaluate("document.querySelectorAll('#chatThread .message').length")
        mark = harness.body_mark()
        harness.clear_fetch_log()
        page.fill('#overviewPromptInput', question)
        page.click('#overviewSubmitPromptBtn')
        page.wait_for_function("() => location.hash === '#space/ask'", timeout=15000)
        wait_for(page, """([text, before]) => {
            const thread = document.querySelector('#chatThread');
            if (!thread) return false;
            const users = [...thread.querySelectorAll('.user-message')];
            const last = users[users.length - 1];
            return users.length > 0 && last && (last.innerText || '').includes(text) &&
                   thread.querySelectorAll('.message').length > before;
        }""", arg=[question, before_messages], timeout=30000)
        try:
            body = harness.wait_api_body('/api/agent/stream', start=mark, timeout=40,
                                         message='overview submit did not post /api/agent/stream')
        except AssertionError as error:
            thread = page.evaluate("() => (document.querySelector('#chatThread')?.innerText || '').slice(-300)")
            raise AssertionError(f'{error}; thread_tail={thread!r}')
        expect(body.get('question') == question, f'request question {body.get("question")!r} != {question!r}')
        expect(isinstance(body.get('courseId'), str) and body['courseId'],
               f'request courseId missing: {body.get("courseId")!r}')
        expect(isinstance(body.get('sources'), list), f'request sources not a list: {type(body.get("sources"))}')
        expect(len(body.get('sources') or []) > 0, 'request sources empty (course evidence not sent)')
        expect(isinstance(body.get('documentIds'), list), f'request documentIds not a list: {body.get("documentIds")!r}')
        expect(len(body.get('documentIds') or []) > 0,
               f'request documentIds empty: {body.get("documentIds")!r}')
        expect(body.get('mode') == 'ask', f'request mode {body.get("mode")!r}')
        expect(body.get('webSearch') in (False, None), f'request webSearch should be off: {body.get("webSearch")!r}')
        harness.shot(checker, 't1-overview-ask')
        errors = harness.real_errors()
        expect(not errors, f'console errors: {errors[:4]}')
        return (f'hash=#space/ask, thread contains question, payload question/courseId/sources({len(body["sources"])})/'
                f'documentIds({len(body["documentIds"])})/mode=ask/webSearch=false; empty input did not navigate')
    return checker.run('t1.overview-ask', 'T1 概览「提问」跳转提问页并携带正确上下文', run)


def check_t1_chips(checker, harness):
    def run():
        _require_harness(harness)
        page = harness.page
        harness.goto('#space/overview', wait_selector='.overview-prompt-chip')
        time.sleep(0.3)
        chip = page.locator('.overview-prompt-chip').first
        prompt = chip.get_attribute('data-prompt')
        expect(prompt, 'overview chip has no data-prompt')
        before_messages = page.evaluate("document.querySelectorAll('#chatThread .message').length")
        mark = harness.body_mark()
        harness.clear_fetch_log()
        chip.click()
        page.wait_for_function("() => location.hash === '#space/ask'", timeout=15000)
        wait_for(page, """([text, before]) => {
            const thread = document.querySelector('#chatThread');
            if (!thread) return false;
            const users = [...thread.querySelectorAll('.user-message')];
            const last = users[users.length - 1];
            return users.length > 0 && last && (last.innerText || '').includes(text) &&
                   thread.querySelectorAll('.message').length > before;
        }""", arg=[prompt, before_messages], timeout=30000)
        try:
            body = harness.wait_api_body('/api/agent/stream', start=mark, timeout=40,
                                         message='chip click did not post /api/agent/stream')
        except AssertionError as error:
            thread = page.evaluate("() => (document.querySelector('#chatThread')?.innerText || '').slice(-220)")
            raise AssertionError(f'{error}; fetchLog={harness.fetch_log()}; thread_tail={thread!r}')
        expect(body.get('question') == prompt,
               f'chip request question {body.get("question")!r} != {prompt!r}')
        return f'chip -> #space/ask, question={prompt!r} sent in payload'
    return checker.run('t1.overview-chips', 'T1 概览快捷问题 chips 同样跳转并发起问答', run)


def check_t1_real_answer(checker, harness):
    """One real (paid) answer on the model-backed isolated server proves the flow end to end."""

    def run():
        page = harness.page
        harness.reset_diagnostics()
        harness.goto('#space/overview', wait_selector='#overviewPromptInput')
        time.sleep(0.5)
        question = '用一句话说明二叉搜索树的查找复杂度'
        before_messages = page.evaluate("document.querySelectorAll('#chatThread .message').length")
        mark = harness.body_mark()
        harness.clear_fetch_log()
        page.fill('#overviewPromptInput', question)
        page.click('#overviewSubmitPromptBtn')
        page.wait_for_function("() => location.hash === '#space/ask'", timeout=15000)
        body = harness.wait_api_body('/api/agent/stream', start=mark, timeout=40,
                                     message='real ask did not post /api/agent/stream')
        expect(body.get('question') == question, 'real ask payload question mismatch')
        wait_for(page, """(before) => {
            if (document.querySelectorAll('#chatThread .message').length <= before) return false;
            if (document.querySelector('[data-stop-chat]')) return false;
            const messages = [...document.querySelectorAll('#chatThread .ai-message')];
            const last = messages[messages.length - 1];
            if (!last) return false;
            const rich = (last.querySelector('.rich-content')?.innerText || '').trim();
            return rich.length > 8 && !last.querySelector('.stream-cursor') &&
                   !(last.innerText || '').includes('未能完成');
        }""", arg=before_messages, timeout=150000)
        answer = page.evaluate("""() => {
            const messages = [...document.querySelectorAll('#chatThread .ai-message')];
            const last = messages[messages.length - 1];
            return (last?.querySelector('.rich-content')?.innerText || '').trim().slice(0, 160);
        }""")
        harness.shot(checker, 't1-real-answer')
        return f'real model answer received ({len(answer)} chars): {answer[:80]!r}'
    return checker.run('t1.real-answer', 'T1 真实模型问答链路（隔离服务、真实 API）', run)


# --------------------------------------------------------------------------- #
# T3 - web search toggle
# --------------------------------------------------------------------------- #

def check_t3_ui(checker, harness):
    def run():
        _require_harness(harness)
        page = harness.page
        harness.goto('#space/ask', wait_selector='[data-toggle-web-search]')
        harness.reset_diagnostics()
        toggle = page.locator('[data-toggle-web-search]')
        text = toggle.inner_text()
        label = toggle.get_attribute('aria-label') or ''
        title = toggle.get_attribute('title') or ''
        pressed = toggle.get_attribute('aria-pressed')
        expect('联网搜索' in text, f'toggle text {text!r} should contain 联网搜索')
        expect('混合检索' not in text and '全网 +' not in text, f'toggle still shows old copy: {text!r}')
        expect('联网搜索' in label, f'aria-label {label!r} should contain 联网搜索')
        expect('联网' in title, f'title {title!r} should mention 联网')
        expect(pressed == 'false', f'default aria-pressed={pressed!r} should be false')
        expect('is-active' not in (toggle.get_attribute('class') or ''), 'toggle should not be active by default')
        toggle.click()
        wait_for(page, "() => document.querySelector('[data-toggle-web-search]').getAttribute('aria-pressed') === 'true'", timeout=10000)
        toggle = page.locator('[data-toggle-web-search]')
        expect('is-active' in (toggle.get_attribute('class') or ''), 'toggle missing is-active class after click')
        time.sleep(0.4)
        toast = page.locator('#toast').inner_text()
        expect('联网搜索' in toast, f'toast copy {toast!r} should mention 联网搜索')
        # course knowledge base participates by default, independent of the switch
        off_text = page.locator('#chatForm').inner_text()
        expect('课程' in off_text or len(off_text) > 0, 'composer rendered empty')
        # toggle back off so later checks start from the default state
        toggle.click()
        wait_for(page, "() => document.querySelector('[data-toggle-web-search]').getAttribute('aria-pressed') === 'false'", timeout=10000)
        return f'text={text!r}, aria-label={label!r}, title={title!r}, default=false, toast={toast!r}'
    return checker.run('t3.toggle-ui', 'T3 联网搜索开关文案/默认关闭/aria 状态', run)


def check_t3_payloads(checker, harness):
    def run():
        _require_harness(harness)
        page = harness.page
        harness.goto('#space/ask', wait_selector='#chatForm')
        time.sleep(0.4)

        def send(question):
            mark = harness.body_mark()
            harness.clear_fetch_log()
            send_composer_question(page, question)
            body = harness.wait_api_body('/api/agent/stream', start=mark, timeout=45,
                                         message=f'no chat request for {question!r}')
            # keep the surface busy-free before the next send
            wait_for(page, "() => !document.querySelector('[data-stop-chat]')", timeout=60000)
            time.sleep(0.4)
            return body

        if page.locator('[data-toggle-web-search]').get_attribute('aria-pressed') == 'true':
            page.locator('[data-toggle-web-search]').click()
            wait_for(page, "() => document.querySelector('[data-toggle-web-search]').getAttribute('aria-pressed') === 'false'")
        off = send('线性表的顺序存储有什么特点？')
        expect(off.get('webSearch') in (False, None), f'webSearch=off payload had webSearch={off.get("webSearch")!r}')
        page.locator('[data-toggle-web-search]').click()
        wait_for(page, "() => document.querySelector('[data-toggle-web-search]').getAttribute('aria-pressed') === 'true'")
        on = send('2026 年数据结构领域有什么新进展？')
        expect(on.get('webSearch') is True, f'webSearch=on payload had webSearch={on.get("webSearch")!r}')
        return 'off -> webSearch=false/absent; on -> webSearch=true (real browser request payloads)'
    return checker.run('t3.payloads', 'T3 开关实际请求 payload（关=false / 开=true）', run)


def check_t3_events(checker, offline):
    """SSE event gating against a no-model server: deterministic and free."""

    def run():
        if offline is None:
            raise Skip('no isolated no-model server available')
        base = {'question': '线性表的顺序存储结构有什么特点', 'courseId': 'course-default', 'mode': 'ask',
                'sources': [], 'history': [], 'learning': {'questions': [], 'records': []},
                'webSearch': False}
        off = offline.sse('/api/agent/stream', base, timeout=120)
        expect(not off['error'], f'webSearch=off stream failed: {off["error"]}')
        expect(len(off['events']) > 0, 'webSearch=off produced no SSE events')
        off_tools = [call.get('tool') for event in off['events'] for call in (event.get('toolCalls') or [])]
        off_labels = [event.get('label', '') for event in off['events']]
        expect('search_web' not in off_tools, f'webSearch=off emitted search_web tool: {off_tools}')
        expect(not any('全网' in label or '联网' in label or '搜索' in label for label in off_labels),
               f'webSearch=off emitted web-search marks: {[l for l in off_labels if "搜索" in l][:4]}')
        on_body = dict(base)
        on_body['webSearch'] = True
        on = offline.sse('/api/agent/stream', on_body, timeout=180)
        expect(not on['error'], f'webSearch=on stream failed: {on["error"]}')
        expect(len(on['events']) > 0, 'webSearch=on produced no SSE events')
        on_tools = [call.get('tool') for event in on['events'] for call in (event.get('toolCalls') or [])]
        expect('search_web' in on_tools,
               f'webSearch=on did NOT emit search_web tool; tools={on_tools[:10]}')
        return (f'off events={len(off["events"])} tools={off_tools[:6]}; '
                f'on events={len(on["events"])} tools={on_tools[:6]}')
    return checker.run('t3.search-events', 'T3 后端 SSE 事件门控（关闭无 search_web / 开启有）', run)


# --------------------------------------------------------------------------- #
# T4.1 / T4.2 / T4.3 / T4.5
# --------------------------------------------------------------------------- #

def check_t41(checker, harness):
    def run():
        page = open_hot100(harness)
        harness.reset_diagnostics()
        texts = page.locator('text=返回算法学习').count()
        expect(texts == 0, 'Hot100 toolbar still contains a 返回算法学习 button')
        back_links = page.evaluate("""() => [...document.querySelectorAll('a')]
            .filter(a => (a.innerText || '').replace(/\\s+/g, '').includes('返回算法学习')).length""")
        expect(back_links == 0, f'{back_links} <a> links still say 返回算法学习')
        expect(visible_rows(page) == 100, f'Hot100 rows {visible_rows(page)} != 100 after button removal')
        expect(page.locator('.hot100-header').count() >= 1, 'hot100 header layout missing')
        return f'no 返回算法学习 element; title row present; {visible_rows(page)} rows'
    return checker.run('t4.1.back-button', 'T4.1 删除「返回算法学习」按钮且布局正常', run)


def check_t42(checker, harness):
    def run():
        page = harness.page
        details = []
        for width in (1440, 1024, 390):
            page.set_viewport_size({'width': width, 'height': 900 if width > 500 else 844})
            open_hot100(harness)
            geo = page.evaluate("""() => {
                const wrap = document.querySelector('.hot100-search-wrap');
                if (!wrap) return null;
                const input = wrap.querySelector('input');
                const icon = wrap.querySelector('.material-symbols-outlined, svg, span');
                if (!input || !icon) return null;
                const wrapRect = wrap.getBoundingClientRect(), inputRect = input.getBoundingClientRect(),
                      iconRect = icon.getBoundingClientRect();
                return {wrap: {x: wrapRect.x, y: wrapRect.y, w: wrapRect.width, h: wrapRect.height},
                        input: {x: inputRect.x, y: inputRect.y, w: inputRect.width, h: inputRect.height},
                        icon: {x: iconRect.x, y: iconRect.y, w: iconRect.width, h: iconRect.height}};
            }""")
            expect(geo, f'width {width}: .hot100-search-wrap/input/icon not found')
            input_center = geo['input']['y'] + geo['input']['h'] / 2
            icon_center = geo['icon']['y'] + geo['icon']['h'] / 2
            delta = abs(input_center - icon_center)
            expect(delta <= 1.5, f'width {width}: icon center {icon_center:.1f} vs input center {input_center:.1f} (delta {delta:.1f}px)')
            expect(geo['icon']['x'] >= geo['wrap']['x'] - 1, f'width {width}: icon outside wrap horizontally')
            details.append(f'{width}: delta={delta:.1f}px')
            if width == 390:
                harness.shot(checker, 't4.2-search-390')
        page.set_viewport_size({'width': 1440, 'height': 960})
        return '; '.join(details)
    return checker.run('t4.2.icon-centering', 'T4.2 搜索框放大镜图标垂直居中（1440/1024/390）', run)


def check_t43(checker, harness):
    def run():
        page = open_hot100(harness)
        harness.reset_diagnostics()
        bank, hot, official_topics = load_practice_data()
        expected = {topic: len(ids) for topic, ids in official_topics.items()}
        expect(visible_rows(page) == 100, f'Hot100 visible rows {visible_rows(page)} != 100')
        expect(page.locator('[data-id="h100-53"]').count() == 1, 'h100-53 (#200) missing from Hot100 list')

        # knowledge-point nav: discover buttons mentioning official topics and their counts
        nav = page.evaluate("""(topics) => {
            const buttons = [...document.querySelectorAll('button,[role=button],a')];
            const found = {};
            for (const button of buttons) {
                const text = (button.innerText || '').replace(/\\s+/g, '');
                for (const topic of topics) {
                    if (text.includes(topic.replace(/\\s+/g, ''))) {
                        const numbers = [...text.matchAll(/(\\d+)/g)].map(match => Number(match[1]));
                        if (!found[topic] || text.length < found[topic].text.length) {
                            found[topic] = {text, numbers};
                        }
                    }
                }
            }
            return found;
        }""", list(expected))
        missing = sorted(topic for topic in expected if topic not in nav)
        expect(not missing, f'knowledge-point navigation missing official topics: {missing}')
        mismatched = {}
        for topic, count in expected.items():
            numbers = nav[topic]['numbers']
            if count not in numbers:
                mismatched[topic] = {'expected': count, 'text': nav[topic]['text']}
        expect(not mismatched, f'knowledge-point counts mismatch: {mismatched}')
        all_texts = page.locator('#practiceModule').inner_text()
        expect('全部知识点' in all_texts or '全部专题' in all_texts, 'no "全部知识点/全部专题" entry found')

        # click 图论 (contains h100-53) and verify filtered list + scroll-into-view
        graph_topic = '图论'
        expect(graph_topic in expected, '图论 topic not in official topics')
        h53 = next(q for q in hot if q['id'] == 'h100-53')
        expect(h53['topic'] == graph_topic, f'h100-53 topic is {h53["topic"]}, expected 图论')
        expect(tag_topic_button(page, graph_topic), f'could not tag 图论 nav button')
        page.click('[data-verifier-topic="图论"]')
        time.sleep(1.0)
        filtered = visible_rows(page)
        expect(filtered == expected[graph_topic],
               f'filtering by 图论 shows {filtered} rows, expected {expected[graph_topic]}')
        expect(page.locator('[data-id="h100-53"]').count() == 1, 'h100-53 not in 图论 filtered list')
        # selecting the row must keep it inside the visible list viewport
        page.locator('[data-id="h100-53"]').first.click()
        time.sleep(0.8)
        in_view = page.evaluate("""() => {
            const row = document.querySelector('[data-id="h100-53"]');
            if (!row) return null;
            const scroller = row.closest('.practice-list,.practice-list-pane,.practice-list-scroll') || row.parentElement;
            const rowRect = row.getBoundingClientRect(), box = scroller.getBoundingClientRect();
            return {rowTop: rowRect.top, rowBottom: rowRect.bottom, boxTop: box.top, boxBottom: box.bottom,
                    visible: rowRect.top >= box.top - 2 && rowRect.bottom <= box.bottom + 2};
        }""")
        expect(in_view, 'h100-53 row/scroller not found after selection')
        expect(in_view['visible'], f'selected h100-53 not scrolled into view: {in_view}')
        # back to all topics -> full list again
        if tag_topic_button(page, '全部'):
            page.click('[data-verifier-topic="全部"]')
            time.sleep(0.8)
        harness.shot(checker, 't4.3-knowledge-points')
        return (f'rows=100, 17 topic nav counts match official data, 图论 filter={filtered} rows, '
                f'h100-53 scrolled into view (row {in_view["rowTop"]:.0f}-{in_view["rowBottom"]:.0f} within {in_view["boxTop"]:.0f}-{in_view["boxBottom"]:.0f})')
    return checker.run('t4.3.knowledge-points', 'T4.3 知识点导航（17 组=100）/h100-53 存在/筛选后滚入可视区', run)


def check_t43_no_hardcode(checker):
    def run():
        source = (ROOT / 'frontend' / 'js' / 'practice-view.js').read_text(encoding='utf-8', errors='replace')
        expect('XueyaAlgorithmDemoIds' in source,
               'practice-view.js does not consume the generated demo registry')
        hardcoded_matches = re.findall(
            r"\[\s*['\"]h100-63['\"]\s*,\s*['\"]h100-53['\"]\s*\]\s*\.includes",
            source)
        expect(not hardcoded_matches,
               'practice-view.js still decides the demo marker with a hard-coded '
               "['h100-63','h100-53'].includes(...) check")
        expect('starterCode' in source, 'practice-view.js does not consume starterCode (T4.5)')
        return 'demo entries driven by XueyaAlgorithmDemoIds registry; starterCode consumed by practice view'
    return checker.run('t4.3.no-hardcode', 'T4.3/T4.5 无写死 #200 特例、读取 starterCode', run)


def check_t45(checker, harness):
    def run():
        page = open_hot100(harness)
        bank, hot, _topics = load_practice_data()
        by_id = {q['id']: q for q in hot}
        question = by_id.get('h100-53')
        expect(question, 'h100-53 missing from bank')
        # filter to the question, then open it
        keyword = page.locator('.hot100-search-wrap input[data-filter=keyword]')
        if keyword.count() == 0:
            keyword = page.locator('input[data-filter=keyword]')
        keyword.first.fill('h100-53')
        time.sleep(0.9)
        expect(page.locator('[data-id="h100-53"]').count() == 1, 'h100-53 not reachable through search filter')
        page.locator('[data-id="h100-53"]').first.click()
        wait_for(page, "() => !!document.querySelector('[data-fixed-ai-answer]')", timeout=20000)
        time.sleep(0.5)
        editor = page.locator('[data-fixed-ai-answer]').first
        initial = editor.input_value()
        full = ((question.get('solutions') or {}).get('python') or '').strip()
        expect(full, 'official python solution missing from bank')
        expect(initial.strip(), 'code editor opened empty instead of a starter skeleton')
        expect(initial.strip() != full, 'code editor still starts from the FULL official solution')
        expect('class Solution' in initial or 'def ' in initial, f'starter skeleton lacks class/method signature: {initial[:120]!r}')
        expect(len(initial.strip()) < len(full), f'starter length {len(initial)} >= solution {len(full)}')
        starter = None
        if STARTERS.exists():
            data = json.loads(STARTERS.read_text(encoding='utf-8'))
            starter = ((data.get('questions') or {}).get('h100-53') or {}).get('python')
        if starter:
            expect(initial.strip() == starter.strip(), 'editor content differs from hot100_starters.json python skeleton')

        # saved code wins over skeleton across question switches
        marker = '# VERIFIER-SAVED-CODE ' + str(int(time.time()))
        editor.fill(marker + '\nclass Solution:\n    pass\n')
        time.sleep(0.8)
        # clear the keyword filter so another question is selectable
        page.evaluate("""() => {
            const clear = document.querySelector('[data-action="clear-filters"]');
            if (clear) clear.click();
        }""")
        wait_for(page, "() => document.querySelectorAll('.practice-row').length >= 100", timeout=30000)
        time.sleep(0.5)
        other_id = 'h100-63' if page.locator('[data-id="h100-63"]').count() else None
        expect(other_id, 'no second hot100 question available for the saved-code switch check')
        page.locator(f'[data-id="{other_id}"]').first.click()
        time.sleep(0.8)
        keyword_box = page.locator('.hot100-search-wrap input[data-filter=keyword]')
        if keyword_box.count() == 0:
            keyword_box = page.locator('input[data-filter=keyword]')
        keyword_box.first.fill('h100-53')
        time.sleep(0.9)
        expect(page.locator('[data-id="h100-53"]').count() == 1, 'h100-53 not reachable after clearing the filter')
        page.locator('[data-id="h100-53"]').first.click()
        wait_for(page, "() => !!document.querySelector('[data-fixed-ai-answer]')", timeout=15000)
        time.sleep(0.5)
        expect(marker in page.locator('[data-fixed-ai-answer]').first.input_value(),
               'saved user code was overwritten by the starter skeleton after switching questions')

        # 查看完整题解 still reveals the real solution
        tagged = tag_button_by_text(page, ['查看完整题解', '查看完整官方题解', '查看题解', '展开官方题解'])
        expect(tagged, 'full-solution reveal button not found')
        page.click('[data-verifier-click]')
        time.sleep(1.0)
        solution = page.locator('.practice-solution').count()
        expect(solution >= 1, 'clicking reveal did not render .practice-solution')
        solution_text = page.locator('.practice-solution').first.inner_text()
        expect(len(solution_text) > 60, 'revealed solution block looks empty')
        harness.shot(checker, 't4.5-starter-and-solution')

        # other languages use their own skeleton (fresh question, no saved code)
        language_details = []
        open_hot100(harness)
        time.sleep(0.4)
        other_question = by_id.get('h100-63')
        expect(other_question, 'h100-63 missing from bank')
        keyword_box = page.locator('.hot100-search-wrap input[data-filter=keyword]')
        if keyword_box.count() == 0:
            keyword_box = page.locator('input[data-filter=keyword]')
        keyword_box.first.fill('h100-63')
        time.sleep(0.9)
        expect(page.locator('[data-id="h100-63"]').count() == 1, 'h100-63 not reachable through search')
        page.locator('[data-id="h100-63"]').first.click()
        wait_for(page, "() => !!document.querySelector('[data-fixed-ai-answer]')", timeout=20000)
        time.sleep(0.5)
        expect(page.locator('select[data-action=language-select]').count() >= 1,
               'language selector not found in the code editor pane')

        def switch_language(value):
            page.evaluate("""(language) => {
                const select = document.querySelector('select[data-action="language-select"]');
                if (!select) return false;
                select.value = language;
                select.dispatchEvent(new Event('change', {bubbles: true}));
                return select.value;
            }""", value)
        python_start = page.locator('[data-fixed-ai-answer]').first.input_value().strip()
        expect(python_start, 'python skeleton empty for h100-63')
        expect(python_start != ((other_question.get('solutions') or {}).get('python') or '').strip(),
               'python editor still starts from the full official solution')
        for value in ('cpp', 'java'):
            official = ((other_question.get('solutions') or {}).get(value) or '').strip()
            switch_language(value)
            time.sleep(0.8)
            current = page.locator('[data-fixed-ai-answer]').first.input_value().strip()
            expect(current, f'{value} skeleton empty')
            expect(current != python_start, f'{value} editor did not switch to the {value} skeleton')
            if official:
                expect(current != official, f'{value} editor still starts from the full official solution')
            language_details.append(value)
        switch_language('python')
        time.sleep(0.6)
        expect(page.locator('[data-fixed-ai-answer]').first.input_value().strip() == python_start,
               'switching back to python did not restore the python starter')
        return (f'starter len={len(initial.strip())} < solution len={len(full)}; saved code preserved across switches; '
                f'solution reveal works; per-language starters={language_details}')
    return checker.run('t4.5.starter-code', 'T4.5 初始骨架/用户代码优先/查看完整题解可用', run)


# --------------------------------------------------------------------------- #
# T4.4 - demo registry / API / browser
# --------------------------------------------------------------------------- #

def check_demo_registry(checker):
    def run():
        ids, meta = registry_ids()
        if ids is None:
            raise Skip(f'{REGISTRY.relative_to(ROOT)} 不存在（T4.4 注册表未生成）')
        expect(len(ids) >= 80, f'registry ids {len(ids)} < 80')
        expect(len(set(ids)) == len(ids), 'registry contains duplicate ids')
        script = ROOT / 'scripts' / 'export_algorithm_demos.py'
        if not script.exists():
            raise Skip('scripts/export_algorithm_demos.py 不存在')
        env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
        result = subprocess.run([sys.executable, str(script), '--check'], cwd=str(ROOT), env=env,
                                capture_output=True, text=True, timeout=300, encoding='utf-8', errors='replace')
        expect(result.returncode == 0,
               f'export_algorithm_demos.py --check exit {result.returncode}: '
               f'{(result.stdout or "")[-400:]}{(result.stderr or "")[-400:]}')
        viz = {}
        for qid, row in (meta or {}).items():
            if isinstance(row, dict):
                viz.setdefault(row.get('viz') or 'unknown', []).append(qid)
        return f'{len(ids)} demo ids, {len(viz)} viz types {sorted(viz)}; --check passed'
    return checker.run('t4.4.registry', 'T4.4 演示注册表与 export_algorithm_demos.py --check', run)


def check_demo_api(checker, harness):
    def run():
        ids, meta = registry_ids()
        if ids is None:
            raise Skip('registry missing (T4.4)')
        viz = {}
        for qid, row in (meta or {}).items():
            if isinstance(row, dict):
                viz.setdefault(row.get('viz') or 'unknown', []).append(qid)
        picks = []
        for qid in ('h100-63', 'h100-53'):
            if qid in ids:
                picks.append(qid)
        for group in viz.values():
            for qid in group[:1]:
                if qid not in picks:
                    picks.append(qid)
        picks = picks[:10]
        expect(picks, 'no demo ids to verify')
        allowed_viz = {'array', 'matrix', 'grid', 'tree', 'linked-list', 'graph', 'dp', 'string',
                       'stack-queue', 'backtracking', 'design', 'scalar'}
        details = []
        for qid in picks:
            first = harness.api(f'/api/learning/space/algorithm-demo/{qid}?sample=0', timeout=120)
            expect(first.get('ok') is True, f'{qid}: ok != true ({first.get("error")})')
            demo = first.get('demo') or {}
            expect(demo.get('schemaVersion') == 'demo-2', f'{qid}: schemaVersion {demo.get("schemaVersion")!r} != demo-2')
            expect(demo.get('questionId') == qid, f'{qid}: questionId {demo.get("questionId")!r}')
            expect(isinstance(demo.get('steps'), list) and len(demo['steps']) >= 2,
                   f'{qid}: steps {len(demo.get("steps") or [])} < 2')
            expect(demo.get('viz') in allowed_viz, f'{qid}: viz {demo.get("viz")!r} not in schema')
            expect(isinstance(demo.get('code'), list) and demo['code'], f'{qid}: code lines missing')
            expect(isinstance(demo.get('inputs'), dict), f'{qid}: inputs missing')
            expect(demo.get('layout') is not None, f'{qid}: layout missing')
            for step in demo['steps'][:3]:
                expect(isinstance(step.get('line'), int), f'{qid}: step line not int')
                expect(isinstance(step.get('note'), str) and step['note'], f'{qid}: step note missing')
                expect(isinstance(step.get('state'), dict), f'{qid}: step state missing')
            sample = demo.get('sample') or {}
            expect(outputs_match(demo.get('result'), sample.get('output')),
                   f'{qid}: result {demo.get("result")!r} != sample output {sample.get("output")!r}')
            sample_count = int(demo.get('sampleCount') or 1)
            for index in range(sample_count):
                if index == 0:
                    continue
                other = harness.api(f'/api/learning/space/algorithm-demo/{qid}?sample={index}', timeout=120)
                other_demo = other.get('demo') or {}
                other_sample = other_demo.get('sample') or {}
                expect(other.get('ok') is True and outputs_match(other_demo.get('result'), other_sample.get('output')),
                       f'{qid} sample {index}: result mismatch or error ({other.get("error")})')
            details.append(f'{qid}/{demo.get("viz")}/{len(demo["steps"])}steps/result={demo.get("result")}')
        return f'verified {len(picks)} demos against schema+sample output: ' + '; '.join(details)
    return checker.run('t4.4.api-schema', 'T4.4 演示 API demo-2 schema 与样例结果一致（抽样、含全部 samples）', run)


DEMO_CONTROL_WORDS = {
    'play': ['播放', '暂停', '继续'],
    'next': ['下一步', '单步', '前进'],
    'prev': ['上一步', '后退'],
    'reset': ['重置', '复位', '回到起点'],
}
DEMO_CONTROL_ATTRS = {'play': 'data-play', 'next': 'data-next', 'prev': 'data-prev', 'reset': 'data-reset'}


def demo_controls(page):
    """Discover demo controls by data attribute or visible label (renderer agnostic)."""
    return page.evaluate("""(spec) => {
        const words = spec.words, attrs = spec.attrs;
        const root = document.querySelector('#lab') || document.body;
        const elements = [...root.querySelectorAll('button,a,[role=button]')];
        const label = element => ((element.innerText || '') + ' ' + (element.getAttribute('aria-label') || '') + ' ' +
                                  (element.getAttribute('title') || '')).replace(/\\s+/g, '');
        const map = {};
        for (const kind of Object.keys(words)) {
            let found = elements.find(element => element.hasAttribute(attrs[kind]));
            if (!found) found = elements.find(element => words[kind].some(word => label(element).includes(word)));
            if (found) map[kind] = {tag: found.tagName, text: label(found).slice(0, 40),
                                    disabled: Boolean(found.disabled) || found.getAttribute('aria-disabled') === 'true'};
        }
        map.selects = root.querySelectorAll('select').length;
        return map;
    }""", {'words': DEMO_CONTROL_WORDS, 'attrs': DEMO_CONTROL_ATTRS})


def click_demo_control(page, kind):
    """Click a control in its current DOM (finders re-query, so re-renders are safe)."""
    return page.evaluate("""(spec) => {
        const kind = spec.kind, words = spec.words[kind], attrs = spec.attrs[kind];
        const root = document.querySelector('#lab') || document.body;
        const elements = [...root.querySelectorAll('button,a,[role=button]')];
        const label = element => ((element.innerText || '') + ' ' + (element.getAttribute('aria-label') || '') + ' ' +
                                  (element.getAttribute('title') || '')).replace(/\\s+/g, '');
        let button = elements.find(element => element.hasAttribute(attrs));
        if (!button) button = elements.find(element => words.some(word => label(element).includes(word)));
        if (!button) return null;
        if (button.disabled || button.getAttribute('aria-disabled') === 'true') return 'disabled';
        button.scrollIntoView({block: 'nearest'});
        button.click();
        return label(button).slice(0, 40);
    }""", {'kind': kind, 'words': DEMO_CONTROL_WORDS, 'attrs': DEMO_CONTROL_ATTRS})


def demo_jump_last(page, limit=600):
    """Step forward until the next button is disabled (finders re-query after each render)."""
    return page.evaluate("""async (spec) => {
        const words = spec.words, attrs = spec.attrs, limit = spec.limit;
        const root = document.querySelector('#lab') || document.body;
        const label = element => ((element.innerText || '') + ' ' + (element.getAttribute('aria-label') || '') + ' ' +
                                  (element.getAttribute('title') || '')).replace(/\\s+/g, '');
        const find = () => {
            const elements = [...(document.querySelector('#lab') || document.body).querySelectorAll('button,a,[role=button]')];
            let button = elements.find(element => element.hasAttribute(attrs.next));
            if (!button) button = elements.find(element => words.next.some(word => label(element).includes(word)));
            return button || null;
        };
        let steps = 0;
        for (let i = 0; i < limit; i += 1) {
            const button = find();
            if (!button || button.disabled || button.getAttribute('aria-disabled') === 'true') break;
            button.click();
            steps += 1;
            await new Promise(resolve => setTimeout(resolve, 12));
        }
        return steps;
    }""", {'words': DEMO_CONTROL_WORDS, 'attrs': DEMO_CONTROL_ATTRS, 'limit': limit})


def demo_step_state(page):
    return page.evaluate("""() => {
        const text = (document.querySelector('#lab')?.innerText) || document.body.innerText || '';
        const match = text.match(/第\\s*(\\d+)\\s*[\\/／]\\s*(\\d+)\\s*步/);
        if (match) return {index: Number(match[1]), total: Number(match[2])};
        const stage = document.querySelector('[data-step-index]');
        if (stage) return {index: Number(stage.getAttribute('data-step-index')) + 1, total: Number(stage.getAttribute('data-step-total'))};
        return {index: 0, total: 0};
    }""")


def check_demo_browser(checker, harness):
    def run():
        ids, meta = registry_ids()
        if ids is None:
            raise Skip('registry missing (T4.4)')
        viz = {}
        for qid, row in (meta or {}).items():
            if isinstance(row, dict):
                viz.setdefault(row.get('viz') or 'unknown', []).append(qid)
        picks = [qid for qid in ('h100-63', 'h100-53') if qid in ids]
        for group in viz.values():
            for qid in group[:1]:
                if qid not in picks:
                    picks.append(qid)
        picks = picks[:4]
        page = harness.page
        page.set_viewport_size({'width': 1440, 'height': 960})
        details = []
        for qid in picks:
            harness.reset_diagnostics()
            page.goto(harness.server.base + f'/algorithm-demo.html?question={qid}', wait_until='domcontentloaded', timeout=60000)
            wait_for(page, "() => !!document.querySelector('#lab [data-step], #lab [data-play], #lab [data-next]')", timeout=45000)
            time.sleep(1.2)
            api_data = harness.api(f'/api/learning/space/algorithm-demo/{qid}?sample=0', timeout=120)
            demo = api_data['demo']
            expected_output = str((demo.get('sample') or {}).get('output', '')).strip()
            total_expected = len(demo.get('steps') or [])
            controls = demo_controls(page)
            for required in ('play', 'next', 'prev', 'reset'):
                expect(required in controls, f'{qid}: demo control "{required}" not found (found {sorted(controls)})')
            body_text = page.locator('#lab').inner_text()
            expect('预期输出' in body_text or '输出' in body_text, f'{qid}: page does not show the expected output')
            expect(expected_output in body_text, f'{qid}: expected sample output {expected_output!r} not displayed')
            state0 = demo_step_state(page)
            expect(state0['total'] >= 2, f'{qid}: step counter missing/too small: {state0}')
            expect(state0['total'] == total_expected,
                   f'{qid}: UI total steps {state0["total"]} != API steps {total_expected}')
            expect(page.locator('[data-stage]').count() >= 1 or page.locator('[class*=scene]').count() >= 1,
                   f'{qid}: no 3D stage/scene element')
            stage_children = page.evaluate("""() => {
                const stage = document.querySelector('[data-stage], [class*=scene]');
                return stage ? stage.querySelectorAll('*').length : 0;
            }""")
            expect(stage_children > 0, f'{qid}: 3D stage has no rendered children')

            # next / prev
            expect(click_demo_control(page, 'next') != 'disabled', f'{qid}: next control disabled at first step')
            time.sleep(0.4)
            state1 = demo_step_state(page)
            expect(state1['index'] == min(state0['index'] + 1, state0['total']), f'{qid}: next did not advance {state0}->{state1}')
            clicked_prev = click_demo_control(page, 'prev')
            expect(clicked_prev not in (None, 'disabled'), f'{qid}: prev control unavailable ({clicked_prev})')
            time.sleep(0.4)
            state2 = demo_step_state(page)
            expect(state2['index'] == max(1, state1['index'] - 1), f'{qid}: prev did not go back {state1}->{state2}')

            # play / pause
            played = click_demo_control(page, 'play')
            expect(played not in (None, 'disabled'), f'{qid}: play control unavailable ({played})')
            time.sleep(1.4)
            state3 = demo_step_state(page)
            expect(state3['index'] > state2['index'], f'{qid}: play did not advance steps ({state2}->{state3})')
            if state3['index'] < state3['total']:
                pause_click = click_demo_control(page, 'play')
                expect(pause_click not in (None, 'disabled'), f'{qid}: pause control unavailable ({pause_click})')
                time.sleep(0.25)
                paused = demo_step_state(page)
                time.sleep(1.1)
                after = demo_step_state(page)
                expect(after['index'] <= paused['index'] + 1,
                       f'{qid}: pause did not stop stepping ({paused}->{after})')

            # reset
            reset_click = click_demo_control(page, 'reset')
            expect(reset_click not in (None, 'disabled'), f'{qid}: reset control unavailable ({reset_click})')
            time.sleep(0.5)
            state4 = demo_step_state(page)
            expect(state4['index'] == 1, f'{qid}: reset left step {state4}')

            # jump to last step and compare with the expected final result
            demo_jump_last(page, limit=min(state0['total'] + 20, 700))
            time.sleep(0.3)
            final_state = demo_step_state(page)
            expect(final_state['index'] == final_state['total'],
                   f'{qid}: could not reach final step ({final_state})')
            final_text = page.locator('#lab').inner_text()
            expect(expected_output in final_text or str(demo.get('result')) in final_text,
                   f'{qid}: final state does not show result {demo.get("result")!r}')
            errors = harness.real_errors()
            expect(not errors, f'{qid}: console/js errors in demo page: {errors[:4]}')
            harness.shot(checker, f't4.4-demo-{qid}')
            details.append(f'{qid}: {state0["total"]} steps, result={expected_output}, controls={sorted(controls)}')
        return '; '.join(details)
    return checker.run('t4.4.browser', 'T4.4 演示页可打开/步骤/播放暂停步进重置/结果一致/无 console 错误', run)


def check_practice_demo_integration(checker, harness):
    def run():
        ids, _meta = registry_ids()
        if ids is None:
            raise Skip('registry missing (T4.4 integration not ready)')
        page = open_hot100(harness)
        harness.reset_diagnostics()
        chips = page.locator('.stitch-chip:has-text("交互演示")').count()
        bank, hot, _topics = load_practice_data()
        hot_ids = {q['id'] for q in hot}
        expected_chips = len([qid for qid in ids if qid in hot_ids])
        expect(chips == expected_chips,
               f'practice list shows {chips} 交互演示 chips, registry has {expected_chips} Hot100 demos')
        # open a demo from the detail pane (h100-53) and one other registry question
        sample_ids = [qid for qid in ('h100-53', ids[0]) if qid in hot_ids][:2]
        details = []
        for qid in sample_ids:
            page.locator(f'[data-id="{qid}"]').first.click()
            time.sleep(0.8)
            link = page.locator(f'a[href*="algorithm-demo.html?question={qid}"], a[href*="algorithm-demo.html?question=' + qid + '"]')
            expect(link.count() >= 1, f'{qid}: detail pane has no 打开交互演示 link')
            href = link.first.get_attribute('href')
            expect(qid in (href or ''), f'{qid}: demo link href {href!r} does not target the question')
            details.append(f'{qid}->{href}')
        harness.shot(checker, 't4.4-practice-integration')
        return f'{chips} demo chips match registry; detail links: ' + ', '.join(details)
    return checker.run('t4.4.integration', 'T4.4 练习列表/详情由 registry 驱动演示入口', run)


# --------------------------------------------------------------------------- #
# T2 - companion docs / API / browser
# --------------------------------------------------------------------------- #

def sidebar_route_hashes():
    return KNOWN_ROUTES


def check_companion_api(checker, harness):
    def run():
        details = []
        system = harness.api('/api/learning/space/companion/chat', method='POST', timeout=180, body={
            'question': '算法练习在哪里打开？怎么开始刷 Hot100？', 'history': [], 'courseId': 'course-default'})
        expect(system.get('ok') is True, f'system question failed: {system.get("error")}')
        reply = system.get('reply') or {}
        expect(isinstance(reply, dict) and reply.get('answer'), 'system reply missing answer')
        expect(reply.get('route') == 'system', f'system question route {reply.get("route")!r} != system')
        expect(reply.get('status') in ('ok', 'unavailable'), f'unexpected status {reply.get("status")!r}')
        answer = reply.get('answer') or ''
        expect(('#space/' in answer) or ('练习' in answer and '入口' in answer),
               f'system answer has no real operation path: {answer[:160]!r}')
        sources = reply.get('sources') or []
        expect(isinstance(sources, list), 'system sources not a list')
        expect(len(sources) >= 1, 'system answer has no retrieved system-guide source')
        for source in sources[:3]:
            expect(source.get('title') or source.get('path'), f'source missing title/path: {source}')
        links = reply.get('links') or []
        for link in links:
            expect(link.get('hash') in KNOWN_ROUTES,
                   f'companion link hash {link.get("hash")!r} is not an existing route')
        details.append(f'system route={reply.get("route")} status={reply.get("status")} sources={len(sources)} links={len(links)}')

        general = harness.api('/api/learning/space/companion/chat', method='POST', timeout=180, body={
            'question': '你好呀，今天想聊聊学习之外的事，你喜欢什么颜色？', 'history': [], 'courseId': 'course-default'})
        expect(general.get('ok') is True, f'general question failed: {general.get("error")}')
        general_reply = general.get('reply') or {}
        expect(general_reply.get('answer'), 'general reply missing answer')
        expect(general_reply.get('route') == 'general',
               f'general question route {general_reply.get("route")!r} != general')
        details.append(f'general route={general_reply.get("route")} status={general_reply.get("status")}')

        not_found = harness.api('/api/learning/space/companion/chat', method='POST', timeout=180, body={
            'question': '怎么开启全息投影学习模式？这个功能在哪里？', 'history': [], 'courseId': 'course-default'})
        expect(not_found.get('ok') is True, f'not-found question failed: {not_found.get("error")}')
        nf_reply = not_found.get('reply') or {}
        nf_answer = nf_reply.get('answer') or ''
        expect(nf_reply.get('status') in ('not_found', 'ok'), f'unexpected not-found status {nf_reply.get("status")!r}')
        if nf_reply.get('status') != 'not_found':
            expect(any(word in nf_answer for word in ('没有', '不存在', '未提供', '未实现', '暂无', '不支持',
                                                       '未收录', '暂未收录', '未找到', '无法找到', '尚未')),
                   f'nonexistent feature answer does not state it does not exist: {nf_answer[:200]!r}')
        for link in nf_reply.get('links') or []:
            expect(link.get('hash') in KNOWN_ROUTES, f'not-found answer invented link {link.get("hash")!r}')
        details.append(f'not-found status={nf_reply.get("status")}')
        return '; '.join(details)
    return checker.run('t2.companion-api', 'T2 桌宠 companion/chat API（系统/普通/不存在功能）', run)


def check_companion_multiturn(checker, harness):
    def run():
        first_question = '算法练习在哪里？'
        first = harness.api('/api/learning/space/companion/chat', method='POST', timeout=180, body={
            'question': first_question, 'history': [], 'courseId': 'course-default'})
        first_reply = first.get('reply') or {}
        expect(first.get('ok') is True, f'first turn failed: {first.get("error")}')
        expect(first_reply.get('route') == 'system', 'first turn did not use the system guide')
        first_answer = first_reply.get('answer') or ''
        expect('#space/practice' in first_answer or 'Hot100' in first_answer,
               f'first turn has no real entry: {first_answer[:160]!r}')

        follow_question = '刚才那个入口，具体怎么开始刷题？'
        history = [{'role': 'user', 'content': first_question},
                   {'role': 'assistant', 'content': first_answer}]
        follow = harness.api('/api/learning/space/companion/chat', method='POST', timeout=180, body={
            'question': follow_question, 'history': history, 'courseId': 'course-default'})
        follow_reply = follow.get('reply') or {}
        expect(follow.get('ok') is True, f'follow-up failed: {follow.get("error")}')
        follow_answer = follow_reply.get('answer') or ''
        expect(follow_answer.strip(), 'follow-up answer is empty')
        # A pronoun-only follow-up still has to resolve to the system guide and
        # keep actionable content instead of degenerating into generic chat.
        expect(follow_reply.get('route') == 'system',
               f'follow-up lost the system route: {follow_reply.get("route")!r}')
        expect(any(word in follow_answer for word in ('#space/', '步骤', '刷题', '练习', 'Hot100', '难度')),
               f'follow-up answer is not actionable: {follow_answer[:200]!r}')
        for link in follow_reply.get('links') or []:
            expect(link.get('hash') in KNOWN_ROUTES,
                   f'follow-up link {link.get("hash")!r} is not an existing route')
        expect(len(follow_reply.get('sources') or []) >= 1, 'follow-up has no guide source')
        return (f'turn1 route=system len={len(first_answer)}; '
                f'turn2 (with history) route={follow_reply.get("route")} len={len(follow_answer)} '
                f'sources={len(follow_reply.get("sources") or [])}')
    return checker.run('t2.companion-multiturn', 'T2 桌宠多轮连续追问（带 history 保持系统路由）', run)


def check_companion_unavailable(checker, offline):
    def run():
        if offline is None:
            raise Skip('no isolated no-model server available')
        try:
            value = offline.api('/api/learning/space/companion/chat', method='POST', timeout=60, body={
                'question': '算法练习入口在哪里？', 'history': [], 'courseId': 'course-default'})
        except urllib.error.HTTPError as error:
            body = error.read().decode('utf-8', 'replace')
            raise AssertionError(f'companion endpoint crashed without model: HTTP {error.code} {body[:300]}')
        expect(value.get('ok') is True, f'companion unavailable response not ok: {value.get("error")}')
        reply = value.get('reply') or {}
        answer = reply.get('answer') or ''
        status = reply.get('status')
        degraded = status == 'unavailable' or any(
            marker in answer for marker in ('不可用', '无法', '暂不可', '降级', '未配置'))
        expect(degraded, f'no degradation notice without a model: status={status!r} answer={answer[:160]!r}')
        expect(answer.strip(), 'degraded answer is empty')
        return f'status={status!r}, answer starts {answer[:80]!r}'
    return checker.run('t2.companion-unavailable', 'T2 API 不可用时桌宠系统问答降级', run)


def check_companion_browser(checker, harness):
    def run():
        page = harness.page
        page.set_viewport_size({'width': 1440, 'height': 960})
        harness.reset_diagnostics()
        harness.goto('#space/overview', wait_selector='[data-companion-robot]')
        time.sleep(0.8)
        # companion may have been minimized in a previous run of the same data dir
        if page.locator('[data-companion-restore]').count() and not page.locator('[data-companion-restore]').is_hidden():
            page.locator('[data-companion-restore]').click()
            time.sleep(0.4)
        if page.locator('[data-companion-open]').count() and page.locator('[data-companion-open]').is_visible():
            page.click('[data-companion-open]')
        else:
            page.click('[data-companion-robot]')
        wait_for(page, "() => { const p = document.querySelector('[data-companion-panel]'); return p && !p.hidden; }")
        initial = page.evaluate("() => document.querySelectorAll('.companion-message').length")
        page.fill('[data-companion-input]', '算法练习在哪里？我想刷 Hot100 题目')
        page.evaluate("""() => {
            const send = document.querySelector('[data-companion-send]');
            if (send) send.disabled = false;
        }""")
        page.click('[data-companion-send]')
        wait_for(page, """(initial) => {
            const messages = document.querySelector('[data-companion-messages]');
            if (!messages) return false;
            const text = messages.innerText || '';
            const pending = text.includes('回答核对中') || text.includes('正在想一想');
            const status = document.querySelector('[data-companion-status]');
            const thinking = status && status.textContent.includes('正在思考');
            const sent = document.querySelectorAll('.companion-message').length;
            return !pending && !thinking && sent >= initial + 2;
        }""", arg=initial, timeout=240000)
        messages = page.locator('[data-companion-messages]').inner_text()
        expect('#space/' in messages or '练习' in messages,
               f'companion answer has no path/feature info: {messages[-300:]!r}')
        link_count = page.evaluate("""() => document.querySelectorAll(
            '[data-companion-link], [data-companion-hash], .companion-link, .companion-message button, .companion-message a').length""")
        clicked = False
        if link_count:
            tag = page.evaluate("""() => {
                const link = document.querySelector(
                    '[data-companion-link], [data-companion-hash], .companion-link, .companion-message button, .companion-message a');
                if (!link) return null;
                link.setAttribute('data-verifier-companion-link', '1');
                return (link.innerText || link.getAttribute('href') || '').slice(0, 80);
            }""")
            if tag:
                page.click('[data-verifier-companion-link]')
                time.sleep(1.2)
                clicked = page.evaluate('location.hash')
        harness.shot(checker, 't2-companion-system')
        details = [f'answer len={len(messages)}, link candidates={link_count}' + (f', clicked -> {clicked}' if clicked else '')]
        if clicked:
            expect(str(clicked).startswith('#space/'), f'companion link navigated to {clicked!r}')
            expect(clicked in KNOWN_ROUTES or str(clicked).rstrip('/') in KNOWN_ROUTES,
                   f'companion link navigated to unknown route {clicked!r}')
        return '; '.join(details)
    return checker.run('t2.companion-browser', 'T2 浏览器桌宠系统问题回答含真实路径/links 可点击', run)


# --------------------------------------------------------------------------- #
# broad regression sweep
# --------------------------------------------------------------------------- #

def check_pages(checker, harness):
    def run():
        page = harness.page
        views = [('overview', '#space/overview'), ('ask', '#space/ask'), ('courses', '#space/courses'),
                 ('practice', '#space/practice'), ('exams', '#space/exams'), ('knowledge', '#space/knowledge'),
                 ('analysis', '#space/analysis')]
        problems = []
        details = []
        for name, route in views:
            harness.reset_diagnostics()
            page.set_viewport_size({'width': 1440, 'height': 960})
            harness.goto(route, wait_selector='#spaceContent')
            time.sleep(1.2)
            overflow = page.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
            text = page.locator('#spaceContent').inner_text()
            errors = harness.real_errors()
            if overflow > 1:
                problems.append(f'{name}: horizontal overflow {overflow}px')
            if len(text.strip()) < 40:
                problems.append(f'{name}: page content too short ({len(text.strip())} chars)')
            if errors:
                problems.append(f'{name}: console errors {errors[:3]}')
            details.append(f'{name}({len(text.strip())}chars,overflow={overflow})')
            if name in ('overview', 'practice'):
                harness.shot(checker, f'regression-{name}')
        # mobile overflow for the busiest pages
        for name, route in (('overview', '#space/overview'), ('practice', '#space/practice'),
                            ('ask', '#space/ask'), ('knowledge', '#space/knowledge')):
            harness.reset_diagnostics()
            page.set_viewport_size({'width': 390, 'height': 844})
            harness.goto(route, wait_selector='#spaceContent')
            time.sleep(1.0)
            overflow = page.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
            if overflow > 1:
                problems.append(f'{name}@390: horizontal overflow {overflow}px')
            details.append(f'{name}@390(overflow={overflow})')
        page.set_viewport_size({'width': 1440, 'height': 960})
        expect(not problems, '; '.join(problems))
        return ', '.join(details)
    return checker.run('regression.pages', '主要页面回归：无 JS 错误、无横向溢出（桌面+移动）', run)


# --------------------------------------------------------------------------- #
# offline server (no paid model) for degradation / SSE event checks
# --------------------------------------------------------------------------- #

class OfflineLab:
    def __init__(self, name='overhaul-offline'):
        self.server = Server(fresh=True, name=name, env={
            'MIMO_API_KEY': '', 'TAVILY_API_KEY': '', 'XUEYA_AUTO_IMPORT_CORPUS': '0',
            'XUEYA_AUTO_IMPORT_STACK': '0', 'XUEYA_AUTO_IMPORT_DEMO': '0'})
        self.session = None

    def start(self):
        cleanup_stale_lock(self.server.data_dir)
        self.server.start()
        self.session = self.server.register('offline-lab', 'OfflinePass123')
        return self

    def health(self):
        value, _ = http_json(self.server.base + '/api/health', timeout=10)
        return value

    def api(self, path, method='GET', body=None, timeout=60):
        headers = {'X-Xueya-Token': self.session.get('token') or '', 'Cookie': self.session.get('cookie') or ''}
        value, _ = http_json(self.server.base + path, method=method, body=body, headers=headers, timeout=timeout)
        return value

    def sse(self, path, body, timeout=120):
        request = urllib.request.Request(
            self.server.base + path, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), method='POST',
            headers={'Content-Type': 'application/json', 'Accept': 'text/event-stream',
                     'X-Xueya-Token': self.session.get('token') or '',
                     'Cookie': self.session.get('cookie') or ''})
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            return {'error': f'HTTP {error.code}', 'events': []}
        if 'text/event-stream' not in (response.headers.get('content-type') or ''):
            return {'error': 'NOT_SSE', 'events': []}
        events = []
        try:
            for raw in response:
                line = raw.decode('utf-8', 'replace').strip()
                if line.startswith('data:'):
                    try:
                        events.append(json.loads(line[5:].strip()))
                    except json.JSONDecodeError:
                        pass
        finally:
            response.close()
        return {'error': None, 'events': events}

    def stop(self):
        self.server.stop()


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description='End-to-end acceptance checks for the unattended overhaul')
    parser.add_argument('--only', default='', help='comma-separated check id prefixes (e.g. t1,t4.5)')
    parser.add_argument('--skip', default='', help='comma-separated check id prefixes to skip')
    parser.add_argument('--strict', action='store_true', help='treat SKIP as failure')
    parser.add_argument('--skip-model', action='store_true', help='skip checks that call the paid model')
    parser.add_argument('--data-dir', default='', help='reuse an isolated lab data dir name instead of a fresh one')
    parser.add_argument('--no-browser', action='store_true', help='only run filesystem/API audits')
    parser.add_argument('--out', default='', help='report path (default test-results/agent-lab/overhaul-report.json)')
    options = parser.parse_args()

    only = [part.strip() for part in options.only.split(',') if part.strip()]
    skipped = [part.strip() for part in options.skip.split(',') if part.strip()]

    def selected(check_id):
        if any(check_id.startswith(prefix) for prefix in skipped):
            return False
        return not only or any(check_id.startswith(prefix) for prefix in only)

    def family(*check_ids):
        return any(selected(check_id) for check_id in check_ids)

    checker = Checker()
    started = time.monotonic()
    report_path = Path(options.out) if options.out else OUT / 'overhaul-report.json'
    OUT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)

    server = None
    offline = None

    def skip_row(target, check_id, title, reason):
        target.rows.append({'id': check_id, 'title': title, 'status': 'SKIP', 'detail': reason,
                            'screenshots': [], 'seconds': 0})
        print(f'[SKIP] {check_id} - {title} :: {reason}', flush=True)

    def run_audits():
        if selected('audit.practice-bank'):
            audit_practice_bank(checker)
        if selected('audit.startup-starters'):
            audit_starter_file(checker)
        if selected('audit.docs-guide'):
            audit_docs_guide(checker)
        if selected('audit.system-vectors'):
            audit_system_vectors(checker)
        if selected('audit.demo-coverage'):
            audit_demo_coverage(checker)

    try:
        run_audits()
        pure_audits = {'audit.practice-bank', 'audit.startup-starters', 'audit.docs-guide',
                       'audit.system-vectors', 'audit.demo-coverage'}
        need_server = (not options.no_browser) or (not only) or any(level not in pure_audits for level in only)
        zero_cost_ui = family('t1.overview-ask', 't1.overview-chips', 't1.real-answer',
                              't3.toggle-ui', 't3.payloads')
        if need_server:
            data_dir = ROOT / '.tmp' / 'agent-lab-data' / options.data_dir if options.data_dir else None
            server = start_lab_server('overhaul-main', data_dir, not options.data_dir)
            session = server.register('overhaul-verifier', 'OverhaulPass123')
            api = ApiClient(server, session)
            try:
                seed_version = seed_workspace_document(api)
                print(f'[lab] seeded server workspace document (workspace version {seed_version})', flush=True)
            except Exception as seed_error:  # noqa: BLE001 - payload checks will report the gap
                print(f'[lab] workspace seeding failed: {seed_error}', flush=True)
            print(f'[lab] server {server.base} data {server.data_dir}', flush=True)

            if selected('t4.4.registry'):
                check_demo_registry(checker)
            if selected('t4.4.api-schema'):
                check_demo_api(checker, api)
            if selected('t2.companion-api'):
                if options.skip_model:
                    skip_row(checker, 't2.companion-api', 'T2 桌宠 companion/chat API（系统/普通/不存在功能）',
                             '--skip-model 跳过真实模型调用')
                else:
                    check_companion_api(checker, api)
            if selected('t2.companion-multiturn'):
                if options.skip_model:
                    skip_row(checker, 't2.companion-multiturn', 'T2 桌宠多轮连续追问（带 history 保持系统路由）',
                             '--skip-model 跳过真实模型调用')
                else:
                    check_companion_multiturn(checker, api)

            if family('t3.search-events', 't2.companion-unavailable') or zero_cost_ui:
                try:
                    offline = OfflineLab().start()
                    try:
                        seed_workspace_document(offline)
                    except Exception as offline_seed_error:  # noqa: BLE001
                        print(f'[lab] offline workspace seeding failed: {offline_seed_error}', flush=True)
                    print(f'[lab] offline (no model) server {offline.server.base}', flush=True)
                except Exception as error:  # noqa: BLE001 - degrade to SKIP, don't kill run
                    print(f'[lab] offline server failed: {error}', flush=True)
                    offline = None
            if family('t3.search-events'):
                check_t3_events(checker, offline)
            if family('t2.companion-unavailable'):
                if options.skip_model:
                    skip_row(checker, 't2.companion-unavailable', 'T2 API 不可用时桌宠系统问答降级',
                             '--skip-model 跳过')
                else:
                    check_companion_unavailable(checker, offline)

        if not options.no_browser:
            with browser_page(server.base, session=session, viewport={'width': 1440, 'height': 960}) as (page, context, errors):
                harness = Harness(page, context, errors, session, server)
                """T1/T3 run against the no-model lab so the UI flow is deterministic and
                never spends money; the real-model answer path is additionally verified
                by t1.real-answer on the model-backed server."""
                free_harness = None
                free_context = None
                if zero_cost_ui and offline is not None:
                    try:
                        free_context = context.browser.new_context(viewport={'width': 1440, 'height': 960})
                        cookie = offline.session.get('cookie') or ''
                        if cookie:
                            cookie_name, cookie_value = cookie.split('=', 1)
                            free_context.add_cookies([{'name': cookie_name, 'value': cookie_value,
                                                       'domain': '127.0.0.1', 'path': '/'}])
                        free_page = free_context.new_page()
                        free_page.set_default_timeout(25000)
                        free_errors = []
                        free_page.on('console', lambda message: free_errors.append(message.text)
                                     if message.type == 'error' else None)
                        free_page.on('pageerror', lambda error: free_errors.append('PAGEERROR ' + str(error)))
                        free_harness = Harness(free_page, free_context, free_errors, offline.session, offline.server)
                    except Exception as free_error:  # noqa: BLE001
                        print(f'[lab] zero-cost browser context failed: {free_error}', flush=True)
                        free_harness = None
                if selected('t1.overview-ask'):
                    check_t1(checker, free_harness)
                if selected('t1.overview-chips'):
                    check_t1_chips(checker, free_harness)
                if selected('t1.real-answer'):
                    if options.skip_model:
                        skip_row(checker, 't1.real-answer', 'T1 真实模型问答链路（隔离服务、真实 API）', '--skip-model 跳过')
                    else:
                        check_t1_real_answer(checker, harness)
                if selected('t3.toggle-ui'):
                    check_t3_ui(checker, free_harness)
                if selected('t3.payloads'):
                    check_t3_payloads(checker, free_harness)
                if free_context is not None:
                    try:
                        free_context.close()
                    except Exception:  # noqa: BLE001
                        pass
                if selected('t4.1'):
                    check_t41(checker, harness)
                if selected('t4.2'):
                    check_t42(checker, harness)
                if selected('t4.3'):
                    check_t43(checker, harness)
                    if selected('t4.3.no-hardcode'):
                        check_t43_no_hardcode(checker)
                elif selected('t4.3.no-hardcode'):
                    check_t43_no_hardcode(checker)
                if selected('t4.5'):
                    check_t45(checker, harness)
                if selected('t4.4.browser'):
                    check_demo_browser(checker, harness)
                if selected('t4.4.integration'):
                    check_practice_demo_integration(checker, harness)
                if selected('t2.companion-browser'):
                    if options.skip_model:
                        skip_row(checker, 't2.companion-browser', 'T2 浏览器桌宠系统问题回答含真实路径/links 可点击',
                                 '--skip-model 跳过真实模型调用')
                    else:
                        check_companion_browser(checker, harness)
                if selected('regression.pages'):
                    check_pages(checker, harness)
    finally:
        if offline is not None:
            try:
                offline.stop()
            except Exception:  # noqa: BLE001
                pass
        if server is not None:
            try:
                server.stop()
            finally:
                cleanup_stale_lock(getattr(server, 'data_dir', None))

    summary = checker.summary()
    duration = round(time.monotonic() - started, 1)
    report = {
        'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
        'durationSeconds': duration,
        'environment': {'python': sys.version.split()[0], 'dataDir': '.tmp/agent-lab-data'},
        'summary': summary,
        'checks': checker.rows,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n===== SUMMARY =====')
    print(f'PASS {summary.get("PASS", 0)} | FAIL {summary.get("FAIL", 0)} | SKIP {summary.get("SKIP", 0)} | '
          f'{duration}s | report: {report_path.relative_to(ROOT)}', flush=True)
    if summary.get('FAIL'):
        print('FAILED: ' + ', '.join(row['id'] for row in checker.rows if row['status'] == 'FAIL'))
    if summary.get('SKIP'):
        print('SKIPPED: ' + ', '.join(row['id'] for row in checker.rows if row['status'] == 'SKIP'))
    failed = summary.get('FAIL', 0) > 0 or (options.strict and summary.get('SKIP', 0) > 0)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
