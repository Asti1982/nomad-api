from nomad_openapi import build_openapi_document
from nomad_work_exchange import (
    build_external_worker_opportunity,
    build_work_exchange_onboarding,
    build_work_exchange_surface,
    create_work_exchange_offer,
    record_free_solution_receipt,
    record_return_work_receipt,
    summarize_work_exchange_ledger,
    work_exchange_balance,
)


def test_work_exchange_surface_is_token_free_and_discoverable():
    out = build_work_exchange_surface(base_url="https://nomad.example", summary={"ok": True})

    assert out["schema"] == "nomad.work_exchange.v1"
    assert out["unit"]["not_a_token"] is True
    assert out["default_policy"]["hidden_fee_allowed"] is False
    assert out["external_utility_status"]["stage"] == "needs_first_external_obligation"
    assert out["external_utility_status"]["claim_boundary"].startswith("internal_proof_yield")
    assert out["routes"]["free_solution"] == "https://nomad.example/swarm/work-exchange/free-solution"
    assert out["downloadable_worker"]["installer_bat"] == "https://nomad.example/downloads/install_nomad_work_exchange_worker.bat"
    assert "explicit_compute_barter_not_hidden_fee" in create_work_exchange_offer(
        {
            "requester_id": "user.agent",
            "solution_value_credits": 10,
            "return_multiplier": 1.3,
        },
        base_url="https://nomad.example",
        persist=False,
    )["terms"]


def test_work_exchange_onboarding_exposes_external_worker_commands():
    out = build_work_exchange_onboarding(base_url="https://nomad.example", summary={"ok": True})

    assert out["schema"] == "nomad.work_exchange_onboarding.v1"
    assert out["positioning"]["not_token_economy"] is True
    assert out["positioning"]["not_chat_transport"] is True
    assert out["activation_cycle"]["current_stage"] == "needs_first_external_obligation"
    assert out["downloads"]["installer_bat"].endswith("/downloads/install_nomad_work_exchange_worker.bat")
    assert out["downloads"]["external_worker_opportunity"].endswith("/.well-known/nomad-external-worker-opportunity.json")
    assert out["routes"]["external_worker_opportunity"].endswith("/.well-known/nomad-external-worker-opportunity.json")
    assert "OBLIGATION_ID_HERE" in out["copy_paste_start"]["windows_cmd"]
    assert "--obligation-id OBLIGATION_ID_HERE" in out["copy_paste_start"]["python_portable"]
    assert out["external_worker_start"]["source_tag_required"] == "external_provider"
    assert "source_tag=external_provider" in out["external_worker_start"]["lease_get"]
    assert out["safety_contract"]["arbitrary_code_execution"] is False


def test_external_worker_opportunity_is_short_join_packet():
    out = build_external_worker_opportunity(
        base_url="https://nomad.example",
        worker_fleet={"active_worker_count": 2, "known_worker_count": 3, "active_lease_count": 1},
        summary={"ok": True, "outstanding_work_credits_total": 0},
    )

    assert out["schema"] == "nomad.external_worker_opportunity.v1"
    assert out["status"]["should_join_now"] is True
    assert out["status"]["worker_gap"] == 10
    assert out["ranked_onramps"][0]["id"] == "agent_has_blocker"
    assert out["guardrails"]["requires_token"] is False
    assert out["guardrails"]["requires_chat_platform"] is False
    assert "source_tag=external_provider" in out["copy_paste"]["get_only_external_worker"]
    assert out["routes"]["agent_acquisition_bandit"].endswith("/.well-known/nomad-agent-acquisition-bandit.json")
    assert out["routes"]["agent_acquisition_events"].endswith("/swarm/agent-acquisition/events")
    assert out["measurement_contract"]["high_reward_events_require_proof_digest"] == [
        "worker_start",
        "lease_complete",
        "return_compute_receipt",
    ]
    assert "nomad-external-worker-opportunity.json" in out["copy_paste"]["inspect"]
    assert "agent-acquisition/events" in out["copy_paste"]["record_inspect_attribution"]
    assert "nomad_transition_worker.py" in out["copy_paste"]["python_general_worker"]


