"""§41 engine B — fold style: an independent re-implementation used only to cross-check engine A.

Same statute, different code path (dict fold for QRE, guard-clause ordering for the methods). If A and B
disagree by more than a rounding penny, `compute_credit` refuses the number and the mission escalates.
"""
from __future__ import annotations


def _round2(x: float) -> float:
    return round(x, 2)


def compute(i) -> dict:
    # QRE via a component map (contract at 65%), each line rounded, then totalled
    lines = {
        "qualified_wages": _round2(i.qualified_wages),
        "qualified_supplies": _round2(i.qualified_supplies),
        "contract_research_65pct": _round2(i.contract_research * 0.65),
        "cloud_computing": _round2(i.cloud_computing),
    }
    qre = _round2(sum(lines.values()))

    # ASC: startup rule first (guard clause), else incremental
    priors = tuple(i.prior_qre)[:3]
    has_full_history = len(priors) == 3 and min(priors) > 0
    if not has_full_history:
        asc = _round2(0.06 * qre)
    else:
        incremental_base = (priors[0] + priors[1] + priors[2]) / 6.0   # 0.5 * mean(3)
        excess = qre - incremental_base
        asc = _round2(0.14 * excess) if excess > 0 else 0.0

    # RRC: fixed-base product vs 50% floor, whichever is larger, is the base
    fb = i.fixed_base_pct
    fb = 0.0 if fb < 0 else (0.16 if fb > 0.16 else fb)
    base_from_history = fb * i.avg_gross_receipts_prior4
    floor = 0.5 * qre
    base_amount = base_from_history if base_from_history > floor else floor
    excess_rrc = qre - base_amount
    rrc = _round2(0.20 * excess_rrc) if excess_rrc > 0 else 0.0

    elected = "ASC" if asc >= rrc else "RRC"
    return {"qre": qre, "components": lines, "asc": asc, "rrc": rrc,
            "elected": elected, "credit": _round2(max(asc, rrc)),
            "base_amount": _round2(base_amount)}
