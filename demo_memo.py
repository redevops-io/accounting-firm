"""Second deliverable demo: an ASC 606 technical accounting memo — same runtime, new domain module."""
import os
import time

from accounting_firm.contracts import Decision, Engagement, SignOff
from accounting_firm.deliverables import tech_accounting_memo as memo

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_data")
PATHS = {"contract": f"{DATA}/contract.txt", "trial_balance": f"{DATA}/trial_balance.csv"}


def cpa_review(d):
    return SignOff("J. Rivera, CPA", time.time(), "full deliverable", Decision.APPROVE)


def main() -> int:
    eng = Engagement("ENG-2026-0002", "Acme Corp", "tech_accounting_memo",
                     "ASC 606 revenue recognition — 2025", 6500, 48)
    d, led = memo.run(eng, PATHS, cpa_review)
    print(d.rendered)
    print("=" * 72)
    print(f"STATUS: {d.status.upper()}   conclusion: {d.qualifications[0].conclusion.value}")
    print(f"claims verified: {sum(1 for c in d.claims if c.verified)}/{len(d.claims)}")
    print(f"reconciliation: {d.reconciliations[0].status} (computed deferred vs trial balance)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
