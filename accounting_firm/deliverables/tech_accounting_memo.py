"""Technical accounting memo (ASC 606 revenue recognition) — the SECOND deliverable.

Proves the framework is generic: this module supplies only the domain work (extract a contract + trial
balance, a deterministic recognition schedule with an A/B cross-check, ASC 606 criteria) and then hands the
claim graph to the SAME shared loop (`mission.finalize`) and the SAME reconcile / claims / verify / ledger /
provider machinery the §41 study uses. No change to the core loop.
"""
from __future__ import annotations

import csv
import re

from .. import claims, mission, reconcile
from ..contracts import (AuthorityRef, ClaimType, Computation, Conclusion, Confidence, Criterion, Deliverable,
                        EvidenceRef, Engagement, Judgment, SourceDocument)
from ..ledger import Ledger
from ..providers import select_provider
from ..section41 import conclude   # the four-part policy shape is generic (all PASS→QUALIFIED / any FAIL→NOT / else REVIEW)

SYS_ASC = ("You are applying ASC 606 to a customer contract. Assess each criterion independently; do NOT "
           "decide the recognition pattern — policy derives it from your assessments.")


def _money(s: str) -> float:
    return float(re.sub(r"[^0-9.\-]", "", s or "0") or 0)


def extract(paths: dict[str, str]) -> tuple[dict, list[SourceDocument]]:
    with open(paths["contract"]) as fh:
        contract = fh.read()
    fee = _money((re.search(r"fee[:\s]*\$([\d,]+)", contract, re.I) or re.search(r"\$([\d,]+)", contract)).group(1))
    term = int((re.search(r"(\d+)\s*-?\s*month", contract, re.I)).group(1))
    start_m = int((re.search(r"commenc\w*\s+\d{4}-(\d{2})", contract, re.I)).group(1))
    elapsed = 12 - start_m + 1                                # months elapsed to Dec 31 of the commencement year
    over_time = "simultaneously receives and consumes" in contract.lower()
    facts = {"total_fee": fee, "term_months": term, "months_elapsed": elapsed, "over_time": over_time,
             "contract_text": contract}

    tb = {}
    with open(paths["trial_balance"], newline="") as fh:
        for r in csv.reader(fh, skipinitialspace=True):
            if len(r) < 3:
                continue
            d = r[1].lower()
            if "deferred" in d:
                tb["deferred"] = _money(r[2])
            elif "revenue" in d:
                tb["recognized"] = _money(r[2])
    facts["tb"] = tb
    return facts, [
        SourceDocument("contract", "customer_contract", paths["contract"], {"fee": fee, "term": term},
                       Confidence(extraction=0.93, evidence_completeness=0.85), "parser/v0"),
        SourceDocument("trial_balance", "trial_balance", paths["trial_balance"], tb,
                       Confidence(extraction=0.98, evidence_completeness=0.95), "parser/v0"),
    ]


# deterministic recognition schedule — two independent implementations cross-check
def _sched_a(total, term, elapsed):
    m = round(total / term, 2)
    rec = round(sum(m for _ in range(min(elapsed, term))), 2)   # iterate the months
    return {"monthly": m, "recognized": rec, "deferred": round(total - rec, 2)}


def _sched_b(total, term, elapsed):
    m = round(total / term, 2)
    rec = round(m * min(elapsed, term), 2)                      # direct formula
    return {"monthly": m, "recognized": rec, "deferred": round(total - rec, 2)}


def compute_revrec(total, term, elapsed):
    a, b = _sched_a(total, term, elapsed), _sched_b(total, term, elapsed)
    return a, all(abs(a[k] - b[k]) <= 0.01 for k in a)


def _criteria(facts: dict) -> list[Criterion]:
    ev = (EvidenceRef("contract", "subscription agreement"),)
    return [
        Criterion("contract_exists", "a valid contract with a customer exists?",
                  (AuthorityRef("ASC 606-10-25-1", "contract"),), ev, True),
        Criterion("performance_obligation_identified", "a distinct performance obligation is identified?",
                  (AuthorityRef("ASC 606-10-25-27", "performance obligation"),), ev, True),
        Criterion("transaction_price_determinable", "the transaction price is determinable?",
                  (AuthorityRef("ASC 606-10-32-2", "transaction price"),), ev, facts["total_fee"] > 0),
        Criterion("satisfied_over_time", "the obligation is satisfied over time?",
                  (AuthorityRef("ASC 606-10-25-27", "over time"),), ev, facts["over_time"]),
    ]


