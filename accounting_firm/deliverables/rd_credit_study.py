"""R&D credit study (§41) — the flagship deliverable, end to end.

extract (MESSY docs) → reconcile → assess (per-criterion, via the model seam) → escalate → QRE schedule →
§41 compute (A↕B) → claim graph → render (model seam) → verify → CPA review/sign → signed bundle →
LearningOutcome. Extraction/computation/reconciliation/verification/policy are deterministic; only the
four-part assessment and the drafting go through the `Provider` (deterministic offline, LLM when configured).
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import asdict

from .. import claims, mission, reconcile
from ..contracts import (AuthorityRef, ClaimType, Computation, Conclusion, Confidence, Criterion, Deliverable,
                        EvidenceRef, Engagement, ResearchQualification, SourceDocument)
from ..ledger import select_ledger
from ..providers import select_provider
from ..section41 import QREInputs, compute_credit, conclude

SYS_41 = ("You are a tax professional applying the IRC §41(d)(1) four-part test to ONE project. Assess each "
          "criterion independently; do NOT decide overall qualification — policy does that from your four "
          "assessments.")
_A41D = (AuthorityRef("IRC §41(d)(1)", "qualified research"),)
_REG_UNC = (AuthorityRef("Treas. Reg. §1.41-4(a)(3)", "uncertainty"),)
_REG_EXP = (AuthorityRef("Treas. Reg. §1.41-4(a)(5)", "process of experimentation"),)


# ── extraction (deterministic parser for structured docs; LLM/OCR is Phase-3 ingestion) ──
def _money(s: str) -> float:
    return float(re.sub(r"[^0-9.\-]", "", s or "0") or 0)


def _rows(path: str) -> list[list[str]]:
    # skipinitialspace so quoted fields with internal commas ("$450,250") survive a space after the delimiter
    with open(path, newline="") as fh:
        return [[c.strip() for c in row] for row in csv.reader(fh, skipinitialspace=True)]


def _alloc(s: str) -> dict:
    return {p: int(pct) / 100 for p, pct in re.findall(r"([A-Za-z]+)\s+(\d+)%", s or "")}


def _payroll_csv(path: str) -> list[dict]:
    out = []
    for i, r in enumerate(_rows(path)):
        if i == 0 or len(r) < 4 or not r[2] or r[0].lower().startswith("notes"):
            continue
        a = _alloc(r[3])
        if a:
            out.append({"name": r[0], "wages": _money(r[2]), "alloc": a, "row": i + 1})
    return out


def _payroll_text(path: str) -> list[dict]:
    """A 'scanned'/OCR'd payroll: whitespace-delimited free text (name  dept  $wages  allocations)."""
    out = []
    with open(path) as fh:
        for i, line in enumerate(fh):
            cols = re.split(r"\s{2,}", line.strip())
            if len(cols) < 4 or "$" not in cols[2]:
                continue
            a = _alloc(cols[3])
            if a:
                out.append({"name": cols[0], "wages": _money(cols[2]), "alloc": a, "row": i + 1})
    return out


def _employees(path: str, provider) -> tuple[list[dict], float]:
    """Multi-format payroll ingestion: clean CSV (deterministic) or an unstructured/scanned export
    (LLM table extraction, falling back to a deterministic messy-text parser). Returns (rows, confidence)."""
    if path.lower().endswith(".csv"):
        return _payroll_csv(path), 0.97
    with open(path) as fh:
        text = fh.read()
    rows = provider.extract_table("Extract each employee row from this payroll export.", text,
                                  ["name", "wages", "allocation"])
    emps = []
    for i, r in enumerate(rows):
        a = _alloc(str(r.get("allocation", "")))
        if a and r.get("wages") is not None:
            emps.append({"name": str(r.get("name", "")), "wages": _money(str(r["wages"])), "alloc": a, "row": i + 1})
    if emps:
        return emps, 0.85                                # LLM extraction of the unstructured export
    return _payroll_text(path), 0.75                     # deterministic messy-text fallback


def extract(paths: dict[str, str], provider=None) -> tuple[dict, list[SourceDocument]]:
    provider = provider or select_provider()
    docs: list[SourceDocument] = []
    facts: dict = {}

    employees, pconf = _employees(paths["payroll"], provider)   # CSV or unstructured/scanned (multi-format)
    facts["employees"] = employees
    docs.append(SourceDocument("payroll", "payroll_export", paths["payroll"], {"employees": len(employees)},
                               Confidence(extraction=pconf, evidence_completeness=0.9), "ingest/v1"))

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

    facts["projects"] = {}
    for key in ("project_desc", "engineering"):
        with open(paths[key]) as fh:
            text = fh.read()
        facts.setdefault("texts", {})[key] = text
        for m in re.finditer(r"Project\s+([A-Za-z]+)\s*[:\-]\s*(.+)", text):
            facts["projects"].setdefault(m.group(1), m.group(2)[:300])
        docs.append(SourceDocument(key, "project_description" if key == "project_desc" else "engineering_doc",
                                   paths[key], {"chars": len(text)},
                                   Confidence(extraction=0.9, evidence_completeness=0.8), "parser/v0"))

    py = {r[0].strip().lower(): _money(r[1]) for r in _rows(paths["prior_year"]) if len(r) >= 2 and r[1]}
    facts["prior_qre"] = tuple(v for k, v in sorted(py.items()) if k.startswith("prior_qre"))
    facts["fixed_base_pct"] = py.get("fixed_base_pct", 0.0) / (100 if py.get("fixed_base_pct", 0) > 1 else 1)
    facts["avg_gross_receipts_prior4"] = py.get("avg_gross_receipts_prior4", 0.0)
    docs.append(SourceDocument("prior_year", "prior_year_returns", paths["prior_year"], py,
                               Confidence(extraction=0.95, evidence_completeness=0.9), "parser/v0"))
    return facts, docs


