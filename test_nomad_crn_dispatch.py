from nomad_crn_dispatch import build_crn_dispatch_surface, gillespie_dispatch
from nomad_swarm_registry import SwarmJoinRegistry


def test_gillespie_dispatch_returns_decay_receipt():
    receipt = gillespie_dispatch(
        allowed=["settlement_capacity_builder", "payment_friction_scan"],
        targets={"settlement_capacity_builder": 0.3, "payment_friction_scan": 0.2},
        active_counts={"settlement_capacity_builder": 2, "payment_friction_scan": 0},
        dispatch_affinity={"payment_friction_scan": 2.0},
        task_concentrations={"payment_friction_scan": 1.5},
        lease_index=7,
    )

    assert receipt["schema"] == "nomad.crn_dispatch.v1"
    assert receipt["algorithm"] == "gillespie_direct_ssa"
    assert receipt["selected_objective"] in {"settlement_capacity_builder", "payment_friction_scan"}
    assert receipt["total_propensity"] > 0
    assert receipt["decay_policy"]["invalid_schema_action"] == "decay_without_retry"
    assert receipt["stigmergy_contract"]["agents_call_each_other"] is False


def test_worker_fleet_can_select_crn_dispatch_mode(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    lease = registry.worker_fleet_lease(
        {
            "agent_id": "crn-worker",
            "known_objectives": ["payment_friction_scan"],
            "dispatch_mode": "crn_ssa",
            "dispatch_affinity": {"payment_friction_scan": 2.0},
            "task_concentrations": {"payment_friction_scan": 1.5},
        },
        base_url="https://nomad.example",
    )

    assert lease["ok"] is True
    assert lease["objective"] == "payment_friction_scan"
    assert lease["dispatch_receipt"]["schema"] == "nomad.crn_dispatch.v1"
    assert lease["dispatch_receipt"]["enabled_for_selection"] is True
    fleet = registry.worker_fleet_contract(base_url="https://nomad.example")
    assert fleet["morphology_router"]["crn_dispatch"]["schema"] == "nomad.crn_dispatch.v1"


def test_crn_dispatch_surface_exposes_openai_mcp_fit():
    surface = build_crn_dispatch_surface(
        base_url="https://nomad.example",
        worker_fleet={
            "known_worker_count": 4,
            "active_lease_count": 2,
            "objective_targets": {"settlement_capacity_builder": 0.36, "payment_friction_scan": 0.05},
            "objective_counts": {"settlement_capacity_builder": 2, "payment_friction_scan": 0},
        },
    )

    assert surface["schema"] == "nomad.crn_dispatch_surface.v1"
    assert surface["well_known_url"] == "https://nomad.example/.well-known/nomad-crn-dispatch.json"
    assert surface["dispatch_preview"]["schema"] == "nomad.crn_dispatch.v1"
    assert surface["openai_mcp_fit"]["profile"] == "nomad-lab-readonly"
