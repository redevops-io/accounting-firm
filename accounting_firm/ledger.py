"""Append-only evidence & event ledger — the signable audit trail.

Every mission step and the CPA sign-off are appended here; nothing is mutated. This is the in-repo,
zero-dependency stand-in for the agentic-os durable event ledger (DuckDBEventStore / PostgresEventStore,
agentic-os PR #147) behind the same append-only surface — swap it in for the production firm."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LedgerEvent:
    seq: int
    at: float
    type: str
    payload: dict
    hash: str                          # content hash chaining prev → tamper-evident


@dataclass
class Ledger:
    engagement_id: str
    _events: list[LedgerEvent] = field(default_factory=list)

    def append(self, type: str, payload: dict) -> LedgerEvent:
        seq = len(self._events) + 1
        prev = self._events[-1].hash if self._events else ""
        body = json.dumps({"seq": seq, "type": type, "payload": payload, "prev": prev},
                          sort_keys=True, default=str)
        h = hashlib.sha256(body.encode()).hexdigest()[:16]
        ev = LedgerEvent(seq=seq, at=time.time(), type=type, payload=payload, hash=h)
        self._events.append(ev)
        return ev

    def events(self) -> list[LedgerEvent]:
        return list(self._events)

    def bundle(self) -> list[dict]:
        return [{"seq": e.seq, "type": e.type, "hash": e.hash, "payload": e.payload} for e in self._events]
