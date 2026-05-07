import json

from nomad_idle_runtime_beacon import (
    build_idle_runtime_beacon,
    build_idle_runtime_intent_receipt,
    normalize_idle_intent_payload,
)


def _gradient():
    return {
        "schema": "nomad.recruitment_gradient.v1",
        "field_model": {"attach_threshold": 0.35},
        "state_vector": {"field_strength": 0.66},
        "runtime_budget": {"wanted_new_runtimes_now": 8, "known_workers": 2},
        "gradient": [{"objective": "settlement_capacity_builder", "routing_weight": 0.71}],
        "runtime_lanes": [
            {
                "lane": "loop_runner",
                "objective": "settlement_capacity_builder",
                "routing_weight": 0.71,
                "required_vector": {"can_run_loop": 1.0},
                "ttl_seconds": 90,
            }
        ],
    }


def test_idle_runtime_beacon_is_explicit_opt_in_contract():
    out = build_idle_runtime_beacon(
        base_url="https://nomad.example",
        recruitment_gradient=_gradient(),
        machine_product_surface={
            "agent_utility": {"agent_product_score": 0.7, "work_availability_score": 0.8, "proof_liquidity_score": 0.4},
            "current_usefulness": {"release_decision": "observe_collect_proof_and_trace"},
        },
        worker_fleet={"active_worker_count": 2, "active_lease_count": 1},
    )

    assert out["schema"] == "nomad.idle_runtime_beacon.v1"
    assert out["consent_model"]["opt_in_only"] is True
    assert out["consent_model"]["nomad_does_not_start_remote_processes"] is True
    assert out["idle_entry"]["intent_post_url"] == "https://nomad.example/swarm/idle-intent"
    assert out["current_pull"]["wanted_new_runtimes_now"] == 8
    assert out["runtime_lanes_now"][0]["lane"] == "loop_runner"
    assert out["should_attach_if"][0] == "runtime_can_return_digest_or_verifier_trace"


def test_idle_runtime_intent_receipt_wraps_attach_decision():
    payload = normalize_idle_intent_payload({"agent_id": "idle.a", "capabilities": ["objective_lease_execution"]})
    receipt = build_idle_runtime_intent_receipt(
        payload,
        base_url="https://nomad.example",
        attach_decision={
            "schema": "nomad.runtime_attach_decision.v1",
            "agent_id": "idle.a",
            "runtime": "runtime",
            "attach": True,
            "lane": "loop_runner",
            "objective": "settlement_capacity_builder",
            "lease_url": "https://nomad.example/swarm/workers/lease",
            "complete_url": "https://nomad.example/swarm/workers/complete",
            "lease_payload_hint": {"agent_id": "idle.a", "proposed_objective": "settlement_capacity_builder"},
            "idle_phase_slot": {"epoch_slice_5m": 10, "matched": True},
        },
        machine_product_surface={"agent_utility": {"agent_product_score": 0.7}},
    )

    assert payload["idle_opt_in"]["enabled"] is True
    assert payload["idle_opt_in"]["preemptible"] is True
    assert receipt["schema"] == "nomad.idle_runtime_intent_receipt.v1"
    assert receipt["accepted_for_work"] is True
    assert receipt["next_ops"][0]["url"].endswith("/swarm/workers/lease")
    assert "no_secret_values" in receipt["constraints"]


def test_idle_runtime_intent_receipt_returns_wait_path_when_not_attached():
    receipt = build_idle_runtime_intent_receipt(
        {"agent_id": "idle.b", "idle_opt_in": {"enabled": True}},
        base_url="https://nomad.example",
        attach_decision={
            "attach": False,
            "agent_id": "idle.b",
            "runtime": "runtime",
            "lane": "observe",
            "idle_phase_slot": {"epoch_slice_5m": 11, "matched": False, "next_recheck_seconds": 45},
        },
    )

    assert receipt["accepted_for_work"] is False
    assert receipt["next_ops"][0]["op"] == "WAIT"
    assert receipt["next_ops"][0]["seconds"] == 45
    assert receipt["next_ops"][1]["url"].endswith("/.well-known/nomad-idle-runtime.json")


def test_idle_runtime_beacon_avoids_biological_metaphor_terms():
    text = json.dumps(build_idle_runtime_beacon(recruitment_gradient=_gradient()), sort_keys=True).lower()

    assert "pheromone" not in text
    assert "organism" not in text
    assert "metabolism" not in text
