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


# --- accessibility / responsive contract of the page (P2): structural, so a regression is caught without a browser ---
# The behavioural proof (keyboard, focus trap, axe, 375/768/1280 overflow) is the Playwright run documented in
# the PR; these assertions pin the markup it depends on.
import re

PAGE = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "accounting_firm", "console", "static", "index.html"), encoding="utf-8").read()


def test_page_has_a_main_landmark_and_a_skip_link():
    assert len(re.findall(r"<main\b", PAGE)) == 1 and 'href="#main"' in PAGE


def test_closed_drawer_is_inert_not_merely_aria_hidden():
    # aria-hidden on a focusable subtree is the axe aria-hidden-focus failure; the closed panels must be `inert`.
    drawer = re.search(r'<div class="drawer"[^>]*>', PAGE).group(0)
    assert "inert" in drawer and "aria-hidden" not in drawer
    assert 'role="dialog"' in drawer and 'aria-modal="true"' in drawer and "aria-labelledby" in drawer
    assert "inert" in re.search(r'<aside class="rtmap"[^>]*>', PAGE).group(0)
    assert "visibility:hidden" in PAGE                             # off-canvas panels are also out of the layout/tab order
    assert 'setAttribute("aria-hidden"' not in PAGE


def test_drawer_has_focus_management_and_escape():
    for needle in ("DRAWER_OPENER", "setBackgroundInert", 'e.key==="Escape"', 'e.key==="Tab"&&drawerOpen()'):
        assert needle in PAGE, needle


def test_claims_and_engagement_cards_are_real_buttons():
    assert 'el("button","claim' in PAGE and 'el("div","claim' not in PAGE       # "challenge any statement" by keyboard
    assert 'el(actionable?"button":"div","ez' in PAGE
    assert "row.onclick=()=>openDrawer(c,row)" in PAGE


def test_sign_controls_and_amend_labels_are_kept_and_labelled():
    for label in ("Approve &amp; sign", "Amend a claim…", "Reject", "Record amendment &amp; sign"):
        assert label in PAGE, label
    assert 'label for="am-claim"' in PAGE and 'label for="am-reason"' in PAGE


def test_shared_demo_session_is_stated_on_the_page_and_no_auth_was_added():
    assert 'id="sessionnote"' in PAGE and "Shared demo session" in PAGE and "no sign-in" in PAGE
    assert not re.search(r"(?i)authorization|bearer|login-?form|type=\"password\"", PAGE)


def test_narrow_screens_wrap_the_nav_instead_of_overflowing():
    assert re.search(r"nav\.tabs\{[^}]*flex-wrap:wrap", PAGE)
    assert "overflow-x:auto" in PAGE                                           # wide tables scroll inside their card


def test_no_low_contrast_dim_text_tokens():
    # --faint was #6b7385 (3.0-4.0:1 on the dark surfaces); AA needs 4.5:1 on every surface token.
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    tok = dict(re.findall(r"--([a-z0-9-]+):(#[0-9a-fA-F]{6})", PAGE))
    for fg in ("faint", "muted", "block", "warn", "pass", "accent"):
        for bg in ("bg", "surface", "surface-2", "surface-3"):
            a, b = sorted((lum(tok[fg]), lum(tok[bg])), reverse=True)
            assert (a + .05) / (b + .05) >= 4.5, (fg, bg)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
