"""§41 engine A — schedule style: build each QRE line, then apply each method step by step.

Independent of engine_b by construction (different control flow + intermediate schedule). Both must agree.
"""
from __future__ import annotations

ASC_RATE = 0.14
ASC_STARTUP_RATE = 0.06     # no QRE in one of the 3 prior years → 6% of current QRE (IRC §41(c)(4)(B))
RRC_RATE = 0.20
RRC_FLOOR = 0.50            # base amount ≥ 50% of current QRE (IRC §41(c)(2))
FIXED_BASE_CAP = 0.16


def compute(i) -> dict:
    # ── QRE schedule (component-rounded, then summed) ──
    wages = round(i.qualified_wages, 2)
    supplies = round(i.qualified_supplies, 2)
    contract = round(0.65 * i.contract_research, 2)
    cloud = round(i.cloud_computing, 2)
    qre = round(wages + supplies + contract + cloud, 2)
    components = {"qualified_wages": wages, "qualified_supplies": supplies,
                 "contract_research_65pct": contract, "cloud_computing": cloud}

    # ── Alternative Simplified Credit ──
    priors = list(i.prior_qre)[:3]
    if len(priors) == 3 and all(p > 0 for p in priors):
        base = 0.5 * (sum(priors) / 3.0)
        asc = round(ASC_RATE * max(qre - base, 0.0), 2)
    else:
        asc = round(ASC_STARTUP_RATE * qre, 2)

    # ── Regular Research Credit ──
    fixed_base = min(max(i.fixed_base_pct, 0.0), FIXED_BASE_CAP)
    computed_base = fixed_base * i.avg_gross_receipts_prior4
    base_amount = max(computed_base, RRC_FLOOR * qre)
    rrc = round(RRC_RATE * max(qre - base_amount, 0.0), 2)

    elected = "ASC" if asc >= rrc else "RRC"
    credit = round(max(asc, rrc), 2)
    return {"qre": qre, "components": components, "asc": asc, "rrc": rrc,
            "elected": elected, "credit": credit,
            "base_amount": round(base_amount, 2)}
