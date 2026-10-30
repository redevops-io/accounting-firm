"""Static invariants of the Kubernetes image (deploy/aks/Dockerfile) and of the workflow that publishes it. No Docker needed.

The built image is checked by deploy/aks/scan_image.py (run by the workflow before and after the push). Pinned here: the base
image is pinned by digest; the image is non-root with a HEALTHCHECK; nothing secret-shaped is baked in; the kernel pin agrees
with pyproject.toml and the compose Dockerfile; the build context is deny-by-default; and the workflow starts only from a
version tag or a manual dispatch, writes only the immutable version tag, signs by digest and attaches SBOM + provenance.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCKERFILE = (REPO / "deploy" / "aks" / "Dockerfile").read_text()
IGNORE = (REPO / "deploy" / "aks" / "Dockerfile.dockerignore").read_text()
WF = (REPO / ".github" / "workflows" / "build-image.yml").read_text()
SECRET_SHAPED = re.compile(r"(SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY|PRIVATE_?KEY|CREDENTIAL|_KEY$|_B64$)", re.I)


def _lines(text: str) -> list[str]:
    out, cur = [], ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.endswith("\\"):
            cur += s[:-1] + " "
            continue
        out.append((cur + s).strip())
        cur = ""
    return out


def test_base_image_is_pinned_by_digest_and_nothing_floats():
    m = re.search(r"^ARG PYTHON_IMAGE=(\S+)$", DOCKERFILE, re.M)
    assert m and re.search(r"@sha256:[0-9a-f]{64}$", m.group(1))
    for ln in _lines(DOCKERFILE):
        f = re.match(r"FROM\s+(\S+)", ln, re.I)
        if f:
            assert f.group(1).startswith("${PYTHON_IMAGE}") or f.group(1) in {"venv"}, f.group(1)
    assert ":latest" not in DOCKERFILE


def test_image_is_nonroot_has_a_healthcheck_and_a_data_path():
    final = DOCKERFILE.split("FROM ${PYTHON_IMAGE}\n")[-1]
    users = re.findall(r"^USER\s+(\S+)$", final, re.M)
    assert users and re.fullmatch(r"[1-9][0-9]*(:[1-9][0-9]*)?", users[-1])
    assert re.search(r"^HEALTHCHECK\b(?!.*NONE)", final, re.M)
    assert "/data/ledger" in DOCKERFILE and "MISSION_EVENT_PATH=/data/ledger/events.jsonl" in DOCKERFILE
    assert "network_mode" not in DOCKERFILE and "privileged" not in DOCKERFILE.lower()


def test_nothing_secret_shaped_or_credential_like_is_baked_in():
    for ln in _lines(DOCKERFILE):
        m = re.match(r"(ENV|ARG)\s+(.*)$", ln, re.I)
        if m:
            for n in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=", m.group(2)) or [m.group(2).split()[0]]:
                assert not SECRET_SHAPED.search(n), n
        if ln.upper().startswith(("COPY", "ADD")):
            assert not re.search(r"\.env\b|\.pem\b|\.key\b|credentials|id_rsa", ln), ln
            assert not ln.upper().startswith("ADD "), ln
    assert "FIRM_LLM_BASE_URL" not in DOCKERFILE          # no model endpoint is configured in the image


def test_kernel_pin_agrees_with_pyproject_and_the_compose_dockerfile():
    pins = set(re.findall(r"agentic-os\.git@(v[0-9.]+)", (REPO / "pyproject.toml").read_text()))
    pins |= set(re.findall(r"agentic-os\.git@(v[0-9.]+)", (REPO / "accounting_firm" / "console" / "Dockerfile.runtime").read_text()))
    aks = re.search(r"^ARG AGENTIC_OS_REF=(v[0-9.]+)$", DOCKERFILE, re.M).group(1)
    assert pins == {aks}, f"kernel pins disagree: {pins} vs {aks}"


def test_build_context_is_deny_by_default():
    lines = [ln.strip() for ln in IGNORE.splitlines() if ln.strip() and not ln.startswith("#")]
    assert lines[0] == "*"
    for needed in ("!accounting_firm", "!demo_data", "**/.env", "**/*.pem", "**/*.key"):
        assert needed in lines, needed
    for src in re.findall(r"^COPY (?:--from=\S+ )?(\S+) ", DOCKERFILE, re.M):
        if not src.startswith("/"):
            assert any(ln.startswith("!") and src.rstrip("/").startswith(ln[1:]) for ln in lines), f"{src} not allowed through the filter"


def test_workflow_starts_only_from_a_version_tag_or_a_manual_run():
    on_block = WF.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert re.findall(r"^  (\w+):", on_block, re.M) == ["push", "workflow_dispatch"]
    assert '"v[0-9]+.[0-9]+.[0-9]+"' in on_block and "branches" not in on_block and "pull_request" not in on_block
    assert re.search(r"publish:\n(?:.*\n)*?\s+default: false", on_block)


def test_tag_policy_and_signing():
    for ln in WF.splitlines():
        if re.match(r"^\s*tags:\s*\S", ln):
            assert "latest" not in ln and "stable" not in ln and "github.sha" not in ln, ln
    assert "Version tags are immutable" in WF and "already exists" in WF
    assert "provenance: mode=max" in WF and "sbom: true" in WF
    assert 'cosign sign --yes "$REGISTRY/$IMAGE_NAME@$DIGEST"' in WF
    assert "cosign attest --yes --type spdxjson" in WF and "cosign verify-attestation" in WF
    assert "id-token: write" in WF and WF.count("id-token: write") == 1       # only the build job, not the workflow
    # the publish steps are all conditional on PUBLISH; the scan runs before the push
    assert WF.index("scan_image.py \"$IMAGE_NAME:ci\"") < WF.index("Build and push")
    for name in ("Log in to GHCR", "Build and push", "Sign the image by digest", "Attest the SBOM"):
        block = WF.split(f"- name: {name}", 1)[1].split("- name:", 1)[0]
        assert "if: env.PUBLISH == 'true'" in block, name
