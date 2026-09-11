"""The model seam is deliverable-agnostic: per-criterion assessment, policy-concluded, stubbed (no network)."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounting_firm.contracts import Conclusion, Criterion, Decision, Engagement, Result, SignOff
from accounting_firm.deliverables import rd_credit_study
from accounting_firm.providers import DeterministicProvider, LLMProvider, select_provider
from accounting_firm.section41 import conclude

_FOUR = ("permitted_purpose", "technological_in_nature", "elimination_of_uncertainty",
         "process_of_experimentation")
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_data")
PATHS = {"payroll": f"{DATA}/payroll_export.csv", "gl": f"{DATA}/gl_extract.csv",
         "prior_year": f"{DATA}/prior_year.csv", "project_desc": f"{DATA}/project_description.txt",
         "engineering": f"{DATA}/engineering_doc.txt"}


def _chat(results):
    def chat(system, user):
        if "four-part test" in system or "criterion" in user:
            return json.dumps({c: {"result": results[i], "confidence": 0.9} for i, c in enumerate(_FOUR)})
        return "# Rendered memo (from claims)"
    return chat


def _crit():
    return [Criterion(c, hint=True) for c in _FOUR]


def test_llm_assess_is_per_criterion():
    a = LLMProvider(_chat(["PASS", "PASS", "INSUFFICIENT", "PASS"])).assess("four-part test", "ev", _crit())
    assert set(a) == set(_FOUR)
    assert a["permitted_purpose"].result == Result.PASS
    assert a["elimination_of_uncertainty"].result == Result.INSUFFICIENT
    assert conclude(*a.values()) == Conclusion.REVIEW_REQUIRED     # policy concludes, not the model


def test_llm_malformed_output_fails_safe():
    a = LLMProvider(lambda s, u: "not json").assess("four-part test", "ev", _crit())
    assert all(x.result == Result.INSUFFICIENT for x in a.values())


def test_deterministic_reflects_hints():
    crit = [Criterion("a", hint=True), Criterion("b", hint=False)]
    a = DeterministicProvider().assess("sys", "ev", crit)
    assert a["a"].result == Result.PASS and a["b"].result == Result.INSUFFICIENT


def test_select_provider_defaults_deterministic(monkeypatch):
    for k in ("FIRM_LLM_BASE_URL", "FIRM_LLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert isinstance(select_provider(), DeterministicProvider)
    assert isinstance(select_provider(chat_fn=lambda s, u: "{}"), LLMProvider)


def test_run_wires_through_the_llm_seam():
    prov = LLMProvider(_chat(["PASS", "PASS", "PASS", "PASS"]))
    d, led = rd_credit_study.run(Engagement("E", "C", "rd_credit_study", "2025", 9500, 48), PATHS,
                                 lambda dd: SignOff("CPA", time.time(), "full", Decision.APPROVE), provider=prov)
    assert d.status == "signed"
    assert next(c for c in d.computations if c.name == "rd_credit").agreement
    assert any(e.payload.get("provider") == "llm" for e in led.events())
    assert all(c.verified for c in d.claims)


if __name__ == "__main__":
    class _MP:
        def delenv(self, k, raising=False): os.environ.pop(k, None)
        def setenv(self, k, v): os.environ[k] = v
    for k, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        fn(_MP()) if "monkeypatch" in fn.__code__.co_varnames else fn()
        print("ok", k)
    print("\npassed")
