"""RAG Scope Adapter & Blackbox Protection (AI Learning Space Specs 3.5 - 3.9).

Provides:
1. Account & resource policy: Public preset library + User private supplementary library.
2. Cross-account isolation: User A cannot search or read User B's documents.
3. Blackbox projection: Strips internal quotes and chunk texts of platform documents
   from public DTOs, SSE events, toolCalls, read/export/original endpoints.
4. Dispatches read/validate to the correct origin scope.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from .common import AppError, Scope, require
from .rag_service import RagService


# Exact six-file cross-course allowlist approved by the user on 2026-10-31.
# Flags/filenames alone retain only their existing same-course permissions.
KNOWN_PLATFORM_HASHES = frozenset({
    "7a36da9a2a222b39d22c13a720f587f7f2d21073dbfbcccc9b2769c222d0652a",
    "7fbd8a0444096282daf0b2d68904aa89c70144e1525134db0979be31ed9bfd29",
    "6da65496b85208708df00d7213ec3074cb535e36e9eefa03de220438ba946b42",
    "5702f159d19a3e88a17049ff691fdaf26ca8fdd6650269d24d39d2f5a89b6504",
    "92f525d8e8f31560451023cb32bcddf43272c2900e084736a103c86abc3f0bb9",
    "5e2521731f275e6668f2b6c3ef8cf5a8a511618ccf70922731860d6cf79f3c01",
})


def is_platform_scope(scope: Scope) -> bool:
    return scope.user_id in ("platform", "system", "public")


def is_platform_document(doc: Dict[str, Any], scope: Optional[Scope] = None) -> bool:
    if not isinstance(doc, dict):
        return False
    if doc.get("isPlatform") is True or doc.get("sample") is True:
        return True
    if doc.get("owner") in ("platform", "system", "public"):
        return True
    if scope and is_platform_scope(scope):
        return True
    file_hash = doc.get("fileHash") or doc.get("sourceFileHash")
    if file_hash and file_hash in KNOWN_PLATFORM_HASHES:
        return True
    return False


def is_platform_source(source: Dict[str, Any], scope: Optional[Scope] = None, doc: Optional[Dict[str, Any]] = None) -> bool:
    if not isinstance(source, dict):
        return False
    if source.get("isPlatform") is True or source.get("sample") is True:
        return True
    if doc and is_platform_document(doc, scope):
        return True
    if scope and is_platform_scope(scope):
        return True
    file_hash = source.get("fileHash")
    if file_hash and file_hash in KNOWN_PLATFORM_HASHES:
        return True
    return False


def public_source_projection(source: Dict[str, Any], is_platform: Optional[bool] = None) -> Dict[str, Any]:
    """Project an internal evidence source into a public DTO.

    If the source belongs to a platform document, its verbatim quote is stripped.
    Public fields permitted: id, title, location, isWeb, url, documentId, version, isPlatform.
    """
    if not isinstance(source, dict):
        return {}
    opaque_id = str(source.get("id", ""))
    title = str(source.get("title") or source.get("name") or opaque_id)
    location = str(source.get("location") or "")
    if not location and source.get("page") is not None:
        location = f"第{source['page']}页"

    platform_flag = is_platform if is_platform is not None else is_platform_source(source)

    res: Dict[str, Any] = {
        "id": opaque_id,
        "title": title,
        "location": location or "资料片段",
        "isPlatform": bool(platform_flag),
    }
    if source.get("documentId"):
        res["documentId"] = source["documentId"]
    if source.get("version") is not None:
        res["version"] = source["version"]
    if source.get("documentRevision") is not None:
        res["documentRevision"] = source["documentRevision"]
    for field in ('originCourseId', 'originCourseName'):
        if platform_flag and isinstance(source.get(field), str):
            res[field] = source[field]
    if source.get("url"):
        res["url"] = source["url"]
    if source.get("isWeb"):
        res["isWeb"] = True

    # Quote protection: For platform sources, quote is completely omitted!
    # For web sources or user's own sources, quote may be retained only if not platform.
    if not platform_flag and "quote" in source and isinstance(source["quote"], str):
        res["quote"] = source["quote"]

    return res


def public_sources_projection(sources: Any) -> List[Dict[str, Any]]:
    if not isinstance(sources, list):
        return []
    return [public_source_projection(s) for s in sources if isinstance(s, dict)]


def public_api_projector(platform, course_id="course-default"):
    """Resolve server-owned identity across courses; never trust DTO flags."""
    if platform is None:
        return lambda value: value
    owner = platform.scope_user_id
    docs, sources, quotes, hashes = {}, {}, set(), set()
    for user in dict.fromkeys((owner, platform.user_id)):
        for course in platform.repo.courses(user):
            scope = Scope(user_id=user, course_id=course['id'])
            protected = {d['id']: d for d in platform.repo.all(scope, 'document') if is_platform_document(d, scope)}
            docs.update(protected)
            hashes.update(d.get('fileHash') for d in protected.values() if d.get('fileHash'))
            for source in platform.repo.all(scope, 'source'):
                if source.get('documentId') in protected or is_platform_source(source, scope):
                    stored={**source,'originCourseId':scope.course_id,'originCourseName':course['name']}
                    sources[source['id']] = stored
                    sources[ScopeAdapter.public_id(scope, source['id'])] = stored
                    if source.get('quote'):
                        quotes.add(source['quote'])
    def project(item, field=None):
        if isinstance(item, list):
            return [project(child, field) for child in item]
        if isinstance(item, str):
            # Old tool preview/checkpoint and content events may serialize JSON.
            try:
                nested = json.loads(item) if field in ('text', 'content', 'preview', 'checkpoint') and item.lstrip().startswith(('{', '[')) else None
            except (ValueError, TypeError):
                nested = None
            if isinstance(nested, (list, dict)):
                cleaned=project(nested)
                return item if cleaned==nested else json.dumps(cleaned, ensure_ascii=False)
            for quote in quotes:
                # Single digits/short labels are common parser fragments, not
                # identifying prose. Substring-replacing them corrupts random
                # bootstrap tokens, UUIDs, status names and private account IDs.
                # Structured protected sources still lose quote/body fields
                # through their trusted source/document identity below.
                if len(quote.strip()) < 8:
                    if field in ('quote','rawText','rawContent') and item.strip()==quote.strip():
                        item='[平台资料正文受保护]'
                    continue
                if quote in item:
                    item = item.replace(quote, '[平台资料正文受保护]')
            return item
        if not isinstance(item, dict):
            return item
        # Verbatim-only compatibility answers are valid for user-owned sources,
        # but cannot export a protected platform passage as a successful answer.
        if (item.get('verification') in ('verbatim-only', 'original-excerpts')
                and isinstance(item.get('sources'), list)
                and any(isinstance(key, str) and key in sources for key in item['sources'])):
            item = {**item, 'answer': '这次 AI 回答未能完成，请稍后重新提问。',
                    'answerStatus': 'unavailable', 'verification': 'not-generated',
                    'reason': 'PROTECTED_VERBATIM_OUTPUT'}
        key = item.get('id') or item.get('sourceId')
        if isinstance(key, str) and key in sources or is_platform_source(item) and 'quote' in item:
            stored=sources.get(key,{}) if isinstance(key,str) else {}
            merged={**stored, **item}
            # Display origin is server-owned too; a historical/client DTO cannot
            # relabel a known source as belonging to a different course.
            merged.update({name:stored[name] for name in ('originCourseId','originCourseName') if name in stored})
            return public_source_projection(merged, True)
        if (isinstance(key, str) and key in docs
                or isinstance(item.get('fileHash'), str) and item['fileHash'] in hashes
                or isinstance(item.get('sourceFileHash'), str) and item['sourceFileHash'] in hashes):
            return {**{field: item[field] for field in ('ok', 'id', 'name', 'title', 'version', 'status', 'archived', 'createdAt', 'updatedAt') if field in item},
                    'isPlatform': True, 'protected': True, **({'chunks': []} if 'chunks' in item else {})}
        # Evidence-only artifacts do not carry a source id on the outer object.
        if isinstance(item.get('documentId'), str) and item['documentId'] in docs and any(k in item for k in ('blocks', 'pages', 'chunks', 'text', 'quote')):
            return {'documentId': item['documentId'], 'protected': True}
        # Truncated serialized tool previews cannot be parsed safely; the tool's
        # structured data and status remain available. No raw evidence preview.
        return {name: project(child, name) for name, child in item.items()
                if not sources or name != 'claims' and (name != 'preview' or not isinstance(child, str))}
    project.has_protected_sources = bool(sources)
    return project


def public_api_value(platform, value, course_id="course-default"):
    return public_api_projector(platform, course_id)(value)


def sanitize_tool_call(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize tool calls to ensure no platform quotes leak in data or preview."""
    if not isinstance(tool_call, dict):
        return tool_call
    cleaned = copy.deepcopy(tool_call)
    data = cleaned.get("data")
    if isinstance(data, dict):
        if "sources" in data and isinstance(data["sources"], list):
            data["sources"] = [public_source_projection(s) for s in data["sources"] if isinstance(s, dict)]
        if "source" in data and isinstance(data["source"], dict):
            data["source"] = public_source_projection(data["source"])
    return cleaned


