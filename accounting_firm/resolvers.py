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


def select_resolver():
    if os.environ.get("FIRM_CORPUS") == "rag" and os.environ.get("FIRM_RAG_DB"):
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
