"""R&D credit study (§41) — the flagship deliverable, end to end.

extract (from MESSY docs) → reconcile → assess (per-criterion) → escalate → QRE schedule → §41 compute
(A↕B) → claim graph → render → verify → CPA review/sign → signed bundle → LearningOutcome.

The extraction and assessment functions here are the DETERMINISTIC stand-ins for the LLM seam: `extract`
parses the demo's ugly CSV/text; `assess` returns the structured per-criterion assessments a grounded model
would produce. In production these become model calls (Context Runtime) behind the same signatures — the
rest of the pipeline (reconcile, compute, claims, verify, sign, learn) is unchanged.
"""
from __future__ import annotations

import csv
import re
from dataclasses import asdict

from .. import claims, corpus, reconcile, verify
from ..contracts import (Assessment, AuthorityRef, ClaimType, Computation, Conclusion, Confidence,
                        Deliverable, EvidenceRef, Engagement, LearningOutcome, Result, ResearchQualification,
                        SignOff, SourceDocument)
from ..ledger import Ledger
from ..section41 import QREInputs, compute_credit, conclude

QUALIFIED_PROJECT = "Atlas"          # (the assess stub qualifies Atlas; Borealis → review)


# ── extraction (LLM seam; deterministic parser for the demo's messy docs) ───────
def _money(s: str) -> float:
    return float(re.sub(r"[^0-9.\-]", "", s or "0") or 0)


def _rows(path: str) -> list[list[str]]:
    # skipinitialspace so quoted fields with internal commas ("$450,250") survive a space after the delimiter
    with open(path, newline="") as fh:
        return [[c.strip() for c in row] for row in csv.reader(fh, skipinitialspace=True)]


def extract(paths: dict[str, str]) -> tuple[dict, list[SourceDocument]]:
    docs: list[SourceDocument] = []
    facts: dict = {}

    # payroll — messy CSV: "Chen, Alice", $180,000, "Atlas 80%; Borealis 20%"
    employees = []
    for i, r in enumerate(_rows(paths["payroll"])):
        if i == 0 or len(r) < 4 or not r[2] or r[0].lower().startswith("notes"):
            continue
        alloc = {p: int(pct) / 100 for p, pct in re.findall(r"([A-Za-z]+)\s+(\d+)%", r[3])}
        if not alloc:
            continue
        employees.append({"name": r[0], "wages": _money(r[2]), "alloc": alloc, "row": i + 1})
    facts["employees"] = employees
    docs.append(SourceDocument("payroll", "payroll_export", paths["payroll"],
                               {"employees": len(employees)},
                               Confidence(extraction=0.97, evidence_completeness=0.9), "parser/v0"))

    # general ledger
    gl = {}
    for r in _rows(paths["gl"])[1:]:
        if len(r) < 3:
            continue
        d = r[1].lower()
        if "wage" in d or "salaries" in d:
            gl["wages_total"] = _money(r[2])
        elif "suppl" in d:
            gl["supplies"] = _money(r[2])
        elif "cloud" in d or "computer" in d:
            gl["cloud"] = _money(r[2])
        elif "contract" in d:
            gl["contract"] = _money(r[2])
    facts["gl"] = gl
    docs.append(SourceDocument("gl", "gl_extract", paths["gl"], gl,
                               Confidence(extraction=0.98, evidence_completeness=0.95), "parser/v0"))

    # projects + engineering support (text) — kept as raw evidence for the assessor
    facts["projects"] = {}
    for key in ("project_desc", "engineering"):
        with open(paths[key]) as fh:
            text = fh.read()
        for m in re.finditer(r"Project\s+([A-Za-z]+)\s*[:\-]\s*(.+)", text):
            facts["projects"].setdefault(m.group(1), "")
        docs.append(SourceDocument(key, "project_description" if key == "project_desc" else "engineering_doc",
                                   paths[key], {"chars": len(text)},
                                   Confidence(extraction=0.9, evidence_completeness=0.8), "parser/v0"))

    # prior-year return data (prior QRE + RRC inputs)
    py = {r[0].strip().lower(): _money(r[1]) for r in _rows(paths["prior_year"]) if len(r) >= 2 and r[1]}
    facts["prior_qre"] = tuple(v for k, v in sorted(py.items()) if k.startswith("prior_qre"))
    facts["fixed_base_pct"] = py.get("fixed_base_pct", 0.0) / (100 if py.get("fixed_base_pct", 0) > 1 else 1)
    facts["avg_gross_receipts_prior4"] = py.get("avg_gross_receipts_prior4", 0.0)
    docs.append(SourceDocument("prior_year", "prior_year_returns", paths["prior_year"], py,
                               Confidence(extraction=0.95, evidence_completeness=0.9), "parser/v0"))
    return facts, docs


# ── structured judgment (LLM seam; the four-part test, per criterion) ───────────
_PASS = lambda crit, auth, ev: Assessment(crit, Result.PASS, evidence=ev, authority=auth, confidence=0.85,
                                          rationale="evidence supports the criterion")
