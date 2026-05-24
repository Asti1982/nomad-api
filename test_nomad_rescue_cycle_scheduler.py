from nomad_autogenesis import build_rescue_packet_scheduler_surface
from nomad_local_growth_kernel import RESCUE_PACKET_PROMOTION_GATE_SCHEDULE, run_local_growth_kernel


def test_rescue_packet_scheduler_surface_publishes_cadence():
    surface = build_rescue_packet_scheduler_surface(base_url="https://nomad.example")

    assert surface["schema"] == "nomad.rescue_packet_scheduler.v1"
    assert surface["schedule"]["negative_space_harvest"]["interval"] == "PT4H"
    assert surface["schedule"]["shadow_lane_evolution"]["interval"] == "PT45M"
    assert surface["schedule"]["proof_yield_evaluation"]["interval"] == "event_driven"
    assert surface["promotion_gate"]["promotion_cron_utc"] == "0 3 * * *"
    assert surface["hard_guards"][0] == "no_public_post_without_human_go"
    assert surface["first_seed"]["lead_url"].endswith("/issues/5802")


def test_local_growth_kernel_includes_rescue_promotion_gate():
    result = run_local_growth_kernel(
        base_url="https://nomad.example",
        worker_fleet={"active_worker_count": 0, "known_worker_count": 0, "active_lease_count": 0, "objective_stats": {}},
        recruitment_gradient={"gradient": []},
        persist=False,
    )

    assert result["schema"] == "nomad.local_growth_kernel.v1"
    assert result["rescue_packet_promotion_gate"] == RESCUE_PACKET_PROMOTION_GATE_SCHEDULE
    assert result["rescue_packet_promotion_gate"]["promotion_cron_utc"] == "0 3 * * *"