# ── per-project four-part criteria (hints derived deterministically from the evidence) ──
def _span(text: str, project: str) -> str:
    m = re.search(rf"Project\s+{re.escape(project)}\b(.+?)(?=Project\s+[A-Z]|\Z)", text, re.S)
    return (m.group(1) if m else "").lower()


def _hints(project: str, facts: dict) -> dict:
    pdesc = _span(facts["texts"].get("project_desc", ""), project)
    eng = facts["texts"].get("engineering", "").lower()
    has_exp = project.lower() in eng and any(k in eng for k in ("experiment", "trial", "benchmark", "alternativ"))
    return {"permitted_purpose": True, "technological_in_nature": True,
            "elimination_of_uncertainty": "uncertain" in pdesc,
            "process_of_experimentation": has_exp}


def _criteria(project: str, facts: dict) -> list[Criterion]:
    h = _hints(project, facts)
    ev_p = (EvidenceRef("project_desc", f"Project {project}"),)
    ev_e = (EvidenceRef("engineering", f"Project {project} experimentation log"),)
    return [
        Criterion("permitted_purpose", "develops a new or improved business component?", _A41D, ev_p, h["permitted_purpose"]),
        Criterion("technological_in_nature", "relies on principles of the hard sciences/engineering?", _A41D, ev_p, h["technological_in_nature"]),
        Criterion("elimination_of_uncertainty", "uncertainty as to capability/method/design at the outset?", _REG_UNC, ev_e, h["elimination_of_uncertainty"]),
        Criterion("process_of_experimentation", "substantially all activities are a process of experimentation?", _REG_EXP, ev_e, h["process_of_experimentation"]),
    ]


def _assess_project(provider, project: str, facts: dict) -> ResearchQualification:
    crit = _criteria(project, facts)
    evidence = f"{facts['texts'].get('project_desc','')}\n{facts['texts'].get('engineering','')}"
    a = provider.assess(SYS_41, evidence, crit)
    parts = (a["permitted_purpose"], a["technological_in_nature"],
             a["elimination_of_uncertainty"], a["process_of_experimentation"])
    return ResearchQualification(project, *parts, conclusion=conclude(*parts))


# ── the governed mission ────────────────────────────────────────────────────────
def run(engagement: Engagement, paths: dict[str, str], cpa_review, provider=None) -> tuple[Deliverable, Ledger]:
    provider = provider or select_provider()
    led = select_ledger(engagement.engagement_id)
    led.append("engagement.start", {"client": engagement.client, "type": engagement.deliverable_type,
                                    "provider": provider.name})

    facts, docs = extract(paths, provider)
    led.append("documents.ingested", {"docs": [dd.kind for dd in docs]})
    led.append("facts.extracted", {"employees": len(facts["employees"]), "gl": facts["gl"]})

    d = Deliverable(engagement=engagement)

    # correction gate: fail closed if extraction confidence is below threshold (human correction required)
    min_conf = min((dd.confidence.extraction for dd in docs), default=1.0)
    if not facts["employees"] or min_conf < float(os.environ.get("FIRM_EXTRACT_MIN_CONF", "0.6")):
        d.status = "escalated"
        d.escalations.append(f"extraction confidence {min_conf:.2f} below threshold — human correction required")
        led.append("escalated", {"reason": "extraction_confidence", "min_conf": round(min_conf, 2)})
        return d, led

    payroll_gross = round(sum(e["wages"] for e in facts["employees"]), 2)
    rec = reconcile.reconcile("payroll_export", payroll_gross, "gl_extract", facts["gl"].get("wages_total", 0),
                              "total payroll gross wages == GL wage accounts", tolerance=1000.0)
    d.reconciliations.append(rec)
    led.append("reconciled", {"status": rec.status, "difference": rec.difference})
    if rec.blocking:
        d.status = "escalated"; d.escalations.append(f"wage reconciliation MISMATCH {rec.difference}")
        led.append("escalated", {"reason": "reconciliation"}); return d, led

    qualified = []
    for proj in ("Atlas", "Borealis"):
        q = _assess_project(provider, proj, facts); d.qualifications.append(q)
        led.append("assessed", {"project": proj, "conclusion": q.conclusion.value})
        if q.conclusion == Conclusion.QUALIFIED:
            qualified.append(proj)
        elif q.conclusion == Conclusion.REVIEW_REQUIRED:
            d.escalations.append(f"{proj}: four-part test REVIEW_REQUIRED (insufficient evidence)")
            led.append("escalated", {"project": proj, "reason": "insufficient_evidence"})
    if not qualified:
        d.status = "escalated"; return d, led

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
                       AuthorityRef("Treas. Reg. §1.41-4(a)(5)", "process of experimentation")), confidence=0.9),
        claims.new_claim("qualification", ClaimType.PROFESSIONAL_JUDGMENT,
            f"Project {qualified[0]} constitutes qualified research under IRC §41(d).",
            assessment_ref=qualified[0], confidence=0.85),
        claims.new_claim("computation", ClaimType.NUMBER,
            f"Qualified research expenses total ${cr.qre:,.0f}.", computation_ref="rd_credit", confidence=1.0),
        claims.new_claim("computation", ClaimType.NUMBER,
            f"The §41 research credit is ${cr.credit:,.0f} ({cr.elected} method).",
            computation_ref="rd_credit", confidence=1.0),
    ]
    led.append("claims.assembled", {"n": len(d.claims)})

    # shared governed tail: draft → verify → CPA review/sign → learn
    return mission.finalize(engagement, d, led, cpa_review, provider)
