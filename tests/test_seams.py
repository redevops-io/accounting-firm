"""Runtime seams: grounding resolver + durable-ledger backend. Defaults stay offline; adapters conform."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounting_firm.contracts import AuthorityRef, ClaimType, Deliverable, Engagement
from accounting_firm.ledger import AgenticOSLedger, Ledger, select_ledger
from accounting_firm.resolvers import LocalResolver, select_resolver
from accounting_firm import claims, verify


def test_defaults_are_offline(monkeypatch):
    for k in ("FIRM_CORPUS", "FIRM_RAG_DB", "FIRM_LEDGER"):
        monkeypatch.delenv(k, raising=False)
    assert isinstance(select_resolver(), LocalResolver)
    assert isinstance(select_ledger("E"), Ledger)


def test_local_resolver_grounds_and_rejects():
    r = LocalResolver()
    assert r.resolve("IRC §41(d)(1)", ("qualified research",))[0]
    assert r.resolve("ASC 606-10-25-27", ("over time",))[0]
    assert not r.resolve("IRC §999(z)", ("fabricated",))[0]        # no fabricated authority resolves


def test_verify_uses_injected_resolver():
    eng = Engagement("E", "C", "x", "", 0, 48)
    d = Deliverable(engagement=eng)
    d.claims = [claims.new_claim("authority", ClaimType.AUTHORITY_INTERPRETATION, "cites law",
                                 authority=(AuthorityRef("IRC §41(d)(1)", "qualified research"),))]

    class _Reject:
        def resolve(self, a, about=()):
            return False, ""
    assert verify.verify(d, resolver=_Reject())["all_ok"] is False   # unresolved citation blocks
    assert verify.verify(d, resolver=LocalResolver())["all_ok"] is True


def test_agenticos_ledger_adapter_conforms():
    # a fake EventStore with the agentic-os surface (append(type, mission_id, payload) / for_mission)
    class _Ev:
        def __init__(self, seq, type, mid, payload):
            self.seq, self.ts, self.type, self.mission_id, self.payload = seq, 0.0, type, mid, payload

    class _Store:
        def __init__(self):
            self._e = []
        def append(self, type, mid, payload):
            ev = _Ev(len(self._e) + 1, type, mid, payload); self._e.append(ev); return ev
        def for_mission(self, mid):
            return [e for e in self._e if e.mission_id == mid]

    led = AgenticOSLedger("ENG-1", _Store())
    e1 = led.append("computed", {"credit": 100})
    led.append("signoff", {"decision": "APPROVE"})
    evs = led.events()
    assert [e.type for e in evs] == ["computed", "signoff"]
    assert e1.hash and evs[-1].hash and len(led.bundle()) == 2   # hashes present, bundle round-trips


if __name__ == "__main__":
    class _MP:
        def delenv(self, k, raising=False): os.environ.pop(k, None)
    for k, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        fn(_MP()) if "monkeypatch" in fn.__code__.co_varnames else fn()
        print("ok", k)
    print("\npassed")