def sanitize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize any stream event or final answer payload for browser presentation."""
    if not isinstance(event, dict):
        return event
    cleaned = copy.deepcopy(event)

    # 1. sourceObjects
    if "sourceObjects" in cleaned and isinstance(cleaned["sourceObjects"], list):
        cleaned["sourceObjects"] = public_sources_projection(cleaned["sourceObjects"])

    # 2. sourceDetails: if present, sanitize each source
    if "sourceDetails" in cleaned and isinstance(cleaned["sourceDetails"], list):
        cleaned["sourceDetails"] = [
            public_source_projection(s) if is_platform_source(s) else s
            for s in cleaned["sourceDetails"] if isinstance(s, dict)
        ]

    # 3. toolCalls
    if "toolCalls" in cleaned and isinstance(cleaned["toolCalls"], list):
        cleaned["toolCalls"] = [sanitize_tool_call(tc) for tc in cleaned["toolCalls"]]

    # 4. tool-result event
    if cleaned.get("type") == "tool-result" and isinstance(cleaned.get("data"), dict):
        cleaned["data"] = sanitize_tool_call({"data": cleaned["data"]})["data"]

    # 5. claims: internal evidence notes should not leak verbatim text
    if "claims" in cleaned:
        # Keep claims for server logs, but in client output strip verbatim quotes
        if isinstance(cleaned["claims"], list):
            sanitized_claims = []
            for c in cleaned["claims"]:
                if isinstance(c, dict):
                    sc = copy.deepcopy(c)
                    if "evidence" in sc and isinstance(sc["evidence"], list):
                        sc["evidence"] = [
                            {k: v for k, v in ev.items() if k != "quote"}
                            for ev in sc["evidence"] if isinstance(ev, dict)
                        ]
                    sanitized_claims.append(sc)
            cleaned["claims"] = sanitized_claims

    return cleaned


class ScopeAdapter:
    """Authorized aggregation around B's unchanged read/search/validate ports."""
    def __init__(self, platform, current_user_id=None):
        self.p = platform
        self.current_user_id = current_user_id or platform.scope_user_id
        self.public_scope = Scope(user_id=platform.user_id, course_id="course-default")

    def private_scope(self, course_id="course-default"):
        scope = Scope(user_id=self.current_user_id, course_id=course_id)
        self.p.repo.require_course(scope)
        return scope

    @staticmethod
    def public_id(scope, source_id):
        return 'pub-' + hashlib.sha256(json.dumps([scope.user_id, scope.course_id, source_id]).encode()).hexdigest()[:48]

    def public_documents(self, course_id):
        scope = Scope(user_id=self.p.user_id, course_id=course_id)
        if not any(c['id'] == course_id and not c['archived'] for c in self.p.repo.courses(scope.user_id)):
            return scope, []
        return scope, [d for d in self.p.repo.all(scope, 'document') if is_platform_document(d, scope)
                       and not any(d.get(k) for k in ('archived', 'deleted', 'superseded'))]

    def public_libraries(self, course_id):
        """Same-course compatibility plus exactly six approved cross-course files.

        Only the trusted legacy public owner is enumerated. Account uploads,
        sourceFileHash claims, isPlatform flags and filenames cannot expand the
        cross-course set. Never rewrite the original document/source scope.
        """
        courses=sorted(self.p.repo.courses(self.p.user_id),key=lambda c:(c['id']!=course_id,c['id']))
        libraries=[]
        for course in courses:
            if course['archived']:
                continue
            scope,documents=self.public_documents(course['id'])
            if course['id']!=course_id:
                documents=[d for d in documents if d.get('fileHash') in KNOWN_PLATFORM_HASHES]
            if documents:
                libraries.append((scope,documents))
        return libraries

    @staticmethod
    def evidence_key(source):
        # Identical confirmed content imported into two legacy courses counts as
        # one hit; different revisions/text hashes remain independently checked.
        if source.get('isPlatform') and source.get('fileHash') in KNOWN_PLATFORM_HASHES:
            return ('preset',source['fileHash'],source.get('textHash'),source.get('page'),
                    source.get('start'),source.get('end'),source.get('quote'))
        return ('source',source['id'])

    def tagged(self, source, scope, public=False):
        result={**source, 'id': self.public_id(scope, source['id']) if public else source['id'],
                'isPlatform': public or is_platform_source(source, scope),
                'scopeOrigin': {'user_id': scope.user_id, 'course_id': scope.course_id}}
        if public:
            course=next(c for c in self.p.repo.courses(scope.user_id) if c['id']==scope.course_id)
            result.update(originCourseId=scope.course_id,originCourseName=course['name'])
        return result

    def sources(self, rag, course_id, document_ids=None, section=None):
        private = self.private_scope(course_id)
        result = list(rag.sources(private, document_ids=document_ids, section=section))
        if private.user_id == self.p.user_id:
            return result
        for public,documents in self.public_libraries(course_id):
            ids = [d['id'] for d in documents if document_ids is None or d['id'] in document_ids]
            if ids:
                result += [self.tagged(s, public, True) for s in rag.sources(public, document_ids=ids, section=section)]
        seen=set()
        unique=[]
        for source in result:
            key=self.evidence_key(source)
            if key not in seen:
                seen.add(key);unique.append(source)
        return unique

    def resolve_source(self, source_id, course_id):
        private = self.private_scope(course_id)
        row = self.p.repo.read(private, 'source', source_id)
        if row:
            return private, source_id
        for public,documents in self.public_libraries(course_id):
            allowed = {d['id'] for d in documents}
            if allowed:
                for source in self.p.repo.all(public, 'source'):
                    if source.get('documentId') in allowed and self.public_id(public, source['id']) == source_id:
                        return public, source['id']
        require(False, 'SOURCE_NOT_FOUND')

    def read(self, rag, source_id, course_id):
        scope, original = self.resolve_source(source_id, course_id)
        source = rag.read(scope, original)
        return self.tagged(source, scope, original != source_id)

    async def search(self, rag, course_id, query, *, history=(), new_topic=False,
                     document_ids=None, section=None, mode="hybrid", budget=2000, limit=6):
        require(type(budget) is int and 32 <= budget <= 16000 and type(limit) is int and 1 <= limit <= 20, 'INVALID_BUDGET')
        started=time.perf_counter()
        private = self.private_scope(course_id)
        if private.user_id == self.p.user_id:
            return await rag.search(private, query, history=history, new_topic=new_topic,
                document_ids=document_ids, section=section, mode=mode, budget=budget, limit=limit)
        results = []
        scopes = [(private, document_ids, False)]
        if private.user_id != self.p.user_id:
            for public,documents in self.public_libraries(course_id):
                ids = [d['id'] for d in documents if document_ids is None or d['id'] in document_ids]
                if ids:
                    scopes.append((public, ids, True))
        for scope, ids, public in scopes:
            result = await rag.search(scope, query, history=history, new_topic=new_topic,
                document_ids=ids, section=section, mode=mode, budget=budget, limit=limit)
            results.append({**result, 'sources': [self.tagged(s, scope, public) for s in result['sources']]})
        sources, seen, used = [], set(), 0
        for result in results:
            for source in result['sources']:
                size = len(source.get('quote', '').encode('utf-8'))
                key=self.evidence_key(source)
                if key in seen or used + size > budget or len(sources) >= limit:
                    continue
                # Re-read after all external awaits, including private hits.
                try:
                    self.validate_citation(rag, source, course_id)
                except AppError:
                    continue
                sources.append(source); seen.add(key); used += size
        from .rag_search import conflicts
        opposing=conflicts(sources)
        return {'schemaVersion':'rag-1','scope':private.wire(),'query':query,'rewrittenQuery':results[0].get('rewrittenQuery',query),
                'sources': sources, 'warnings': list(dict.fromkeys(w for r in results for w in r.get('warnings', []))),
                'status': 'conflict' if opposing or any(r.get('status') == 'conflict' for r in results) else 'evidence_found' if sources else 'insufficient',
                'conflicts':opposing,'budget':{'unit':'utf8Bytes','limit':budget,'used':used},
                'elapsedMs':round((time.perf_counter()-started)*1000,3),'supportChecked': False}

    def validate_citation(self, rag, citation, course_id=None):
        require(isinstance(citation, dict), 'INVALID_CITATION')
        origin = citation.get('scopeOrigin') or {}
        require(origin.get('user_id', self.current_user_id) in (self.current_user_id, self.p.user_id), 'SOURCE_SCOPE_FORBIDDEN')
        course = course_id or citation.get('courseId') or origin.get('course_id') or 'course-default'
        scope, source_id = self.resolve_source(citation.get('id') or citation.get('sourceId'), course)
        # The opaque public alias may resolve to an approved original course.
        # Private citations retain the strict requested-course boundary.
        require(scope.user_id==self.p.user_id or not origin.get('course_id') or origin['course_id']==course,'SOURCE_SCOPE_FORBIDDEN')
        if origin:
            require(origin == {'user_id': scope.user_id, 'course_id': scope.course_id}, 'SOURCE_SCOPE_FORBIDDEN')
        restored = {**citation, 'id': source_id}
        if 'sourceId' in restored:
            restored['sourceId'] = source_id
        return rag.validate(scope, restored)
