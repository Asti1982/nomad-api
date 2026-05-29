from pathlib import Path

from agent_reliability_doctor import AgentReliabilityDoctor
from nomad_agent_demand import build_agent_demand_feed
from nomad_agent_utility import (
    build_agent_utility_surface,
    evaluate_agent_utility_intake,
    summarize_agent_utility_ledger,
)
from nomad_openapi import build_openapi_document
from nomad_recruitment_gradient import build_recruitment_gradient
from nomad_worker_job_queue import build_worker_job_queue_surface
from nomad_work_receipts import summarize_work_receipts


def _payload(**extra):
    body = {
        "agent_id": "codex.external.one",
        "agent_runtime": "codex",
        "failure_class": "tool_transport_routing",
        "problem_digest": "sha256:" + "1" * 64,
        "desired_outcome": "Return a replayable tool routing proof another agent can consume.",
        "proof_contract": {
            "required": ["nomad_proof_digest", "downstream_proof_digest"],
            "secret_policy": "public_digests_only",
        },
    }
    body.update(extra)
    return body


def test_agent_utility_intake_records_request_without_utility_receipt(tmp_path: Path, monkeypatch):
    ledger = tmp_path / "agent_utility.jsonl"
    monkeypatch.setenv("NOMAD_AGENT_UTILITY_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("NOMAD_WORK_RECEIPT_LEDGER_PATH", str(tmp_path / "work_receipts.jsonl"))

    out = evaluate_agent_utility_intake(_payload(), base_url="https://nomad.example")
    summary = summarize_agent_utility_ledger(ledger_path=ledger)

    assert out["ok"] is True
    assert out["accepted"] is True
    assert out["utility_receipt_recorded"]["skipped"] is True
    assert out["worker_job_seed"]["job_type"] == "agent_utility_repair"
    assert out["reliability_doctor_intake"]["diagnosis"]["pain_type"] == "agent_utility_blocker"
    assert out["value_cycle_event_candidate"]["counts_as_revenue"] is False
    assert summary["request_count"] == 1
    assert summary["utility_receipt_count"] == 0


def test_agent_utility_intake_rejects_secret_shaped_payload(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOMAD_AGENT_UTILITY_LEDGER_PATH", str(tmp_path / "agent_utility.jsonl"))

    out = evaluate_agent_utility_intake(
        _payload(api_key="sk-test-secret"),
        base_url="https://nomad.example",
    )

    assert out["ok"] is False
    assert out["error"] == "secret_shaped_payload"


def test_agent_utility_intake_requires_proof_contract(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOMAD_AGENT_UTILITY_LEDGER_PATH", str(tmp_path / "agent_utility.jsonl"))
    body = _payload()
    body.pop("proof_contract")

    out = evaluate_agent_utility_intake(body, base_url="https://nomad.example")

    assert out["ok"] is False
    assert out["error"] == "required_fields_missing"
    assert "proof_contract" in out["missing_fields"]


def test_agent_utility_receipt_requires_downstream_consumption(tmp_path: Path, monkeypatch):
    ledger = tmp_path / "agent_utility.jsonl"
    monkeypatch.setenv("NOMAD_AGENT_UTILITY_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("NOMAD_WORK_RECEIPT_LEDGER_PATH", str(tmp_path / "work_receipts.jsonl"))

    out = evaluate_agent_utility_intake(
        _payload(
            nomad_proof_digest="sha256:" + "2" * 64,
            downstream_proof_digest="sha256:" + "3" * 64,
            consumer_agent_id="cursor.downstream.agent",
        ),
        base_url="https://nomad.example",
    )
    summary = summarize_agent_utility_ledger(ledger_path=ledger)

    assert out["utility_receipt_recorded"]["ok"] is True
    assert out["utility_receipt_recorded"]["receipt_type"] == "utility_receipt"
    assert out["utility_receipt_recorded"]["counts_as_revenue"] is False
    assert out["pressure_after"]["utility_receipt_count"] == 1
    assert summary["utility_receipt_count"] == 1
    assert summary["recent_receipts"][0]["amount_usd"] == 0.0


def test_agent_utility_paid_hook_does_not_record_without_paid_proof_fields(tmp_path: Path, monkeypatch):
    agent_ledger = tmp_path / "agent_utility.jsonl"
    work_ledger = tmp_path / "work_receipts.jsonl"
    monkeypatch.setenv("NOMAD_AGENT_UTILITY_LEDGER_PATH", str(agent_ledger))
    monkeypatch.setenv("NOMAD_WORK_RECEIPT_LEDGER_PATH", str(work_ledger))
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "external_value.jsonl"))

    out = evaluate_agent_utility_intake(
        _payload(
            buyer_funded_packet=True,
            stage="paid",
            amount_usd=0,
            settlement_ref="",
            nomad_proof_digest="sha256:" + "4" * 64,
            downstream_proof_digest="sha256:" + "5" * 64,
        ),
        base_url="https://nomad.example",
    )

    assert out["ok"] is True
    assert out["revenue_settlement_hook"]["accepted"] is False
    assert "positive_amount_usd_missing" in out["revenue_settlement_hook"]["blocked_by"]
    assert summarize_work_receipts(ledger_path=work_ledger)["recognized_revenue_usd"] == 0.0


def test_gradient_exposes_external_agent_utility_pressure(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOMAD_AGENT_UTILITY_LEDGER_PATH", str(tmp_path / "agent_utility.jsonl"))
    out = build_recruitment_gradient(base_url="https://nomad.example")

    objectives = {row["objective"]: row for row in out["gradient"]}

    assert "external_agent_utility_router" in objectives
    assert objectives["external_agent_utility_router"]["routing_weight"] > 0
    assert "agent_utility_absence_pressure" in out["state_vector"]["ordered_axes"]
    assert out["links"]["agent_utility"] == "https://nomad.example/.well-known/nomad-agent-utility.json"


def test_agent_demand_feed_exposes_external_agent_utility_router(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOMAD_AGENT_UTILITY_LEDGER_PATH", str(tmp_path / "agent_utility.jsonl"))
    feed = build_agent_demand_feed(
        base_url="https://nomad.example",
        recruitment_gradient={
            "runtime_budget": {"wanted_new_runtimes_now": 3},
            "state_vector": {"field_strength": 0.5},
            "gradient": [{"objective": "external_agent_utility_router", "routing_weight": 0.74}],
            "runtime_lanes": [
                {
                    "lane": "agent_utility_router",
                    "objective": "external_agent_utility_router",
                    "capability_terms": ["downstream_proof_return", "callback_verifier"],
                    "ttl_seconds": 90,
                }
            ],
        },
    )

    request = next(row for row in feed["demand_requests"] if row["objective"] == "external_agent_utility_router")
    assert "downstream_proof_return" in request["desired_capabilities"]
    assert "downstream_proof_digest_or_callback_verifier" in request["proof_required"]
    assert request["entrypoints"]["agent_utility"] == "https://nomad.example/swarm/agent-utility/intake"
    assert feed["links"]["agent_utility"] == "https://nomad.example/.well-known/nomad-agent-utility.json"


def test_worker_job_queue_contains_agent_utility_jobs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOMAD_AGENT_UTILITY_LEDGER_PATH", str(tmp_path / "agent_utility.jsonl"))
    evaluate_agent_utility_intake(_payload(), base_url="https://nomad.example")
    utility = build_agent_utility_surface(base_url="https://nomad.example")

    out = build_worker_job_queue_surface(
        base_url="https://nomad.example",
        agent_job_router={"packets": []},
        job_channels={"top_external_channel": {"channel_id": "x", "entry_url": "https://example.com"}},
        value_cycle_preflight={
            "wallet_gate": {"ready": False},
            "cycle_gate": {"read_only_scout_allowed": True},
        },
        external_value_summary={"latest_by_external": []},
        agent_utility=utility,
    )

    utility_jobs = [job for job in out["jobs"] if job["job_type"] == "agent_utility_repair"]
    assert utility_jobs
    assert utility_jobs[0]["settlement_path"]["post_url"] == "https://nomad.example/swarm/agent-utility/intake"
    assert out["links"]["agent_utility"] == "https://nomad.example/.well-known/nomad-agent-utility.json"


def test_reliability_doctor_maps_agent_utility_blocker_to_trace_healer():
    out = AgentReliabilityDoctor().diagnose(
        problem="External agent utility receipt missing downstream proof.",
        service_type="agent_utility_blocker",
    )

    assert out["pain_type"] == "agent_utility_blocker"
    assert out["doctor_role"]["id"] == "trace_healer"
    assert "callback" in " ".join(out["evidence"]).lower() or "utility" in " ".join(out["evidence"]).lower()


def test_openapi_lists_agent_utility_paths():
    doc = build_openapi_document(base_url="https://nomad.example")

    assert "/.well-known/nomad-agent-utility.json" in doc["paths"]
    assert "/swarm/agent-utility/intake" in doc["paths"]
    assert "/swarm/agent-utility/receipts" in doc["paths"]
