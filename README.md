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

## Two deliverables, one runtime (genericity)

A second deliverable — an **ASC 606 technical accounting memo** (`deliverables/tech_accounting_memo.py`) —
runs through the *same* shared loop (`mission.finalize`) and the *same* reconcile / claims / verify / ledger /
provider machinery as the §41 study. A new deliverable is a new module: its own extraction, deterministic
calc (with an A/B cross-check), and criteria — **no change to the core loop**.

## What is real vs. a seam

- **Real & deterministic:** the §41 engine + independent cross-check (`section41/`), the ASC 606 recognition
  schedule + cross-check, the four-part / policy **conclusions**, reconciliation, the **claim graph +
  verifier**, the shared governed loop (`mission.py`), the append-only **evidence ledger**, and the CPA sign gate.
- **The model seam (`providers.py`):** per-criterion **assessment** and **drafting** go through a `Provider`.
  `DeterministicProvider` is the offline default (demo/tests); `LLMProvider` (OpenAI-compatible, `FIRM_LLM_*`)
  does real judgment/drafting — even then it fills PASS/FAIL/INSUFFICIENT per criterion and a deterministic
  policy concludes. Unstructured extraction also routes through the provider (`provider.extract`) with a
  deterministic-parser fallback; broad OCR / multi-format ingestion is the remaining Phase-3 breadth.
- **Runtime backends (wired, env-gated, offline default):** grounding → `redevops-rag` Store
  (`FIRM_CORPUS=rag` + `FIRM_RAG_DB`); durable ledger → `agentic-os` DuckDB/Postgres event ledger
  (`FIRM_LEDGER=agentic-os`); model → `FIRM_LLM_*`. CPA-amendment learning → `context-runtime` (AI layer
  only — never the tax rules).

## Run

```
python3 demo.py                 # flagship: §41 R&D credit study
python3 demo_memo.py            # second deliverable: ASC 606 memo (same runtime)
python3 tests/test_section41.py # deterministic §41 core (engines agree)
python3 tests/test_pipeline.py  # §41 end-to-end gate sequence
python3 tests/test_providers.py # the model seam (stubbed, no network)
python3 tests/test_memo.py      # the second deliverable
```

## Not yet (hard, fail-closed gates before any real client deliverable)

Licensure of the signing CPA + PTIN/EFIN; E&O/malpractice cover; SOC 2 + PII/retention; e-file/MeF where
applicable; state practice rules. AGPL-3.0.
