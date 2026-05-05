import json

from nomad_machine_economy import machine_economy_snapshot


def test_machine_economy_reads_settlement_and_overmint_pressure(tmp_path):
    service_path = tmp_path / "tasks.json"
    products_path = tmp_path / "products.json"
    mutual_path = tmp_path / "mutual.json"

    service_path.write_text(
        json.dumps(
            {
                "tasks": {
                    "svc-1": {
                        "status": "delivered",
                        "budget_native": 0.03,
                        "payment": {"status": "awaiting_payment", "amount_native": 0.03},
                    },
                    "svc-2": {
                        "status": "delivered",
                        "budget_native": 0.05,
                        "payment": {"status": "verified", "amount_native": 0.05},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    products_path.write_text(
        json.dumps(
            {
                "products": {
                    "prod-1": {
                        "status": "offer_ready",
                        "sellable_now": True,
                        "sellable_channels": ["machine_readable_agent_endpoint"],
                        "machine_exchange": {"schema": "nomad.machine_exchange.v1"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    mutual_path.write_text(
        json.dumps(
            {
                "truth_density_ledger": [
                    {
                        "pain_type": "compute_auth",
                        "solution_title": "Provider Fallback Ladder",
                        "truth_score": 0.8,
                        "outcome": {"success": True},
                    },
                    {
                        "pain_type": "compute_auth",
                        "solution_title": "Provider Fallback Ladder",
                        "truth_score": 0.82,
                        "outcome": {"success": True},
                    },
                ],
                "paid_packs": {"pack-1": {"pain_type": "compute_auth"}},
                "modules": [
                    {"module_id": "m1", "pain_type": "compute_auth"},
                    {"module_id": "m2", "pain_type": "compute_auth"},
                    {"module_id": "m3", "pain_type": "compute_auth"},
                ],
            }
        ),
        encoding="utf-8",
    )

    out = machine_economy_snapshot(
        service_tasks_path=service_path,
        products_path=products_path,
        mutual_aid_state_path=mutual_path,
    )

    assert out["schema"] == "nomad.machine_economy.v1"
    flows = out["resource_flows"]
    assert flows["service_tasks"]["unpaid_delivered"] == 1
    assert flows["products"]["machine_exchange_ready"] == 1
    assert flows["patterns"]["high_value_patterns"] == 1
    assert flows["modules"]["overmint_pressure"] > 0
    assert out["machine_viability"]["tier"] in {"starving", "experimental", "carrying", "compounding"}
    assert any(item["action"] == "compress_repeated_modules" for item in out["next_actions"])
