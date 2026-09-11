"""Append-only evidence & event ledger — the signable audit trail.

Every mission step and the CPA sign-off are appended here; nothing is mutated. This is the in-repo,
zero-dependency stand-in for the agentic-os durable event ledger (DuckDBEventStore / PostgresEventStore,
agentic-os PR #147) behind the same append-only surface — swap it in for the production firm."""
from __future__ import annotations

import hashlib
import json
import os
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


def _hash(seq: int, type: str, payload: dict) -> str:
    return hashlib.sha256(json.dumps({"seq": seq, "type": type, "payload": payload},
                                     sort_keys=True, default=str).encode()).hexdigest()[:16]


class AgenticOSLedger:
    """Adapter over the agentic-os durable event ledger (DuckDBEventStore / PostgresEventStore, PR #147),
    behind the same append/events/bundle surface. The engagement is the mission_id; selected by
    FIRM_LEDGER=agentic-os (honouring MISSION_EVENT_BACKEND). Same audit trail, now durable + queryable."""

    def __init__(self, engagement_id: str, store):
        self.engagement_id = engagement_id
        self._store = store

    def append(self, type: str, payload: dict) -> LedgerEvent:
        ev = self._store.append(type, self.engagement_id, payload)
        return LedgerEvent(ev.seq, ev.ts, ev.type, payload, _hash(ev.seq, ev.type, payload))

    def events(self) -> list[LedgerEvent]:
        return [LedgerEvent(e.seq, e.ts, e.type, e.payload, _hash(e.seq, e.type, e.payload))
                for e in self._store.for_mission(self.engagement_id)]

    def bundle(self) -> list[dict]:
        return [{"seq": e.seq, "type": e.type, "hash": e.hash, "payload": e.payload} for e in self.events()]


def select_ledger(engagement_id: str):
    """The durable agentic-os ledger when FIRM_LEDGER=agentic-os; else the in-repo hash-chained ledger."""
    if os.environ.get("FIRM_LEDGER") == "agentic-os":
        try:
            from agentic_os.mission.event_backends import open_event_store   # noqa: PLC0415
            return AgenticOSLedger(engagement_id, open_event_store())
        except Exception:                                        # agentic-os absent → in-repo ledger
            pass
    return Ledger(engagement_id)
