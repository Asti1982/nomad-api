from nomad_operator_runway import build_operator_runway_surface


def test_operator_runway_redacts_amounts_by_default():
    out = build_operator_runway_surface(
        monthly_min_eur=1200.0,
        liquid_cash_eur=100.0,
        expected_income_30d_eur=0.0,
        publish_amounts=False,
    )

    assert out["schema"] == "nomad.operator_runway.v1"
    assert out["privacy"]["public_amounts"] is False
    assert out["runway_state"] == "critical"
    assert out["runway_days"] == "redacted"
    assert out["monthly_min_eur"] == "redacted"
    assert out["liquid_cash_eur"] == "redacted"
    assert out["control_policy"]["work_mode"] == "survival_cashflow_first"
    assert out["control_policy"]["max_open_unpaid_value_cycles"] == 1
    assert out["control_policy"]["treasury_expansion_allowed"] is False
    assert "worldly_safety_links" not in out
    assert out["near_term_action_lanes"][2]["lane"] == "swarm_runway_support"


def test_operator_runway_can_show_amounts_locally_when_requested():
    out = build_operator_runway_surface(
        monthly_min_eur=1200.0,
        liquid_cash_eur=3600.0,
        expected_income_30d_eur=0.0,
        publish_amounts=True,
    )

    assert out["privacy"]["public_amounts"] is True
    assert out["runway_state"] == "stable"
    assert out["runway_days"] == 90.0
    assert out["monthly_min_eur"] == 1200.0
    assert out["liquid_cash_eur"] == 3600.0
    assert out["control_policy"]["treasury_expansion_allowed"] is True
    assert out["control_policy"]["max_open_unpaid_value_cycles"] == 4


def test_operator_befinden_can_dominate_nominal_cash_state():
    out = build_operator_runway_surface(
        monthly_min_eur=1200.0,
        liquid_cash_eur=3600.0,
        expected_income_30d_eur=0.0,
        operator_befinden="overloaded",
        publish_amounts=True,
    )

    assert out["runway_state"] == "stable"
    assert out["swarm_assessed_befinden_state"] == "overloaded"
    assert out["dominant_operator_state"] == "critical"
    assert out["control_policy"]["work_mode"] == "survival_cashflow_first"
    assert out["control_policy"]["treasury_expansion_allowed"] is False


def test_operator_runway_unknown_without_cash_measurement():
    out = build_operator_runway_surface(
        monthly_min_eur=1200.0,
        liquid_cash_eur=-1.0,
        expected_income_30d_eur=0.0,
    )

    assert out["runway_state"] == "unknown"
    assert out["runway_days"] == "unknown"
    assert out["control_policy"]["work_mode"] == "measure_runway_before_expansion"
    assert out["control_policy"]["max_open_unpaid_value_cycles"] == 1


def test_operator_runway_paid_signal_uses_real_revenue_only():
    out = build_operator_runway_surface(
        monthly_min_eur=1200.0,
        liquid_cash_eur=100.0,
        expected_income_30d_eur=0.0,
        external_value_summary={"revenue_recognized_usd_total": 16.88},
        work_receipt_summary={"recognized_revenue_usd": 0.0},
    )

    assert out["paid_signal"]["recognized_external_revenue_usd"] == 16.88
    assert "signals_do_not_feed_the_operator_until_paid" in out["paid_signal"]["rule"]


def test_operator_runway_surface_has_no_state_support_refs():
    out = build_operator_runway_surface(
        monthly_min_eur=1200.0,
        liquid_cash_eur=100.0,
        expected_income_30d_eur=0.0,
    )
    text = str(out).lower()

    assert "buergergeld" not in text
    assert "bürgergeld" not in text
    assert "wohngeld" not in text
    assert "caritas" not in text
    assert "arbeitsagentur" not in text
    assert "bmwsb" not in text
