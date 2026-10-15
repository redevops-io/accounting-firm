# Status

- **Maturity:** simulation-only
- **Version:** pyproject 0.0.1; git tag v0.1.0 (per org listing)
- **Last git activity on the default branch:** 2026-10-14 (from `git log -1 --format=%cs`; the working clone is shallow)

## What is supported
- python3 demo.py: offline synthetic §41 R&D credit study and ASC 606 memo demo
- Local tests listed in README Run section; CI in .github/workflows/tests.yml
- Env-gated backends (redevops-rag grounding, agentic-os ledger, OpenAI-compatible model) as wiring, not verified here

## What is not supported / not claimed
- Not a service offer; no real client work, no licensed CPA, PTIN/EFIN, E&O cover, SOC 2, e-file/MeF or state practice compliance (README 'Not yet')
- Sibling runtimes accounting-runtime and personal-tax-runtime are not in the org's public repos
- Authority corpus not in repo; grounding against real IRC §41 / ASC 606 text is not reproducible here
- $43,400 is synthetic demo output

## Known issues
- GitHub repo description was empty at audit time (proposed text in PR)
- pyproject version 0.0.1 vs tag v0.1.0
- Regulated-services wording is a counsel item

No quantitative claim in this repo has been externally reproduced or field validated.
