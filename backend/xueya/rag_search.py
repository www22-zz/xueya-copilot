"""Deterministic lexical baseline, exact cosine/RRF, and extractive evidence budgets."""
from __future__ import annotations

from collections import Counter
import math
import re
import hashlib

from .common import require

# Small transparent domain dictionary, injectable for other courses. No hidden model.
TERMS = {"二叉搜索树": ("bst", "binary search tree", "二叉查找树"), "广度优先": ("bfs", "宽度优先"),
         "深度优先": ("dfs",), "光合作用": ("photosynthesis",), "叶绿体": ("chloroplast",),
         "时间复杂度": ("time complexity",), "栈": ("stack", "后进先出", "lifo"), "队列": ("queue", "先进先出", "fifo"),
         "先序遍历": ("前序遍历", "先根遍历", "preorder", "pre-order"),
         "中序遍历": ("inorder", "in-order"), "后序遍历": ("后根遍历", "postorder", "post-order"),
         "层序遍历": ("level order", "level-order"), "二分查找": ("折半查找", "binary search"),
         "散列表": ("哈希表", "hash table", "hashtable", "hashmap"),
         "哈夫曼树": ("霍夫曼树", "huffman tree", "huffman"),
         "最小生成树": ("最小支撑树", "minimum spanning tree", "mst"),
         "邻接矩阵": ("adjacency matrix",), "快速排序": ("quicksort", "quick sort"),
         "堆排序": ("heapsort", "heap sort"), "冒泡排序": ("起泡排序", "bubble sort")}
STOP = {"什么", "怎么", "如何", "为何", "为什么", "哪里", "哪些", "这个", "那个", "请问", "一下", "可以", "是否", "介绍", "解释"}


def source_order(source):
    """Content/location breaks ties before random per-import entity IDs."""
    quote = source.get('quote', '')
    return (source.get('title', '').casefold(), source.get('fileHash') or hashlib.sha256(quote.encode()).hexdigest(),
            source.get('page') or 0, source.get('start', 0), source.get('end', 0), quote, source.get('id', ''))


def terms(text, dictionary=None):
    text = str(text).casefold()
    output = re.findall(r"[a-z0-9_]+(?:[.+#-][a-z0-9_]+)*", text)
    for word in re.findall(r"[\u4e00-\u9fff]+", text):
        output.extend(word[i:i+2] for i in range(len(word)-1) if word[i:i+2] not in STOP)
        if len(word) == 1 and word in ("栈", "树", "图"):
            output.append(word)
    for term, aliases in (TERMS if dictionary is None else dictionary).items():
        if term in text or any(re.search(r"(?<![a-z0-9])"+re.escape(alias)+r"(?![a-z0-9])", text) for alias in aliases):
            output.append("term:"+term)
    return output


def definition_subject(query):
    compact = re.sub(r'\s+', '', str(query)).strip('？?。.!！')
    compact = re.sub(r'^(?:请问|请解释一下|请解释|解释一下|介绍一下)', '', compact)
    # A second question must not hide the definition requested in the first one.
    compact = re.split(r'[？?。；;，,]', compact, maxsplit=1)[0]
    match = (re.search(r'(?:什么是|什么叫|何谓)([^，,？?。；;]{1,40})', compact)
             or re.fullmatch(r'(.{1,40}?)(?:的(?:基本)?(?:定义|概念|含义)(?:是什么|是啥|是)?|是什么)', compact))
    return match[1].strip() if match else None


def comparison_subjects(query):
    """Transparent vocabulary expansion; require both named comparison targets."""
    if not re.search(r'区别|不同|差异|异同|比较|对比|不选|不用|而不是|替代', query):
        return []
    names = [term for term in TERMS if term in query]
    names = [name for name in names if not any(name != other and name in other for other in names)]
    return names if 2 <= len(names) <= 4 else []


def defining_strength(source, subject):
    names = [subject]
    for term, aliases in TERMS.items():
        if subject == term or subject.casefold() in aliases:
            names += [term, *aliases]
    text, strength = source['quote'], 0
    for name in names:
        word = r'(?<![\u3400-\u9fffA-Za-z0-9_])'+re.escape(name)
        heading = bool(re.search(r'^\s*[\d一二三四五六七八九十.．、()（）\s]*'+re.escape(name)+r'的(?:基本)?(?:定义|概念)\s*[:：]?\s*$', text, re.M | re.I))
        prose = bool(re.search(word+r'(?:\s*[（(][^）)\n]{0,60}[）)])?\s*(?:是|指)', text, re.I))
        named = bool(re.search(r'称为\s*'+re.escape(name)+r'(?![\u3400-\u9fffA-Za-z0-9_])', text, re.I))
        strength = max(strength, 2*heading+prose, int(named))
    return strength


