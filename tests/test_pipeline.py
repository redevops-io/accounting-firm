"""The flagship milestone gate sequence, end to end, offline."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounting_firm.contracts import Conclusion, Decision, Engagement, SignOff
from accounting_firm.deliverables import rd_credit_study

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "demo_data")
PATHS = {"payroll": f"{DATA}/payroll_export.csv", "gl": f"{DATA}/gl_extract.csv",
         "prior_year": f"{DATA}/prior_year.csv", "project_desc": f"{DATA}/project_description.txt",
         "engineering": f"{DATA}/engineering_doc.txt"}


def _eng():
    return Engagement("ENG-T", "Test Co", "rd_credit_study", "2025", 9500, 48)


def _approve(d):
    return SignOff("CPA", time.time(), "full", Decision.APPROVE)


def _run(cpa=_approve):
    return rd_credit_study.run(_eng(), PATHS, cpa)


def test_end_to_end_signed_and_credit_correct():
    d, led = _run()
    assert d.status == "signed"
    comp = next(c for c in d.computations if c.name == "rd_credit")
    assert comp.outputs["qre"] == 360000.0
    assert comp.outputs["credit"] == 43400.0 and comp.outputs["elected"] == "ASC"
    assert comp.agreement                                     # engines A/B agree


def test_qualified_and_review_projects_handled():
    d, _ = _run()
    by = {q.project_id: q.conclusion for q in d.qualifications}
    assert by["Atlas"] == Conclusion.QUALIFIED
    assert by["Borealis"] == Conclusion.REVIEW_REQUIRED       # insufficient evidence
    assert any("Borealis" in e for e in d.escalations)        # escalated, not silently dropped


def test_reconciliation_ran_and_passed():
    d, _ = _run()
    assert d.reconciliations and d.reconciliations[0].status == "OK"
    assert d.reconciliations[0].value_a == 450000.0           # payroll gross


def test_every_claim_is_verified():
    d, _ = _run()
    assert d.claims and all(c.verified for c in d.claims)     # provenance by construction
    # a NUMBER claim rests on the cross-checked computation
    num = next(c for c in d.claims if c.claim_type.value == "NUMBER")
    assert num.computation_ref == "rd_credit"


def test_ledger_is_append_only_and_complete():
    _, led = _run()
    types = [e.type for e in led.events()]
    for t in ("documents.ingested", "reconciled", "assessed", "computed", "verified", "signoff", "learning"):
        assert t in types, t
    assert [e.seq for e in led.events()] == list(range(1, len(led.events()) + 1))


def test_cpa_amendment_emits_learning_outcome():
    def amend(d):
        c = d.claims[0]
        return SignOff("CPA", time.time(), "full", Decision.AMEND,
                       amendments=[{"claim_id": c.claim_id, "stage": "draft", "ai_choice": "wording"}])
    d, _ = _run(amend)
    outs = getattr(d, "learning_outcomes", [])
    assert outs and any(o.kind == "cpa_amendment" for o in outs)
    assert all(o.context.get("stage") for o in outs if o.kind == "cpa_amendment")


def test_scanned_payroll_multiformat_ingestion():
    # Phase 3: an unstructured/"scanned" payroll (free text) yields the same result as the clean CSV
    paths = dict(PATHS, payroll=f"{DATA}/payroll_scanned.txt")
    d, _ = rd_credit_study.run(_eng(), paths, _approve)
    assert d.status == "signed"
    assert next(c for c in d.computations if c.name == "rd_credit").outputs["credit"] == 43400.0


def test_extraction_confidence_gate_escalates():
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write("garbled scan with no readable rows\n")
        bad = fh.name
    paths = dict(PATHS, payroll=bad)
    d, led = rd_credit_study.run(_eng(), paths, _approve)
    assert d.status == "escalated" and any("correction" in e for e in d.escalations)
    os.remove(bad)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
