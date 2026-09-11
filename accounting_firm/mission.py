"""The shared governed tail of every deliverable: draft → verify → CPA review/sign → learn.

Each deliverable does its own domain work (extract · reconcile · assess · compute · claim graph) and then
hands the claim graph here. Nothing below is deliverable-specific — adding a new deliverable adds a module,
never a change to this loop (the Phase-2 genericity criterion).
"""
from __future__ import annotations

from . import verify
from .contracts import Deliverable, Engagement, LearningOutcome, SignOff
from .ledger import Ledger

_STATUS = {"APPROVE": "signed", "AMEND": "signed", "REJECT": "rejected"}


def finalize(engagement: Engagement, d: Deliverable, led: Ledger, cpa_review, provider) -> tuple[Deliverable, Ledger]:
    d.rendered = provider.draft(engagement, d)
    led.append("drafted", {"chars": len(d.rendered), "provider": provider.name})

    v = verify.verify(d)
    led.append("verified", {"all_ok": v["all_ok"], "blocking": v["blocking_claims"]})
    if not v["all_ok"]:
        d.status = "escalated"; d.escalations.append(f"unverified claims: {v['blocking_claims']}")
        return d, led

    d.status = "ready_for_review"
    signoff: SignOff = cpa_review(d)
    d.sign_offs.append(signoff)
    led.append("signoff", {"decision": signoff.decision.value, "amendments": len(signoff.amendments),
                           "cpa": signoff.cpa_principal})
    d.status = _STATUS[signoff.decision.value]
    signoff.ledger_ref = led.events()[-1].hash

    outcomes = [LearningOutcome(context={"stage": am.get("stage", "draft"), "claim": am["claim_id"],
                                         "provider": provider.name},
                                decision=am.get("ai_choice", "draft"), reward=-0.5, kind="cpa_amendment")
                for am in signoff.amendments]
    if signoff.decision.value == "APPROVE":
        outcomes.append(LearningOutcome(context={"deliverable": engagement.deliverable_type,
                                                 "provider": provider.name},
                                        decision="accepted_as_drafted", reward=1.0))
    led.append("learning", {"outcomes": len(outcomes)})
    setattr(d, "learning_outcomes", outcomes)
    return d, led
