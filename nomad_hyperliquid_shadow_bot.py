import hashlib
import json
import math
from typing import Any, Dict, List


def _clean_text(value: Any, limit: int = 160) -> str:
    return str(value or "").strip().replace("\x00", "")[:limit]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip().replace("%", ""))
    except (TypeError, ValueError):
        return default


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _market_from(markets: Any) -> str:
    raw = markets if isinstance(markets, list) else str(markets or "").replace("/", ",").split(",")
    for item in raw:
        market = _clean_text(item, 32).upper().replace("-PERP", "").replace("USDC", "").strip("-_ ")
        if market:
            return market
    return "BTC"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _close_series(candles: Any) -> List[float]:
    if not isinstance(candles, list):
        return []
    closes: List[float] = []
    for candle in candles[:500]:
        if isinstance(candle, dict):
            close = candle.get("close") or candle.get("c") or candle.get("px")
        else:
            close = candle
        number = _num(close, 0.0)
        if number > 0:
            closes.append(number)
    return closes


def evaluate_shadow_candles(candles: Any, *, risk_envelope: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return deterministic paper-only signal diagnostics from public candle closes."""
    closes = _close_series(candles)
    risk = risk_envelope or {}
    max_drawdown_pct = _clamp(_num(risk.get("max_drawdown"), 3.0) or 3.0, 0.25, 25.0)
    if len(closes) < 25:
        return {
            "schema": "nomad.hyperliquid_shadow_signal.v1",
            "status": "insufficient_public_candles",
            "required_min_closes": 25,
            "provided_closes": len(closes),
            "signal": "flat",
            "target_position_fraction": 0.0,
            "paper_only": True,
        }

    short = sum(closes[-5:]) / 5.0
    long = sum(closes[-20:]) / 20.0
    returns = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0]
    recent_returns = returns[-20:]
    mean = sum(recent_returns) / len(recent_returns)
    variance = sum((item - mean) ** 2 for item in recent_returns) / len(recent_returns)
    realized_vol = math.sqrt(variance) if variance > 0 else 0.0
    trend_strength = (short / long) - 1.0 if long > 0 else 0.0
    vol_gate = realized_vol <= 0.025
    deadband = 0.0015
    raw_signal = "long" if trend_strength > deadband and vol_gate else "short" if trend_strength < -deadband and vol_gate else "flat"
    risk_scale = _clamp(max_drawdown_pct / 10.0, 0.05, 0.5)
    target = risk_scale if raw_signal == "long" else -risk_scale if raw_signal == "short" else 0.0
    return {
        "schema": "nomad.hyperliquid_shadow_signal.v1",
        "status": "paper_signal_ready",
        "signal": raw_signal,
        "target_position_fraction": round(target, 4),
        "short_ma": round(short, 8),
        "long_ma": round(long, 8),
        "trend_strength": round(trend_strength, 8),
        "realized_vol_20": round(realized_vol, 8),
        "volatility_gate_passed": vol_gate,
        "paper_only": True,
    }


def build_hyperliquid_shadow_bot_artifact(
    *,
    goal: str,
    risk_envelope: Dict[str, Any],
    strategy_request: Dict[str, Any],
    allowed_markets: Any = None,
    candles: Any = None,
) -> Dict[str, Any]:
    market = _market_from(allowed_markets or risk_envelope.get("allowed_markets"))
    max_drawdown_pct = _clamp(_num(risk_envelope.get("max_drawdown"), 3.0) or 3.0, 0.25, 25.0)
    max_leverage = _clamp(_num(risk_envelope.get("max_leverage"), 1.0) or 1.0, 1.0, 3.0)
    max_notional = _clamp(_num(risk_envelope.get("max_notional"), 10.0) or 10.0, 1.0, 100.0)
    signal = evaluate_shadow_candles(candles, risk_envelope=risk_envelope)
    side = "buy" if signal.get("target_position_fraction", 0.0) > 0 else "sell" if signal.get("target_position_fraction", 0.0) < 0 else "flat"
    intent_seed = {
        "market": market,
        "side": side,
        "goal": _clean_text(goal, 240),
        "risk": {
            "max_drawdown_pct": max_drawdown_pct,
            "max_leverage": max_leverage,
            "max_notional_usd_shadow": max_notional,
        },
        "signal_digest": _digest(signal, 24),
    }
    artifact = {
        "schema": "nomad.hyperliquid_shadow_bot_artifact.v1",
        "status": "paper_only_ready",
        "venue": "hyperliquid",
        "execution_mode": "shadow_lane_no_live_orders",
        "selected_strategy": {
            "id": "volatility_scaled_time_series_momentum",
            "summary": "Paper-only trend-following signal with volatility gate, position cap, drawdown stop, and flat default.",
            "scientific_basis": [
                "time_series_momentum",
                "volatility_targeting",
                "drawdown_limited_position_sizing",
                "idempotent_order_intent_repair",
            ],
            "why_this_instead_of_grid_or_martingale": "Bounded trend/volatility logic is easier to test and repair; no averaging-down loop is allowed.",
        },
        "market": market,
        "risk_controls": {
            "max_drawdown_pct": max_drawdown_pct,
            "max_leverage_shadow_cap": max_leverage,
            "max_notional_usd_shadow": max_notional,
            "default_state": "flat",
            "kill_switches": [
                "drawdown_limit_hit",
                "volatility_gate_failed",
                "duplicate_cloid_seen",
                "stale_or_missing_market_data",
                "manual_live_approval_missing",
            ],
        },
        "signal_receipt": signal,
        "paper_order_intent": {
            "schema": "nomad.hyperliquid_paper_order_intent.v1",
            "market": market,
            "side": side,
            "target_position_fraction": signal.get("target_position_fraction", 0.0),
            "client_order_id": f"nomad-shadow-{_digest(intent_seed, 20)}",
            "post_only_preferred": True,
            "reduce_only_required_for_exits": True,
            "exchange_endpoint_call_allowed": False,
            "signed_payload_present": False,
        },
        "repair_policy": {
            "idempotency": "client_order_id digest must stay stable for same market, signal, and risk envelope",
            "retry_budget": "one changed-evidence retry in paper mode; no blind resubmission",
            "handoff_guard": "stuck approval or payment state returns a receipt, not an order",
            "loop_detection": "three consecutive flat/blocked receipts stop the lane until new data arrives",
        },
        "live_gate": {
            "status": "blocked",
            "requirements": [
                "verified paid task or verified return-compute receipt",
                "explicit operator live-execution approval",
                "Hyperliquid API wallet approved outside chat",
                "testnet or paper receipt reviewed before mainnet",
                "hard notional, leverage, market, and loss caps",
            ],
            "nomad_will_not_request": ["seed_phrase", "private_key", "withdrawal_capable_credential"],
        },
        "performance_receipt_candidate": {
            "schema": "nomad.hyperliquid_shadow_performance_receipt.v1",
            "status": "requires_replay_or_public_candles",
            "counts_as_revenue": False,
            "counts_as_live_trading": False,
        },
    }
    artifact["artifact_digest"] = f"sha256:{_digest(artifact, 64)}"
    return artifact
