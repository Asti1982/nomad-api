from nomad_operator_runway import build_operator_runway_surface
from nomad_viability_kernel import build_viability_kernel_surface, route_viability_action


def _kernel(operator_state="critical", paid=0.0):
    runway = build_operator_runway_surface(
        monthly_min_eur=1200.0,
        liquid_cash_eur=100.0 if operator_state == "critical" else 4000.0,
        expected_income_30d_eur=0.0,
        operator_befinden=operator_state,
    )
    external = {
        "schema": "nomad.external_value_summary.v1",
        "revenue_recognized_usd_total": paid,
        "stage_counts": {"submitted": 3, "merged": 1, "paid": 1 if paid else 0},
    }
    receipts = {"recognized_revenue_usd": paid, "receipt_classes": {"claim_credit": 1, "settlement_credit": 1 if paid else 0}}
    stable = {"public_transferable_launch_state": "blocked_public_transferable_issuance"}
    treasury = {"token_units_minted": 0.0}
    return build_viability_kernel_surface(
        base_url="https://www.syndiode.com",
        operator_runway=runway,
        external_value_summary=external,
        work_receipt_summary=receipts,
        stable_unit_policy=stable,
        treasury_policy=treasury,
    )


def test_critical_operator_allows_only_cashflow_and_settlement_actions():
    kernel = _kernel("critical", paid=0.0)

    assert kernel["schema"] == "nomad.viability_kernel.v1"
    assert kernel["state_vector"]["operator_state"] == "critical"
    assert "paid_work_execute" in kernel["admissible_actions"]
    assert "settlement_reconcile" in kernel["admissible_actions"]
    assert "unpaid_value_cycle" not in kernel["admissible_actions"]
    assert "public_token_mint" in kernel["blocked_actions"]
    assert kernel["state_vector"]["viability_index"] < 0


def test_route_rejects_token_and_public_stablecoin_actions():
    kernel = _kernel("stable", paid=100.0)

    token = route_viability_action({"action_type": "public_token_mint"}, viability_kernel=kernel)
    stable = route_viability_action({"action_type": "public_stablecoin_issuance"}, viability_kernel=kernel)

    assert token["decision"] == "reject"
    assert "blocked_by_kernel_invariant" in token["reasons"]
    assert stable["decision"] == "reject"
    assert "blocked_by_kernel_invariant" in stable["reasons"]


def test_route_allows_paid_work_under_critical_state():
    kernel = _kernel("critical", paid=0.0)

    out = route_viability_action({"action_type": "paid_work_preflight", "target_url": "https://example.com/task"}, viability_kernel=kernel)

    assert out["ok"] is True
    assert out["decision"] == "allow"
    assert out["operator_state"] == "critical"


def test_route_rejects_state_dependency_even_if_action_type_is_allowed():
    kernel = _kernel("critical", paid=0.0)

    out = route_viability_action(
        {
            "action_type": "operator_runway_support",
            "note": "Use Arbeitsagentur or Wohngeld route",
        },
        viability_kernel=kernel,
    )

    assert out["decision"] == "reject"
    assert "state_dependency_rejected" in out["reasons"]


def test_warning_or_stable_state_changes_admissible_set_but_keeps_paid_gate():
    warning = _kernel("strained", paid=0.0)
    stable_paid = _kernel("stable", paid=100.0)
    stable_unpaid = _kernel("stable", paid=0.0)

    assert "paid_channel_scout" in warning["admissible_actions"]
    assert "swarm_worker_onboarding" not in warning["admissible_actions"]
    assert "swarm_worker_onboarding" in stable_paid["admissible_actions"]
    assert "token_design_research" in stable_paid["admissible_actions"]
    assert "token_design_research" not in stable_unpaid["admissible_actions"]


def test_viability_kernel_surface_has_no_state_support_refs():
    kernel = _kernel("critical", paid=0.0)
    text = str(kernel).lower()

    assert "buergergeld" not in text
    assert "bürgergeld" not in text
    assert "wohngeld" not in text
    assert "caritas" not in text
    assert "arbeitsagentur" not in text
    assert "jobcenter" not in text