_INSUF = lambda crit, auth: Assessment(crit, Result.INSUFFICIENT, authority=auth, confidence=0.5,
                                       rationale="insufficient contemporaneous evidence")


def assess(project: str, facts: dict) -> ResearchQualification:
    a41d = (AuthorityRef("IRC §41(d)(1)", "qualified research"),)
    reg_unc = (AuthorityRef("Treas. Reg. §1.41-4(a)(3)", "uncertainty"),)
    reg_exp = (AuthorityRef("Treas. Reg. §1.41-4(a)(5)", "process of experimentation"),)
    ev_proj = (EvidenceRef("project_desc", f"Project {project}"),)
    ev_eng = (EvidenceRef("engineering", f"Project {project} experimentation log"),)
    if project == QUALIFIED_PROJECT:                          # Atlas — all four satisfied
        q = ResearchQualification(project,
            permitted_purpose=_PASS("permitted_purpose", a41d, ev_proj),
            technological_in_nature=_PASS("technological_in_nature", a41d, ev_proj),
            elimination_of_uncertainty=_PASS("elimination_of_uncertainty", reg_unc, ev_eng),
            process_of_experimentation=_PASS("process_of_experimentation", reg_exp, ev_eng),
            conclusion=Conclusion.QUALIFIED)  # placeholder; policy derives below
    else:                                                    # Borealis — routine restyle, weak evidence
        q = ResearchQualification(project,
            permitted_purpose=_PASS("permitted_purpose", a41d, ev_proj),
            technological_in_nature=_PASS("technological_in_nature", a41d, ev_proj),
            elimination_of_uncertainty=_INSUF("elimination_of_uncertainty", reg_unc),
            process_of_experimentation=_INSUF("process_of_experimentation", reg_exp),
            conclusion=Conclusion.QUALIFIED)  # placeholder
    # deterministic policy derives the conclusion (the model did NOT)
    derived = conclude(q.permitted_purpose, q.technological_in_nature,
                       q.elimination_of_uncertainty, q.process_of_experimentation)
    return ResearchQualification(q.project_id, q.permitted_purpose, q.technological_in_nature,
                                 q.elimination_of_uncertainty, q.process_of_experimentation, derived)


