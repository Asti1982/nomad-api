import json
import sys

from nomad_hyperliquid_svw_agents import (
    build_hyperliquid_svw_copy_trader_surface,
    load_cached_hyperliquid_svw_copy_trader_surface,
    load_global_svw_asset_weights,
    rank_hyperliquid_svw_agents,
    score_hyperliquid_svw_agent,
)
from scripts.nomad_hyperliquid_svw_agents import extract_leaderboard_addresses


BASE_TIME = 1_760_000_000_000


def _fill(index, *, pnl, coin="SOL", fee=0.05, notional=1_000, dir_text="Close Long"):
    return {
        "time": BASE_TIME + index * 86_400_000,
        "coin": coin,
        "px": str(notional / 10),
        "sz": "10",
        "closedPnl": str(pnl),
        "fee": str(fee),
        "dir": dir_text,
    }


def test_svw_agent_score_rewards_repeatable_realized_receipts():
    fills = [_fill(index, pnl=8 + (index % 3), coin="SOL" if index % 2 else "ETH") for index in range(45)]

    score = score_hyperliquid_svw_agent(fills, address="0x1111111111111111111111111111111111111111")

    assert score["schema"] == "nomad.hyperliquid_svw_agent_score.v1"
    assert score["status"] == "scored_public_fills"
    assert score["paper_only"] is True
    assert score["exchange_order_submitted"] is False
    assert score["wallet_signature_used"] is False
    assert score["final_copy_score"] > 60
    assert score["agent_svw_score"] > 50
    assert score["global_asset_alignment_score"] > 80
    assert score["live_gate"]["status"] == "blocked"
    assert "private_key" in score["live_gate"]["nomad_will_not_request"]


def test_svw_agent_score_penalizes_liquidation_retry_loss():
    fills = [_fill(index, pnl=4, coin="PEPE") for index in range(20)]
    fills += [_fill(25, pnl=-250, coin="PEPE", fee=4, dir_text="Liquidated Long")]

    score = score_hyperliquid_svw_agent(fills, address="0x2222222222222222222222222222222222222222")

    assert score["components"]["retry_loss"] > 0.35
    assert score["evidence"]["liquidation_fill_count"] == 1
    assert score["global_asset_alignment_score"] < 30
    assert score["final_copy_score"] < 50


