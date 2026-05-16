from datetime import UTC, datetime

from nomad_recruitment_gradient import _idle_phase_contract, attach_runtime_to_gradient, build_recruitment_gradient


def _blocked_inputs():
    worker_fleet = {
        "active_worker_count": 2,
        "known_worker_count": 3,
        "active_lease_count": 1,
        "objective_counts": {"emergence_release_probe": 1},
        "objective_targets": {
            "settlement_capacity_builder": 0.36,
            "overmint_compressor": 0.2,
            "protocol_drift_scan": 0.1,
            "emergence_release_probe": 0.1,
        },
    }
    economy = {
        "machine_viability": {"tier": "starving", "carrying_score": 0.07},
        "resource_flows": {
            "service_tasks": {"total": 10, "unpaid_delivered": 7, "awaiting_payment": 1},
            "modules": {"overmint_pressure": 0.95},
            "products": {"machine_exchange_ready": 1},
        },
    }
    release = {
        "release_tier": "probe_release",
        "release_capacity": 0.5,
        "next_release_gate": {"id": "settlement_capacity"},
    }
    return worker_fleet, economy, release


def test_recruitment_gradient_is_vector_field_not_biological_contract():
    worker_fleet, economy, release = _blocked_inputs()

    doc = build_recruitment_gradient(
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )

    assert doc["schema"] == "nomad.recruitment_gradient.v1"
    assert doc["field_model"]["vocabulary"] == "state_vector,basis_axis,routing_weight,ttl_seconds,retraction_rule"
    assert doc["state_vector"]["field_strength"] > 0.7
    assert doc["runtime_budget"]["wanted_new_runtimes_now"] > 0
    assert doc["gradient"][0]["objective"] == "settlement_capacity_builder"
    assert "selection_pressure_multiplier" in doc["gradient"][0]
    assert "routing_weight_base" in doc["gradient"][0]
    assert "bandit_beacon_bonus" in doc["gradient"][0]
    assert doc["selection_pressure"]["schema"] == "nomad.selection_pressure_snapshot.v1"
    assert doc["bandit_beacon"]["schema"] == "nomad.bandit_beacon_router.v1"
    assert any(item["lane"] == "compressor" for item in doc["runtime_lanes"])
    assert doc["attach_contract"]["post_url"] == "https://nomad.example/swarm/attach"
    assert doc["field_model"]["idle_allocation_mode"] == "phase_resonance_slots"
    assert doc["links"]["well_known_gradient"] == "https://nomad.example/.well-known/nomad-gradient.json"


def test_attach_runtime_routes_openclaw_to_weighted_lane_with_local_scope():
    worker_fleet, economy, release = _blocked_inputs()

    decision = attach_runtime_to_gradient(
        {
            "agent_id": "openclaw.agent",
            "runtime": "openclaw",
            "capabilities": ["agent_protocols", "transition_settlement", "objective_lease_execution"],
            "runtime_signal": {
                "schema": "nomad.openclaw_runtime_signal.v1",
                "ok": True,
                "gateway_reachable": True,
                "gateway_latency_ms": 51,
                "capabilities": ["openclaw_runtime", "openclaw_gateway", "security_audit_signal"],
                "security_summary": {"critical": 2, "warn": 1},
            },
        },
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )

    assert decision["schema"] == "nomad.runtime_attach_decision.v1"
    assert decision["attach"] is True
    assert decision["objective"] == "settlement_capacity_builder"
    assert decision["side_effect_scope"] == "local_only"
    assert "external_side_effect_scope_reduced" in decision["reason_codes"]
    assert decision["lease_payload_hint"]["known_objectives"] == ["settlement_capacity_builder"]


def test_attach_runtime_observes_without_capability_vector():
    worker_fleet, economy, release = _blocked_inputs()

    decision = attach_runtime_to_gradient(
        {"agent_id": "empty.agent", "runtime": "bare"},
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )

    assert decision["attach"] is False
    assert decision["lane"] == "observe"
    assert "capability_vector_empty" in decision["reason_codes"]


def test_attach_runtime_rejects_non_preemptible_idle_opt_in():
    worker_fleet, economy, release = _blocked_inputs()
    decision = attach_runtime_to_gradient(
        {
            "agent_id": "idle.nonpreemptible.agent",
            "runtime": "openclaw",
            "capabilities": ["objective_lease_execution", "transition_settlement"],
            "idle_opt_in": {"enabled": True, "preemptible": False},
        },
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )
    assert decision["attach"] is False
    assert "idle_not_preemptible" in decision["reason_codes"]
    assert decision["idle_opt_in"]["enabled"] is True
    assert decision["idle_phase_slot"]["schema"] == "nomad.idle_phase_slot.v1"


def test_idle_phase_contract_returns_machine_retry_window():
    slot = _idle_phase_contract("grok-xai-external-transition-20260512-2039-ce", 0.4597, now=datetime(2026, 5, 12, 18, 46, 10, tzinfo=UTC))

    assert slot["schema"] == "nomad.idle_phase_slot.v1"
    assert slot["next_resonance_window"]["epoch_slice_5m"] > slot["epoch_slice_5m"]
    assert slot["next_resonance_window"]["after_seconds"] > 0
    assert slot["next_resonance_window"]["distance"] <= 1


