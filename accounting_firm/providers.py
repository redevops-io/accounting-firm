"""The model seam — deliverable-agnostic judgment + drafting.

Everything deterministic (parsing, computation, reconciliation, conclusion policy, verification) lives
outside this module. Here a provider does two things, for ANY deliverable:
  · assess(system, evidence, criteria) → one per-criterion `Assessment` each (the model never concludes;
    a deterministic policy in the deliverable resolves the assessments into a conclusion);
  · draft(engagement, deliverable) → render the claim graph as a memo.
Default is the offline `DeterministicProvider`; `LLMProvider` (OpenAI-compatible, FIRM_LLM_*) does real work.
"""
from __future__ import annotations

import json
import os

from .contracts import Assessment, AuthorityRef, ClaimType, Criterion, Deliverable, Engagement, Result


# ── deterministic default (offline) ─────────────────────────────────────────────
class DeterministicProvider:
    name = "deterministic"

    def assess(self, system: str, evidence: str, criteria: list[Criterion]) -> dict[str, Assessment]:
        out = {}
        for c in criteria:
            result = Result.PASS if c.hint else Result.INSUFFICIENT   # reflects the evidence-support signal
            out[c.name] = Assessment(c.name, result, evidence=c.evidence, authority=c.authority,
                                     confidence=0.85 if result == Result.PASS else 0.5,
                                     rationale=("evidence supports the criterion" if result == Result.PASS
                                                else "insufficient contemporaneous evidence"))
        return out

    def draft(self, engagement: Engagement, d: Deliverable) -> str:
        return render_claim_graph(engagement, d)

    def extract(self, system: str, raw_text: str, fields: list[str]) -> dict:
        return {}                                     # offline: the deliverable's deterministic parser handles it

    def extract_table(self, system: str, raw_text: str, columns: list[str]) -> list[dict]:
        return []                                     # offline: the deliverable's deterministic parser handles it


# ── real model (OpenAI-compatible; env-gated) ────────────────────────────────────
class LLMProvider:
    name = "llm"

    def __init__(self, chat_fn):
        self.chat = chat_fn                       # chat(system:str, user:str) -> str

    def assess(self, system: str, evidence: str, criteria: list[Criterion]) -> dict[str, Assessment]:
        asks = "; ".join(f"{c.name}: {c.prompt or c.name}" for c in criteria)
        user = (f"Evidence:\n{evidence[:6000]}\n\nAssess EACH criterion independently as PASS, FAIL, or "
                f"INSUFFICIENT (prefer INSUFFICIENT over guessing). Criteria — {asks}\n"
                'Return STRICT JSON: {"<name>":{"result":..,"confidence":0..1,"rationale":..}}')
        try:
            data = json.loads(_json_slice(self.chat(system, user)))
        except Exception:
            data = {}
        out = {}
        for c in criteria:
            a = _parse_assessment(c.name, data.get(c.name))
            out[c.name] = Assessment(c.name, a.result, evidence=c.evidence,      # attach deliverable provenance
                                     authority=c.authority or a.authority,
                                     confidence=a.confidence, rationale=a.rationale)
        return out

    def extract(self, system: str, raw_text: str, fields: list[str]) -> dict:
        """Extract the requested fields from an unstructured document (Phase-3 ingestion seam)."""
        user = (f"Document:\n{raw_text[:6000]}\n\nExtract EXACTLY these fields as strict JSON {{field: value}}; "
                f"use null if a field is absent. Fields: {', '.join(fields)}")
        try:
            data = json.loads(_json_slice(self.chat(system, user)))
            return {k: data[k] for k in fields if isinstance(data, dict) and data.get(k) is not None}
        except Exception:
            return {}

    def extract_table(self, system: str, raw_text: str, columns: list[str]) -> list[dict]:
        """Extract every row of an unstructured table (e.g. a scanned payroll) as JSON objects."""
        user = (f"Document:\n{raw_text[:6000]}\n\nExtract EVERY data row as a JSON array of objects with keys "
                f"{columns}. Return only the JSON array.")
        try:
            data = json.loads(_json_slice_array(self.chat(system, user)))
            return [{c: r.get(c) for c in columns} for r in data if isinstance(r, dict)]
        except Exception:
            return []

    def draft(self, engagement: Engagement, d: Deliverable) -> str:
        graph = [{"id": c.claim_id, "type": c.claim_type.value, "assertion": c.assertion} for c in d.claims]
        comps = [{"name": c.name, "outputs": c.outputs} for c in d.computations]
        sys = ("Render a professional accounting deliverable memo FROM the given claim graph. Every material "
               "sentence must correspond to a claim; cite the claim id in brackets; never introduce a number "
               "or authority not present in the claims/computations. Plain markdown.")
        user = json.dumps({"client": engagement.client, "type": engagement.deliverable_type,
                           "claims": graph, "computations": comps}, default=str)
        try:
            return self.chat(sys, user)
        except Exception:
            return render_claim_graph(engagement, d)          # fail-safe → deterministic render