def preserve_definitions(query, ranked, candidates):
    """Keep required definitions through fusion; candidates share the same scope."""
    subjects = comparison_subjects(query)
    subject = definition_subject(query)
    subjects = subjects or ([subject] if subject else [])
    chosen = {}
    for name in subjects:
        matches = [(score, source) for score, source in candidates if defining_strength(source, name)]
        if matches:
            _, source = min(matches, key=lambda row: (-defining_strength(row[1], name), -row[0], source_order(row[1])))
            chosen[source['id']] = source
    if not chosen:
        return ranked
    ceiling = max((score for score, _ in ranked), default=0)+1
    return [(ceiling, source) for source in chosen.values()]+[(score, source) for score, source in ranked if source['id'] not in chosen]


def preserve_sections(query, ranked, sources):
    """Honor explicit heading identifiers, within the caller's existing scope.

    A user asking for C06 or SQ01.3 should receive that actual section rather
    than adjacent prose repeating the same topic words. No document is opened
    outside the already filtered source set; the caller revalidates after awaits.
    """
    requested = {m.casefold() for m in re.findall(r'(?<![A-Za-z0-9_])[A-Za-z]{1,6}\d{1,4}(?:\.\d+)*(?![A-Za-z0-9_])', query)}
    if not requested:
        return ranked
    chosen = []
    for source in sources:
        for heading in source.get('sectionPath', []):
            match = re.match(r'^([A-Za-z]{1,6}\d{1,4}(?:\.\d+)*)\b', heading)
            if match and match[1].casefold() in requested:
                chosen.append(source)
                break
    if not chosen:
        return ranked
    chosen.sort(key=lambda s: (s.get('blockType') == 'heading', source_order(s)))
    ids = {s['id'] for s in chosen}
    ceiling = max((score for score, _ in ranked), default=0)+1
    return [(ceiling, s) for s in chosen]+[(score, s) for score, s in ranked if s['id'] not in ids]


def lexical(query, sources, *, limit=24):
    query_terms = set(terms(query))
    subject = definition_subject(query)
    if subject:
        query_terms.update(terms(subject))
    if not query_terms or not sources:
        return []
    documents = [Counter(terms(s.get("title", "")+" "+s["quote"]+" "+" ".join(s.get("sectionPath", [])))) for s in sources]
    single_concept = str(query).strip('？?。 \t\n')
    if single_concept in ('栈', '树', '图'):
        for source, doc in zip(sources, documents):
            if single_concept in source.get('title', '') + source['quote']:
                doc[single_concept] = max(1, doc[single_concept])
    df = Counter(t for doc in documents for t in doc)
    average = sum(sum(doc.values()) for doc in documents)/len(documents) or 1
    rows = []
    for source, doc in zip(sources, documents):
        score = 0
        for term in query_terms & doc.keys():
            freq, length = doc[term], sum(doc.values())
            idf = math.log(1+(len(documents)-df[term]+.5)/(df[term]+.5))
            score += idf*freq*2.2/(freq+1.2*(.25+.75*length/average))
        if score > 0:
            rows.append((score, source))
    # Definition questions need the defining prose ahead of dense code/index
    # fragments that repeat the same term. The original quotes stay unchanged.
    if subject and rows:
        priority = max(score for score, _ in rows)+1
        rows = [(score+priority*defining_strength(source, subject), source) for score, source in rows]
    # Reserve a defining passage for each side instead of letting repeated words
    # in exercises crowd one side out. Operates only on the caller's scoped rows.
    subjects = comparison_subjects(query)
    if subjects and rows:
        priority = max(score for score, _ in rows)+1
        chosen = set()
        for name in subjects:
            candidates = [(score, source) for score, source in rows if defining_strength(source, name)]
            if candidates:
                _, best = min(candidates, key=lambda row: (-defining_strength(row[1], name), -row[0], source_order(row[1])))
                chosen.add(best['id'])
        rows = [(score+priority if source['id'] in chosen else score, source) for score, source in rows]
    return sorted(rows, key=lambda row: (-row[0], source_order(row[1])))[:limit]


