"""The model seam — judgment (the four-part assessment) and narrative (drafting).

Everything deterministic (parsing, §41 computation, reconciliation, the conclusion policy, verification) lives
outside this module. Here is the *only* place a model may act, and even here it never concludes: for the
four-part test it fills per-criterion `Assessment`s (PASS/FAIL/INSUFFICIENT) which a deterministic policy then
resolves. Default is the offline `DeterministicProvider` (used by the demo/tests); `LLMProvider` is selected
when FIRM_LLM_* is configured, matching the capmarkets/learnerbot scorer-seam pattern.
"""
from __future__ import annotations

import json
import os

from . import claims as _claims
from .contracts import (Assessment, AuthorityRef, ClaimType, Conclusion, Deliverable, Engagement,
                        EvidenceRef, Result, ResearchQualification)
from .section41 import conclude

_FOUR_PARTS = ("permitted_purpose", "technological_in_nature", "elimination_of_uncertainty",
               "process_of_experimentation")


# ── deterministic default (offline) ─────────────────────────────────────────────
class DeterministicProvider:
    name = "deterministic"
    qualified_project = "Atlas"

    def assess(self, project: str, facts: dict) -> ResearchQualification:
        a41d = (AuthorityRef("IRC §41(d)(1)", "qualified research"),)
        reg_unc = (AuthorityRef("Treas. Reg. §1.41-4(a)(3)", "uncertainty"),)
        reg_exp = (AuthorityRef("Treas. Reg. §1.41-4(a)(5)", "process of experimentation"),)
        ev_proj = (EvidenceRef("project_desc", f"Project {project}"),)
        ev_eng = (EvidenceRef("engineering", f"Project {project} experimentation log"),)

        def a(crit, result, auth, ev):
            return Assessment(crit, result, evidence=ev, authority=auth,
                              confidence=0.85 if result == Result.PASS else 0.5,
                              rationale=("evidence supports the criterion" if result == Result.PASS
                                         else "insufficient contemporaneous evidence"))
        if project == self.qualified_project:
            parts = [a("permitted_purpose", Result.PASS, a41d, ev_proj),
                     a("technological_in_nature", Result.PASS, a41d, ev_proj),
                     a("elimination_of_uncertainty", Result.PASS, reg_unc, ev_eng),
                     a("process_of_experimentation", Result.PASS, reg_exp, ev_eng)]
        else:
            parts = [a("permitted_purpose", Result.PASS, a41d, ev_proj),
                     a("technological_in_nature", Result.PASS, a41d, ev_proj),
                     a("elimination_of_uncertainty", Result.INSUFFICIENT, reg_unc, ()),
                     a("process_of_experimentation", Result.INSUFFICIENT, reg_exp, ())]
        return ResearchQualification(project, *parts, conclusion=conclude(*parts))

    def draft(self, engagement: Engagement, d: Deliverable, cr, qualified: list[str]) -> str:
        return render_claim_graph(engagement, d, cr, qualified)


# ── real model (OpenAI-compatible; env-gated) ────────────────────────────────────
_ASSESS_SYS = (
    "You are a tax professional applying the IRC §41(d)(1) four-part test to ONE project. Assess EACH of the "
    "four criteria independently as PASS, FAIL, or INSUFFICIENT based ONLY on the provided evidence and cited "
    "authority. Do NOT decide whether the project qualifies overall — that is decided by policy from your four "
    "assessments. Return STRICT JSON: {\"permitted_purpose\":{\"result\":..,\"confidence\":0..1,"
    "\"rationale\":..,\"authority\":[..]}, \"technological_in_nature\":{..}, "
    "\"elimination_of_uncertainty\":{..}, \"process_of_experimentation\":{..}}. Prefer INSUFFICIENT over "
    "guessing.")


class LLMProvider:
    name = "llm"

    def __init__(self, chat_fn):
        self.chat = chat_fn                       # chat(system:str, user:str) -> str

    def assess(self, project: str, facts: dict) -> ResearchQualification:
        evidence = json.dumps({"project": project, "projects": facts.get("projects", {})}, default=str)[:6000]
        try:
            raw = self.chat(_ASSESS_SYS, f"Project: {project}\nEvidence:\n{evidence}")
            data = json.loads(_json_slice(raw))
        except Exception:
            data = {}
        parts = [_parse_assessment(crit, data.get(crit)) for crit in _FOUR_PARTS]
        return ResearchQualification(project, *parts, conclusion=conclude(*parts))

    def draft(self, engagement: Engagement, d: Deliverable, cr, qualified: list[str]) -> str:
        graph = [{"id": c.claim_id, "type": c.claim_type.value, "assertion": c.assertion} for c in d.claims]
        sys = ("Render a professional R&D tax credit study memo FROM the given claim graph. Every material "
               "sentence must correspond to a claim; cite the claim id in brackets; never introduce a number "
               "or authority not present in the claims. Plain markdown.")
        user = json.dumps({"client": engagement.client, "credit": cr.credit, "elected": cr.elected,
                           "qre": cr.qre, "claims": graph}, default=str)
        try:
            return self.chat(sys, user)
        except Exception:
            return render_claim_graph(engagement, d, cr, qualified)   # fail safe → deterministic render


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


def _json_slice(s: str) -> str:
    i, j = s.find("{"), s.rfind("}")
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
    base = os.environ.get("FIRM_LLM_BASE_URL")
    key = os.environ.get("FIRM_LLM_API_KEY")
    model = os.environ.get("FIRM_LLM_MODEL", "kimi-k2.6")
    if base and key:
        return LLMProvider(_http_chat(base, key, model))
    return DeterministicProvider()


# ── claim-graph render (deterministic; also the LLM fail-safe) ────────────────────
def render_claim_graph(eng: Engagement, d: Deliverable, cr, qualified: list[str]) -> str:
    L = [f"# R&D Tax Credit Study (IRC §41) — {eng.client}", "",
         f"Engagement {eng.engagement_id} · fixed fee ${eng.price_usd:,.0f} · SLA {eng.sla_hours}h", "",
         "## Qualified activities"]
    for c in d.claims:
        if c.section in ("facts", "qualification"):
            L.append(f"- {c.assertion}  _[{c.claim_id} · {c.claim_type.value}]_")
    if d.escalations:
        L += ["", "## Held for CPA review (not included in the credit)"] + [f"- {e}" for e in d.escalations]
    L += ["", "## Authority"]
    for c in d.claims:
        if c.claim_type == ClaimType.AUTHORITY_INTERPRETATION:
            L.append(f"- {c.assertion}  _[{', '.join(a.authority for a in c.authority_refs)}]_")
    L += ["", "## Computation (deterministic; engines A and B agree)",
          f"- Qualified research expenses: **${cr.qre:,.0f}**",
          f"- ASC method: ${cr.asc:,.0f} · Regular method: ${cr.rrc:,.0f}",
          f"- **Credit claimed ({cr.elected}): ${cr.credit:,.0f}**  _[rd_credit · cross-checked]_", ""]
    return "\n".join(L)
