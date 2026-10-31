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
from typing import Any, Dict, List, Optional, Tuple

from .common import AppError, Scope, require
from .rag_service import RagService


# Preset file hashes from materials/ manifest
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
    """Resolve protected identities on the server before projecting an HTTP payload.

    Model/tool adapters may omit fileHash or isPlatform; those omissions must not
    allow a protected source to leak through chat, entity lists or workspace sync.
    Stored evidence and model inputs are untouched.
    """
    if platform is None:
        return lambda value:value
    scope = platform.scope(course_id)
    documents = {d['id']:d for d in platform.repo.all(scope, 'document')}
    protected_documents = {key for key,doc in documents.items() if is_platform_document(doc, scope)}
    sources = {s['id']:s for s in platform.repo.all(scope, 'source')}
    protected_sources = {key for key,source in sources.items()
                         if source.get('documentId') in protected_documents or is_platform_source(source, scope)}

    def project(item):
        if isinstance(item, list):
            return [project(child) for child in item]
        if not isinstance(item, dict):
            return item
        key = item.get('id')
        if isinstance(key, str) and (key in protected_sources or ('quote' in item and is_platform_source(item))):
            original = sources.get(key, {})
            return public_source_projection({**original, **item}, True)
        if isinstance(key, str) and key in protected_documents:
            return {**{field:item[field] for field in ('id','name','title','version','status','archived','superseded','createdAt','updatedAt') if field in item},
                    'isPlatform':True, 'protected':True}
        return {name:project(child) for name,child in item.items()}
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
    """Manages Public preset scope + Current account private scope with budget constraints."""

    def __init__(self, platform, current_user_id: Optional[str] = None):
        self.p = platform
        self.current_user_id = current_user_id or getattr(platform, "user_id", "local-user")
        self.public_scope = Scope(user_id="local-user", course_id="course-default")

    def private_scope(self, course_id: str = "course-default") -> Scope:
        # User's own scope
        return Scope(user_id=self.current_user_id, course_id=course_id)

    async def search(
        self,
        rag: RagService,
        course_id: str,
        query: str,
        *,
        history: Tuple = (),
        new_topic: bool = False,
        document_ids: Optional[List[str]] = None,
        section: Optional[str] = None,
        mode: str = "hybrid",
        budget: int = 2000,
        limit: int = 6
    ) -> Dict[str, Any]:
        """Perform combined search across public and private scopes within the single global budget."""
        require(type(budget) is int and 32 <= budget <= 16000 and type(limit) is int and 1 <= limit <= 20, "INVALID_BUDGET")

        # If user is local-user on course-default, standard search
        user_scope = self.private_scope(course_id)
        if user_scope.user_id == self.public_scope.user_id and user_scope.course_id == self.public_scope.course_id:
            res = await rag.search(
                user_scope, query, history=history, new_topic=new_topic,
                document_ids=document_ids, section=section, mode=mode, budget=budget, limit=limit
            )
            # Mark platform status
            for s in res.get("sources", []):
                s["isPlatform"] = is_platform_source(s, user_scope)
                s["scopeOrigin"] = {"user_id": user_scope.user_id, "course_id": user_scope.course_id}
            return res

        # Otherwise, search both scopes concurrently
        # Allocate half budget/limit to each as initial candidates, then re-rank and trim to global budget
        cand_limit = min(limit, 6)
        cand_budget = min(budget, 4000)

        # 1. Search public
        public_res = await rag.search(
            self.public_scope, query, history=history, new_topic=new_topic,
            section=section, mode=mode, budget=cand_budget, limit=cand_limit
        )

        # 2. Search private (if course exists)
        private_res = {"sources": [], "warnings": []}
        try:
            self.p.repo.require_course(user_scope)
            private_res = await rag.search(
                user_scope, query, history=history, new_topic=new_topic,
                document_ids=document_ids, section=section, mode=mode, budget=cand_budget, limit=cand_limit
            )
        except Exception:
            pass

        # Tag origins
        for s in public_res.get("sources", []):
            s["isPlatform"] = True
            s["scopeOrigin"] = {"user_id": self.public_scope.user_id, "course_id": self.public_scope.course_id}

        for s in private_res.get("sources", []):
            s["isPlatform"] = False
            s["scopeOrigin"] = {"user_id": user_scope.user_id, "course_id": user_scope.course_id}

        # Merge results, deduplicate by id, respect total limit & budget
        combined_sources: List[Dict[str, Any]] = []
        seen_ids = set()
        total_bytes = 0

        # Alternate or prioritize best hits
        pool = []
        # Pair up: private sources first (personal user notes are specific), followed by public
        p_sources = private_res.get("sources", [])
        pub_sources = public_res.get("sources", [])

        idx = 0
        while idx < max(len(p_sources), len(pub_sources)):
            if idx < len(p_sources):
                pool.append(p_sources[idx])
            if idx < len(pub_sources):
                pool.append(pub_sources[idx])
            idx += 1

        for s in pool:
            if s["id"] in seen_ids:
                continue
            quote_bytes = len(s.get("quote", "").encode("utf-8"))
            if total_bytes + quote_bytes > budget:
                continue
            seen_ids.add(s["id"])
            combined_sources.append(s)
            total_bytes += quote_bytes
            if len(combined_sources) >= limit:
                break

        warnings = list(dict.fromkeys(public_res.get("warnings", []) + private_res.get("warnings", [])))
        return {
            "sources": combined_sources,
            "warnings": warnings,
            "status": "conflict" if ("conflict" in (public_res.get("status"), private_res.get("status"))) else "evidence_found" if combined_sources else "insufficient",
            "supportChecked": False
        }

    def validate_citation(self, rag: RagService, citation: Dict[str, Any]) -> bool:
        """Validate citation back against its origin scope."""
        require(isinstance(citation, dict), "INVALID_CITATION")
        origin = citation.get("scopeOrigin")
        if origin and isinstance(origin, dict) and origin.get("user_id") and origin.get("course_id"):
            target_scope = Scope(user_id=origin["user_id"], course_id=origin["course_id"])
        else:
            # Fallback to current scope
            target_scope = self.private_scope(citation.get("courseId", "course-default"))
        require(target_scope.user_id in (self.current_user_id, self.public_scope.user_id), "SOURCE_SCOPE_FORBIDDEN")
        return rag.validate(target_scope, citation)