def normalize(vector, dimension):
    require(isinstance(vector, list) and len(vector) == dimension and all(type(v) in (int, float) and math.isfinite(v) for v in vector), "INVALID_EMBEDDING")
    norm = math.sqrt(sum(v*v for v in vector))
    require(norm > 0 and math.isfinite(norm), "INVALID_EMBEDDING")
    return [v/norm for v in vector]


def exact(query_vector, rows, *, limit=24, threshold=.25):
    result = []
    for vector, source in rows:
        if len(vector) != len(query_vector):
            continue
        score = sum(a*b for a, b in zip(query_vector, vector))
        if score >= threshold:
            result.append((score, source))
    return sorted(result, key=lambda row: (-row[0], source_order(row[1])))[:limit]


def fuse(*rankings, limit=24):
    scores, catalog = Counter(), {}
    for ranking in rankings:
        for rank, (_, source) in enumerate(ranking, 1):
            scores[source["id"]] += 1/(60+rank)
            catalog[source["id"]] = source
    return [(score, catalog[key]) for key, score in sorted(scores.items(), key=lambda p: (-p[1], source_order(catalog[p[0]])))[:limit]]


def rewrite_query(query, history=(), *, new_topic=False):
    require(isinstance(query, str) and 0 < len(query.strip()) <= 4000, "INVALID_QUERY")
    query = query.strip()
    if new_topic or re.search(r"换个话题|换题|另外一个问题|现在讨论", query):
        return query
    if re.match(r"^(那|它|这|为什么|为何|继续|再举|有什么例子|复杂度呢)", query):
        # Only a user's question can anchor a follow-up. Assistant prose is never evidence.
        for message in reversed(list(history)[-12:]):
            if isinstance(message, dict) and message.get("role") == "user":
                anchor = message.get("content", message.get("text", ""))
                if isinstance(anchor, str) and anchor.strip():
                    return anchor[:1000]+" "+query
    return query


def compress(query, ranked, *, budget=2000, limit=6):
    """Conservative UTF-8 byte budget (upper bound on byte-fallback tokenizer tokens)."""
    require(type(budget) is int and 32 <= budget <= 16000 and type(limit) is int and 1 <= limit <= 20, "INVALID_BUDGET")
    evidence, used, ranges, quotes = [], 0, [], set()
    qterms = set(terms(query))
    # Headings provide navigation metadata but rarely prove an explanation.
    # Keep their fallback availability without allowing short titles to crowd
    # out equally scoped prose/code, even when a vector rank puts titles first.
    ranked = sorted(ranked, key=lambda row: row[1].get('blockType') == 'heading')
    for score, source in ranked:
        if len(evidence) >= limit:
            break
        start, end = source["start"], source["end"]
        # Sliding chunks deliberately overlap. Dropping every overlapping sibling
        # loses the continuation containing a condition/formula; only suppress
        # substantial overlap, while still charging all returned bytes.
        if any(doc == source["documentId"] and
               max(0, min(end, b)-max(start, a))*2 >= min(end-start, b-a)
               for doc, a, b in ranges):
            continue
        quote, offset = source["quote"], 0
        if quote.strip() in quotes:
            continue
        # Preserve whole structured blocks. Never truncate tables, code or formulas.
        available = budget-used
        if len(quote.encode()) > available:
            if source.get("blockType") in ("table", "code", "formula", "image"):
                continue
            candidates = [(sum(1 for t in terms(m[0]) if t in qterms), m.start(), m[0]) for m in re.finditer(r"[^。！？.!?\n]+[。！？.!?]?", quote)]
            if not candidates:
                continue
            _, offset, quote = max(candidates, key=lambda row: (row[0], -row[1]))
            if len(quote.encode()) > available:
                continue
        item = {**source, "quote": quote, "start": start+offset, "end": start+offset+len(quote), "score": round(score, 6)}
        evidence.append(item)
        quotes.add(quote.strip())
        used += len(quote.encode())
        ranges.append((source["documentId"], item["start"], item["end"]))
    return evidence, used


def conflicts(evidence):
    """Flag simple opposing assertions for review; does not claim semantic entailment."""
    result = []
    for i, one in enumerate(evidence):
        for two in evidence[i+1:]:
            left, right = one["quote"], two["quote"]
            if left != right and (re.sub(r"不|不是|不能|未", "", left) == re.sub(r"不|不是|不能|未", "", right)):
                result.append([one["id"], two["id"]])
    return result
