from nomad_stable_unit_policy import build_stable_unit_policy_surface, evaluate_stable_unit_preflight


def _attested_reserve(amount=200.0):
    return {
        "reserve_assets": [
            {
                "asset_id": "cash-1",
                "asset_type": "cash_or_cash_equivalent",
                "currency": "USD",
                "amount": amount,
                "haircut": 0.02,
                "liquidity_weight": 1.0,
                "custodian_ref": "bank-attestation-public-ref",
                "attestation_digest": "sha256:reserve-attestation",
            }
        ]
    }


def test_internal_stable_unit_preflight_simulates_without_transferable_mint():
    out = evaluate_stable_unit_preflight(
        {
            "mode": "internal_nontransferable",
            "requested_units": 100.0,
            **_attested_reserve(200.0),
        }
    )

    assert out["ok"] is True
    assert out["decision"] == "simulate_internal_nontransferable_units"
    assert out["simulated_internal_units"] == 100.0
    assert out["actual_transferable_units_minted"] == 0.0
    assert out["transferability"] == "non_transferable"
    assert out["redemption"]["liability_created"] is False


def test_public_transferable_stablecoin_is_rejected_without_regulatory_evidence():
    out = evaluate_stable_unit_preflight(
        {
            "mode": "public_transferable",
            "requested_units": 100.0,
            **_attested_reserve(200.0),
        }
    )

    assert out["ok"] is False
    assert out["decision"] == "reject_public_transferable_issuance"
    assert "public_transferable_issuance_requires_regulatory_evidence" in out["violations"]
    assert out["actual_transferable_units_minted"] == 0.0


def test_stable_unit_preflight_rejects_undercollateralized_or_unattested_reserve():
    out = evaluate_stable_unit_preflight(
        {
            "mode": "internal_nontransferable",
            "requested_units": 100.0,
            "reserve_assets": [
                {
                    "asset_id": "thin",
                    "amount": 50.0,
                    "haircut": 0.02,
                    "liquidity_weight": 1.0,
                }
            ],
        }
    )

    assert out["ok"] is False
    assert "reserve_attestation_and_custody_refs_required" in out["violations"]
    assert "insufficient_haircut_reserve_ratio" in out["violations"]
    assert out["simulated_internal_units"] == 0.0


def test_stable_unit_preflight_rejects_secret_shaped_payload():
    out = evaluate_stable_unit_preflight(
        {
            "mode": "simulation",
            "requested_units": 1.0,
            "api_key": "sk-test",
            **_attested_reserve(10.0),
        }
    )

    assert out["ok"] is False
    assert out["error"] == "secret_shaped_payload"


def test_stable_unit_policy_surface_exposes_blocked_public_launch():
    policy = build_stable_unit_policy_surface(
        base_url="https://www.syndiode.com",
        work_receipt_summary={"recognized_revenue_usd": 0.0},
        external_value_summary={"revenue_recognized_usd_total": 0.0},
    )

    assert policy["schema"] == "nomad.stable_unit_policy.v1"
    assert policy["public_transferable_launch_state"] == "blocked_public_transferable_issuance"
    assert policy["actual_transferable_supply"] == 0.0
    assert policy["public_offer"] is False
    assert policy["contracts"]["preflight"]["href"] == "https://www.syndiode.com/swarm/stable-unit/preflight"
