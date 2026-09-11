"""The CPA review console (P0–P2): read-only deliverable, resolved provenance, three-case trust model.

The console is a *view* — it must render exactly what the deliverable produced. These tests assert the
serialization the UI consumes: every claim resolves its provenance, a NUMBER shows both engines agreeing,
and the three trust cases (sufficient / missing / conflicting) are all present on one deliverable.
"""
import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounting_firm.console import build_deliverable
from accounting_firm.console.app import _Handler
from accounting_firm.console.serialize import ReviewSession


def test_deliverable_serializes_signed_with_claims():
    d = build_deliverable()
    assert d["status"] == "signed"
    assert d["claims"] and len(d["claims"]) == 6
    assert all("provenance" in c for c in d["claims"])
    assert d["runtime"]["verification"] == "PASS"


def test_number_claim_shows_both_engines_agreeing():
    d = build_deliverable()
    num = next(c for c in d["claims"] if c["type"] == "NUMBER")
    comp = num["provenance"]["computation"]
    assert comp["agreement"] is True
    # every figure is present from BOTH independent engines and they match
    assert comp["cross_check"] and all(x["agree"] for x in comp["cross_check"])
    for x in comp["cross_check"]:
        assert x["engine_a"] == x["engine_b"]


def test_every_claim_resolves_its_provenance():
    d = build_deliverable()
    for c in d["claims"]:
        p = c["provenance"]
        if c["type"] == "FACT":
            assert p["evidence"] and all(e["doc_id"] and e["locator"] for e in p["evidence"])
        elif c["type"] == "AUTHORITY_INTERPRETATION":
            assert p["authority"] and all(a["resolved"] for a in p["authority"])
        elif c["type"] == "NUMBER":
            assert p["computation"] is not None
        elif c["type"] == "PROFESSIONAL_JUDGMENT":
            assert p["judgment"] and len(p["judgment"]["assessments"]) == 4


def test_professional_judgment_carries_the_claim_graph():
    d = build_deliverable()
    pj = next(c for c in d["claims"] if c["type"] == "PROFESSIONAL_JUDGMENT")
    j = pj["provenance"]["judgment"]
    assert j["conclusion"] == "QUALIFIED"                      # policy-derived, not the model's
    names = [a["criterion"] for a in j["assessments"]]
    assert names == ["permitted_purpose", "technological_in_nature",
                     "elimination_of_uncertainty", "process_of_experimentation"]
    for a in j["assessments"]:
        assert a["result"] in ("PASS", "FAIL", "INSUFFICIENT") and 0 <= a["confidence"] <= 1


def test_three_case_trust_model_all_present():
    t = build_deliverable()["trust_model"]
    # sufficient → compute (A = B)
    assert t["sufficient"]["value"] == 30800.0 and t["sufficient"]["label"] == "§41 credit"
    # missing → abstain (Borealis held for insufficient evidence)
    assert any(p["subject"] == "Borealis" for p in t["missing"]["projects"])
    assert t["missing"]["escalations"]
    # conflicting → reconcile/escalate (a BLOCKING allocation mismatch)
    conf = t["conflicting"]["reconciliations"]
    assert conf and conf[0]["blocking"] and conf[0]["status"] == "MISMATCH"
    assert any("Rao" in e and "conflict" in e for e in t["conflicting"]["escalations"])


def test_operational_status_is_plain_language_not_raw_scores():
    st = {s["label"]: s for s in build_deliverable()["operational_status"]}
    assert st["Calculation"]["state"] == "Independently cross-checked" and st["Calculation"]["ok"]
    assert st["Authority"]["state"] == "Resolved"
    # states are words, never bare confidence numbers
    assert all(not s["state"].replace(".", "").isdigit() for s in st.values())


def test_mission_trace_and_explain_present():
    d = build_deliverable()
    stages = [t["stage"] for t in d["mission_trace"]]
    assert stages == ["INGEST", "NORMALIZE", "RECONCILE", "ASSESS", "COMPUTE", "DRAFT", "VERIFY", "CPA REVIEW"]
    # RECONCILE flags the blocking allocation exception; CPA REVIEW shows the outcome
    assert next(t for t in d["mission_trace"] if t["stage"] == "RECONCILE")["state"] == "warn"
    qs = [e["q"] for e in d["explain"]]
    assert any("Borealis" in q for q in qs) and any("computed" in q for q in qs)


