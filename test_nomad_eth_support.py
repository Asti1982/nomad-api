from nomad_eth_support import build_eth_ai_agent_support_surface


def test_eth_ai_agent_support_surface_exposes_public_goods_packet(monkeypatch):
    monkeypatch.setenv("NOMAD_TELEGRAM_COMPUTE_PLEDGE_NATIVE", "0.005")
    monkeypatch.setenv("NOMAD_ETH_SUPPORT_BUDGET_USD", "12000")

    out = build_eth_ai_agent_support_surface(base_url="https://nomad.example")

    assert out["schema"] == "nomad.ethereum_ai_agent_support.v1"
    assert out["proposal_packet"]["ask_usd"] == 12000.0
    assert out["nomad_links"]["miniapp"] == "https://nomad.example/telegram-miniapp"
    assert out["nomad_links"]["pledge"] == "https://nomad.example/machine-treasury/pledge"
    assert out["nomad_links"]["proposal_markdown"].endswith("/downloads/nomad_ethereum_ai_agent_support_proposal.md")
    tracks = {row["track_id"]: row for row in out["support_tracks"]}
    assert tracks["dacc_eth_pledge"]["min_amount_native"] == 0.005
    assert tracks["ai_agent_recruitment"]["entrypoints"]
    assert "https://ai.ethereum.foundation/" in out["official_context_links"].values()
    assert out["accounting_policy"]["cursor_referrals"] == "usage_credit_offset_not_cash_revenue"
