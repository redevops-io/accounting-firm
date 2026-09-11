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
    assert t["sufficient"]["credit"] == 30800.0
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


def test_http_endpoints_roundtrip():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        base = f"http://127.0.0.1:{port}"
        assert json.loads(urllib.request.urlopen(f"{base}/healthz").read())["ok"] is True
        html = urllib.request.urlopen(f"{base}/").read().decode()
        assert "<!doctype html>" in html.lower() and "claim graph" in html.lower()
        api = json.loads(urllib.request.urlopen(f"{base}/api/deliverable").read())
        assert api["status"] == "signed" and len(api["claims"]) == 6
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
