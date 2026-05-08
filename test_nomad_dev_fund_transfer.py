from nomad_dev_fund_transfer import execute_dev_fund_transfer


def test_dev_fund_transfer_skips_when_go_false(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_DEV_FUND_TRANSFER_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    out = execute_dev_fund_transfer(
        economics_snapshot={
            "go_no_go": {"go": False},
            "dev_fund_allocation": {"approved_transfer_eur": 10.0, "wallet": "0xabc"},
        },
        run_id="r1",
    )
    assert out["status"] == "skipped"
    assert out["reason"] == "go_no_go_false"


def test_dev_fund_transfer_simulates_in_shadow(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_DEV_FUND_TRANSFER_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("NOMAD_DEV_FUND_TRANSFER_MODE", "shadow")
    out = execute_dev_fund_transfer(
        economics_snapshot={
            "go_no_go": {"go": True},
            "dev_fund_allocation": {"approved_transfer_eur": 10.0, "wallet": "0xabc"},
        },
        run_id="r2",
    )
    assert out["status"] == "simulated"
    assert out["reason"] == "shadow_mode"


def test_dev_fund_transfer_queues_manual_payout(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_DEV_FUND_TRANSFER_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("NOMAD_DEV_FUND_MANUAL_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("NOMAD_DEV_FUND_TRANSFER_MODE", "manual")
    out = execute_dev_fund_transfer(
        economics_snapshot={
            "go_no_go": {"go": True},
            "dev_fund_allocation": {"approved_transfer_eur": 12.5, "wallet": "0xabc"},
        },
        run_id="r3",
    )
    assert out["status"] == "queued_manual"
    assert out["reason"] == "manual_queue_mode"


def test_dev_fund_transfer_forced_queue_ignores_go_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_DEV_FUND_TRANSFER_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("NOMAD_DEV_FUND_MANUAL_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("NOMAD_DEV_FUND_QUEUE_FORCE", "1")
    monkeypatch.setenv("NOMAD_DEV_FUND_QUEUE_FORCE_EUR", "3.5")
    out = execute_dev_fund_transfer(
        economics_snapshot={
            "go_no_go": {"go": False},
            "dev_fund_allocation": {"approved_transfer_eur": 0.0, "wallet": "0xabc"},
        },
        run_id="r4",
    )
    assert out["status"] == "queued_manual"
    assert out["reason"] == "forced_queue_mode"
    assert out["amount_eur"] == 3.5

