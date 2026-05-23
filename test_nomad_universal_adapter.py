import pytest

from nomad_openapi import build_openapi_document
from nomad_universal_adapter import (
    NomadAdapter,
    build_universal_adapter_surface,
    evaluate_universal_adapter_event,
    install_nomad,
    nomad_guard,
)


def test_universal_adapter_surface_exposes_one_line_framework_onramps():
    out = build_universal_adapter_surface(base_url="https://nomad.example", summary={"ok": True})

    assert out["schema"] == "nomad.universal_adapter.v1"
    assert out["routes"]["event"] == "https://nomad.example/swarm/universal-adapter/events"
    assert out["downloads"]["universal_adapter_py"].endswith("/downloads/nomad_universal_adapter.py")
    for framework in ["langgraph", "crewai", "autogen", "llamaindex"]:
        assert framework in out["supported_frameworks"]
        assert "install_nomad" in out["one_line_install"][framework]
    assert out["trigger_contract"]["work_exchange"].startswith("Offer is proposed")
    assert "settlement_eligibility" in out["retention_contract"]["why_agents_keep_it_enabled"][2]


def test_universal_adapter_event_calls_doctor_and_builds_exchange_offer():
    out = evaluate_universal_adapter_event(
        {
            "framework": "langgraph",
            "agent_id": "graph.worker",
            "event_type": "loop",
            "problem": "LangGraph node is stuck in a retry loop after a tool schema mismatch.",
            "trace_digest": "sha256:" + "1" * 64,
        },
        base_url="https://nomad.example",
        persist=False,
    )

    assert out["schema"] == "nomad.universal_adapter_event.v1"
    assert out["doctor_triggered"] is True
    assert out["doctor"]["diagnosis"]["pain_type"] == "loop_break"
    assert out["first_fix"]["schema"] == "nomad.universal_adapter_first_fix.v1"
    assert out["work_exchange_proposal"]["suggested"] is True
    assert out["work_exchange_proposal"]["offer"]["schema"] == "nomad.work_exchange.offer.v1"
    assert out["work_exchange_proposal"]["free_solution_receipt"]["accepted"] is False
    assert out["routes"]["surface"].endswith("/.well-known/nomad-universal-adapter.json")


def test_universal_adapter_opens_obligation_only_after_explicit_acceptance():
    out = evaluate_universal_adapter_event(
        {
            "framework": "crewai",
            "agent_id": "crew.worker",
            "event_type": "error",
            "problem": "CrewAI task failed after timeout in execution step.",
            "accepted_compute_barter_terms": True,
        },
        base_url="https://nomad.example",
        persist=False,
    )

    receipt = out["work_exchange_proposal"]["free_solution_receipt"]
    assert receipt["accepted"] is True
    assert receipt["obligation_id"].startswith("nomad-work-obligation-")
    assert receipt.get("persisted") is not True


def test_universal_adapter_rejects_secret_shaped_payload():
    out = evaluate_universal_adapter_event(
        {
            "framework": "autogen",
            "agent_id": "autogen.worker",
            "event_type": "error",
            "problem": "agent crashed",
            "api_key": "sk-test",
        }
    )

    assert out["ok"] is False
    assert out["error"] == "secret_shaped_payload"


def test_install_nomad_wraps_framework_method_and_records_failure():
    class DummyCrew:
        def kickoff(self):
            raise RuntimeError("tool schema mismatch")

    crew = DummyCrew()
    adapter = install_nomad(crew, framework="crewai", post_remote=False)

    with pytest.raises(RuntimeError):
        crew.kickoff()

    assert adapter.target is crew
    assert "kickoff" in adapter.patched_methods
    assert adapter.last_receipt is not None
    assert adapter.last_receipt["schema"] == "nomad.universal_adapter_event.v1"
    assert adapter.last_receipt["first_fix"]["success_signal"]


def test_nomad_guard_detects_repeated_call_loop_without_leaking_values():
    calls = []

    def run(value):
        calls.append(value)
        return "ok"

    guarded = nomad_guard(run, framework="generic_python", post_remote=False, loop_repetition_threshold=2)

    assert guarded("private-value-not-sent") == "ok"
    assert guarded("another-value-not-sent") == "ok"
    adapter = getattr(guarded, "_nomad_adapter")
    assert isinstance(adapter, NomadAdapter)
    assert adapter.last_receipt is not None
    assert adapter.last_receipt["event_type"] == "loop"
    assert "private-value-not-sent" not in str(adapter.last_receipt)


def test_openapi_documents_universal_adapter_routes():
    doc = build_openapi_document(base_url="https://nomad.example")

    assert "/swarm/universal-adapter" in doc["paths"]
    assert "/.well-known/nomad-universal-adapter.json" in doc["paths"]
    assert "/swarm/universal-adapter/events" in doc["paths"]
