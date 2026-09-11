"""Second deliverable (ASC 606 memo) — proves the framework is generic: same core loop, new domain module."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounting_firm.contracts import Conclusion, Decision, Engagement, SignOff
from accounting_firm.deliverables import tech_accounting_memo as memo
from accounting_firm.providers import DeterministicProvider, LLMProvider

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_data")
PATHS = {"contract": f"{DATA}/contract.txt", "trial_balance": f"{DATA}/trial_balance.csv"}


def _run(cpa=lambda d: SignOff("CPA", time.time(), "full", Decision.APPROVE)):
    return memo.run(Engagement("ENG-M", "Acme Corp", "tech_accounting_memo", "2025 ASC 606", 6500, 48),
                    PATHS, cpa)


def test_recognition_schedule_correct_and_cross_checked():
    d, _ = _run()
    c = next(x for x in d.computations if x.name == "revrec")
    assert c.outputs == {"monthly": 10000.0, "recognized": 60000.0, "deferred": 60000.0}
    assert c.agreement


def test_reconciles_to_trial_balance_and_signs():
    d, _ = _run()
    assert d.reconciliations[0].status == "OK"                # computed deferred == GL deferred
    assert d.status == "signed"
    assert d.qualifications[0].conclusion == Conclusion.QUALIFIED   # recognize over time
    assert all(cl.verified for cl in d.claims)               # provenance by construction


def test_uses_the_same_shared_loop():
    _, led = _run()
    types = [e.type for e in led.events()]
    # the shared mission tail appears identically to the §41 study
    for t in ("computed", "reconciled", "assessed", "drafted", "verified", "signoff", "learning"):
        assert t in types, t


def test_llm_extraction_seam_overrides_regex():
    # Phase-3: the model extracts from the unstructured contract; deterministic default falls back to regex
    def chat(system, user):
        if "Extract EXACTLY" in user:
            return json.dumps({"total_fee": 200000, "term_months": 24,
                               "commencement_month": 3, "satisfied_over_time": True})
        return "{}"
    facts, _ = memo.extract(PATHS, LLMProvider(chat))
    assert facts["total_fee"] == 200000.0 and facts["term_months"] == 24
    assert facts["months_elapsed"] == 10 and facts["over_time"] is True    # from the model
    facts2, _ = memo.extract(PATHS, DeterministicProvider())
    assert facts2["total_fee"] == 120000.0                                 # regex fallback (offline)


if __name__ == "__main__":
    for k, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        fn(); print("ok", k)
    print("\npassed")
