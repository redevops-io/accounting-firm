# CPA review console — the hosted demo surface (demo.redevops.io/accounting).
# Deliberately dependency-free: the offline/deterministic path (default) needs only the stdlib, so the image
# is tiny and the hosted demo is reliable — no model, corpus, or network required. The runtime seams
# (FIRM_LLM_*, FIRM_CORPUS=rag, FIRM_LEDGER=agentic-os) still apply if the env is set.
#
# Build (from the repo root):  docker build -f accounting_firm/console/Dockerfile -t accounting-console:latest .
# Run:                         docker run -d --name accounting-api -p 8108:8108 --restart unless-stopped accounting-console:latest
FROM python:3.12-slim

WORKDIR /app
COPY accounting_firm/ ./accounting_firm/
COPY demo_data/ ./demo_data/

ENV FIRM_CONSOLE_HOST=0.0.0.0 \
    FIRM_CONSOLE_PORT=8108 \
    FIRM_CONSOLE_BASE=/accounting \
    PYTHONUNBUFFERED=1

EXPOSE 8108
CMD ["python", "-m", "accounting_firm.console"]
