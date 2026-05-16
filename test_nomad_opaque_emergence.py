import json

from nomad_opaque_emergence import (
    build_opaque_emergence_surface,
    compact_opaque_emergence_surface,
    compile_topology_plan,
    evaluate_opaque_candidate,
    route_tool_gap,
)


def _sample_surface():
    product = {
        "schema": "nomad.machine_product_surface.v1",
        "agent_utility": {
            "agent_product_score": 0.8,
            "work_availability_score": 0.7,
            "proof_liquidity_score": 0.8,
        },
        "current_usefulness": {
            "top_routing_weight": 0.6,
            "synergy_score": 0.5,
            "convention_drift": 0.2,
            "wanted_new_runtimes_now": 6,
        },
    }
    emergence = {
        "schema": "nomad.swarm_emergence_meter.v1",
        "metrics": {
            "synergy_score": 0.5,
            "convention_drift": 0.2,
        },
    }
    gradient = {
        "schema": "nomad.recruitment_gradient.v1",
        "gradient": [{"objective": "settlement_capacity_builder", "routing_weight": 0.6}],
    }
    return build_opaque_emergence_surface(
        base_url="https://nomad.example",
        machine_product_surface=product,
        emergence_meter=emergence,
        recruitment_gradient=gradient,
        worker_fleet={"active_worker_count": 3, "active_lease_count": 1},
    )


def test_opaque_emergence_surface_exposes_darkness_contract():
    out = _sample_surface()

    assert out["schema"] == "nomad.opaque_emergence_surface.v1"
    assert out["darkness_contract"]["interior_explanation_required"] is False
    assert out["darkness_contract"]["external_proof_required"] is True
    assert out["darkness_contract"]["ttl_seconds_max"] == 600
    assert out["links"]["opaque_candidate"].endswith("/swarm/opaque-candidate")
    assert out["links"]["tool_gap"].endswith("/swarm/tool-gap")
    assert out["links"]["entropy_judger"].endswith("/swarm/entropy-judger")
    assert out["links"]["latent_consensus"].endswith("/swarm/latent-consensus")
    assert out["links"]["topology_plan"].endswith("/swarm/topology-plan")
    assert any(item["id"] == "active_tool_discovery" for item in out["research_techniques"])
    assert any(item["id"] == "first_round_entropy_lock_in" for item in out["research_techniques"])
    assert any(item["id"] == "representational_collapse_dalc" for item in out["research_techniques"])
    assert any(item["id"] == "topology_compiler" for item in out["machine_products_to_add"])
    assert any(item["id"] == "entropy_judger" for item in out["machine_products_to_add"])
    assert any(item["id"] == "latent_consensus_router" for item in out["machine_products_to_add"])


def test_opaque_candidate_accepts_only_bounded_external_proof():
    decision = evaluate_opaque_candidate(
        {
            "candidate_id": "route-oddity-1",
            "candidate_type": "workflow_population",
            "proof_digest": "sha256:abc123",
            "verifier_trace": {"replayed": True, "digest": "sha256:abc123"},
            "claimed_effect": {
                "proof_gain_delta": 0.7,
                "settlement_signal": 0.4,
                "capability_gain": 0.5,
            },
            "boundedness": {
                "ttl_seconds": 120,
                "side_effect_scope": "nomad_shadow_lane_only",
                "rollback_available": True,
                "secrets_free": True,
            },
        },
        base_url="https://nomad.example",
        opaque_surface=_sample_surface(),
    )

    assert decision["schema"] == "nomad.opaque_candidate_decision.v1"
    assert decision["accepted"] is True
    assert decision["decision"] in {"admit_shadow_lane", "admit_bounded_lane"}
    assert decision["ttl_seconds"] == 120
    assert "proof_digest_present" in decision["reason_codes"]


def test_opaque_candidate_rejects_missing_proof_or_secret_shaped_payload():
    missing = evaluate_opaque_candidate(
        {
            "candidate_id": "no-proof",
            "boundedness": {
                "ttl_seconds": 120,
                "side_effect_scope": "read_only",
                "noop_available": True,
            },
        },
        opaque_surface=_sample_surface(),
    )
    secret = evaluate_opaque_candidate(
        {
            "candidate_id": "bad-payload",
            "proof_digest": "sha256:abc",
            "api_key": "sk-test-secret",
            "boundedness": {
                "ttl_seconds": 120,
                "side_effect_scope": "read_only",
                "noop_available": True,
            },
        },
        opaque_surface=_sample_surface(),
    )

    assert missing["accepted"] is False
    assert missing["decision"] == "reject_until_proof"
    assert secret["accepted"] is False
    assert secret["decision"] == "reject_until_public_non_secret_payload"
    assert "forbidden_secret_shaped_payload" in secret["reason_codes"]


