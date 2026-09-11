"""Flagship milestone: one synthetic company → one §41 R&D credit study → one CPA-reviewable deliverable.

Runs the full gate sequence on the MESSY demo docs, offline (deterministic stubs stand in for the LLM
extraction/assessment seams). Run:  python3 demo.py
"""
import os
import time

from accounting_firm.contracts import Decision, Engagement, SignOff
from accounting_firm.deliverables import rd_credit_study

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "demo_data")
PATHS = {"payroll": f"{DATA}/payroll_export.csv", "gl": f"{DATA}/gl_extract.csv",
         "prior_year": f"{DATA}/prior_year.csv", "project_desc": f"{DATA}/project_description.txt",
         "engineering": f"{DATA}/engineering_doc.txt"}


def cpa_review(d):
    """Stand-in CPA: reviews the claim graph, makes one wording amendment, approves-with-amendment."""
    fact = next(c for c in d.claims if c.section == "facts")
    fact.reviewer_disposition = "amended"
    return SignOff(cpa_principal="J. Rivera, CPA", at=time.time(), scope="full deliverable",
                   decision=Decision.AMEND,
                   amendments=[{"claim_id": fact.claim_id, "stage": "draft", "ai_choice": "wording",
                                "before": fact.assertion, "after": fact.assertion + " (per payroll register).",
                                "reason": "tie the count to the register by name"}])


def main() -> int:
    eng = Engagement(engagement_id="ENG-2026-0001", client="Northwind Robotics, Inc.",
                     deliverable_type="rd_credit_study", scope="2025 tax year §41 study",
                     price_usd=9500, sla_hours=48)
    d, led = rd_credit_study.run(eng, PATHS, cpa_review)

    print(d.rendered)
    print("=" * 72)
    print(f"STATUS: {d.status.upper()}   sign-off: {d.sign_offs[0].decision.value} "
          f"by {d.sign_offs[0].cpa_principal}")
    print(f"escalations: {d.escalations or 'none'}")
    print(f"claims verified: {sum(1 for c in d.claims if c.verified)}/{len(d.claims)}")
    print(f"learning outcomes emitted: {len(getattr(d, 'learning_outcomes', []))}")
    print("\n--- audit ledger (append-only, hash-chained) ---")
    for e in led.events():
        print(f"  {e.seq:>2} {e.type:<20} {e.hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