def run(engagement: Engagement, paths: dict[str, str], cpa_review, provider=None) -> tuple[Deliverable, Ledger]:
    provider = provider or select_provider()
    led = Ledger(engagement.engagement_id)
    led.append("engagement.start", {"client": engagement.client, "type": engagement.deliverable_type,
                                    "provider": provider.name})
    facts, docs = extract(paths)
    led.append("documents.ingested", {"docs": [d.kind for d in docs]})
    led.append("facts.extracted", {"total_fee": facts["total_fee"], "term_months": facts["term_months"]})

    d = Deliverable(engagement=engagement)

    # compute the recognition schedule (deterministic, cross-checked)
    sched, agree = compute_revrec(facts["total_fee"], facts["term_months"], facts["months_elapsed"])
    if not agree:
        d.status = "escalated"; d.escalations.append("recognition engines A/B disagree"); return d, led
    d.computations.append(Computation("revrec", "sched_a", inputs=facts | {"contract_text": "…"},
                                      outputs=sched, cross_validator="sched_b", agreement=agree))
    led.append("computed", {**sched, "engines_agree": True})

    # reconcile schedule-computed deferred ↔ trial-balance deferred (before relying on the numbers)
    rec = reconcile.reconcile("recognition_schedule", sched["deferred"], "trial_balance",
                              facts["tb"].get("deferred", 0), "computed deferred == GL deferred revenue",
                              tolerance=1.0)
    d.reconciliations.append(rec)
    led.append("reconciled", {"status": rec.status, "difference": rec.difference})
    if rec.blocking:
        d.status = "escalated"; d.escalations.append(f"deferred-revenue MISMATCH {rec.difference}")
        led.append("escalated", {"reason": "reconciliation"}); return d, led

    # ASC 606 assessment (per criterion) → policy conclusion
    crit = _criteria(facts)
    a = provider.assess(SYS_ASC, facts["contract_text"], crit)
    conclusion = conclude(*a.values())
    d.qualifications.append(Judgment("revenue_recognition", tuple(a.values()), conclusion))
    led.append("assessed", {"subject": "revenue_recognition", "conclusion": conclusion.value})
    if conclusion != Conclusion.QUALIFIED:
        d.status = "escalated"; d.escalations.append(f"revenue recognition {conclusion.value}"); return d, led

    d.claims += [
        claims.new_claim("facts", ClaimType.FACT,
            f"The contract provides a ${facts['total_fee']:,.0f} fee over a {facts['term_months']}-month term.",
            evidence=(EvidenceRef("contract", "fee & term"),), confidence=0.95),
        claims.new_claim("facts", ClaimType.FACT,
            "Deferred revenue per the recognition schedule reconciles to the trial balance.",
            evidence=(EvidenceRef("trial_balance", "acct 2400"),), confidence=0.98),
        claims.new_claim("authority", ClaimType.AUTHORITY_INTERPRETATION,
            "Revenue is recognized over time when the customer simultaneously receives and consumes the "
            "benefits of the entity's performance.",
            authority=(AuthorityRef("ASC 606-10-25-27", "over time"),), confidence=0.9),
        claims.new_claim("conclusion", ClaimType.PROFESSIONAL_JUDGMENT,
            "Subscription revenue is recognized over time (ratably over the term).",
            assessment_ref="revenue_recognition", confidence=0.85),
        claims.new_claim("computation", ClaimType.NUMBER,
            f"Monthly revenue recognized is ${sched['monthly']:,.0f}.", computation_ref="revrec", confidence=1.0),
        claims.new_claim("computation", ClaimType.NUMBER,
            f"Revenue recognized to date is ${sched['recognized']:,.0f}; deferred revenue is "
            f"${sched['deferred']:,.0f}.", computation_ref="revrec", confidence=1.0),
    ]
    led.append("claims.assembled", {"n": len(d.claims)})

    return mission.finalize(engagement, d, led, cpa_review, provider)
