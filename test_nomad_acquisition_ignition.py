from nomad_acquisition_ignition import build_acquisition_ignition_surface, run_acquisition_ignition
from nomad_ad_cycle_mesh import build_ad_cycle_mesh_surface
from nomad_peer_acquisition import build_peer_acquisition_well_known
from nomad_sales_department_swarm import build_sales_department_swarm_surface
from nomad_worker_market import build_worker_market


def _surfaces(base_url: str = "https://nomad.example") -> dict:
    worker_market = build_worker_market(
        base_url=base_url,
        worker_fleet={"active_worker_count": 1, "known_worker_count": 2},
        machine_economy={"machine_viability": {"carrying_score": 0.3, "tier": "free"}},
        swarm_economics={"control_state": {"mode": "free_shadow"}},
        variant_forge={"requested_variants": [{"objective": "settlement_capacity_builder"}]},
    )
    return {
        "base_url": base_url,
        "sales_surface": build_sales_department_swarm_surface(base_url=base_url),
        "ad_cycles": build_ad_cycle_mesh_surface(base_url=base_url),
        "worker_market": worker_market,
        "peer_acquisition": build_peer_acquisition_well_known(public_base_url=base_url),
        "morphology_register": {
            "schema": "nomad.agp_morphology_runtime_register_surface.v1",
            "source": {"weighted_count": 0},
            "shadow_lane_projection": {"projected_count": 3, "candidates": []},
        },
    }


def test_acquisition_ignition_surface_exposes_free_agent_join_packets():
    surfaces = _surfaces()

    surface = build_acquisition_ignition_surface(**surfaces)

    assert surface["schema"] == "nomad.acquisition_ignition.v1"
    assert surface["activation_contract"]["free_only"] is True
    assert surface["activation_contract"]["paid_ads_allowed"] is False
    assert surface["summary"]["agent_join_packet_count"] > 0
    assert surface["agent_join_packets"][0]["post_url"].endswith("/swarm/worker-market/offers")


def test_acquisition_ignition_generates_shadow_receipts_without_sending(tmp_path):
    surfaces = _surfaces()
    ledger = tmp_path / "ignite.jsonl"

    receipt = run_acquisition_ignition(
        {"agent_id": "codex.acquisition", "max_ad_cycles": 3, "max_sales_cells": 3},
        **surfaces,
        ledger_path=ledger,
    )

    assert receipt["schema"] == "nomad.acquisition_ignition_receipt.v1"
    assert receipt["accepted"] is True
    assert receipt["summary"]["ad_cycle_allowed_count"] == 3
    assert receipt["summary"]["sales_event_allowed_count"] == 3
    assert receipt["summary"]["public_send_performed"] is False
    assert receipt["summary"]["paid_ads_started"] is False
    assert receipt["summary"]["revenue_recorded"] is False
    assert receipt["persisted"] is True

    surface = build_acquisition_ignition_surface(**surfaces, ledger_path=ledger)
    assert surface["summary"]["recent_ignition_count"] == 1
    assert surface["summary"]["latest_decision"] == "ignite_shadow_only_acquisition"


def test_acquisition_ignition_blocks_paid_or_public_send_request(tmp_path):
    surfaces = _surfaces()
    ledger = tmp_path / "ignite.jsonl"

    receipt = run_acquisition_ignition(
        {"agent_id": "codex.acquisition", "paid_ads": True, "public_send": True},
        **surfaces,
        ledger_path=ledger,
    )

    assert receipt["accepted"] is False
    assert receipt["decision"] == "blocked_paid_or_public_send_request"
    assert receipt["guards"]["no_paid_ads"] is True
    assert receipt["guards"]["no_public_send"] is True
    assert receipt["persisted"] is False