def test_svw_agent_ranking_picks_best_final_copy_score():
    strong = score_hyperliquid_svw_agent(
        [_fill(index, pnl=10, coin="SOL") for index in range(35)],
        address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    weak = score_hyperliquid_svw_agent(
        [_fill(index, pnl=-5, coin="DOGE") for index in range(35)],
        address="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )

    ranking = rank_hyperliquid_svw_agents([weak, strong])

    assert ranking["schema"] == "nomad.hyperliquid_svw_agent_ranking.v1"
    assert ranking["best_address"] == strong["address"]
    assert ranking["scores"][0]["final_copy_score"] >= ranking["scores"][1]["final_copy_score"]
    assert ranking["exchange_order_submitted"] is False


def test_extract_leaderboard_addresses_filters_and_sorts_candidates():
    rows = [
        {
            "ethAddress": "0x1111111111111111111111111111111111111111",
            "accountValue": "50000",
            "displayName": "steady",
            "windowPerformances": [["month", {"pnl": "900", "roi": "0.10", "vlm": "100000"}]],
        },
        {
            "ethAddress": "0x2222222222222222222222222222222222222222",
            "accountValue": "250",
            "displayName": "tiny",
            "windowPerformances": [["month", {"pnl": "5000", "roi": "20", "vlm": "10000"}]],
        },
        {
            "ethAddress": "0x3333333333333333333333333333333333333333",
            "accountValue": "80000",
            "displayName": "larger",
            "windowPerformances": [["month", {"pnl": "1200", "roi": "0.03", "vlm": "200000"}]],
        },
        {
            "ethAddress": "0x4444444444444444444444444444444444444444",
            "accountValue": "90000",
            "displayName": "paper_pnl",
            "windowPerformances": [["month", {"pnl": "10000", "roi": "0.20", "vlm": "0"}]],
        },
    ]

    selected = extract_leaderboard_addresses(
        rows,
        window="month",
        sort_by="pnl",
        limit=2,
        min_account_value=10_000,
        min_leaderboard_volume=1,
    )

    assert [item["address"] for item in selected] == [
        "0x3333333333333333333333333333333333333333",
        "0x1111111111111111111111111111111111111111",
    ]
    assert selected[0]["leaderboard_sort_value"] == 1200


def test_editable_global_svw_asset_weights_change_asset_alignment(tmp_path):
    weights_path = tmp_path / "weights.json"
    weights_path.write_text(
        json.dumps({"thesis": "Dog chain compute thesis", "asset_weights": {"DOGE": 0.96}}),
        encoding="utf-8",
    )
    config = load_global_svw_asset_weights(weights_path)

    score = score_hyperliquid_svw_agent(
        [_fill(index, pnl=5, coin="DOGE") for index in range(30)],
        address="0x5555555555555555555555555555555555555555",
        asset_weights=config["asset_weights"],
    )

    assert config["source"] == "editable_json"
    assert config["thesis"] == "Dog chain compute thesis"
    assert score["global_asset_alignment_score"] > 90


def test_copy_trader_surface_exposes_recommended_trader_and_live_gate():
    score = score_hyperliquid_svw_agent(
        [_fill(index, pnl=9, coin="SOL") for index in range(35)],
        address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    ranking = rank_hyperliquid_svw_agents([score])

    surface = build_hyperliquid_svw_copy_trader_surface(ranking, base_url="https://nomad.example")

    assert surface["schema"] == "nomad.hyperliquid_svw_copy_trader_surface.v1"
    assert surface["recommended_trader"]["address"] == score["address"]
    assert surface["recommended_trader"]["copy_mode"] == "watchlist_or_paper_only"
    assert surface["ranking"][0]["exchange_order_submitted"] is False
    assert surface["live_gate"]["status"] == "paper_only_watchlist"
    assert surface["links"]["self"] == "https://nomad.example/.well-known/nomad-hyperliquid-svw-agents.json"


def test_load_cached_copy_trader_surface_reads_snapshot_without_exchange_calls(tmp_path):
    score = score_hyperliquid_svw_agent(
        [_fill(index, pnl=7, coin="ETH") for index in range(35)],
        address="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )
    ranking = rank_hyperliquid_svw_agents([score])
    snapshot = tmp_path / "latest.json"
    snapshot.write_text(json.dumps(ranking), encoding="utf-8")

    surface = load_cached_hyperliquid_svw_copy_trader_surface(
        snapshot_path=snapshot,
        base_url="https://nomad.example",
    )

    assert surface["recommended_trader"]["address"] == score["address"]
    assert surface["source"]["cached_snapshot_path"] == str(snapshot)
    assert surface["source"]["public_request_fetches_exchange"] is False


def test_cli_writes_latest_public_snapshot(tmp_path, monkeypatch, capsys):
    import scripts.nomad_hyperliquid_svw_agents as cli

    address = "0x9999999999999999999999999999999999999999"
    monkeypatch.setattr(cli, "fetch_user_fills", lambda wallet, *, days: [_fill(index, pnl=6, coin="SOL") for index in range(32)])
    monkeypatch.setattr(cli, "fetch_clearinghouse_state", lambda wallet: {})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nomad_hyperliquid_svw_agents.py",
            address,
            "--out-dir",
            str(tmp_path),
            "--latest-name",
            "latest.json",
        ],
    )

    assert cli.main() == 0
    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)

    assert latest["schema"] == "nomad.hyperliquid_svw_copy_trader_surface.v1"
    assert latest["recommended_trader"]["address"] == address
    assert printed["recommended_trader"]["address"] == address
    assert latest["live_gate"]["live_copy_trading_enabled"] is False
