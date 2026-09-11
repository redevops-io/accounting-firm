"""The CPA review console — a thin, read-only view over a governed deliverable.

The console renders nothing the firm didn't produce: it runs a deliverable's `run()` and serialises the
resulting claim graph, its provenance (evidence / authority / cross-checked computation A=B), the three-case
trust model (sufficient → compute · missing → abstain · conflicting → reconcile/escalate) and the ledger.
It is a *view*, not a second source of truth — every number and conclusion comes from the deliverable.

Run it:  python -m accounting_firm.console      (offline, deterministic; http://127.0.0.1:8088)
"""
from .serialize import build_deliverable

__all__ = ["build_deliverable"]
