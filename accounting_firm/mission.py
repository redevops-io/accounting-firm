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


def prepare(engagement: Engagement, d: Deliverable, led: Ledger, provider) -> tuple[Deliverable, Ledger]:
    """Draft the claim graph and verify it, up to the CPA gate. On success status = ready_for_review; the
    deliverable is now signable. Split out from finalize so a review surface can hold it and sign later."""
    d.rendered = provider.draft(engagement, d)
    led.append("drafted", {"chars": len(d.rendered), "provider": provider.name})

    v = verify.verify(d)
    led.append("verified", {"all_ok": v["all_ok"], "blocking": v["blocking_claims"]})
    if not v["all_ok"]:
        d.status = "escalated"; d.escalations.append(f"unverified claims: {v['blocking_claims']}")
        return d, led

    d.status = "ready_for_review"
    return d, led


def sign(engagement: Engagement, d: Deliverable, led: Ledger, cpa_review, provider) -> tuple[Deliverable, Ledger]:
    """The CPA gate: apply the review decision, record dispositions, seal the ledger, emit learning. The
    decision (APPROVE/AMEND/REJECT) moves state; an amendment tunes the AI layer only, never the rules."""
    signoff: SignOff = cpa_review(d)
    d.sign_offs.append(signoff)
    led.append("signoff", {"decision": signoff.decision.value, "amendments": len(signoff.amendments),
                           "cpa": signoff.cpa_principal})
    d.status = _STATUS[signoff.decision.value]
    signoff.ledger_ref = led.events()[-1].hash

    amended = {am["claim_id"] for am in signoff.amendments}
    disposition = {"APPROVE": "accepted", "AMEND": "accepted", "REJECT": "rejected"}[signoff.decision.value]
    for c in d.claims:
        c.reviewer_disposition = "amended" if c.claim_id in amended else disposition

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


def finalize(engagement: Engagement, d: Deliverable, led: Ledger, cpa_review, provider) -> tuple[Deliverable, Ledger]:
    d, led = prepare(engagement, d, led, provider)
    if d.status != "ready_for_review":
        return d, led
    return sign(engagement, d, led, cpa_review, provider)