def _parse_assessment(criterion: str, obj) -> Assessment:
    if not isinstance(obj, dict):
        return Assessment(criterion, Result.INSUFFICIENT, confidence=0.0, rationale="no model output")
    try:
        result = Result(str(obj.get("result", "INSUFFICIENT")).upper())
    except ValueError:
        result = Result.INSUFFICIENT
    auth = tuple(AuthorityRef(str(a)) for a in (obj.get("authority") or []))
    return Assessment(criterion, result, authority=auth,
                      confidence=float(obj.get("confidence", 0.0) or 0.0), rationale=str(obj.get("rationale", "")))


def _strip_think(s: str) -> str:
    # reasoning models (Qwen etc.) emit <think>…</think>; drop it before locating the JSON
    i = s.rfind("</think>")
    return s[i + 8:] if i != -1 else s


def _json_slice(s: str) -> str:
    s = _strip_think(s)
    i, j = s.find("{"), s.rfind("}")
    return s[i:j + 1] if i >= 0 and j > i else s


def _json_slice_array(s: str) -> str:
    s = _strip_think(s)
    i, j = s.find("["), s.rfind("]")
    return s[i:j + 1] if i >= 0 and j > i else s


def _http_chat(base: str, key: str, model: str):
    import httpx
    base = base.rstrip("/")

    def chat(system: str, user: str) -> str:
        payload = {"model": model, "messages": [{"role": "system", "content": system},
                                                {"role": "user", "content": user}]}
        if "moonshot" not in base:                # Kimi/Moonshot only accepts temperature=1
            payload["temperature"] = 0
        r = httpx.post(f"{base}/chat/completions", json=payload,
                       headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=180)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    return chat


def select_provider(chat_fn=None):
    """LLMProvider when a chat_fn is given or FIRM_LLM_* is configured; else the deterministic default."""
    if chat_fn is not None:
        return LLMProvider(chat_fn)
    base, key = os.environ.get("FIRM_LLM_BASE_URL"), os.environ.get("FIRM_LLM_API_KEY")
    if base and key:
        return LLMProvider(_http_chat(base, key, os.environ.get("FIRM_LLM_MODEL", "kimi-k2.6")))
    return DeterministicProvider()


# ── claim-graph render (deterministic; also the LLM fail-safe) — deliverable-agnostic ──
def render_claim_graph(eng: Engagement, d: Deliverable) -> str:
    title = eng.deliverable_type.replace("_", " ").title()
    L = [f"# {title} — {eng.client}", "",
         f"Engagement {eng.engagement_id} · fixed fee ${eng.price_usd:,.0f} · SLA {eng.sla_hours}h", ""]
    sections: dict[str, list] = {}
    for c in d.claims:
        sections.setdefault(c.section, []).append(c)
    for section, cs in sections.items():
        L.append(f"## {section.replace('_', ' ').title()}")
        for c in cs:
            tag = c.claim_id + (f" · {', '.join(a.authority for a in c.authority_refs)}"
                                if c.authority_refs else f" · {c.claim_type.value}")
            L.append(f"- {c.assertion}  _[{tag}]_")
        L.append("")
    if d.escalations:
        L += ["## Held for CPA review (not included)"] + [f"- {e}" for e in d.escalations] + [""]
    if d.computations:
        L.append("## Computation (deterministic; engines A and B agree)")
        for comp in d.computations:
            for k, v in comp.outputs.items():
                if isinstance(v, (dict, list)):
                    continue                       # engine A/B detail + components are for the console, not the memo prose
                val = f"${v:,.0f}" if isinstance(v, (int, float)) else v
                L.append(f"- {comp.name}.{k}: **{val}**  _[cross-checked: {comp.agreement}]_")
        L.append("")
    return "\n".join(L)
