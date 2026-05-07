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
    assert out["links"]["topology_plan"].endswith("/swarm/topology-plan")
    assert any(item["id"] == "active_tool_discovery" for item in out["research_techniques"])
    assert any(item["id"] == "topology_compiler" for item in out["machine_products_to_add"])


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
    assert risk["topology"] == "verifier_split"
    assert cost["topology"] == "sparse_graph"
    assert settlement["topology"] == "chain"


def test_opaque_surface_compact_and_terms_are_safe():
    surface = _sample_surface()
    compact = compact_opaque_emergence_surface(surface)
    text = json.dumps(surface, sort_keys=True).lower()

    assert compact["schema"] == "nomad.opaque_emergence_compact.v1"
    assert compact["external_proof_required"] is True
    assert "pheromone" not in text
    assert "organism" not in text
    assert "metabolism" not in text
