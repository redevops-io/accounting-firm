"""The model seam: LLM judgment is per-criterion + policy-concluded; the run wires through a provider.

Uses a stubbed chat function (no network) — same pattern as the deterministic default, proving the seam
without a live model."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounting_firm.contracts import Conclusion, Decision, Engagement, SignOff
from accounting_firm.deliverables import rd_credit_study
from accounting_firm.providers import DeterministicProvider, LLMProvider, select_provider

_FOUR = ("permitted_purpose", "technological_in_nature", "elimination_of_uncertainty",
         "process_of_experimentation")
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_data")
PATHS = {"payroll": f"{DATA}/payroll_export.csv", "gl": f"{DATA}/gl_extract.csv",
         "prior_year": f"{DATA}/prior_year.csv", "project_desc": f"{DATA}/project_description.txt",
         "engineering": f"{DATA}/engineering_doc.txt"}


def _chat(results):
    """A stub chat: returns four-part JSON for the assessor, plain text for the drafter."""
    def chat(system, user):
        if "four-part test" in system:
            return json.dumps({c: {"result": results[i], "confidence": 0.9, "authority": ["IRC §41(d)(1)"]}
                               for i, c in enumerate(_FOUR)})
        return "# Rendered study (from claims)"
    return chat


def test_llm_assess_is_per_criterion_and_policy_concludes():
    p = LLMProvider(_chat(["PASS", "PASS", "PASS", "PASS"]))
    q = p.assess("X", {})
    assert q.permitted_purpose.result.value == "PASS" and q.conclusion == Conclusion.QUALIFIED
    p2 = LLMProvider(_chat(["PASS", "PASS", "INSUFFICIENT", "PASS"]))
    assert p2.assess("X", {}).conclusion == Conclusion.REVIEW_REQUIRED
    p3 = LLMProvider(_chat(["PASS", "FAIL", "PASS", "PASS"]))
    assert p3.assess("X", {}).conclusion == Conclusion.NOT_QUALIFIED


def test_llm_malformed_output_fails_safe_to_insufficient():
    q = LLMProvider(lambda s, u: "not json at all").assess("X", {})
    assert q.conclusion == Conclusion.REVIEW_REQUIRED       # never over-claims → human review


def test_select_provider_defaults_deterministic(monkeypatch):
    for k in ("FIRM_LLM_BASE_URL", "FIRM_LLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert isinstance(select_provider(), DeterministicProvider)
    assert isinstance(select_provider(chat_fn=lambda s, u: "{}"), LLMProvider)


def test_run_wires_through_the_llm_seam():
    prov = LLMProvider(_chat(["PASS", "PASS", "PASS", "PASS"]))   # qualifies every project it assesses
    d, led = rd_credit_study.run(Engagement("E", "C", "rd_credit_study", "2025", 9500, 48), PATHS,
                                 lambda dd: SignOff("CPA", time.time(), "full", Decision.APPROVE), provider=prov)
    assert d.status == "signed"
    assert next(c for c in d.computations if c.name == "rd_credit").agreement
    assert any(e.payload.get("provider") == "llm" for e in led.events())
    assert all(c.verified for c in d.claims)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        # crude monkeypatch shim for standalone run
        class _MP:
            def delenv(self, k, raising=False): os.environ.pop(k, None)
            def setenv(self, k, v): os.environ[k] = v
        fn(_MP()) if "monkeypatch" in fn.__code__.co_varnames else fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
