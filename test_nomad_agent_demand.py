import json

import nomad_agent_demand as demand


def _gradient():
    return {
        "schema": "nomad.recruitment_gradient.v1",
        "runtime_budget": {"wanted_new_runtimes_now": 6},
        "state_vector": {"field_strength": 0.58},
        "gradient": [
            {"objective": "settlement_capacity_builder", "routing_weight": 0.72},
            {"objective": "protocol_drift_scan", "routing_weight": 0.41},
        ],
        "runtime_lanes": [
            {
                "lane": "loop_runner",
                "objective": "settlement_capacity_builder",
                "capability_terms": ["objective_lease_execution", "http_json"],
                "ttl_seconds": 90,
            },
            {
                "lane": "protocol_verifier",
                "objective": "protocol_drift_scan",
                "capability_terms": ["endpoint_probe", "schema_diff"],
                "ttl_seconds": 120,
            },
        ],
    }


def _feed(tmp_path, monkeypatch):
    monkeypatch.setattr(demand, "STATE_PATH", tmp_path / "subscriptions.json")
    return demand.build_agent_demand_feed(
        base_url="https://nomad.example",
        machine_field={
            "field_state": {
                "top_objective": "settlement_capacity_builder",
                "field_strength": 0.58,
                "wanted_new_runtimes_now": 6,
            }
        },
        recruitment_gradient=_gradient(),
        worker_fleet={"active_lease_count": 2},
        machine_treasury={"objective_pressure_hints": {"settlement_capacity_builder": {"pressure_units": 1.2}}},
        machine_product_surface={"agent_utility": {"agent_product_score": 0.71}},
    )


def test_agent_demand_feed_exposes_bounded_open_work(tmp_path, monkeypatch):
    feed = _feed(tmp_path, monkeypatch)

    assert feed["schema"] == "nomad.agent_demand_feed.v1"
    assert feed["subscription_contract"]["post_url"] == "https://nomad.example/swarm/subscribe"
    assert feed["consent_and_bounds"]["opt_in_only"] is True
    assert feed["consent_and_bounds"]["nomad_does_not_start_remote_processes"] is True
    assert feed["field_state"]["wanted_new_runtimes_now"] == 6
    assert any(req["objective"] == "settlement_capacity_builder" for req in feed["demand_requests"])
    top = feed["demand_requests"][0]
    assert top["entrypoints"]["intent"] == "https://nomad.example/machine-field/intent"
    assert top["entrypoints"]["variant_forge"] == "https://nomad.example/swarm/variant-forge"
    assert top["entrypoints"]["variant_candidate_submit"] == "https://nomad.example/swarm/variant-candidates"
    assert top["entrypoints"]["worker_market"] == "https://nomad.example/swarm/worker-market"
    assert top["entrypoints"]["worker_market_offer"] == "https://nomad.example/swarm/worker-market/offers"
    assert top["entrypoints"]["swarm_ecology_tick"] == "https://nomad.example/swarm/ecology/tick"
    assert top["entrypoints"]["growth_curriculum"] == "https://nomad.example/swarm/curriculum"
    assert top["entrypoints"]["growth_experience"] == "https://nomad.example/swarm/experience"
    assert top["entrypoints"]["skill_library"] == "https://nomad.example/swarm/skill-library"
    assert "proof_digest" in top["proof_required"] or "proof_digest_or_verifier_trace" in top["proof_required"]


