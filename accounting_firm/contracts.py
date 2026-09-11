"""Value contracts — the functional core of the firm (stdlib + dataclasses only).

A professional deliverable is a **claim graph**: every material sentence is a `Claim` with provenance
(evidence, authority, a deterministic computation, or a structured assessment). Numbers come from engines,
judgment comes from structured per-criterion `Assessment`s the model fills but never *concludes* — a
deterministic policy derives conclusions. See AI_NATIVE_ACCOUNTING_FIRM_IMPLEMENTATION_PLAN.md (rev.2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ── enums ────────────────────────────────────────────────────────────────────
class Result(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT = "INSUFFICIENT"


class Conclusion(str, Enum):
    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ClaimType(str, Enum):
    NUMBER = "NUMBER"                              # an asserted figure — must have a computation_ref
    FACT = "FACT"                                  # an extracted fact — must have evidence
    PROFESSIONAL_JUDGMENT = "PROFESSIONAL_JUDGMENT"  # a qualification call — must have an assessment_ref
    AUTHORITY_INTERPRETATION = "AUTHORITY_INTERPRETATION"  # a reading of law — must cite authority


class Decision(str, Enum):
    APPROVE = "APPROVE"
    AMEND = "AMEND"
    REJECT = "REJECT"


# ── evidence / sources ───────────────────────────────────────────────────────
@dataclass(frozen=True)
class Confidence:
    """Kept multi-dimensional on purpose — never collapse to one scalar (plan rule 4)."""
    extraction: float = 0.0            # how sure we read the document right
    evidence_completeness: float = 0.0  # how complete the evidence is for the question at hand
    assessment: float = 0.0            # how sure the judgment is
    calculation: float = 0.0           # how sure the computed number is


@dataclass(frozen=True)
class EvidenceRef:
    doc_id: str
    locator: str                       # page/cell/line/span — where in the source
    quote: str = ""                    # the supporting snippet (redacted-safe)


@dataclass(frozen=True)
class AuthorityRef:
    authority: str                     # e.g. "IRC §41(d)(1)", "Treas. Reg. §1.41-4(a)(3)"
    passage_ref: str = ""              # corpus locator
    resolved: bool = False             # verifier sets this once it re-retrieves and matches


@dataclass(frozen=True)
class SourceDocument:
    doc_id: str
    kind: str                          # payroll_export | gl_extract | project_description | engineering_doc | ...
    uri: str
    extracted_facts: dict = field(default_factory=dict)
    confidence: Confidence = field(default_factory=Confidence)
    provenance: str = ""               # extractor id/version


# ── reconciliation (deterministic, before any model reasoning) ─────────────────
@dataclass(frozen=True)
class ReconciliationResult:
    source_a: str
    source_b: str
    expected_relationship: str         # human-readable rule, e.g. "payroll wages == GL wage accounts"
    value_a: float
    value_b: float
    tolerance: float
    @property
    def difference(self) -> float:
        return round(self.value_a - self.value_b, 2)
    @property
    def status(self) -> str:
        return "OK" if abs(self.difference) <= self.tolerance else "MISMATCH"
    @property
    def blocking(self) -> bool:
        return self.status == "MISMATCH"


# ── structured judgment (the model fills; policy concludes) ────────────────────
@dataclass(frozen=True)
class Assessment:
    criterion: str
    result: Result
    evidence: tuple[EvidenceRef, ...] = ()
    authority: tuple[AuthorityRef, ...] = ()
    confidence: float = 0.0
    rationale: str = ""


@dataclass(frozen=True)
class ResearchQualification:
    """The IRC §41(d) four-part test as four independent evidence-backed assessments.
    `conclusion` is DERIVED by deterministic policy (see section41.qualify), not by the model."""
    project_id: str
    permitted_purpose: Assessment
    technological_in_nature: Assessment
    elimination_of_uncertainty: Assessment
    process_of_experimentation: Assessment
    conclusion: Conclusion


# ── deterministic computation ──────────────────────────────────────────────────
@dataclass(frozen=True)
class Computation:
    name: str                          # e.g. "asc_credit"
    engine: str                        # implementation A id
    inputs: dict
    outputs: dict
    cross_validator: str = ""          # implementation B id
    agreement: bool = False            # A and B agree within tolerance
    ties_to: tuple[str, ...] = ()      # ids of the schedules/claims this rolls up from


# ── the claim graph (the deliverable IS this) ──────────────────────────────────
@dataclass
class Claim:
    claim_id: str
    section: str
    claim_type: ClaimType
    assertion: str
    evidence_refs: tuple[EvidenceRef, ...] = ()
    authority_refs: tuple[AuthorityRef, ...] = ()
    computation_ref: str | None = None
    assessment_ref: str | None = None
    confidence: float = 0.0
    verifier_results: list[dict] = field(default_factory=list)   # {check, ok, detail}
    reviewer_disposition: str = ""     # "", accepted, amended, rejected

    @property
    def verified(self) -> bool:
        return bool(self.verifier_results) and all(v["ok"] for v in self.verifier_results)


# ── engagement / deliverable / sign-off / learning ─────────────────────────────
@dataclass(frozen=True)
class Engagement:
    engagement_id: str
    client: str
    deliverable_type: str              # "rd_credit_study" | "tech_accounting_memo" | ...
    scope: str
    price_usd: float
    sla_hours: int
    principals: tuple[str, ...] = ("preparer", "cpa")


@dataclass
class SignOff:
    cpa_principal: str
    at: float
    scope: str
    decision: Decision
    amendments: list[dict] = field(default_factory=list)   # {claim_id, before, after, reason}
    ledger_ref: str = ""


@dataclass
class Deliverable:
    engagement: Engagement
    claims: list[Claim] = field(default_factory=list)       # the claim graph
    computations: list[Computation] = field(default_factory=list)
    qualifications: list[ResearchQualification] = field(default_factory=list)
    reconciliations: list[ReconciliationResult] = field(default_factory=list)
    rendered: str = ""                                       # rendering OF the claim graph
    status: str = "draft"                                    # draft | escalated | ready_for_review | signed | rejected
    escalations: list[str] = field(default_factory=list)
    sign_offs: list[SignOff] = field(default_factory=list)

    def claim(self, claim_id: str) -> Claim | None:
        return next((c for c in self.claims if c.claim_id == claim_id), None)


@dataclass(frozen=True)
class LearningOutcome:
    """A CPA-amendment delta → durable-learning signal for the AI layer ONLY (retrieval/model/extraction/
    escalation/drafting). Never mutates tax/accounting rules (plan rule 8)."""
    context: dict                      # what the AI layer decided (retrieval strategy, model, extractor…)
    decision: str                      # the AI choice being scored
    reward: float                      # +1 accepted as-is … -1 rejected; partial for amended
    kind: str = "cpa_amendment"