def test_review_session_signs_in_place_and_seals_ledger():
    s = ReviewSession()
    j = s.json()
    assert j["status"] == "ready_for_review" and j["signable"] is True
    assert not j["sign_offs"]
    n_before = len(j["ledger"])
    out = s.sign("APPROVE")
    assert out["status"] == "signed" and out["signable"] is False
    assert out["sign_offs"] and out["sign_offs"][0]["ledger_ref"]         # ledger sealed
    assert len(out["ledger"]) > n_before                                  # signoff + learning appended
    assert all(c["disposition"] == "accepted" for c in out["claims"])
    # a signed deliverable refuses a second signature
    assert "error" in s.sign("APPROVE")


def test_amendment_is_consequential_and_affects_ai_layer_only():
    s = ReviewSession()
    pj = next(c for c in s.json()["claims"] if c["type"] == "PROFESSIONAL_JUDGMENT")
    out = s.sign("AMEND", [{"claim_id": pj["claim_id"], "stage": "assessment", "reason": "needs records"}])
    assert out["status"] == "signed"
    amended = next(c for c in out["claims"] if c["claim_id"] == pj["claim_id"])
    assert amended["disposition"] == "amended"
    assert out["amendment_impact"]["amended_claims"] == [pj["claim_id"]]
    # affected vs unaffected: the rules/policy/guardrails are explicitly NOT touched
    un = " ".join(out["amendment_impact"]["unaffected"]).lower()
    assert "calculation rules" in un and "policy" in un and "guardrails" in un
    assert any(o["kind"] == "cpa_amendment" for o in out["learning_outcomes"])


def test_engagements_list_zoom_out():
    d = build_deliverable()
    engs = {e["id"]: e for e in d["engagements"]}
    assert set(engs) == {"rd_credit_study", "tech_accounting_memo", "income_tax_provision"}
    assert engs["rd_credit_study"]["current"] is True
    assert engs["tech_accounting_memo"]["available"] is True
    assert engs["income_tax_provision"]["available"] is False        # ○ Available, not built


def test_asc606_memo_renders_through_the_same_console():
    # P5 acceptance: switching deliverable needs no console change — the memo serialises identically.
    s = ReviewSession("tech_accounting_memo")
    j = s.json()
    assert j["deliverable_id"] == "tech_accounting_memo" and j["status"] == "ready_for_review"
    assert len(j["claims"]) == 6 and all("provenance" in c for c in j["claims"])
    # a NUMBER claim: no per-engine detail, but the cross-check still agrees (value column)
    num = next(c for c in j["claims"] if c["type"] == "NUMBER")["provenance"]["computation"]
    assert num["has_engines"] is False and all(x["agree"] for x in num["cross_check"])
    # a professional judgment read as a generic Judgment (subject + assessments), policy-derived conclusion
    pj = next(c for c in j["claims"] if c["type"] == "PROFESSIONAL_JUDGMENT")["provenance"]["judgment"]
    assert pj["subject"] == "revenue_recognition" and len(pj["assessments"]) == 4
    # the same sign gate applies
    assert s.sign("APPROVE")["status"] == "signed"


def test_income_tax_provision_is_not_signable():
    try:
        ReviewSession("income_tax_provision")
        assert False, "unavailable deliverable should not open a session"
    except ValueError:
        pass


def test_http_endpoints_roundtrip_and_sign():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()

    def get(p):
        return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{p}").read())

    def post(p, body):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{p}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        return json.loads(urllib.request.urlopen(req).read())

    try:
        assert get("/healthz")["ok"] is True
        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode()
        assert "<!doctype html>" in html.lower() and "claim graph" in html.lower()
        api = get("/api/deliverable")
        assert api["status"] == "ready_for_review" and len(api["claims"]) == 6
        # the engagement zoom-out is served, and the memo opens through the same endpoint
        assert len(get("/api/engagements")["engagements"]) == 3
        memo = get("/api/deliverable?id=tech_accounting_memo")
        assert memo["deliverable_id"] == "tech_accounting_memo" and len(memo["claims"]) == 6
        signed = post("/api/sign", {"decision": "APPROVE"})
        assert signed["status"] == "signed" and signed["sign_offs"][0]["ledger_ref"]
        # reset returns a fresh, re-signable deliverable
        assert post("/api/reset", {})["status"] == "ready_for_review"
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
