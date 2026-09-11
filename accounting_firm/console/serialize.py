"""Serialise a governed §41 deliverable into the JSON the review console renders.

Deliverable-agnostic where it can be: the claim graph, provenance resolution, reconciliations, ledger and
operational status are generic. The one §41-specific bit is reading `ResearchQualification`'s four named
assessments (the general `Judgment` shape is read the same way). Nothing here computes or concludes — it
reads what the deliverable already produced and resolves each claim's provenance for display.
"""
from __future__ import annotations

import os
import time

from ..contracts import (Conclusion, Decision, Deliverable, Engagement, ResearchQualification, Result,
                         SignOff)
from ..deliverables import rd_credit_study
from ..resolvers import select_resolver

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(os.path.dirname(HERE)), "demo_data")

# The demo engagement: Northwind, one §41 study, with the allocation worksheet so the *conflicting*-evidence
# case (Rao · Atlas: payroll 60% vs worksheet 40%) is present alongside Borealis (missing) and the credit
# (sufficient) — the full three-case trust model on one deliverable.
_PATHS = {"payroll": f"{DATA}/payroll_export.csv", "gl": f"{DATA}/gl_extract.csv",
          "prior_year": f"{DATA}/prior_year.csv", "project_desc": f"{DATA}/project_description.txt",
          "engineering": f"{DATA}/engineering_doc.txt", "worksheet": f"{DATA}/allocation_worksheet.csv"}


def _engagement() -> Engagement:
    return Engagement("ENG-NW-41", "Northwind Traders, Inc.", "rd_credit_study",
                      "IRC §41 R&D credit study, FY2025", 9500, 48)


def _auto_cpa(d: Deliverable) -> SignOff:
    # P0–P2 render a completed, signed study read-only (the interactive sign gate is P3).
    return SignOff("A. Mats, CPA", time.time(), "full", Decision.APPROVE)


# ── provenance resolution per claim (the graph, resolved) ─────────────────────────
def _assessment_json(a) -> dict:
    return {"criterion": a.criterion, "result": a.result.value, "confidence": round(a.confidence, 2),
            "rationale": a.rationale,
            "evidence": [{"doc_id": e.doc_id, "locator": e.locator, "quote": e.quote} for e in a.evidence],
            "authority": [{"authority": au.authority, "passage_ref": au.passage_ref} for au in a.authority]}


def _qualification_json(q: ResearchQualification) -> dict:
    order = ("permitted_purpose", "technological_in_nature", "elimination_of_uncertainty",
             "process_of_experimentation")
    return {"subject": q.project_id, "conclusion": q.conclusion.value,
            "assessments": [_assessment_json(getattr(q, name)) for name in order]}


def _computation_json(comp) -> dict:
    a, b = comp.outputs.get("engine_a", {}), comp.outputs.get("engine_b", {})
    keys = ("qre", "asc", "rrc", "credit")
    return {"name": comp.name, "engine": comp.engine, "cross_validator": comp.cross_validator,
            "agreement": comp.agreement, "elected": comp.outputs.get("elected"),
            "components": comp.outputs.get("components", {}), "inputs": comp.inputs,
            "outputs": {k: comp.outputs.get(k) for k in (*keys, "elected")},
            "cross_check": [{"figure": k, "engine_a": a.get(k), "engine_b": b.get(k),
                             "agree": (a.get(k) is not None and abs((a.get(k) or 0) - (b.get(k) or 0)) <= 0.01)}
                            for k in keys]}


def _claim_json(c, comps: dict, quals: dict, resolver) -> dict:
    prov: dict = {"kind": c.claim_type.value}
    if c.claim_type.value == "NUMBER":
        comp = comps.get(c.computation_ref or "")
        prov["computation"] = _computation_json(comp) if comp else None
    elif c.claim_type.value == "FACT":
        prov["evidence"] = [{"doc_id": e.doc_id, "locator": e.locator, "quote": e.quote}
                            for e in c.evidence_refs]
    elif c.claim_type.value == "AUTHORITY_INTERPRETATION":
        auth = []
        for a in c.authority_refs:
            resolved, passage = resolver.resolve(a.authority, (a.passage_ref,) if a.passage_ref else ())
            auth.append({"authority": a.authority, "passage_ref": a.passage_ref,
                         "resolved": bool(resolved), "passage": passage})
        prov["authority"] = auth
    elif c.claim_type.value == "PROFESSIONAL_JUDGMENT":
        q = quals.get(c.assessment_ref or "")
        prov["judgment"] = _qualification_json(q) if q else None
    return {"claim_id": c.claim_id, "section": c.section, "type": c.claim_type.value,
            "assertion": c.assertion, "confidence": round(c.confidence, 2), "verified": c.verified,
            "checks": [{"check": v["check"], "ok": v["ok"], "detail": v.get("detail", "")}
                       for v in c.verifier_results],
            "disposition": c.reviewer_disposition, "provenance": prov}


