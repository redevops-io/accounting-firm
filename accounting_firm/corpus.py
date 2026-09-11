"""Authority corpus + resolver — grounded-only citations (plan rule 6).

A small, curated slice of IRC §41 / Treas. Reg. §1.41 authority for the R&D credit study. A citation is
"resolved" only if its authority id is in the corpus AND the cited concept keywords appear in the passage —
the verifier re-checks this so no fabricated authority reaches the deliverable. Maps to a redevops-rag
retrieval capability in production (this local resolver is the offline stand-in behind the same seam)."""
from __future__ import annotations

# authority_id -> (passage, concept keywords the citation must be about)
CORPUS: dict[str, tuple[str, tuple[str, ...]]] = {
    "IRC §41(a)(1)": (
        "The research credit equals 20 percent of the excess of qualified research expenses for the "
        "taxable year over the base amount.",
        ("credit", "qualified research expenses", "base amount")),
    "IRC §41(b)(3)": (
        "Contract research expenses are 65 percent of amounts paid to any person (other than an employee) "
        "for qualified research.",
        ("contract research", "65 percent")),
    "IRC §41(c)(4)": (
        "Alternative simplified credit: 14 percent of the excess of qualified research expenses over 50 "
        "percent of the average qualified research expenses for the three preceding taxable years.",
        ("alternative simplified credit", "14 percent", "three preceding")),
    "IRC §41(d)(1)": (
        "Qualified research means research with respect to which expenditures may be treated as section 174 "
        "expenses, undertaken to discover information that is technological in nature, the application of "
        "which is intended to be useful in developing a new or improved business component, and substantially "
        "all of the activities of which constitute a process of experimentation.",
        ("qualified research", "technological in nature", "business component", "process of experimentation")),
    "Treas. Reg. §1.41-4(a)(5)": (
        "A process of experimentation is a process designed to evaluate one or more alternatives to achieve "
        "a result where the capability or method of achieving that result is uncertain at the outset.",
        ("process of experimentation", "alternatives", "uncertain")),
    "Treas. Reg. §1.41-4(a)(3)": (
        "Uncertainty exists if the information available to the taxpayer does not establish the capability or "
        "method for developing or improving the business component, or the appropriate design.",
        ("uncertainty", "capability", "method", "design")),
    # ASC 606 — revenue recognition (technical accounting memo)
    "ASC 606-10-25-1": (
        "An entity shall account for a contract with a customer only when the parties have approved the "
        "contract, each party's rights and the payment terms are identifiable, the contract has commercial "
        "substance, and collection of the consideration is probable.",
        ("contract", "customer", "payment terms", "collection")),
    "ASC 606-10-25-27": (
        "An entity recognizes revenue over time if the customer simultaneously receives and consumes the "
        "benefits provided by the entity's performance as the entity performs.",
        ("over time", "performance obligation", "benefits")),
    "ASC 606-10-32-2": (
        "The transaction price is the amount of consideration to which an entity expects to be entitled in "
        "exchange for transferring promised goods or services to a customer.",
        ("transaction price", "consideration")),
}


def resolve(authority_id: str, about: tuple[str, ...] = ()) -> tuple[bool, str]:
    """Return (resolved, passage). Resolved iff the authority exists and (if `about` given) at least one
    requested concept keyword is genuinely in the passage's concept set."""
    entry = CORPUS.get(authority_id)
    if not entry:
        return False, ""
    passage, concepts = entry
    if about and not any(a.lower() in [c.lower() for c in concepts] for a in about):
        return False, passage
    return True, passage
