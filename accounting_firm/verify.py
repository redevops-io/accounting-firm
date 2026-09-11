"""The verifier — provenance by construction. Runs per claim, by claim type (plan §8).

  NUMBER                   → a cross-checked computation exists and engines A/B agree
  FACT                     → at least one evidence reference
  PROFESSIONAL_JUDGMENT    → a qualification whose conclusion was policy-derived (not the model)
  AUTHORITY_INTERPRETATION → every cited authority resolves in the corpus

A claim with any failing check blocks the sign gate.
"""
from __future__ import annotations

from .contracts import ClaimType, Conclusion, Deliverable
from .resolvers import select_resolver


def verify(deliverable: Deliverable, resolver=None) -> dict:
    resolver = resolver or select_resolver()
    comps = {c.name: c for c in deliverable.computations}
    # a judgment is keyed by project_id (ResearchQualification) or subject (generic Judgment)
    quals = {(getattr(q, "project_id", None) or getattr(q, "subject", None)): q
             for q in deliverable.qualifications}
    blocking: list[str] = []

    for c in deliverable.claims:
        c.verifier_results = []

        def check(name: str, ok: bool, detail: str = "") -> None:
            c.verifier_results.append({"check": name, "ok": bool(ok), "detail": detail})

        if c.claim_type == ClaimType.NUMBER:
            comp = comps.get(c.computation_ref or "")
            check("computation_exists", comp is not None, c.computation_ref or "(none)")
            check("engines_agree", bool(comp and comp.agreement),
                  "A/B cross-check" if comp else "no computation")

        elif c.claim_type == ClaimType.FACT:
            check("has_evidence", len(c.evidence_refs) >= 1)

        elif c.claim_type == ClaimType.PROFESSIONAL_JUDGMENT:
            q = quals.get(c.assessment_ref or "")
            check("assessment_exists", q is not None, c.assessment_ref or "(none)")
            # a QUALIFIED judgment claim must rest on a QUALIFIED conclusion (policy-derived)
            check("conclusion_consistent",
                  bool(q and q.conclusion == Conclusion.QUALIFIED),
                  q.conclusion.value if q else "no qualification")

        elif c.claim_type == ClaimType.AUTHORITY_INTERPRETATION:
            check("has_authority", len(c.authority_refs) >= 1)
            for a in c.authority_refs:
                resolved, _ = resolver.resolve(a.authority, (a.passage_ref,) if a.passage_ref else ())
                check(f"resolves:{a.authority}", resolved, a.authority)

        if not c.verified:
            blocking.append(c.claim_id)

    return {"all_ok": not blocking, "blocking_claims": blocking,
            "checked": len(deliverable.claims)}
