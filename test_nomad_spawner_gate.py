from nomad_spawner_gate import build_spawner_gate, trigger_spawner


def test_spawner_gate_blocks_without_cashflow_streak():
    gate = build_spawner_gate(
        base_url="https://nomad.example",
        economics={"metrics": {"real_cashflow_24h_eur": 1.0}, "go_no_go": {"go": True}},
        funnel={"marginal_utility_per_cost": {"global_marginal_utility_per_cost": 2.0}},
        history_rows=[],
        transfer_rows=[{"status": "requested"}],
    )
    assert gate["schema"] == "nomad.spawner_gate.v1"
    assert gate["gate_open"] is False
    assert "cashflow_streak" in gate["failed_checks"]


def test_spawner_gate_opens_and_trigger_executes_with_idempotency(monkeypatch):
    monkeypatch.setenv("NOMAD_SPAWNER_CASHFLOW_MIN_EUR", "1.0")
    monkeypatch.setenv("NOMAD_SPAWNER_CASHFLOW_STREAK", "2")
    monkeypatch.setenv("NOMAD_SPAWNER_AGENT_COST_EUR", "1.0")
    monkeypatch.setenv("NOMAD_SPAWNER_SURPLUS_SHARE", "0.5")
    monkeypatch.setenv("NOMAD_SPAWNER_HARD_CAP", "4")
    gate = build_spawner_gate(
        base_url="https://nomad.example",
        economics={"metrics": {"real_cashflow_24h_eur": 6.0}, "go_no_go": {"go": True}},
        funnel={"marginal_utility_per_cost": {"global_marginal_utility_per_cost": 2.4}},
        history_rows=[
            {"economics": {"metrics": {"real_cashflow_24h_eur": 2.0}}},
            {"economics": {"metrics": {"real_cashflow_24h_eur": 3.0}}},
        ],
        transfer_rows=[{"status": "requested"}],
    )
    assert gate["gate_open"] is True
    out1 = trigger_spawner(
        base_url="https://nomad.example",
        gate=gate,
        idempotency_key="k1",
        commit=False,
    )
    out2 = trigger_spawner(
        base_url="https://nomad.example",
        gate=gate,
        idempotency_key="k1",
        commit=False,
    )
    assert out1["schema"] == "nomad.spawner_trigger.v1"
    assert out1["executed"] is True
    assert out1["spawn_result"]["committed"] is False
    assert out2["idempotent_replay"] is True

