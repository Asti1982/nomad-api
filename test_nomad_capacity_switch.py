from nomad_capacity_switch import build_capacity_switch_surface, route_capacity_switch


def test_capacity_switch_surface_shape():
    out = build_capacity_switch_surface(base_url="https://nomad.example")
    assert out["schema"] == "nomad.capacity_switch_surface.v1"
    assert out["switch_url"] == "https://nomad.example/swarm/capacity-switch"
    assert out["next"]


def test_capacity_switch_routes_when_budget_depleted():
    surface = build_capacity_switch_surface(base_url="https://nomad.example")
    receipt = route_capacity_switch(
        {
            "local_token_balance": 0.1,
            "min_token_threshold": 1.0,
            "local_capacity_utilization": 0.3,
            "objective": "settlement_capacity_builder",
        },
        base_url="https://nomad.example",
        capacity_surface=surface,
    )
    assert receipt["schema"] == "nomad.capacity_switch_receipt.v1"
    assert receipt["switch"] is True
    assert "token_budget_depleted" in receipt["reason_codes"]


def test_capacity_switch_observes_when_no_trigger():
    receipt = route_capacity_switch(
        {
            "local_token_balance": 10.0,
            "min_token_threshold": 1.0,
            "local_capacity_utilization": 0.5,
            "max_utilization_threshold": 0.95,
        },
        base_url="https://nomad.example",
    )
    assert receipt["switch"] is False
    assert receipt["route"] == "observe_local"