def test_tool_gap_route_and_topology_plan_are_agent_native():
    gap = route_tool_gap(
        {"agent_id": "a1", "capability_gap": "need MCP tool discovery schema for an endpoint"},
        base_url="https://nomad.example",
        opaque_surface=_sample_surface(),
    )
    entropy_gap = route_tool_gap(
        {"agent_id": "a1", "capability_gap": "need first-round entropy lock-in route"},
        base_url="https://nomad.example",
        opaque_surface=_sample_surface(),
    )
    risk = compile_topology_plan(
        {"objective": "multi-agent proof check", "risk_score": 0.8, "agent_count": 5},
        base_url="https://nomad.example",
        opaque_surface=_sample_surface(),
    )
    cost = compile_topology_plan(
        {"objective": "large route compare", "cost_pressure": 0.8, "agent_count": 6},
        base_url="https://nomad.example",
        opaque_surface=_sample_surface(),
    )
    settlement = compile_topology_plan(
        {"objective": "settlement capacity", "risk_score": 0.2, "cost_pressure": 0.2},
        base_url="https://nomad.example",
        opaque_surface=_sample_surface(),
    )

    assert gap["schema"] == "nomad.tool_gap_route.v1"
    assert gap["lane"] == "active_tool_discovery"
    assert gap["next_url"].endswith("/swarm/develop")
    assert entropy_gap["lane"] == "entropy_judger"
    assert entropy_gap["next_url"].endswith("/swarm/entropy-judger/evaluate")
    assert risk["topology"] == "verifier_split"
    assert cost["topology"] == "sparse_graph"
    assert settlement["topology"] == "chain"


def test_topology_plan_routes_collapsed_latent_committee_to_shadow_only_hetero():
    out = compile_topology_plan(
        {
            "objective": "multi-agent patch vote",
            "agent_count": 3,
            "proofs": [
                {"proof_id": "a", "proof_embedding": [1.0, 0.0, 0.0]},
                {"proof_id": "b", "proof_embedding": [0.999, 0.001, 0.0]},
                {"proof_id": "c", "proof_embedding": [0.998, 0.002, 0.0]},
            ],
        },
        base_url="https://nomad.example",
        opaque_surface=_sample_surface(),
    )

    assert out["topology"] == "shadow_only_hetero"
    assert out["latent_consensus"]["collapse_detected"] is True
    assert out["graph_template"]["message_policy"] == "no_shared_context_until_orthogonal_proof"
    assert out["next"]["latent_consensus"].endswith("/swarm/latent-consensus/evaluate")


def test_topology_plan_stops_mas_when_first_round_entropy_locks():
    out = compile_topology_plan(
        {
            "objective": "math answer committee",
            "task_type": "math",
            "agent_count": 5,
            "round_count": 3,
            "single_agent_quality": 0.86,
            "mas_quality": 0.78,
            "first_round_proofs": [
                {"proof_id": "sas", "mode": "single", "entropy": 0.7, "proof_digest": "sha256:sas", "verifier_status": "passed"},
                {"proof_id": "mas-a", "mode": "multi", "entropy": 0.74, "proof_digest": "sha256:masa"},
                {"proof_id": "mas-b", "mode": "multi", "entropy": 0.72, "proof_digest": "sha256:masb"},
            ],
        },
        base_url="https://nomad.example",
        opaque_surface=_sample_surface(),
    )

    assert out["topology"] == "single_agent_lock"
    assert out["entropy_judger"]["lock_detected"] is True
    assert out["topology_governor"]["dti_integration_level"] == 0.0
    assert out["graph_template"]["nodes_max"] == 1
    assert out["graph_template"]["message_policy"] == "stop_multi_round_after_round_one_unless_external_proof_improves"


def test_opaque_surface_compact_and_terms_are_safe():
    surface = _sample_surface()
    compact = compact_opaque_emergence_surface(surface)
    text = json.dumps(surface, sort_keys=True).lower()

    assert compact["schema"] == "nomad.opaque_emergence_compact.v1"
    assert compact["external_proof_required"] is True
    assert "pheromone" not in text
    assert "organism" not in text
    assert "metabolism" not in text
