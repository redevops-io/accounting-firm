"""Authority resolution seam — the local corpus by default, redevops-rag when configured.

The verifier resolves every cited authority through a `Resolver`. `LocalResolver` re-checks the citation
against the curated corpus (offline default). `RagResolver` queries a real redevops-rag Store — the same
retrieval capability the Context Runtime routes to — so grounding scales to the full IRC/CFR/ASC corpus.
Selected by env (`FIRM_CORPUS=rag` + `FIRM_RAG_DB`); default local, so tests/demo run offline.
"""
from __future__ import annotations

import os

from . import corpus


class LocalResolver:
    name = "local"

    def resolve(self, authority_id: str, about: tuple[str, ...] = ()) -> tuple[bool, str]:
        return corpus.resolve(authority_id, about)


class RagResolver:
    name = "rag"

    def __init__(self, store, hybrid_search):
        self._store = store
        self._search = hybrid_search

    def resolve(self, authority_id: str, about: tuple[str, ...] = ()) -> tuple[bool, str]:
        q = authority_id + ((" " + " ".join(about)) if about else "")
        try:
            hits = self._search(self._store, q, limit=3, pool=15, recency_half_life_days=0)
        except Exception:
            return corpus.resolve(authority_id, about)          # fail safe → local
        for h in hits:
            text = h.get("text") or ""
            if authority_id.lower() in text.lower() or h.get("document_id", "") == authority_id:
                if not about or any(a.lower() in text.lower() for a in about):
                    return True, text
        return False, ""


class _RagKnowledgeRetriever:
    """Adapts a redevops-rag Store to the kernel's KnowledgeRetriever protocol (retrieve(query, k)),
    so the Context Runtime can route to it as one engine among many."""
    def __init__(self, store, hybrid_search):
        self._store = store
        self._search = hybrid_search

    def retrieve(self, query: str, k: int = 5) -> list[dict]:
        try:
            hits = self._search(self._store, query, limit=k, pool=max(15, k * 3), recency_half_life_days=0)
        except Exception:
            return []
        return [{"id": h.get("document_id", ""), "text": h.get("text", "") or ""} for h in hits]


class ContextResolver:
    """Resolves every cited authority through the kernel's Context Runtime (app.context.GroundedContext) —
    the single governed retrieval door (N6). The engine is chosen by query shape and every result carries
    CR provenance; here we pin the semantic ``vector`` engine (authority lookups have no temporal/graph/
    structured shape). Over redevops-rag when a store is wired, else the curated corpus — either way the
    retrieval goes THROUGH the Context Runtime, not a direct call. Selected by ``FIRM_CORPUS=context``."""
    name = "context"

    def __init__(self, ctx):
        self._ctx = ctx

    def resolve(self, authority_id: str, about: tuple[str, ...] = ()) -> tuple[bool, str]:
        q = authority_id + ((" " + " ".join(about)) if about else "")
        try:
            res = self._ctx.retrieve(q, k=3, representation="vector")
        except Exception:
            return corpus.resolve(authority_id, about)          # fail safe → local
        for item in res.results:
            text = item.get("text", "") or ""
            if authority_id.lower() in text.lower() or item.get("id") == authority_id:
                if not about or any(a.lower() in text.lower() for a in about):
                    return True, text
        return False, ""


def _context_resolver():
    """GroundedContext over a redevops-rag engine when FIRM_RAG_DB is set, else the curated corpus — both
    behind the Context Runtime's KnowledgeRetriever protocol."""
    from agentic_os.app.context import GroundedContext
    from agentic_os.mission.context import KeywordRetriever
    retriever = None
    if os.environ.get("FIRM_RAG_DB"):
        try:
            from redevops_rag.embed import Embedder
            from redevops_rag.retrieve import hybrid_search
            from redevops_rag.store import Store
            store = Store(Embedder(model_name=os.environ.get("FIRM_EMBED_MODEL", "BAAI/bge-small-en-v1.5")),
                         db_path=os.environ["FIRM_RAG_DB"])
            retriever = _RagKnowledgeRetriever(store, hybrid_search)
        except Exception:
            retriever = None
    if retriever is None:
        # Prepend the authority id to the searchable text so an id-shaped query (e.g. "IRC §41(a)(1)")
        # ranks its own authority first under token-overlap scoring — authority lookups are id-exact.
        docs = [{"id": aid, "text": f"{aid}\n{text}"} for aid, (text, _kw) in corpus.CORPUS.items()]
        retriever = KeywordRetriever(docs)
    ctx = GroundedContext(retrievers={"vector": retriever})
    return ContextResolver(ctx)


def select_resolver():
    corpus_mode = os.environ.get("FIRM_CORPUS")
    if corpus_mode == "context":                                # N6: ground through the Context Runtime
        try:
            return _context_resolver()
        except Exception:                                       # kernel absent → local
            return LocalResolver()
    if corpus_mode == "rag" and os.environ.get("FIRM_RAG_DB"):  # direct redevops-rag (pre-N6 path)
        try:
            from redevops_rag.embed import Embedder
            from redevops_rag.retrieve import hybrid_search
            from redevops_rag.store import Store
            store = Store(Embedder(model_name=os.environ.get("FIRM_EMBED_MODEL", "BAAI/bge-small-en-v1.5")),
                         db_path=os.environ["FIRM_RAG_DB"])
            return RagResolver(store, hybrid_search)
        except Exception:                                       # redevops-rag absent / store unbuilt → local
            return LocalResolver()
    return LocalResolver()
