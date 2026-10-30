# CPA review console (the accounting public showcase), runtime-native, built for Kubernetes.
#
# Differences from accounting_firm/console/Dockerfile.runtime (which keeps serving the compose file unchanged):
#   * the base image is pinned BY DIGEST;
#   * non-root (uid/gid 10001); the code tree is root-owned and read-only at runtime, so the container runs with
#     readOnlyRootFilesystem and PSA `restricted`;
#   * git exists only in the build stage; the kernel is installed into /opt/venv and the venv is copied;
#   * it needs NO host networking, NO seccomp/AppArmor opt-out and NO privileges: it is a stdlib HTTP server on 8108;
#   * a HEALTHCHECK, and a documented data path: the durable event ledger is /data/ledger/events.jsonl, owned by 10001.
#     Mount a volume at /data/ledger (a 1 GiB PVC with fsGroup 10001 on Kubernetes). /tmp must also be writable
#     (emptyDir); nothing else is written.
#   * nothing deployment-specific or secret-shaped is baked in. The ENV values below are the runtime-native defaults the
#     compose file already used (ledger path, corpus mode, privacy mode) and the listening address. No credential, no model URL.
#
# Build (repo root as context):
#     docker build -f deploy/aks/Dockerfile -t accounting-console:local .
ARG PYTHON_IMAGE=python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

FROM ${PYTHON_IMAGE} AS venv
# The kernel pin: keep in step with pyproject.toml [kernel]/[runtime] and accounting_firm/console/Dockerfile.runtime
# (tests/test_aks_image.py checks that they agree).
ARG AGENTIC_OS_REF=v0.3.38
RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir "agentic-os @ git+https://github.com/redevops-io/agentic-os.git@${AGENTIC_OS_REF}"

FROM ${PYTHON_IMAGE}
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app \
 && mkdir -p /data/ledger && chown -R 10001:10001 /data
WORKDIR /app
COPY --from=venv /opt/venv /opt/venv
COPY accounting_firm/ ./accounting_firm/
COPY demo_data/ ./demo_data/
COPY LICENSE /licenses/LICENSE
COPY deploy/aks/healthcheck.py /opt/healthcheck.py
RUN python -m compileall -q /app

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    FIRM_CONSOLE_HOST=0.0.0.0 \
    FIRM_CONSOLE_PORT=8108 \
    FIRM_CONSOLE_BASE=/accounting \
    FIRM_LEDGER=agentic-os \
    MISSION_EVENT_BACKEND=jsonl \
    MISSION_EVENT_PATH=/data/ledger/events.jsonl \
    FIRM_CORPUS=context \
    REDEVOPS_PRIVACY_MODE=strict_private

LABEL org.opencontainers.image.title="accounting-console" \
      org.opencontainers.image.source="https://github.com/redevops-io/accounting-firm" \
      org.opencontainers.image.vendor="RedevOps"
VOLUME ["/data/ledger"]
EXPOSE 8108
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["python", "/opt/healthcheck.py"]
CMD ["python", "-m", "accounting_firm.console"]
