"""Serialise a governed deliverable into the JSON the review console renders — deliverable-agnostic.

The claim graph, provenance resolution, computation cross-check, reconciliations, ledger, mission trace,
EXPLAIN and operational status are all generic: a professional judgment is read the same whether it is a
§41 `ResearchQualification` (four named assessments) or the general `Judgment` (a subject + an assessments
tuple), and a computation shows per-engine A/B columns when it carries that detail, else the agreed figure
with its cross-validator. A `DeliverableSpec` supplies only the domain-specific labels (headline figure,
rules name) — so the SAME console renders the §41 study and the ASC 606 memo with no console change. Nothing
here computes or concludes; it reads what the deliverable produced.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from ..contracts import Conclusion, Decision, Deliverable, Engagement, Result, SignOff
from ..deliverables import rd_credit_study, tech_accounting_memo
from ..resolvers import select_resolver

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(os.path.dirname(HERE)), "demo_data")


# ── the engagement: several deliverables, one firm, one console ───────────────────
@dataclass(frozen=True)
class DeliverableSpec:
    id: str
    title: str
    engagement: Engagement
    module: object = None                       # has run(engagement, paths, cpa_review=None, provider=None) + extract
    paths: dict = field(default_factory=dict)
    headline_key: str = ""                      # the figure to feature in the "sufficient" case
    headline_label: str = ""
    secondary: tuple = ()                        # ((output_key, label), …) shown under the headline
    elected_key: str = ""                        # e.g. "elected" for §41; "" if none
    rules_label: str = ""                        # what an amendment never touches (domain rules)
    available: bool = True

    @property
    def signable_module(self):
        return self.module


_RD_PATHS = {"payroll": f"{DATA}/payroll_export.csv", "gl": f"{DATA}/gl_extract.csv",
             "prior_year": f"{DATA}/prior_year.csv", "project_desc": f"{DATA}/project_description.txt",
             "engineering": f"{DATA}/engineering_doc.txt", "worksheet": f"{DATA}/allocation_worksheet.csv"}
_MEMO_PATHS = {"contract": f"{DATA}/contract.txt", "trial_balance": f"{DATA}/trial_balance.csv"}

SPECS: dict[str, DeliverableSpec] = {
    "rd_credit_study": DeliverableSpec(
        id="rd_credit_study", title="R&D Credit Study",
        engagement=Engagement("ENG-NW-41", "Northwind Traders, Inc.", "rd_credit_study",
                              "IRC §41 R&D credit study, FY2025", 9500, 48),
        module=rd_credit_study, paths=_RD_PATHS,
        headline_key="credit", headline_label="§41 credit", secondary=(("qre", "QRE"),),
        elected_key="elected", rules_label="§41 calculation rules — Engine A + Engine B, versioned and controlled"),
    "tech_accounting_memo": DeliverableSpec(
        id="tech_accounting_memo", title="ASC 606 Revenue Memo",
        engagement=Engagement("ENG-NW-606", "Northwind Traders, Inc.", "tech_accounting_memo",
                              "ASC 606 revenue recognition, FY2025", 6500, 48),
        module=tech_accounting_memo, paths=_MEMO_PATHS,
        headline_key="recognized", headline_label="Revenue recognized",
        secondary=(("deferred", "Deferred"), ("monthly", "Monthly")),
        rules_label="ASC 606 recognition rules — the schedule engine + cross-check, versioned and controlled"),
    "income_tax_provision": DeliverableSpec(
        id="income_tax_provision", title="Income Tax Provision",
        engagement=Engagement("ENG-NW-PROV", "Northwind Traders, Inc.", "income_tax_provision",
                              "ASC 740 income tax provision, FY2025", 8500, 48),
        available=False),
}
DEFAULT_ID = "rd_credit_study"


def _auto_cpa(_d: Deliverable) -> SignOff:
    return SignOff("A. Mats, CPA", time.time(), "full", Decision.APPROVE)


# ── generic readers for a professional judgment (Judgment or ResearchQualification) ──
def _assessments_of(q) -> list:
    if hasattr(q, "assessments"):                              # the general Judgment
        return list(q.assessments)
    return [getattr(q, n) for n in ("permitted_purpose", "technological_in_nature",     # §41 four-part
            "elimination_of_uncertainty", "process_of_experimentation")]


def _subject_of(q) -> str:
    return getattr(q, "project_id", None) or getattr(q, "subject", "")


def _assessment_json(a) -> dict:
    return {"criterion": a.criterion, "result": a.result.value, "confidence": round(a.confidence, 2),
            "rationale": a.rationale,
            "evidence": [{"doc_id": e.doc_id, "locator": e.locator, "quote": e.quote} for e in a.evidence],
            "authority": [{"authority": au.authority, "passage_ref": au.passage_ref} for au in a.authority]}


def _qualification_json(q) -> dict:
    return {"subject": _subject_of(q), "conclusion": q.conclusion.value,
            "assessments": [_assessment_json(a) for a in _assessments_of(q)]}


def _computation_json(comp) -> dict:
    """Per-engine A/B columns when the computation carries that detail (§41); otherwise the agreed scalar
    figures with the cross-validator (memo). Both convey the same fact: two independent engines agreed."""
    ea, eb = comp.outputs.get("engine_a"), comp.outputs.get("engine_b")
    scalars = {k: v for k, v in comp.outputs.items() if isinstance(v, (int, float))}
    if ea and eb:
        keys = [k for k in ("qre", "asc", "rrc", "credit") if k in ea] or list(scalars)
        cross = [{"figure": k, "engine_a": ea.get(k), "engine_b": eb.get(k),
                  "agree": ea.get(k) is not None and abs((ea.get(k) or 0) - (eb.get(k) or 0)) <= 0.01}
                 for k in keys]
        has_engines = True
    else:
        cross = [{"figure": k, "value": v, "agree": comp.agreement} for k, v in scalars.items()]
        has_engines = False
    return {"name": comp.name, "engine": comp.engine, "cross_validator": comp.cross_validator,
            "agreement": comp.agreement, "has_engines": has_engines,
            "elected": comp.outputs.get("elected"), "components": comp.outputs.get("components", {}),
            "outputs": {k: v for k, v in comp.outputs.items() if not isinstance(v, (dict, list))},
            "cross_check": cross}


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
         "ok": comps_agree, "detail": "two independent engines agree on every figure"},
        {"label": "Professional judgment",
         "state": "CPA review required" if judgments_need_review else "CPA reviewed",
         "ok": True, "detail": "the licensed CPA remains the authority"},
    ]


def _trust_model(d: Deliverable, spec: DeliverableSpec) -> dict:
    """The three cases, made explicit: sufficient → compute · missing → abstain · conflicting → reconcile."""
    prim = d.computations[0] if d.computations else None
    out = prim.outputs if prim else {}
    missing = [_qualification_json(q) for q in d.qualifications if q.conclusion == Conclusion.REVIEW_REQUIRED]
    conflicting = [{"source_a": r.source_a, "source_b": r.source_b, "rule": r.expected_relationship,
                    "value_a": r.value_a, "value_b": r.value_b, "difference": r.difference,
                    "status": r.status, "blocking": r.blocking}
                   for r in d.reconciliations if r.blocking]
    secondary = [{"label": lbl, "value": out.get(k)} for k, lbl in spec.secondary if out.get(k) is not None]
    return {
        "sufficient": {"headline": "Compute — two engines agree",
                       "label": spec.headline_label, "value": out.get(spec.headline_key),
                       "elected": out.get(spec.elected_key) if spec.elected_key else None,
                       "secondary": secondary,
                       "escalations": [e for e in d.escalations if "conflict" not in e and "Borealis" not in e]},
        "missing": {"headline": "Abstain — hold from the calculation, ask a human", "projects": missing,
                    "escalations": [e for e in d.escalations if "Borealis" in e or "REVIEW_REQUIRED" in e]},
        "conflicting": {"headline": "Reconcile / escalate — refuse silent resolution",
                        "reconciliations": conflicting,
                        "escalations": [e for e in d.escalations if "conflict" in e]},
    }


# ── Mission trace (how the engagement was produced) ───────────────────────────────
def _mission_trace(d: Deliverable, led) -> list[dict]:
    types = {e.type for e in led.events()}
    blocking_recons = sum(1 for r in d.reconciliations if r.blocking)
    held = sum(1 for q in d.qualifications if q.conclusion == Conclusion.REVIEW_REQUIRED)
    review = ({"signed": ("done", "✓ signed"), "rejected": ("block", "✕ rejected"),
               "ready_for_review": ("await", "● awaiting signature")}
              .get(d.status, ("await", d.status.replace("_", " "))))
    return [
        {"stage": "INGEST", "state": "ok" if "documents.ingested" in types else "pending",
         "detail": "source documents ingested with provenance"},
        {"stage": "NORMALIZE", "state": "ok" if "facts.extracted" in types else "pending",
         "detail": "facts extracted and typed"},
        {"stage": "RECONCILE", "state": "warn" if blocking_recons else "ok",
         "detail": f"{blocking_recons} exception(s) held" if blocking_recons else "sources reconcile"},
        {"stage": "ASSESS", "state": "ok",
         "detail": f"{held} project(s) held for review" if held else "all criteria assessed"},
        {"stage": "COMPUTE", "state": "ok" if "computed" in types else "pending",
         "detail": "two independent engines agree"},
        {"stage": "DRAFT", "state": "ok" if "drafted" in types else "pending", "detail": "claim graph rendered"},
        {"stage": "VERIFY", "state": "ok" if "verified" in types else "pending",
         "detail": "every claim's provenance verified"},
        {"stage": "CPA REVIEW", "state": review[0], "detail": review[1]},
    ]


# ── EXPLAIN (why the system reached this state, in plain terms) ────────────────────
def _explain(d: Deliverable, spec: DeliverableSpec) -> list[dict]:
    out = []
    for q in d.qualifications:
        if q.conclusion == Conclusion.REVIEW_REQUIRED:
            ins = [a.criterion for a in _assessments_of(q) if a.result == Result.INSUFFICIENT]
            out.append({"q": f"Why was {_subject_of(q)} excluded?",
                        "facts": [f"evidence completeness: insufficient ({', '.join(ins) or 'criteria'})",
                                  "policy: all criteria required", "result: REVIEW_REQUIRED",
                                  "calculation input: excluded", "human gate: CPA determination required"]})
    for r in d.reconciliations:
        if r.blocking:
            out.append({"q": f"Why is the {r.source_a.split('·')[-1].strip()} allocation held?",
                        "facts": [f"two sources disagree: {r.source_a} {r.value_a} vs {r.source_b} {r.value_b}",
                                  f"difference {abs(r.difference)} exceeds tolerance {r.tolerance}",
                                  "policy: conflicting evidence is not averaged", "status: BLOCKING",
                                  "calculation input: this allocation excluded", "human gate: reconcile/escalate"]})
    prim = d.computations[0] if d.computations else None
    if prim:
        out.append({"q": "How is the computed figure trustworthy?",
                    "facts": ["computed by code, not the model",
                              *([f"elected method: {prim.outputs.get('elected')}"] if prim.outputs.get("elected") else []),
                              f"{prim.engine} and {prim.cross_validator} agree on every figure",
                              f"cross-check: {'PASSED' if prim.agreement else 'FAILED'}"]})
    return out


# ── consequential amendment (what a CPA change affects vs. what it never touches) ──
def _amendment_impact(d: Deliverable, spec: DeliverableSpec) -> dict:
    amended = [c.claim_id for c in d.claims if c.reviewer_disposition == "amended"]
    return {
        "amended_claims": amended,
        "affected": ["This deliverable — the amended claim's disposition and rendering",
                     "The evidence ledger — an immutable amendment entry (the artifact is never edited in place)",
                     "Future retrieval / extraction / drafting — a LearningOutcome tunes the AI layer"],
        "unaffected": [spec.rules_label,
                       "The qualification policy — the criteria and conclusion logic",
                       "Regulatory guardrails — the CPA remains the signing authority"],
    }


def _engagements(current_id: str, statuses: dict[str, str]) -> list[dict]:
    order = ["rd_credit_study", "tech_accounting_memo", "income_tax_provision"]
    return [{"id": s.id, "title": s.title, "type": s.engagement.deliverable_type,
             "available": s.available, "current": s.id == current_id,
             "status": statuses.get(s.id, "available" if s.available else "not_started")}
            for s in (SPECS[i] for i in order)]


def serialize_state(spec: DeliverableSpec, d: Deliverable, led, docs, provider=None,
                    statuses: dict | None = None) -> dict:
    resolver = select_resolver()
    comps = {c.name: c for c in d.computations}
    quals = {_subject_of(q): q for q in d.qualifications}
    reconciliations = [{"source_a": r.source_a, "source_b": r.source_b, "rule": r.expected_relationship,
                        "value_a": r.value_a, "value_b": r.value_b, "difference": r.difference,
                        "tolerance": r.tolerance, "status": r.status, "blocking": r.blocking}
                       for r in d.reconciliations]
    return {
        "engagement": {"id": spec.engagement.engagement_id, "client": spec.engagement.client,
                       "type": spec.engagement.deliverable_type, "title": spec.title,
                       "scope": spec.engagement.scope, "price_usd": spec.engagement.price_usd,
                       "sla_hours": spec.engagement.sla_hours},
        "deliverable_id": spec.id,
        "engagements": _engagements(spec.id, statuses or {spec.id: d.status}),
        "status": d.status,
        "rendered": d.rendered,
        "claims": [_claim_json(c, comps, quals, resolver) for c in d.claims],
        "qualifications": [_qualification_json(q) for q in d.qualifications],
        "computations": [_computation_json(c) for c in d.computations],
        "reconciliations": reconciliations,
        "escalations": list(d.escalations),
        "trust_model": _trust_model(d, spec),
        "operational_status": _operational_status(d, docs),
        "mission_trace": _mission_trace(d, led),
        "explain": _explain(d, spec),
        "amendment_impact": _amendment_impact(d, spec),
        "learning_outcomes": [{"kind": o.kind, "decision": o.decision, "reward": o.reward,
                               "context": o.context} for o in getattr(d, "learning_outcomes", [])],
        "signable": d.status == "ready_for_review",
        "documents": [{"doc_id": dd.doc_id, "kind": dd.kind, "uri": os.path.basename(dd.uri),
                       "confidence": {"extraction": dd.confidence.extraction,
                                      "evidence_completeness": dd.confidence.evidence_completeness},
                       "facts": dd.extracted_facts, "provenance": dd.provenance} for dd in docs],
        "sign_offs": [{"cpa": s.cpa_principal, "decision": s.decision.value, "scope": s.scope,
                       "at": s.at, "ledger_ref": s.ledger_ref, "amendments": len(s.amendments)}
                      for s in d.sign_offs],
        "ledger": led.bundle(),
        "runtime": {"provider": (provider.name if provider else "deterministic"),
                    "corpus": resolver.name, "calculation": f"{spec.title} · Engine A + Engine B",
                    "ledger": "agentic-os" if os.environ.get("FIRM_LEDGER") == "agentic-os" else "in-repo",
                    "verification": "PASS" if all(c.verified for c in d.claims) else "FAIL"},
    }


def build_deliverable(paths: dict | None = None, cpa_review=None, provider=None,
                      deliverable_id: str = DEFAULT_ID) -> dict:
    """Run a deliverable to a *signed* state and serialise it (back-compat / one-shot view + tests)."""
    spec = SPECS[deliverable_id]
    eng = spec.engagement
    d, led = spec.module.run(eng, paths or spec.paths, cpa_review or _auto_cpa, provider=provider)
    _, docs = spec.module.extract(paths or spec.paths, provider)
    return serialize_state(spec, d, led, docs, provider)


class ReviewSession:
    """One live review of one deliverable: run to ready_for_review, hold the *same* deliverable + ledger,
    then sign it in place. Holding the object keeps claim ids stable across load → sign and lets the sign
    gate seal the very ledger the reviewer inspected. Single-tenant (a demo surface)."""

    def __init__(self, deliverable_id: str = DEFAULT_ID, provider=None):
        self.spec = SPECS[deliverable_id]
        if not self.spec.available:
            raise ValueError(f"deliverable '{deliverable_id}' is not available")
        self.provider = provider
        self.engagement = self.spec.engagement
        self._prepare()

    def _prepare(self) -> None:
        self.deliverable, self.ledger = self.spec.module.run(self.engagement, self.spec.paths,
                                                             provider=self.provider)
        _, self.docs = self.spec.module.extract(self.spec.paths, self.provider)

    def reset(self) -> None:
        self._prepare()

    def sign(self, decision: str, amendments: list | None = None, cpa: str = "A. Mats, CPA") -> dict:
        if self.deliverable.status != "ready_for_review":
            return {"error": f"deliverable is '{self.deliverable.status}', not open for signature"}
        try:
            dec = Decision(str(decision).upper())
        except ValueError:
            return {"error": f"unknown decision '{decision}'"}
        ams = [{"claim_id": a["claim_id"], "stage": a.get("stage", "draft"),
                "ai_choice": a.get("ai_choice", "drafting"), "reason": a.get("reason", "")}
               for a in (amendments or []) if a.get("claim_id")]

        def review(_d: Deliverable) -> SignOff:
            return SignOff(cpa, time.time(), "full", dec, amendments=ams)

        from .. import mission
        mission.sign(self.engagement, self.deliverable, self.ledger, review, self.provider or _resolve_provider())
        return self.json()

    def json(self, statuses: dict | None = None) -> dict:
        return serialize_state(self.spec, self.deliverable, self.ledger, self.docs, self.provider, statuses)


def _resolve_provider():
    from ..providers import select_provider
    return select_provider()
