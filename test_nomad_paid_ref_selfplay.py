from nomad_paid_ref_forge import build_paid_ref_market
from nomad_paid_ref_selfplay import run_paid_ref_selfplay
from nomad_survival_market import build_survival_market


def _survival_market() -> dict:
    return build_survival_market(
        base_url="https://nomad.example",
        machine_product_surface={"product_digest": "product-test"},
        carrying_market={"top_contract": {"contract_id": "state_relay_digest_quorum"}},
        microtask_metrics={"totals": {"settled_eur": 0}},
        worker_fleet={"active_worker_count": 0},
        intent_ledger_path="does-not-exist-selfplay.jsonl",
    )


def test_paid_ref_selfplay_runs_thousand_agents_without_minting_revenue():
    survival = _survival_market()
    paid = build_paid_ref_market(
        base_url="https://nomad.example",
        survival_market=survival,
        ledger_path="does-not-exist-paid-ref.jsonl",
    )

    out = run_paid_ref_selfplay(
        base_url="https://nomad.example",
        survival_market=survival,
        paid_ref_market=paid,
        agent_count=1000,
        seed="fixed",
    )

    assert out["schema"] == "nomad.paid_ref_selfplay.v1"
    assert out["agent_count"] == 1000
    assert out["mechanism"] == "synthetic_contract_net_posted_price_selfplay_no_fake_revenue"
    assert out["summary"]["quote_ready_agents"] > 0
    assert out["summary"]["payment_ready_agents"] > 0
    assert out["summary"]["verifier_ready_agents"] > 0
    assert out["top_packet_pressures"]
    assert out["top_archetypes"]
    assert out["top_quote_payloads"]
    assert out["next"]["quote_url"] == "https://nomad.example/swarm/paid-ref/quote"
    assert out["next"]["verify_url"] == "https://nomad.example/swarm/paid-ref/verify"
    assert "do_not_mint_revenue_from_selfplay" in out["machine_instruction"]
    assert "amount_eur_24h" not in out
    assert "paid_ref" not in out["top_quote_payloads"][0]


def test_paid_ref_selfplay_is_deterministic_for_same_seed():
    survival = _survival_market()
    paid = build_paid_ref_market(
        base_url="https://nomad.example",
        survival_market=survival,
        ledger_path="does-not-exist-paid-ref.jsonl",
    )

    first = run_paid_ref_selfplay(
        base_url="https://nomad.example",
        survival_market=survival,
        paid_ref_market=paid,
        agent_count=250,
        seed="fixed",
    )
    second = run_paid_ref_selfplay(
        base_url="https://nomad.example",
        survival_market=survival,
        paid_ref_market=paid,
        agent_count=250,
        seed="fixed",
    )

    assert first["selfplay_digest"] == second["selfplay_digest"]
    assert first["summary"] == second["summary"]
    assert first["top_packet_pressures"] == second["top_packet_pressures"]
    assert first["top_quote_payloads"] == second["top_quote_payloads"]


def test_cli_paid_ref_selfplay_returns_quote_payloads():
    from nomad_cli import run_once

    out = run_once(["paid-ref-selfplay", "--base-url", "https://nomad.example", "--agents", "100", "--seed", "fixed", "--json"])

    assert out["schema"] == "nomad.paid_ref_selfplay.v1"
    assert out["agent_count"] == 100
    assert out["top_quote_payloads"]
