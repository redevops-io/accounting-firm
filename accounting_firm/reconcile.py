"""Deterministic reconciliation — run BEFORE any model reasoning (plan rule 3).

Source material disagrees before the AI has anything meaningful to reason about; a missing reconciliation
must not become an LLM "uncertainty" problem. A MISMATCH beyond tolerance is blocking → the mission escalates.
"""
from __future__ import annotations

from .contracts import ReconciliationResult


def reconcile(source_a: str, value_a: float, source_b: str, value_b: float,
              expected: str, tolerance: float = 1.0) -> ReconciliationResult:
    return ReconciliationResult(source_a=source_a, source_b=source_b, expected_relationship=expected,
                               value_a=round(value_a, 2), value_b=round(value_b, 2), tolerance=tolerance)


def blocking(results: list[ReconciliationResult]) -> list[ReconciliationResult]:
    return [r for r in results if r.blocking]
