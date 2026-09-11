"""The IRC §41(d) four-part test — deterministic CONCLUSION policy over structured assessments.

The model fills four evidence-backed `Assessment`s (PASS/FAIL/INSUFFICIENT); this code — versioned,
controlled, never learned — derives the conclusion. That is the "LLMs may not decide" doctrine applied to
professional judgment: the model reasons per criterion; policy decides what may advance.
"""
from __future__ import annotations

from ..contracts import Assessment, Conclusion, Result

FOUR_PARTS = (
    "permitted_purpose",            # §41(d)(1)(B)(ii) / §41(d)(3)
    "technological_in_nature",      # §41(d)(1)(B)(i)
    "elimination_of_uncertainty",   # §41(d)(1)(A) / §174
    "process_of_experimentation",   # §41(d)(1)(C) / Treas. Reg. §1.41-4(a)(5)
)


def conclude(*assessments: Assessment) -> Conclusion:
    """All four must PASS to qualify. Any FAIL disqualifies. Otherwise (an INSUFFICIENT) → human review."""
    results = [a.result for a in assessments]
    if Result.FAIL in results:
        return Conclusion.NOT_QUALIFIED
    if Result.INSUFFICIENT in results:
        return Conclusion.REVIEW_REQUIRED
    return Conclusion.QUALIFIED
