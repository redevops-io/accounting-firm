"""Runtime-native seams (N6 grounding + N7 governed model). These require the kernel (agentic_os) on the
path; they skip cleanly when it is absent, so the offline demo/test lane stays green."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounting_firm import corpus, providers, resolvers

kernel = pytest.importorskip("agentic_os.app.llm")   # skips the whole module without the kernel


def test_governed_provider_selected(monkeypatch):
    """FIRM_LLM_GOVERNED=1 selects the LLMProvider backed by the governed chat_fn."""
    monkeypatch.setenv("FIRM_LLM_GOVERNED", "1")
    monkeypatch.setenv("REDEVOPS_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    p = providers.select_provider()
    assert p.name == "llm"


def test_governed_route_is_in_boundary_and_receipted():
    """Customer-confidential accounting evidence routes to an in-boundary endpoint with a receipt, and an
    external route is refused (fail-closed) — the N7 boundary."""
    from agentic_os.app.llm import GovernedLLM
    from agentic_os.app.transports import OpenAICompatibleTransport
    from agentic_os.governance.classification import DataClassification
    from agentic_os.governance.routing import ExecutionBoundary, ModelEndpoint, RoutingRefused, TaskClass

    internal = ModelEndpoint(model_id="firm", provider="self-hosted",
                             boundary=ExecutionBoundary.IN_BOUNDARY,
                             accepts=DataClassification.CUSTOMER_CONFIDENTIAL, network_route="http://x/v1")
    gov = GovernedLLM.from_env(endpoints=(internal,), transport=OpenAICompatibleTransport.from_env())
    routed = gov.route_only("draft", task_class=TaskClass.BUSINESS_REASONING,
                            classifications=(DataClassification.CUSTOMER_CONFIDENTIAL,))
    assert routed.endpoint.boundary is ExecutionBoundary.IN_BOUNDARY
    assert routed.receipt is not None

    # only an EXTERNAL endpoint, strict-private mode → no compliant route → refuse.
    ext = ModelEndpoint(model_id="frontier", provider="anthropic",
                        boundary=ExecutionBoundary.EXTERNAL, accepts=DataClassification.SECRET,
                        network_route="https://api.anthropic.com")
    strict = GovernedLLM.from_env(endpoints=(ext,), transport=OpenAICompatibleTransport.from_env())
    with pytest.raises(RoutingRefused):
        strict.route_only("draft", task_class=TaskClass.BUSINESS_REASONING,
                          classifications=(DataClassification.CUSTOMER_CONFIDENTIAL,))


def test_context_resolver_grounds_through_context_runtime(monkeypatch):
    """FIRM_CORPUS=context resolves authorities through GroundedContext (the Context Runtime door), matching
    the exact-lookup baseline over the curated corpus."""
    monkeypatch.setenv("FIRM_CORPUS", "context")
    monkeypatch.delenv("FIRM_RAG_DB", raising=False)
    r = resolvers.select_resolver()
    assert r.name == "context"
    for aid in list(corpus.CORPUS)[:6]:
        assert r.resolve(aid)[0], f"{aid} should resolve through the Context Runtime"
    assert not r.resolve("IRC §999(z)", ("fabricated",))[0]        # fabricated authority still rejected
