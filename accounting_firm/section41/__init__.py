"""IRC §41 research credit — deterministic. Two independent implementations cross-check every figure.

The credit is CODE, never the model. Engine A (schedule-style) and Engine B (fold-style) are structurally
independent implementations of the same statute; `compute_credit` runs both and refuses to return a number
they do not agree on (the engine-of-record + independent-cross-validator methodology, applied to §41).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import engine_a, engine_b
from .qualify import conclude

CROSS_CHECK_TOLERANCE = 0.01   # dollars; a formula/logic error moves more than a rounding penny


@dataclass(frozen=True)
class QREInputs:
    """Qualified research expense inputs. Wages/supplies/cloud are already qualified-time-weighted and
    restricted to QUALIFIED projects (see qualify + the QRE schedule stage)."""
    qualified_wages: float = 0.0
    qualified_supplies: float = 0.0
    contract_research: float = 0.0          # gross; 65% is includible (IRC §41(b)(3))
    cloud_computing: float = 0.0            # qualified rental of computers/cloud
    prior_qre: tuple[float, ...] = ()       # prior 3 years' QRE (ASC)
    fixed_base_pct: float = 0.0             # RRC, capped at 16%
    avg_gross_receipts_prior4: float = 0.0  # RRC base


@dataclass(frozen=True)
class CreditResult:
    qre: float
    components: dict
    asc: float
    rrc: float
    elected: str
    credit: float
    agreement: bool                         # A and B agree within tolerance
    engine_a: dict = field(default_factory=dict)
    engine_b: dict = field(default_factory=dict)


def compute_credit(inputs: QREInputs) -> CreditResult:
    a = engine_a.compute(inputs)
    b = engine_b.compute(inputs)
    keys = ("qre", "asc", "rrc", "credit")
    agreement = all(abs(a[k] - b[k]) <= CROSS_CHECK_TOLERANCE for k in keys)
    return CreditResult(qre=a["qre"], components=a["components"], asc=a["asc"], rrc=a["rrc"],
                        elected=a["elected"], credit=a["credit"], agreement=agreement,
                        engine_a=a, engine_b=b)


__all__ = ["QREInputs", "CreditResult", "compute_credit", "conclude", "CROSS_CHECK_TOLERANCE"]
