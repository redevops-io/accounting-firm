"""Build the authority corpus into a redevops-rag Store (go-live grounding).

Ingests accounting_firm.corpus.CORPUS (IRC §41 / Treas. Reg. / ASC 606 excerpts) as embedded chunks, so
RagResolver can ground citations at scale. Run with a Python that has redevops-rag installed:

    PYTHONPATH=. /path/to/redevops-rag/.venv/bin/python scripts/build_corpus.py corpus.duckdb

Then serve with FIRM_CORPUS=rag FIRM_RAG_DB=corpus.duckdb.
"""
import hashlib
import os
import sys

from redevops_rag.embed import Embedder
from redevops_rag.store import Store

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from accounting_firm.corpus import CORPUS


def main(db_path: str = "corpus.duckdb") -> int:
    emb = Embedder(model_name=os.environ.get("FIRM_EMBED_MODEL", "BAAI/bge-small-en-v1.5"))
    store = Store(emb, db_path=db_path)
    texts = [f"{aid} — {p}" for aid, (p, _c) in CORPUS.items()]
    vecs = emb.encode(texts)
    chunks = []
    for (aid, (_p, concepts)), text, vec in zip(CORPUS.items(), texts, vecs):
        chunks.append({"document_id": aid, "text": text, "embedding": vec,
                       "content_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
                       "metadata": {"authority": aid, "concepts": list(concepts)}})
    n = store.add_chunks(chunks, reindex=True)
    print(f"ingested {n} authorities → {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "corpus.duckdb"))
