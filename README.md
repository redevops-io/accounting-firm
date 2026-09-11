# accounting-firm

An **AI-native accounting firm**, composed over the ReDevOps runtime stack. Multi-agent workflows draft
professional deliverables to a standard a licensed **CPA reviews and signs** — from messy client source
material, at a fixed price. The firm sells an **outcome**, not software.

This repo is the **composition layer**. The deterministic engines live in the runtimes
(`accounting-runtime`, `personal-tax-runtime`); evidence retrieval in `redevops-rag`; governance/HITL and the
durable ledger in `agentic-os`; retrieval/model optimization + learning in `context-runtime`. The
verticalization is here — the runtimes stay general. See
`~/Documents/AI_NATIVE_ACCOUNTING_FIRM_IMPLEMENTATION_PLAN.md`.

## The design rule

**Numbers are deterministic; judgment is structured; the model never concludes.** A real engine computes
every figure (and an independent second implementation cross-checks it); the model produces evidence-backed
per-criterion assessments; a **deterministic policy** derives conclusions; the deliverable is a **claim
graph** where every material sentence carries provenance; a CPA signs. AI makes the review fast and
defensible — it does not replace the CPA as the professional authority.

## Flagship milestone (implemented)

`python3 demo.py` — one synthetic company → one **§41 R&D credit study** → one CPA-reviewable deliverable,
on ugly inputs, offline. The full gate sequence, none of it stubbed on the deterministic/governance side:

```
messy docs → extract (+provenance) → reconcile → four-part test assessed per project
→ insufficient evidence escalated → QRE schedule → §41 credit  (engine A ↕ independent engine B)
→ claim graph → grounded study rendered → every number + assertion verified
→ CPA amend/approve/reject → signed artifact + hash-chained evidence bundle → CPA delta → LearningOutcome
```

The demo qualifies *Project Atlas*, **escalates** *Project Borealis* (insufficient four-part-test evidence),
computes a cross-checked **$43,400** credit (ASC), verifies all six claims, and records a signed,
hash-chained audit ledger.

## What is real vs. a seam

- **Real & deterministic:** the §41 engine + independent cross-check (`section41/`), the four-part
  **conclusion policy**, reconciliation, the **claim graph + verifier**, the governed pipeline, the
  append-only **evidence ledger**, and the CPA sign gate.
- **Seams (deterministic stand-ins today):** document **extraction** and per-criterion **assessment** and
  **drafting** are the LLM insertion points — implemented as deterministic parsers/fixtures for the demo so
  it runs offline. In production these become Context-Runtime model calls behind the same signatures; nothing
  else changes.
- **Runtime integration points:** ledger → `agentic-os` DuckDB/Postgres event ledger; retrieval → `redevops-rag`;
  CPA-amendment learning → `context-runtime` (AI layer only — never the tax rules).

## Run

```
python3 demo.py                 # the flagship milestone
python3 tests/test_section41.py # deterministic §41 core (engines agree)
python3 tests/test_pipeline.py  # the end-to-end gate sequence
```

## Not yet (hard, fail-closed gates before any real client deliverable)

Licensure of the signing CPA + PTIN/EFIN; E&O/malpractice cover; SOC 2 + PII/retention; e-file/MeF where
applicable; state practice rules. AGPL-3.0.
