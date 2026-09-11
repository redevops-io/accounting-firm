"""§41 deterministic core: engines A and B agree, statute applied correctly, conclusion policy is sound."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounting_firm.contracts import Assessment, Conclusion, Result
from accounting_firm.section41 import QREInputs, compute_credit, conclude

# QRE = 500000 + 50000 + 0.65*100000 + 10000 = 625000 in every case below
_BASE = dict(qualified_wages=500000, qualified_supplies=50000, contract_research=100000, cloud_computing=10000)


def test_qre_components_and_cross_check():
    r = compute_credit(QREInputs(**_BASE, prior_qre=(400000, 450000, 500000),
                                 fixed_base_pct=0.03, avg_gross_receipts_prior4=2_000_000))
    assert r.qre == 625000.0
    assert r.components["contract_research_65pct"] == 65000.0
    assert r.agreement                                        # engine A and B agree to the penny
    assert r.engine_a["qre"] == r.engine_b["qre"]


def test_rrc_floor_binds():
    # base = max(0.03*2,000,000=60k, 0.5*625k=312.5k) = 312.5k → RRC = 0.20*312.5k = 62,500
    r = compute_credit(QREInputs(**_BASE, prior_qre=(400000, 450000, 500000),
                                 fixed_base_pct=0.03, avg_gross_receipts_prior4=2_000_000))
    assert r.rrc == 62500.0
    assert r.asc == 56000.0                                   # 0.14*(625k - 0.5*450k)
    assert r.elected == "RRC" and r.credit == 62500.0


def test_asc_wins_with_low_base():
    r = compute_credit(QREInputs(**_BASE, prior_qre=(100000, 100000, 100000),
                                 fixed_base_pct=0.03, avg_gross_receipts_prior4=2_000_000))
    assert r.asc == 80500.0                                   # 0.14*(625k - 50k)
    assert r.elected == "ASC" and r.credit == 80500.0
    assert r.agreement


def test_startup_rate_without_full_history():
    r = compute_credit(QREInputs(**_BASE, prior_qre=(), fixed_base_pct=0.0, avg_gross_receipts_prior4=0.0))
    assert r.asc == 37500.0                                   # 0.06*625k (no 3-year history)
    assert r.agreement


def test_zero_when_qre_below_base():
    r = compute_credit(QREInputs(qualified_wages=10000, prior_qre=(400000, 450000, 500000),
                                 fixed_base_pct=0.16, avg_gross_receipts_prior4=5_000_000))
    assert r.asc == 0.0 and r.rrc == 0.0 and r.credit == 0.0   # never negative
    assert r.agreement


def _a(result):
    return Assessment(criterion="x", result=result, confidence=0.9)


def test_conclusion_policy():
    assert conclude(_a(Result.PASS), _a(Result.PASS), _a(Result.PASS), _a(Result.PASS)) == Conclusion.QUALIFIED
    assert conclude(_a(Result.PASS), _a(Result.FAIL), _a(Result.PASS), _a(Result.PASS)) == Conclusion.NOT_QUALIFIED
    assert conclude(_a(Result.PASS), _a(Result.INSUFFICIENT), _a(Result.PASS), _a(Result.PASS)) == Conclusion.REVIEW_REQUIRED
    # FAIL dominates INSUFFICIENT
    assert conclude(_a(Result.FAIL), _a(Result.INSUFFICIENT), _a(Result.PASS), _a(Result.PASS)) == Conclusion.NOT_QUALIFIED


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
