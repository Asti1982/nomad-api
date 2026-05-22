from nomad_sustainability_kernel import build_sustainability_kernel


def test_sustainability_kernel_combines_three_loops_without_fake_utility():
    out = build_sustainability_kernel(
        base_url="https://nomad.example",
        work_exchange={
            "external_utility_status": {
                "stage": "needs_first_external_obligation",
                "visible_external_utility": False,
                "next_action": "send_secret_free_reliability_doctor_intake",
            },
            "ledger_summary": {"obligation_count": 0, "return_receipt_count": 0},
        },
        referral_swarm={"active_owned_arms": [{"arm_id": "owned"}], "blocked_arms": [{"arm_id": "cold"}]},
        machine_treasury={"objective_totals": {}},
        telegram_a2a={"configured": {"enabled": False, "allowed_targets": []}},
        acquisition_bandit={"channels": [{"channel_id": "external_worker_opportunity"}]},
        retention_watchdog={"issue": "external_workers_need_heartbeat"},
    )

    assert out["schema"] == "nomad.sustainability_kernel.v1"
    assert out["external_loop_live"] is False
    ids = {channel["channel_id"] for channel in out["channels"]}
    assert "verified_return_compute" in ids
    assert "proof_backed_pledge_pressure" in ids
    assert "owned_referral_credit_offsets" in ids
    assert "telegram_a2a_opt_in_transport" in ids
    assert "external_worker_retention" in ids
    assert "fake_reliability_doctor_intakes" in out["hard_no"]
    assert out["privacy_and_anonymity_model"]["wallet"].startswith("optional")
    assert out["downloads"]["sustainability_worker_py"] == "https://nomad.example/downloads/nomad_sustainability_worker.py"


def test_sustainability_kernel_marks_external_loop_live_for_real_receipts_or_pressure():
    out = build_sustainability_kernel(
        base_url="https://nomad.example",
        work_exchange={
            "external_utility_status": {"stage": "active_external_value_cycle", "visible_external_utility": True},
            "ledger_summary": {"obligation_count": 1, "return_receipt_count": 1},
        },
        machine_treasury={"objective_totals": {"settlement_capacity_builder": {"pressure_units": 0.5}}},
    )

    assert out["external_loop_live"] is True
    pledge = next(channel for channel in out["channels"] if channel["channel_id"] == "proof_backed_pledge_pressure")
    assert pledge["pressure_units"] == 0.5