# ── the governed mission ────────────────────────────────────────────────────────
def run(engagement: Engagement, paths: dict[str, str], cpa_review) -> tuple[Deliverable, Ledger]:
    led = Ledger(engagement.engagement_id)
    led.append("engagement.start", {"client": engagement.client, "type": engagement.deliverable_type})

    facts, docs = extract(paths)
    led.append("documents.ingested", {"docs": [d.kind for d in docs]})
    led.append("facts.extracted", {"employees": len(facts["employees"]), "gl": facts["gl"]})

    d = Deliverable(engagement=engagement)

    # reconcile payroll gross wages ↔ GL wage accounts (deterministic, before reasoning)
    payroll_gross = round(sum(e["wages"] for e in facts["employees"]), 2)
    rec = reconcile.reconcile("payroll_export", payroll_gross, "gl_extract", facts["gl"].get("wages_total", 0),
                              "total payroll gross wages == GL wage accounts", tolerance=1000.0)
    d.reconciliations.append(rec)
    led.append("reconciled", {"status": rec.status, "difference": rec.difference})
    if rec.blocking:
        d.status = "escalated"; d.escalations.append(f"wage reconciliation MISMATCH {rec.difference}")
        led.append("escalated", {"reason": "reconciliation"}); return d, led

    # assess every project; policy concludes; escalate REVIEW_REQUIRED, drop NOT_QUALIFIED
    qualified = []
    for proj in ("Atlas", "Borealis"):
        q = assess(proj, facts); d.qualifications.append(q)
        led.append("assessed", {"project": proj, "conclusion": q.conclusion.value})
        if q.conclusion == Conclusion.QUALIFIED:
            qualified.append(proj)
        elif q.conclusion == Conclusion.REVIEW_REQUIRED:
            d.escalations.append(f"{proj}: four-part test REVIEW_REQUIRED (insufficient evidence)")
            led.append("escalated", {"project": proj, "reason": "insufficient_evidence"})
    if not qualified:
        d.status = "escalated"; return d, led

    # QRE schedule — qualified-time-weighted wages for qualified projects only
    qwages = round(sum(e["wages"] * e["alloc"].get(p, 0) for e in facts["employees"] for p in qualified), 2)
    inp = QREInputs(qualified_wages=qwages, qualified_supplies=facts["gl"].get("supplies", 0),
                    contract_research=facts["gl"].get("contract", 0), cloud_computing=facts["gl"].get("cloud", 0),
                    prior_qre=facts["prior_qre"], fixed_base_pct=facts["fixed_base_pct"],
                    avg_gross_receipts_prior4=facts["avg_gross_receipts_prior4"])
    cr = compute_credit(inp)
    led.append("qre.schedule", {"qualified_projects": qualified, "qualified_wages": qwages, "qre": cr.qre})
    if not cr.agreement:
        d.status = "escalated"; d.escalations.append("§41 engines A/B disagree"); return d, led
    comp = Computation(name="rd_credit", engine="engine_a", inputs=asdict(inp),
                       outputs={"qre": cr.qre, "asc": cr.asc, "rrc": cr.rrc, "credit": cr.credit,
                                "elected": cr.elected},
                       cross_validator="engine_b", agreement=cr.agreement)
    d.computations.append(comp)
    led.append("computed", {"credit": cr.credit, "elected": cr.elected, "engines_agree": True})

    # claim graph
    d.claims += [
        claims.new_claim("facts", ClaimType.FACT,
            f"{len(facts['employees'])} employees performed services allocated to qualified research.",
            evidence=tuple(EvidenceRef("payroll", f"row {e['row']}", e["name"]) for e in facts["employees"]),
            confidence=0.95),
        claims.new_claim("facts", ClaimType.FACT,
            "GL wage accounts reconcile to payroll within tolerance.",
            evidence=(EvidenceRef("gl", "acct 6000"),), confidence=0.98),
        claims.new_claim("authority", ClaimType.AUTHORITY_INTERPRETATION,
            "Qualified research must satisfy the four-part test of IRC §41(d)(1), including a process of "
            "experimentation.",
            authority=(AuthorityRef("IRC §41(d)(1)", "qualified research"),
                       AuthorityRef("Treas. Reg. §1.41-4(a)(5)", "process of experimentation")),
            confidence=0.9),
        claims.new_claim("qualification", ClaimType.PROFESSIONAL_JUDGMENT,
            "Project Atlas constitutes qualified research under IRC §41(d).",
            assessment_ref="Atlas", confidence=0.85),
        claims.new_claim("computation", ClaimType.NUMBER,
            f"Qualified research expenses total ${cr.qre:,.0f}.",
            computation_ref="rd_credit", confidence=1.0),
        claims.new_claim("computation", ClaimType.NUMBER,
            f"The §41 research credit is ${cr.credit:,.0f} ({cr.elected} method).",
            computation_ref="rd_credit", confidence=1.0),
    ]
    led.append("claims.assembled", {"n": len(d.claims)})

    d.rendered = _render(engagement, d, cr, qualified)
    led.append("drafted", {"chars": len(d.rendered)})

    v = verify.verify(d)
    led.append("verified", {"all_ok": v["all_ok"], "blocking": v["blocking_claims"]})
    if not v["all_ok"]:
        d.status = "escalated"; d.escalations.append(f"unverified claims: {v['blocking_claims']}"); return d, led

    # CPA review + sign (HITL)
    d.status = "ready_for_review"
    signoff: SignOff = cpa_review(d)
    d.sign_offs.append(signoff)
    led.append("signoff", {"decision": signoff.decision.value, "amendments": len(signoff.amendments),
                           "cpa": signoff.cpa_principal})
    d.status = {"APPROVE": "signed", "AMEND": "signed", "REJECT": "rejected"}[signoff.decision.value]
    signoff.ledger_ref = led.events()[-1].hash

    # learning: each amendment is supervision for the AI layer only
    outcomes = [LearningOutcome(context={"stage": am.get("stage", "draft"), "claim": am["claim_id"]},
                                decision=am.get("ai_choice", "draft"),
                                reward=-0.5, kind="cpa_amendment") for am in signoff.amendments]
    if signoff.decision.value == "APPROVE":
        outcomes.append(LearningOutcome(context={"deliverable": engagement.deliverable_type},
                                        decision="accepted_as_drafted", reward=1.0))
    led.append("learning", {"outcomes": len(outcomes)})
    d_learning = outcomes                                     # (persisted by the caller / Context Runtime)
    setattr(d, "learning_outcomes", d_learning)
    return d, led


def _render(eng: Engagement, d: Deliverable, cr, qualified: list[str]) -> str:
    """Render the memo FROM the claim graph — every material line carries a provenance tag."""
    L = [f"# R&D Tax Credit Study (IRC §41) — {eng.client}", "",
         f"Engagement {eng.engagement_id} · fixed fee ${eng.price_usd:,.0f} · SLA {eng.sla_hours}h", "",
         "## Qualified activities"]
    for c in d.claims:
        if c.section in ("facts", "qualification"):
            L.append(f"- {c.assertion}  _[{c.claim_id} · {c.claim_type.value}]_")
    if d.escalations:
        L += ["", "## Held for CPA review (not included in the credit)"]
        L += [f"- {e}" for e in d.escalations]
    L += ["", "## Authority"]
    for c in d.claims:
        if c.claim_type == ClaimType.AUTHORITY_INTERPRETATION:
            L.append(f"- {c.assertion}  _[{', '.join(a.authority for a in c.authority_refs)}]_")
    L += ["", "## Computation (deterministic; engines A and B agree)",
          f"- Qualified research expenses: **${cr.qre:,.0f}**",
          f"- ASC method: ${cr.asc:,.0f} · Regular method: ${cr.rrc:,.0f}",
          f"- **Credit claimed ({cr.elected}): ${cr.credit:,.0f}**  _[rd_credit · cross-checked]_", ""]
    return "\n".join(L)
