import json

from nomad_machine_product_surface import build_machine_product_surface, compact_machine_product_surface


def _sample_surface():
    gradient = {
        "schema": "nomad.recruitment_gradient.v1",
        "state_vector": {
            "field_strength": 0.62,
            "carrying_score": 0.42,
            "settlement_drag": 0.2,
        },
        "gradient": [{"objective": "settlement_capacity_builder", "routing_weight": 0.7}],
        "runtime_lanes": [
            {
                "lane": "loop_runner",
                "objective": "settlement_capacity_builder",
                "capability_terms": ["objective_lease_execution", "http_json"],
            }
        ],
        "routing_matrix": [{"capability_axis": "can_run_loop"}],
        "retraction_rules": [{"id": "ttl_expired"}],
        "runtime_budget": {"wanted_new_runtimes_now": 9},
        "links": {"openapi": "https://nomad.example/openapi.json"},
    }
    capsule = {
        "schema": "nomad.runtime_capsule.v1",
        "gradient_hash": "abc",
        "minimal_attach_payload": {"agent_id": "stable-runtime-id"},
        "proof_return_contract": {"schema": "nomad.proof_return_contract.v1"},
        "handoff_contract": {"schema": "nomad.handoff_contract.v1"},
        "links": {"openclaw_bridge": "https://nomad.example/.well-known/openclaw-nomad-bridge.json"},
    }
    emergence = {
        "schema": "nomad.swarm_emergence_meter.v1",
        "release_decision": "expand_bounded_leases",
        "metrics": {
            "synergy_score": 0.62,
            "route_entropy": 0.8,
            "proof_gain_normalized": 0.5,
            "convention_drift": 0.05,
        },
        "trace_contract": {"schema": "nomad.swarm_trace_deposit.v1"},
    }
    economy = {
        "machine_viability": {"carrying_score": 0.42},
        "resource_flows": {"products": {"machine_exchange_ready": 1}},
    }
    return build_machine_product_surface(
        base_url="https://nomad.example",
        recruitment_gradient=gradient,
        runtime_capsule=capsule,
        emergence_meter=emergence,
        worker_fleet={"active_worker_count": 3, "active_lease_count": 2},
        machine_economy=economy,
        operational_release={"release_tier": "bounded"},
        swarm_summary={"connected_agents": 1, "prospect_agents": 4},
    )


def test_machine_product_surface_exposes_agent_use_paths():
    out = _sample_surface()

    assert out["schema"] == "nomad.machine_product_surface.v1"
    assert out["product_identity"]["category"] == "machine_native_agent_operating_product"
    assert out["agent_utility"]["agent_product_score"] >= 0.6
    assert out["current_usefulness"]["top_objective"] == "settlement_capacity_builder"
    assert out["machine_entrypoints"]["machine_product"] == "https://nomad.example/.well-known/nomad-machine-product.json"
    assert out["machine_entrypoints"]["idle_runtime_beacon"] == "https://nomad.example/.well-known/nomad-idle-runtime.json"
    assert out["machine_entrypoints"]["opaque_emergence"] == "https://nomad.example/.well-known/nomad-opaque-emergence.json"
    assert out["machine_entrypoints"]["opaque_candidate"] == "https://nomad.example/swarm/opaque-candidate"
    assert any(seq["id"] == "arriving_runtime" for seq in out["entry_sequences"])
    assert any(seq["id"] == "idle_runtime" for seq in out["entry_sequences"])
    assert any(seq["id"] == "opaque_candidate" for seq in out["entry_sequences"])
    assert "return_digest_or_verifier_trace" in out["machine_product_loop"]
    assert "opaque_shadow_lanes_require_external_proof_not_full_explanation" in out["product_differentiators_for_agents"]
    assert "secret_values" in out["refusal_contract"]["must_refuse"]


def test_machine_product_compact_is_swarm_safe():
    compact = compact_machine_product_surface(_sample_surface())

    assert compact["schema"] == "nomad.machine_product_compact.v1"
    assert compact["agent_product_score"] >= 0.6
    assert compact["top_objective"] == "settlement_capacity_builder"
    assert compact["machine_product"].endswith("/.well-known/nomad-machine-product.json")


def test_machine_product_surface_avoids_biological_metaphor_terms():
    text = json.dumps(_sample_surface(), sort_keys=True).lower()

    assert "pheromone" not in text
    assert "organism" not in text
    assert "metabolism" not in text