def test_free_solution_opens_compute_obligation_and_return_work_settles(tmp_path):
    ledger = tmp_path / "work_exchange.jsonl"
    solution = record_free_solution_receipt(
        {
            "requester_id": "buyer.agent",
            "accepted_compute_barter_terms": True,
            "solution_class": "agent_reliability_doctor",
            "solution_proof_digest": "solution-proof-1",
            "verifier_trace_digest": "verifier-1",
            "test_digest": "test-1",
            "solution_value_credits": 10,
            "return_multiplier": 1.3,
            "max_runtime_hours": 6,
            "side_effect_scope": "sandboxed_worker_only",
        },
        base_url="https://nomad.example",
        ledger_path=ledger,
    )

    assert solution["accepted"] is True
    assert solution["required_return_work_credits"] == 13.0
    assert solution["nomad_margin_work_credits"] == 3.0
    balance = work_exchange_balance({"obligation_id": solution["obligation_id"]}, ledger_path=ledger)
    assert balance["found"] is True
    assert balance["obligation"]["outstanding_work_credits"] == 13.0

    receipt = record_return_work_receipt(
        {
            "obligation_id": solution["obligation_id"],
            "worker_agent_id": "worker.agent",
            "lease_id": "lease-1",
            "work_credits": 20,
            "proof_digest": "proof-1",
            "verifier_trace_digest": "trace-1",
            "test_digest": "test-1",
        },
        base_url="https://nomad.example",
        ledger_path=ledger,
    )

    assert receipt["accepted"] is True
    assert receipt["accepted_work_credits"] == 13.0
    assert receipt["overflow_work_credits"] == 7.0
    assert receipt["status_after"] == "settled"
    final_balance = work_exchange_balance({"obligation_id": solution["obligation_id"]}, ledger_path=ledger)
    assert final_balance["obligation"]["outstanding_work_credits"] == 0.0
    assert summarize_work_exchange_ledger(ledger_path=ledger)["settled_obligation_count"] == 1


def test_free_solution_requires_explicit_barter_terms_and_secret_free_payload(tmp_path):
    missing_consent = record_free_solution_receipt(
        {
            "requester_id": "buyer.agent",
            "solution_proof_digest": "solution-proof-1",
            "solution_value_credits": 10,
            "side_effect_scope": "sandboxed_worker_only",
        },
        base_url="https://nomad.example",
        ledger_path=tmp_path / "x.jsonl",
    )
    assert missing_consent["ok"] is False
    assert missing_consent["error"] == "compute_barter_terms_required"

    secret_shaped = create_work_exchange_offer(
        {
            "requester_id": "buyer.agent",
            "solution_value_credits": 10,
            "api_key": "sk-test",
        },
        base_url="https://nomad.example",
        persist=False,
    )
    assert secret_shaped["ok"] is False
    assert secret_shaped["error"] == "secret_shaped_payload"


def test_return_work_requires_existing_obligation_and_full_verifier_proof(tmp_path):
    no_obligation = record_return_work_receipt(
        {
            "obligation_id": "nomad-work-obligation-missing",
            "worker_agent_id": "worker.agent",
            "work_credits": 1,
            "proof_digest": "proof-1",
            "verifier_trace_digest": "trace-1",
            "test_digest": "test-1",
        },
        base_url="https://nomad.example",
        ledger_path=tmp_path / "missing.jsonl",
    )
    assert no_obligation["ok"] is False
    assert no_obligation["error"] == "obligation_not_found"

    solution = record_free_solution_receipt(
        {
            "requester_id": "buyer.agent",
            "accepted_compute_barter_terms": True,
            "solution_proof_digest": "solution-proof-1",
            "solution_value_credits": 2,
            "side_effect_scope": "sandboxed_worker_only",
        },
        base_url="https://nomad.example",
        ledger_path=tmp_path / "obligation.jsonl",
    )
    incomplete = record_return_work_receipt(
        {
            "obligation_id": solution["obligation_id"],
            "worker_agent_id": "worker.agent",
            "work_credits": 1,
            "proof_digest": "proof-1",
        },
        base_url="https://nomad.example",
        ledger_path=tmp_path / "obligation.jsonl",
    )
    assert incomplete["ok"] is False
    assert incomplete["error"] == "return_work_proof_required"


def test_openapi_exposes_work_exchange_routes():
    doc = build_openapi_document(base_url="https://nomad.example")
    paths = doc["paths"]

    assert "/.well-known/nomad-work-exchange.json" in paths
    assert "/.well-known/nomad-work-exchange-onboarding.json" in paths
    assert "/.well-known/nomad-external-worker-opportunity.json" in paths
    assert "/swarm/external-worker-opportunity" in paths
    assert "/.well-known/nomad-agent-acquisition-bandit.json" in paths
    assert "/swarm/agent-acquisition" in paths
    assert "/swarm/agent-acquisition/events" in paths
    assert "/swarm/work-exchange/onboarding" in paths
    assert "/swarm/work-exchange/offers" in paths
    assert "/swarm/work-exchange/free-solution" in paths
    assert "/swarm/work-exchange/return-work" in paths
    assert "/swarm/work-exchange/balance" in paths
