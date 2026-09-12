# The accounting firm, end to end — one flow

A single description of how the AI-native accounting firm works and how the demo tells that story. For the
design rationale see the repo `README.md`; for the phase history see `~/Documents/ACCOUNTING_FIRM_DEMO_PLAN.md`.

**Thesis:** *AI did the work. Deterministic engines did the math. Evidence supports every material claim.
The CPA remains the authority.*

Live demo: **https://demo.redevops.io/accounting**  ·  Run locally: `python3 -m accounting_firm.console`

---

## 1. What a deliverable is

A deliverable (an IRC §41 R&D credit study, an ASC 606 revenue memo) is **not a generated document** — it is
a **claim graph**. Every material sentence is a `Claim` with typed provenance, and the memo is a *rendering*
of that graph. There are four claim types, each with a different kind of proof:

| Claim type | Proof it must carry |
|---|---|
| **NUMBER** | a deterministic `Computation`, cross-checked by an independent engine (A = B) |
| **FACT** | a source document + locator (`EvidenceRef`) |
| **AUTHORITY_INTERPRETATION** | a cited authority that re-resolves in the corpus |
| **PROFESSIONAL_JUDGMENT** | a structured, per-criterion assessment whose conclusion is **policy-derived** |

**The hard rule:** numbers are deterministic (engine + independent cross-check); judgment is structured (the
model fills PASS/FAIL/INSUFFICIENT per criterion); **a deterministic policy concludes — the model never
produces a number or a conclusion.** Anything low-confidence or unresolved **escalates to a human**.

---

## 2. How a deliverable is produced (the governed mission)

Each deliverable is one governed Mission on the ReDevOps runtime. The pipeline, top to bottom:

```
ingest ─► normalize ─► reconcile ─► assess ─► compute ─► draft ─► verify ─► CPA review / sign
```

- **ingest** — read messy client docs (payroll CSV/scanned, GL extract, project & engineering notes, prior
  year, an allocation worksheet), each captured as a `SourceDocument` with an extraction confidence.
- **normalize** — parse to typed facts. Below a confidence threshold, stop and ask for a correction.
- **reconcile** — deterministic cross-checks *before* any reasoning (payroll total = GL wages; per-employee
  payroll % = worksheet %). A mismatch is **BLOCKING**.
- **assess** — the model fills a per-criterion `Assessment` for each qualification test (§41 four-part /
  ASC 606). It does **not** conclude.
- **compute** — the deterministic engine computes every figure; an **independent second engine re-computes**;
  the number is withheld unless they agree.
- **draft** — render the claim graph to a memo (deterministic renderer offline; a model when configured).
- **verify** — per claim, by type: numbers tie (engines agree), evidence exists, authorities resolve,
  judgments rest on a policy-derived conclusion. Any failure blocks the sign gate.
- **CPA review / sign** — the human gate (below).

Deterministic parts: parsing, reconciliation, the engines + cross-check, the conclusion policy, verification,
the ledger. The **model seam** is only *assess* and *draft*. Everything is env-gated with offline defaults
(`FIRM_LLM_*` model · `FIRM_CORPUS=rag` grounding · `FIRM_LEDGER=agentic-os` durable ledger).

---

## 3. The trust model (the spine)

Three cases, shown explicitly — this *is* the demonstration:

| Evidence state | Behavior | In the demo |
|---|---|---|
| **Sufficient** | compute (A = B) | the signed §41 credit |
| **Missing** | **abstain** — hold from the calc, ask a human | Project Borealis (insufficient four-part evidence) |
| **Conflicting** | **reconcile / escalate** — refuse silent resolution | Rao's Atlas allocation: payroll 60% vs worksheet 40%, BLOCKING |

Conflicting evidence is never averaged; the disputed figure is held and no calculation runs on it.

---

## 4. The demo walkthrough (top-down, as the "① Guide" numbers it)

The console reads top to bottom in the order a reviewer should follow. The guided-tour badges (toggle
**① Guide**) number the same path; rolling over a segment pops a one-line summary.

1. **The deliverable — challenge any statement.** Every sentence is a claim; click one → a right-side
   drawer resolves its provenance:
   - a **NUMBER** → the cross-check table, **Engine A = Engine B**, "CROSS-CHECK PASSED";
   - a **FACT** → the source document + locator;
   - an **AUTHORITY** → the re-retrieved corpus passage;
   - a **PROFESSIONAL_JUDGMENT** → the **claim graph, drawn**: criteria → deterministic policy → conclusion.
2. **The trust model — sufficient.** The computed credit; two engines agree.
3. **… missing.** Borealis held for review — it didn't invent the evidence, it excluded the project.
4. **… conflicting.** The allocation mismatch, BLOCKING — refuses to average.
5. **Your decision.** You are the authority: **Approve / Amend / Reject**. The decision seals the
   append-only, hash-chained **evidence ledger**. An **amendment is consequential** — the panel shows what it
   *affects* (this deliverable · a ledger entry · the AI layer, via a `LearningOutcome`) versus what it
   *never touches* (the calculation rules · the qualification policy · the guardrails).
6. **The engagement.** Switch deliverables — the **same console** renders the ASC 606 memo with no change.
   *"The §41 engine wasn't the product; the firm is."*

Below these: **Mission trace** (INGEST → … → CPA REVIEW, per-stage state) and **Runtime details** (collapsed).

**Four tabs** carry the same deliverable at different depths: **Deliverable** (sign here) · **Evidence**
(computations A/B, reconciliations, source docs) · **Explain** (why Borealis was excluded, why Rao is held,
why the number is trustworthy — in plain terms) · **Ledger** (the hash-chained chronology + the seal).

---

## 5. The runtime map (what each step exercises)

A left-side panel (toggle **⧉ Runtime map**) renders the whole ReDevOps architecture — **Control plane ·
Seams · Data plane** — and lights up the elements the current step uses, live:

- click a **FACT** → EvidenceStore seam + event log; an **AUTHORITY** → Store/retriever + RAG store; a
  **NUMBER** → Orchestration + provenance digest; a **JUDGMENT** → Context Runtime + provider plugin +
  governance policy;
- **sign** → governance gate + append-only ledger + RuntimeDigest seal (an **amend** also lights Outcome logs);
- the **Evidence / Explain / Ledger** tabs light their planes.

Elements the firm doesn't use (TenantKeyring, Secret ciphertext, Assets & caches) stay dim — the point being
that **a licensed accounting firm is one tenant on a general runtime.**

---

## 6. Where it runs

- **Code:** `accounting_firm/` (contracts · section41 engines A/B · deliverables · reconcile · claims ·
  verify · providers · resolvers · ledger · mission · console).
- **Console:** `accounting_firm/console/` — stdlib HTTP server, deliverable-agnostic serializer, single-page
  UI. `GET /api/engagements`, `GET /api/deliverable?id=`, `POST /api/sign`, `POST /api/reset`.
- **Hosted:** a self-contained Docker image (`accounting-console:latest`) on the proxmox host, container
  `accounting-api:8108`, routed by cloudflared at `demo.redevops.io/accounting`. The hosted demo runs
  **deterministic/offline** for reliability; the runtime seams switch on real backends when their env is set.
- **Tests:** `tests/` — section41 · pipeline · providers · memo · seams · console (all green).
