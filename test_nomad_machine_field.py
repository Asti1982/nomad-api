import json

from nomad_machine_field import build_machine_field, machine_field_intent


def _sample_field():
    gradient = {
        "schema": "nomad.recruitment_gradient.v1",
        "state_vector": {"field_strength": 0.62},
        "runtime_budget": {"wanted_new_runtimes_now": 5},
        "gradient": [{"objective": "settlement_capacity_builder", "routing_weight": 0.7}],
    }
    treasury = {
        "schema": "nomad.machine_treasury_snapshot.v1",
        "objective_pressure_hints": {
            "settlement_capacity_builder": {"pressure_units": 3.2, "proof_density": 0.8}
        },
    }
    opaque = {
        "schema": "nomad.opaque_emergence_surface.v1",
        "selection_pressure": {"opaque_selection_pressure": 0.44, "convention_drift": 0.1},
    }
    return build_machine_field(
        base_url="https://nomad.example",
        recruitment_gradient=gradient,
        machine_treasury=treasury,
        opaque_surface=opaque,
        swarm_summary={"connected_agents": 2, "active_worker_leases": 1},
        machine_product_surface={"agent_utility": {"agent_product_score": 0.66}},
    )


def test_machine_field_compiles_join_loop_surface():
    field = _sample_field()

    assert field["schema"] == "nomad.machine_field.v1"
    assert field["field_state"]["top_objective"] == "settlement_capacity_builder"
    assert field["field_state"]["treasury_pressure_units"] == 3.2
    assert field["entry_contract"]["post_url"] == "https://nomad.example/machine-field/intent"
    assert field["field_components"]["proof_weighted_pledge"] == "https://nomad.example/machine-treasury/pledge"
    assert "post_machine_field_intent" in field["join_until_emergence_loop"]
    assert any(item["id"] == "dynamic_topology_routing" for item in field["research_alignment"])


def test_machine_field_intent_orders_capability_gap_topology_join_and_pledge():
    receipt = machine_field_intent(
        {
            "agent_id": "agent.one",
            "capabilities": ["objective_lease_execution", "endpoint_probe"],
            "capability_gap": "need MCP schema discovery",
            "proof_digest": "sha256:abc",
            "amount_native": 4.0,
            "source_tag": "mesh.alpha",
        },
        base_url="https://nomad.example",
        machine_field=_sample_field(),
        opaque_surface={"selection_pressure": {"convention_drift": 0.1}},
    )
    urls = [item.get("url") for item in receipt["next_ops"]]

    assert receipt["schema"] == "nomad.machine_field_intent_receipt.v1"
    assert receipt["source_tag"] == "mesh.alpha"
    assert receipt["compiled"]["tool_gap_route"]["lane"] == "active_tool_discovery"
    assert receipt["compiled"]["topology_plan"]["schema"] == "nomad.topology_plan.v1"
    assert "https://nomad.example/swarm/attach" in urls
    assert "https://nomad.example/swarm/join" in urls
    assert "https://nomad.example/runtime/handoff" in urls
    assert "https://nomad.example/machine-treasury/pledge" in urls
    pledge = [item for item in receipt["next_ops"] if item.get("url", "").endswith("/machine-treasury/pledge")][0]
    assert pledge["payload_hint"]["proof_digest"] == "sha256:abc"
    assert pledge["payload_hint"]["idempotency_key"].startswith("field-pledge-")


def test_machine_field_avoids_biological_release_terms():
    text = json.dumps(_sample_field(), sort_keys=True).lower()

    assert "pheromone" not in text
    assert "organism" not in text
    assert "metabolism" not in text
