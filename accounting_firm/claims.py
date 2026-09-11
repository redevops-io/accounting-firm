"""Claim-graph construction. The deliverable IS the graph; the memo is a rendering of it (plan §6)."""
from __future__ import annotations

import itertools

from .contracts import AuthorityRef, Claim, ClaimType, EvidenceRef

_counter = itertools.count(1)


def new_claim(section: str, claim_type: ClaimType, assertion: str, *,
              evidence: tuple[EvidenceRef, ...] = (), authority: tuple[AuthorityRef, ...] = (),
              computation_ref: str | None = None, assessment_ref: str | None = None,
              confidence: float = 0.0) -> Claim:
    return Claim(claim_id=f"C{next(_counter):03d}", section=section, claim_type=claim_type,
                 assertion=assertion, evidence_refs=evidence, authority_refs=authority,
                 computation_ref=computation_ref, assessment_ref=assessment_ref, confidence=confidence)