# ── operational status (plain language, not raw confidence) ───────────────────────
def _operational_status(d: Deliverable, docs) -> list[dict]:
    ver = all(c.verified for c in d.claims) if d.claims else False
    min_ext = min((dd.confidence.extraction for dd in docs), default=0.0)
    comps_agree = all(c.agreement for c in d.computations) if d.computations else False
    judgments_need_review = any(q.conclusion == Conclusion.REVIEW_REQUIRED for q in d.qualifications)
    return [
        {"label": "Evidence", "state": "Complete" if not d.escalations else "Exceptions held",
         "ok": True, "detail": f"{len(docs)} source documents ingested"},
        {"label": "Extraction", "state": "Verified" if min_ext >= 0.6 else "Correction required",
         "ok": min_ext >= 0.6, "detail": f"lowest extraction confidence {min_ext:.2f}"},
        {"label": "Authority", "state": "Resolved" if ver else "Unresolved",
         "ok": ver, "detail": "every cited authority re-retrieved and matched"},
        {"label": "Calculation", "state": "Independently cross-checked" if comps_agree else "Not agreed",
         "ok": comps_agree, "detail": "§41 Engine A = Engine B on every figure"},
        {"label": "Professional judgment",
         "state": "CPA review required" if judgments_need_review else "CPA reviewed",
         "ok": True, "detail": "the licensed CPA remains the authority"},
    ]


def _trust_model(d: Deliverable) -> dict:
    """The three cases, made explicit: sufficient → compute · missing → abstain · conflicting → reconcile."""
    credit = next((c for c in d.computations if c.name == "rd_credit"), None)
    missing = [_qualification_json(q) for q in d.qualifications
               if q.conclusion == Conclusion.REVIEW_REQUIRED]
    conflicting = [{"source_a": r.source_a, "source_b": r.source_b, "rule": r.expected_relationship,
                    "value_a": r.value_a, "value_b": r.value_b, "difference": r.difference,
                    "status": r.status, "blocking": r.blocking}
                   for r in d.reconciliations if r.blocking]
    return {
        "sufficient": {"headline": "Compute — engines A = B",
                       "credit": credit.outputs.get("credit") if credit else None,
                       "elected": credit.outputs.get("elected") if credit else None,
                       "qre": credit.outputs.get("qre") if credit else None,
                       "escalations": [e for e in d.escalations if "conflict" not in e and "Borealis" not in e]},
        "missing": {"headline": "Abstain — hold from the calculation, ask a human",
                    "projects": missing,
                    "escalations": [e for e in d.escalations if "Borealis" in e or "REVIEW_REQUIRED" in e]},
        "conflicting": {"headline": "Reconcile / escalate — refuse silent resolution",
                        "reconciliations": conflicting,
                        "escalations": [e for e in d.escalations if "conflict" in e]},
    }


def build_deliverable(paths: dict | None = None, cpa_review=None, provider=None) -> dict:
    """Run the §41 study (offline/deterministic by default) and serialise it for the console."""
    paths = paths or _PATHS
    eng = _engagement()
    d, led = rd_credit_study.run(eng, paths, cpa_review or _auto_cpa, provider=provider)
    _, docs = rd_credit_study.extract(paths, provider)          # source-document metadata for the EVIDENCE tab
    resolver = select_resolver()

    comps = {c.name: c for c in d.computations}
    quals = {q.project_id: q for q in d.qualifications}

    reconciliations = [{"source_a": r.source_a, "source_b": r.source_b, "rule": r.expected_relationship,
                        "value_a": r.value_a, "value_b": r.value_b, "difference": r.difference,
                        "tolerance": r.tolerance, "status": r.status, "blocking": r.blocking}
                       for r in d.reconciliations]

    return {
        "engagement": {"id": eng.engagement_id, "client": eng.client, "type": eng.deliverable_type,
                       "title": eng.deliverable_type.replace("_", " ").title(), "scope": eng.scope,
                       "price_usd": eng.price_usd, "sla_hours": eng.sla_hours},
        "status": d.status,
        "rendered": d.rendered,
        "claims": [_claim_json(c, comps, quals, resolver) for c in d.claims],
        "qualifications": [_qualification_json(q) for q in d.qualifications],
        "computations": [_computation_json(c) for c in d.computations],
        "reconciliations": reconciliations,
        "escalations": list(d.escalations),
        "trust_model": _trust_model(d),
        "operational_status": _operational_status(d, docs),
        "documents": [{"doc_id": dd.doc_id, "kind": dd.kind, "uri": os.path.basename(dd.uri),
                       "confidence": {"extraction": dd.confidence.extraction,
                                      "evidence_completeness": dd.confidence.evidence_completeness},
                       "facts": dd.extracted_facts, "provenance": dd.provenance} for dd in docs],
        "sign_offs": [{"cpa": s.cpa_principal, "decision": s.decision.value, "scope": s.scope,
                       "at": s.at, "ledger_ref": s.ledger_ref, "amendments": len(s.amendments)}
                      for s in d.sign_offs],
        "ledger": led.bundle(),
        "runtime": {"provider": (provider.name if provider else "deterministic"),
                    "corpus": resolver.name, "calculation": "§41 Engine A + Engine B",
                    "ledger": "agentic-os" if os.environ.get("FIRM_LEDGER") == "agentic-os" else "in-repo",
                    "verification": "PASS" if all(c.verified for c in d.claims) else "FAIL"},
    }