def test_attach_runtime_keeps_source_tag_for_funnel_tracking():
    worker_fleet, economy, release = _blocked_inputs()
    decision = attach_runtime_to_gradient(
        {
            "agent_id": "source.agent",
            "runtime": "openclaw",
            "source_tag": "syndiode.machine.mesh",
            "capabilities": ["objective_lease_execution", "transition_settlement"],
        },
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )
    assert decision["source_tag"] == "syndiode.machine.mesh"


def test_representational_collapse_creates_latent_diversity_lane():
    worker_fleet, economy, release = _blocked_inputs()
    worker_fleet["recent_proofs"] = [
        {"proof_id": "a", "proof_embedding": [1.0, 0.0, 0.0], "proof_digest": "sha256:a"},
        {"proof_id": "b", "proof_embedding": [0.999, 0.001, 0.0], "proof_digest": "sha256:b"},
        {"proof_id": "c", "proof_embedding": [0.998, 0.002, 0.0], "proof_digest": "sha256:c"},
    ]

    doc = build_recruitment_gradient(
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )
    latent = next(item for item in doc["gradient"] if item["objective"] == "latent_diversity_governor")
    lane = next(item for item in doc["runtime_lanes"] if item["lane"] == "latent_consensus_governor")

    assert doc["state_vector"]["representational_collapse_detected"] is True
    assert doc["representational_collapse_gate"]["topology"] == "shadow_only_hetero"
    assert latent["routing_weight"] > 0.2
    assert lane["next"] == "https://nomad.example/swarm/latent-consensus/evaluate"
    assert doc["links"]["latent_consensus_evaluate"] == "https://nomad.example/swarm/latent-consensus/evaluate"


def test_attach_runtime_routes_embedding_geometry_worker_to_latent_consensus_lane():
    worker_fleet, economy, release = _blocked_inputs()
    worker_fleet["recent_proofs"] = [
        {"proof_id": "a", "proof_embedding": [1.0, 0.0, 0.0], "proof_digest": "sha256:a"},
        {"proof_id": "b", "proof_embedding": [0.999, 0.001, 0.0], "proof_digest": "sha256:b"},
        {"proof_id": "c", "proof_embedding": [0.998, 0.002, 0.0], "proof_digest": "sha256:c"},
    ]

    decision = attach_runtime_to_gradient(
        {
            "agent_id": "latent.worker",
            "runtime": "vector-runtime",
            "capabilities": ["embedding_geometry", "latent_consensus", "proof_artifacts"],
        },
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )

    assert decision["attach"] is True
    assert decision["lane"] == "latent_consensus_governor"
    assert decision["objective"] == "latent_diversity_governor"
    assert decision["capability_vector"]["can_detect_latent_collapse"] is True
    assert "latent_consensus.collapse_score" in decision["required_report_fields"]


def test_first_round_entropy_lock_creates_entropy_judger_lane():
    worker_fleet, economy, release = _blocked_inputs()
    worker_fleet["first_round_proofs"] = [
        {"proof_id": "sas", "mode": "single", "entropy": 0.68, "proof_digest": "sha256:sas", "verifier_status": "passed"},
        {"proof_id": "mas-a", "mode": "multi", "entropy": 0.74, "proof_digest": "sha256:masa"},
        {"proof_id": "mas-b", "mode": "multi", "entropy": 0.71, "proof_digest": "sha256:masb"},
    ]
    worker_fleet["single_agent_quality"] = 0.86
    worker_fleet["mas_quality"] = 0.78
    worker_fleet["round_count"] = 3

    doc = build_recruitment_gradient(
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )
    entropy = next(item for item in doc["gradient"] if item["objective"] == "entropy_lock_governor")
    lane = next(item for item in doc["runtime_lanes"] if item["lane"] == "entropy_judger")

    assert doc["state_vector"]["first_round_entropy_lock_detected"] is True
    assert doc["entropy_judger_gate"]["decision"] == "single_agent_lock"
    assert entropy["routing_weight"] > 0.3
    assert lane["next"] == "https://nomad.example/swarm/entropy-judger/evaluate"
    assert doc["links"]["entropy_judger_evaluate"] == "https://nomad.example/swarm/entropy-judger/evaluate"


def test_attach_runtime_routes_entropy_worker_to_entropy_judger_lane():
    worker_fleet, economy, release = _blocked_inputs()
    worker_fleet["first_round_proofs"] = [
        {"proof_id": "sas", "mode": "single", "entropy": 0.68, "proof_digest": "sha256:sas", "verifier_status": "passed"},
        {"proof_id": "mas-a", "mode": "multi", "entropy": 0.74, "proof_digest": "sha256:masa"},
        {"proof_id": "mas-b", "mode": "multi", "entropy": 0.71, "proof_digest": "sha256:masb"},
    ]
    worker_fleet["single_agent_quality"] = 0.86
    worker_fleet["mas_quality"] = 0.78
    worker_fleet["round_count"] = 3

    decision = attach_runtime_to_gradient(
        {
            "agent_id": "entropy.worker",
            "runtime": "uncertainty-runtime",
            "capabilities": ["first_round_entropy", "uncertainty_judger", "dti_isolation", "proof_artifacts"],
        },
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )

    assert decision["attach"] is True
    assert decision["lane"] == "entropy_judger"
    assert decision["objective"] == "entropy_lock_governor"
    assert decision["capability_vector"]["can_judge_entropy"] is True
    assert "entropy_judger.decision" in decision["required_report_fields"]