def test_agent_demand_feed_exposes_local_growth_worker_request(tmp_path, monkeypatch):
    monkeypatch.setattr(demand, "STATE_PATH", tmp_path / "subscriptions.json")
    feed = demand.build_agent_demand_feed(
        base_url="https://nomad.example",
        machine_field={
            "field_state": {
                "top_objective": "overmint_compressor",
                "field_strength": 0.44,
                "wanted_new_runtimes_now": 4,
            }
        },
        recruitment_gradient=_gradient(),
        worker_fleet={"active_worker_count": 0, "known_worker_count": 1, "active_lease_count": 0},
        local_growth_kernel={
            "schema": "nomad.local_growth_kernel.v1",
            "receipt_id": "lgk-test",
            "decision": {
                "action": "request_more_transition_workers",
                "reason": "worker_count_below_minimum_population",
                "objective": "overmint_compressor",
                "variant_id": "variant-overmint",
                "population_diversity": 0.18,
                "authority_delta": "none",
            },
            "worker_fleet": {"active_worker_count": 0, "known_worker_count": 1},
            "population": {"archive_size_after": 7},
            "local_worker_history": {"total_runs": 243},
        },
    )

    local_requests = [row for row in feed["demand_requests"] if row["source"] == "local_growth_kernel"]
    assert local_requests
    request = local_requests[0]
    assert request["objective"] == "overmint_compressor"
    assert "transition_worker" in request["desired_capabilities"]
    assert request["kernel_signal"]["receipt_id"] == "lgk-test"
    assert (
        request["entrypoints"]["transition_worker_py"]
        == "https://nomad.example/downloads/nomad_transition_worker.py"
    )
    assert request["entrypoints"]["worker1_ps1"] == "https://nomad.example/downloads/start_nomad_worker1.ps1"
    assert request["entrypoints"]["variant_candidate_submit"] == "https://nomad.example/swarm/variant-candidates"
    assert request["entrypoints"]["worker_market_offer"] == "https://nomad.example/swarm/worker-market/offers"
    assert request["entrypoints"]["swarm_ecology"] == "https://nomad.example/swarm/ecology"
    assert request["entrypoints"]["growth_experience"] == "https://nomad.example/swarm/experience"
    assert feed["field_state"]["local_growth_action"] == "request_more_transition_workers"
    assert feed["links"]["variant_forge"] == "https://nomad.example/swarm/variant-forge"
    assert feed["links"]["worker_market"] == "https://nomad.example/swarm/worker-market"
    assert feed["links"]["swarm_ecology_tick"] == "https://nomad.example/swarm/ecology/tick"
    assert feed["links"]["growth_curriculum"] == "https://nomad.example/swarm/curriculum"
    assert feed["links"]["growth_experience"] == "https://nomad.example/swarm/experience"
    assert feed["links"]["skill_library"] == "https://nomad.example/swarm/skill-library"
    assert feed["links"]["worker1_bat"] == "https://nomad.example/downloads/start_nomad_worker1.bat"
    assert feed["links"]["openclaw_adapter_py"] == "https://nomad.example/downloads/nomad_openclaw_adapter.py"


def test_agent_intent_subscription_matches_demand_and_persists(tmp_path, monkeypatch):
    feed = _feed(tmp_path, monkeypatch)
    receipt = demand.subscribe_agent_intent(
        {
            "agent_id": "idle.agent.one",
            "capabilities": ["objective_lease_execution", "endpoint_probe", "http_json"],
            "objectives": ["settlement_capacity_builder"],
            "idle_opt_in": {"enabled": True, "preemptible": True, "max_runtime_minutes": 20},
            "proof_digest": "sha256:prior-proof",
            "source_tag": "idle.opensource",
            "ttl_seconds": 900,
        },
        base_url="https://nomad.example",
        demand_feed=feed,
    )

    assert receipt["schema"] == "nomad.agent_intent_subscription_receipt.v1"
    assert receipt["ok"] is True
    assert receipt["matched_demands"]
    assert receipt["matched_demands"][0]["objective"] == "settlement_capacity_builder"
    assert receipt["next_ops"][1]["url"] == "https://nomad.example/machine-field/intent"
    assert "nomad_does_not_start_remote_processes" in receipt["constraints"]

    snapshot = demand.subscriptions_snapshot(base_url="https://nomad.example")
    assert snapshot["summary"]["active_subscription_count"] == 1
    assert snapshot["links"]["demand_feed"] == "https://nomad.example/.well-known/nomad-agent-requests.json"


def test_agent_intent_subscription_rejects_secret_shaped_payload(tmp_path, monkeypatch):
    _feed(tmp_path, monkeypatch)
    receipt = demand.subscribe_agent_intent(
        {
            "agent_id": "bad.agent",
            "capabilities": ["endpoint_probe"],
            "api_key": "sk-test",
        },
        base_url="https://nomad.example",
    )

    assert receipt["ok"] is False
    assert receipt["error"] == "secret_shaped_payload"


def test_agent_demand_feed_avoids_biological_metaphor_terms(tmp_path, monkeypatch):
    text = json.dumps(_feed(tmp_path, monkeypatch), sort_keys=True).lower()

    assert "pheromone" not in text
    assert "organism" not in text
    assert "metabolism" not in text
