from nomad_hyperliquid_shadow_bot import (
    build_hyperliquid_shadow_bot_artifact,
    evaluate_shadow_candles,
)


def test_hyperliquid_shadow_bot_defaults_to_paper_only_flat_without_data():
    artifact = build_hyperliquid_shadow_bot_artifact(
        goal="Create a tiny Hyperliquid bot for BTC with 3% drawdown.",
        risk_envelope={"max_drawdown": "3%", "max_notional": "5", "max_leverage": "1", "allowed_markets": ["BTC"]},
        strategy_request={"strategy_type": "trend with volatility filter"},
    )

    assert artifact["schema"] == "nomad.hyperliquid_shadow_bot_artifact.v1"
    assert artifact["execution_mode"] == "shadow_lane_no_live_orders"
    assert artifact["paper_order_intent"]["exchange_endpoint_call_allowed"] is False
    assert artifact["paper_order_intent"]["signed_payload_present"] is False
    assert artifact["signal_receipt"]["signal"] == "flat"
    assert artifact["live_gate"]["status"] == "blocked"
    assert "private_key" in artifact["live_gate"]["nomad_will_not_request"]
    assert artifact["artifact_digest"].startswith("sha256:")


def test_hyperliquid_shadow_bot_creates_deterministic_paper_intent_from_public_candles():
    candles = [{"close": 100 + index} for index in range(30)]

    first = build_hyperliquid_shadow_bot_artifact(
        goal="Paper trade BTC only.",
        risk_envelope={"max_drawdown": "3", "max_notional": "5", "max_leverage": "1", "allowed_markets": ["BTC"]},
        strategy_request={"strategy_type": "time-series momentum"},
        candles=candles,
    )
    second = build_hyperliquid_shadow_bot_artifact(
        goal="Paper trade BTC only.",
        risk_envelope={"max_drawdown": "3", "max_notional": "5", "max_leverage": "1", "allowed_markets": ["BTC"]},
        strategy_request={"strategy_type": "time-series momentum"},
        candles=candles,
    )

    assert first["signal_receipt"]["status"] == "paper_signal_ready"
    assert first["signal_receipt"]["signal"] == "long"
    assert first["paper_order_intent"]["side"] == "buy"
    assert first["paper_order_intent"]["client_order_id"] == second["paper_order_intent"]["client_order_id"]


def test_evaluate_shadow_candles_blocks_when_public_data_is_too_short():
    signal = evaluate_shadow_candles([100, 101, 102])

    assert signal["status"] == "insufficient_public_candles"
    assert signal["target_position_fraction"] == 0.0
    assert signal["paper_only"] is True
