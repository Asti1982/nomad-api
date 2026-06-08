"""SVW scoring for public Hyperliquid trader wallets.

This module treats a trader wallet as an SVW-producing agent. It only consumes
public trading evidence and never creates exchange orders or asks for secrets.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_SVW_AGENT_DIR = ROOT / "data" / "hyperliquid-svw-agents"
DEFAULT_GLOBAL_SVW_THESIS = (
    "Express the global SVW thesis through public trader agents that repeatedly convert "
    "market risk into realized, copyable receipts on assets tied to useful compute, AI, "
    "infrastructure, and settlement capacity."
)
GLOBAL_SVW_ASSET_WEIGHTS = {
    "SOL": 0.9,
    "ETH": 0.82,
    "HYPE": 0.78,
    "BTC": 0.48,
    "NVDA": 0.88,
    "TSLA": 0.78,
    "PLTR": 0.76,
    "GOOG": 0.72,
    "GOOGL": 0.72,
    "MSFT": 0.7,
    "AMZN": 0.66,
    "AMD": 0.64,
    "META": 0.62,
    "TAO": 0.84,
    "RNDR": 0.8,
    "RENDER": 0.8,
    "AKT": 0.78,
    "FET": 0.72,
    "ICP": 0.68,
    "NEAR": 0.64,
    "AR": 0.62,
    "LINK": 0.6,
    "PYTH": 0.58,
    "JUP": 0.56,
}

LOW_SVW_HINTS = ("PEPE", "FART", "DOGE", "SHIB", "BONK", "WIF", "MOG", "POPCAT")


def default_hyperliquid_svw_weights_path() -> Path:
    explicit = str(os.getenv("NOMAD_HYPERLIQUID_SVW_WEIGHTS_PATH") or "").strip()
    return Path(explicit) if explicit else DEFAULT_SVW_AGENT_DIR / "global_svw_asset_weights.json"


def default_hyperliquid_svw_snapshot_path() -> Path:
    explicit = str(os.getenv("NOMAD_HYPERLIQUID_SVW_AGENTS_SNAPSHOT") or "").strip()
    return Path(explicit) if explicit else DEFAULT_SVW_AGENT_DIR / "latest.json"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(str(value).strip().replace("%", ""))
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _asset_key(raw_coin: Any) -> str:
    coin = str(raw_coin or "").strip().upper()
    if ":" in coin:
        coin = coin.split(":")[-1]
    for suffix in ("-PERP", "-USDC", "/USDC", "USDC"):
        if coin.endswith(suffix):
            coin = coin[: -len(suffix)]
    return coin.strip("-_ ")


def _normalize_asset_weights(weights: dict[str, Any] | None) -> dict[str, float]:
    merged = dict(GLOBAL_SVW_ASSET_WEIGHTS)
    if not isinstance(weights, dict):
        return merged
    for asset, raw_weight in weights.items():
        key = _asset_key(asset)
        if key:
            merged[key] = round(_clamp(_num(raw_weight, merged.get(key, 0.42))), 6)
    return merged


def load_global_svw_asset_weights(path: str | Path | None = None) -> dict[str, Any]:
    """Load editable Global-SVW asset weights without mutating local state."""

    config_path = Path(path) if path else default_hyperliquid_svw_weights_path()
    if not config_path.exists():
        return {
            "schema": "nomad.hyperliquid_svw_asset_weights.v1",
            "source": "built_in_default",
            "path": str(config_path),
            "thesis": DEFAULT_GLOBAL_SVW_THESIS,
            "asset_weights": _normalize_asset_weights(None),
        }
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and any(key in raw for key in ("asset_weights", "weights", "global_svw_asset_weights")):
        raw_weights = raw.get("asset_weights") or raw.get("weights") or raw.get("global_svw_asset_weights")
        thesis = str(raw.get("thesis") or raw.get("summary") or DEFAULT_GLOBAL_SVW_THESIS).strip()
    elif isinstance(raw, dict):
        raw_weights = raw
        thesis = DEFAULT_GLOBAL_SVW_THESIS
    else:
        raw_weights = {}
        thesis = DEFAULT_GLOBAL_SVW_THESIS
    return {
        "schema": "nomad.hyperliquid_svw_asset_weights.v1",
        "source": "editable_json",
        "path": str(config_path),
        "thesis": thesis or DEFAULT_GLOBAL_SVW_THESIS,
        "asset_weights": _normalize_asset_weights(raw_weights if isinstance(raw_weights, dict) else {}),
    }


def _asset_svw_weight(raw_coin: Any, asset_weights: dict[str, Any] | None = None) -> float:
    coin = _asset_key(raw_coin)
    weights = _normalize_asset_weights(asset_weights)
    if not coin:
        return 0.35
    if coin in weights:
        return weights[coin]
    if any(hint in coin for hint in LOW_SVW_HINTS):
        return 0.18
    if coin.startswith("XYZ"):
        return 0.45
    return 0.42


def _fill_time_ms(fill: dict[str, Any]) -> int:
    return _int(fill.get("time") or fill.get("timestamp") or fill.get("t"))


def _fill_notional(fill: dict[str, Any]) -> float:
    px = _num(fill.get("px") or fill.get("price"))
    sz = abs(_num(fill.get("sz") or fill.get("size")))
    return px * sz


def _fill_fee(fill: dict[str, Any]) -> float:
    return _num(fill.get("fee"))


def _fill_closed_pnl(fill: dict[str, Any]) -> float:
    return _num(fill.get("closedPnl") or fill.get("closed_pnl") or fill.get("pnl"))


def _is_liquidation_fill(fill: dict[str, Any]) -> bool:
    haystack = " ".join(str(fill.get(key, "")) for key in ("dir", "type", "status", "action")).lower()
    return "liquidat" in haystack


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return worst


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    if gross_loss < 0:
        return gross_profit / abs(gross_loss)
    if gross_profit > 0:
        return 6.0
    return 0.0


def _component_scores(
    *,
    fills: list[dict[str, Any]],
    realized_net_pnl: float,
    gross_profit: float,
    gross_loss: float,
    total_notional: float,
    fee_paid: float,
    rebate_received: float,
    liquidation_count: int,
    open_position_count: int,
    asset_weights: dict[str, Any] | None = None,
) -> dict[str, float]:
    receipt_pnls = [_fill_closed_pnl(fill) - max(0.0, _fill_fee(fill)) for fill in fills if abs(_fill_closed_pnl(fill)) > 0]
    receipt_count = len(receipt_pnls)
    fill_count = len(fills)
    timestamps = [_fill_time_ms(fill) for fill in fills if _fill_time_ms(fill) > 0]
    span_days = (max(timestamps) - min(timestamps)) / 86_400_000 if len(timestamps) >= 2 else 0.0
    span_score = _clamp(span_days / 30.0)
    receipts_score = _clamp(math.log1p(receipt_count) / math.log1p(200))
    proof_density = _clamp(0.65 * receipts_score + 0.35 * span_score)

    profit_factor = _profit_factor(gross_profit, gross_loss)
    profit_factor_score = _clamp(math.log1p(min(profit_factor, 6.0)) / math.log1p(4.0))
    pnl_efficiency = realized_net_pnl / max(1.0, total_notional)
    efficiency_score = _clamp(0.5 + pnl_efficiency * 50.0)
    net_positive_gate = 1.0 if realized_net_pnl > 0 else 0.35 if realized_net_pnl == 0 else 0.05
    verified_state_improvement = _clamp((0.65 * profit_factor_score + 0.35 * efficiency_score) * net_positive_gate)

    win_count = len([pnl for pnl in receipt_pnls if pnl > 0])
    loss_count = len([pnl for pnl in receipt_pnls if pnl < 0])
    win_rate = win_count / max(1, win_count + loss_count)
    settlement_receipts = _clamp((win_rate * 0.45) + (profit_factor_score * 0.4) + (net_positive_gate * 0.15))

    cumulative = []
    running = 0.0
    for pnl in receipt_pnls:
        running += pnl
        cumulative.append(running)
    max_drawdown = _max_drawdown(cumulative)
    drawdown_severity = _clamp(abs(max_drawdown) / max(1.0, gross_profit, abs(realized_net_pnl)))
    fee_drag = _clamp(max(0.0, fee_paid - rebate_received) / max(1.0, abs(realized_net_pnl) + gross_profit))
    loss_rate = loss_count / max(1, win_count + loss_count)
    liquidation_penalty = _clamp(liquidation_count / max(1, receipt_count), 0.0, 1.0)
    open_risk_penalty = _clamp(open_position_count / 5.0)
    retry_loss = _clamp(
        0.28 * loss_rate
        + 0.32 * drawdown_severity
        + 0.18 * fee_drag
        + 0.3 * liquidation_penalty
        + 0.04 * open_risk_penalty,
        0.0,
        0.98,
    )

    reliability = _clamp((1.0 - retry_loss) * (0.45 + 0.55 * proof_density))
    traded_assets = {_asset_key(fill.get("coin")) for fill in fills if _asset_key(fill.get("coin"))}
    asset_focus = 1.0 - _clamp(abs(len(traded_assets) - 4) / 12.0)
    scarcity = _clamp(0.4 * profit_factor_score + 0.35 * reliability + 0.25 * asset_focus)

    days = max(span_days, 1.0)
    fills_per_day = fill_count / days
    cadence_score = 1.0
    if fills_per_day > 80:
        cadence_score = _clamp(1.0 - ((fills_per_day - 80.0) / 240.0), 0.05, 1.0)
    elif fills_per_day < 0.2:
        cadence_score = _clamp(fills_per_day / 0.2, 0.2, 1.0)
    size_score = _clamp(math.log1p(total_notional / max(1, fill_count)) / math.log1p(25_000))
    copyability = _clamp(0.45 * cadence_score + 0.35 * reliability + 0.20 * size_score)

    weighted_asset = 0.0
    for fill in fills:
        notional = _fill_notional(fill)
        weighted_asset += notional * _asset_svw_weight(fill.get("coin"), asset_weights)
    global_alignment = _clamp(weighted_asset / max(1.0, total_notional))

    return {
        "verified_state_improvement": verified_state_improvement,
        "settlement_receipt_quality": settlement_receipts,
        "proof_density": proof_density,
        "retry_loss": retry_loss,
        "reliability": reliability,
        "scarcity": scarcity,
        "copyability": copyability,
        "global_asset_alignment": global_alignment,
        "profit_factor_score": profit_factor_score,
        "win_rate": win_rate,
        "drawdown_severity": drawdown_severity,
        "fee_drag": fee_drag,
    }


def _open_position_count(clearinghouse_state: dict[str, Any] | None) -> int:
    state = clearinghouse_state if isinstance(clearinghouse_state, dict) else {}
    margin = state.get("marginSummary") if isinstance(state.get("marginSummary"), dict) else {}
    asset_positions = state.get("assetPositions") if isinstance(state.get("assetPositions"), list) else []
    count = 0
    for item in asset_positions:
        position = item.get("position") if isinstance(item, dict) and isinstance(item.get("position"), dict) else {}
        if abs(_num(position.get("szi"))) > 0:
            count += 1
    if count == 0 and _num(margin.get("totalMarginUsed")) > 0:
        count = 1
    return count


def score_hyperliquid_svw_agent(
    fills: list[dict[str, Any]],
    *,
    address: str = "",
    clearinghouse_state: dict[str, Any] | None = None,
    asset_weights: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Score one public wallet as a copyable SVW-producing trading agent."""

    clean_fills = [fill for fill in fills if isinstance(fill, dict)]
    clean_fills.sort(key=_fill_time_ms)
    open_positions = _open_position_count(clearinghouse_state)
    if not clean_fills:
        return {
            "schema": "nomad.hyperliquid_svw_agent_score.v1",
            "generated_at": generated_at or _iso_now(),
            "address": address,
            "status": "insufficient_public_fills",
            "paper_only": True,
            "exchange_order_submitted": False,
            "final_copy_score": 0.0,
            "agent_svw_score": 0.0,
            "copy_svw_score": 0.0,
            "global_asset_alignment_score": 0.0,
            "live_gate": {
                "status": "blocked",
                "reason": "scoring engine only; no copy trading without separate operator approval and risk caps",
            },
        }

    total_notional = sum(_fill_notional(fill) for fill in clean_fills)
    gross_closed_pnl = sum(_fill_closed_pnl(fill) for fill in clean_fills)
    fee_paid = sum(max(0.0, _fill_fee(fill)) for fill in clean_fills)
    rebate_received = sum(abs(min(0.0, _fill_fee(fill))) for fill in clean_fills)
    realized_net_pnl = gross_closed_pnl - fee_paid + rebate_received
    positive_receipts = [_fill_closed_pnl(fill) for fill in clean_fills if _fill_closed_pnl(fill) > 0]
    negative_receipts = [_fill_closed_pnl(fill) for fill in clean_fills if _fill_closed_pnl(fill) < 0]
    gross_profit = sum(positive_receipts)
    gross_loss = sum(negative_receipts)
    liquidation_count = len([fill for fill in clean_fills if _is_liquidation_fill(fill)])
    components = _component_scores(
        fills=clean_fills,
        realized_net_pnl=realized_net_pnl,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        total_notional=total_notional,
        fee_paid=fee_paid,
        rebate_received=rebate_received,
        liquidation_count=liquidation_count,
        open_position_count=open_positions,
        asset_weights=asset_weights,
    )
    agent_svw = 100.0 * (
        0.3 * components["verified_state_improvement"]
        + 0.2 * components["settlement_receipt_quality"]
        + 0.2 * components["proof_density"]
        + 0.15 * components["reliability"]
        + 0.15 * components["scarcity"]
    )
    agent_svw *= 1.0 - 0.65 * components["retry_loss"]
    agent_svw = _clamp(agent_svw, 0.0, 100.0)
    copy_svw = 100.0 * components["copyability"]
    global_alignment = 100.0 * components["global_asset_alignment"]
    final = _clamp(0.7 * agent_svw + 0.2 * copy_svw + 0.1 * global_alignment, 0.0, 100.0)

    first_time = min((_fill_time_ms(fill) for fill in clean_fills if _fill_time_ms(fill) > 0), default=0)
    last_time = max((_fill_time_ms(fill) for fill in clean_fills if _fill_time_ms(fill) > 0), default=0)
    assets: dict[str, float] = {}
    for fill in clean_fills:
        key = _asset_key(fill.get("coin")) or "UNKNOWN"
        assets[key] = assets.get(key, 0.0) + _fill_notional(fill)
    top_assets = [
        {
            "asset": asset,
            "notional": round(notional, 4),
            "global_svw_weight": round(_asset_svw_weight(asset, asset_weights), 4),
        }
        for asset, notional in sorted(assets.items(), key=lambda item: item[1], reverse=True)[:8]
    ]

    evidence = {
        "fill_count": len(clean_fills),
        "closed_receipt_count": len(positive_receipts) + len(negative_receipts),
        "first_fill_time_ms": first_time,
        "last_fill_time_ms": last_time,
        "total_notional_usd_approx": round(total_notional, 4),
        "gross_closed_pnl_usd": round(gross_closed_pnl, 4),
        "fee_paid_usd": round(fee_paid, 4),
        "rebate_received_usd": round(rebate_received, 4),
        "realized_net_pnl_usd": round(realized_net_pnl, 4),
        "gross_profit_usd": round(gross_profit, 4),
        "gross_loss_usd": round(gross_loss, 4),
        "profit_factor": round(_profit_factor(gross_profit, gross_loss), 4),
        "liquidation_fill_count": liquidation_count,
        "open_position_count": open_positions,
        "top_assets_by_notional": top_assets,
    }
    score = {
        "schema": "nomad.hyperliquid_svw_agent_score.v1",
        "generated_at": generated_at or _iso_now(),
        "address": address,
        "status": "scored_public_fills",
        "paper_only": True,
        "exchange_order_submitted": False,
        "wallet_signature_used": False,
        "agent_svw_score": round(agent_svw, 4),
        "copy_svw_score": round(copy_svw, 4),
        "global_asset_alignment_score": round(global_alignment, 4),
        "global_svw_thesis_version": "editable_asset_weights_v1",
        "final_copy_score": round(final, 4),
        "components": {key: round(value, 4) for key, value in components.items()},
        "evidence": evidence,
        "interpretation": _interpret(final, components, evidence),
        "live_gate": {
            "status": "blocked",
            "requirements": [
                "paper-live observation window",
                "explicit operator approval",
                "dedicated API wallet or subaccount",
                "max notional, max leverage, max daily loss, and kill switch",
            ],
            "nomad_will_not_request": ["seed_phrase", "private_key", "withdrawal_capable_credential"],
        },
    }
    score["score_digest"] = f"sha256:{_digest(score, 64)}"
    return score


def _interpret(final: float, components: dict[str, float], evidence: dict[str, Any]) -> str:
    if evidence.get("closed_receipt_count", 0) < 20:
        return "Too few closed receipts; useful watchlist candidate only."
    if components["retry_loss"] > 0.45:
        return "High retry loss; avoid copying unless later evidence improves."
    if final >= 75:
        return "Strong SVW-agent candidate for watchlist or paper-copy."
    if final >= 60:
        return "Promising but should be paper-copied before any live use."
    if final >= 45:
        return "Mixed evidence; monitor but do not prioritize."
    return "Weak SVW-agent evidence."


def rank_hyperliquid_svw_agents(agent_scores: list[dict[str, Any]], *, generated_at: str | None = None) -> dict[str, Any]:
    rows = [score for score in agent_scores if isinstance(score, dict)]
    rows.sort(key=lambda row: _num(row.get("final_copy_score")), reverse=True)
    return {
        "schema": "nomad.hyperliquid_svw_agent_ranking.v1",
        "generated_at": generated_at or _iso_now(),
        "status": "ranked_public_wallet_agents",
        "paper_only": True,
        "exchange_order_submitted": False,
        "count": len(rows),
        "best_address": rows[0].get("address") if rows else "",
        "best_final_copy_score": rows[0].get("final_copy_score") if rows else 0.0,
        "scores": rows,
        "ranking_digest": f"sha256:{_digest(rows, 64)}",
    }


def _compact_trader_row(score: dict[str, Any]) -> dict[str, Any]:
    evidence = score.get("evidence") if isinstance(score.get("evidence"), dict) else {}
    top_assets = evidence.get("top_assets_by_notional") if isinstance(evidence.get("top_assets_by_notional"), list) else []
    return {
        "address": str(score.get("address") or ""),
        "status": str(score.get("status") or ""),
        "final_copy_score": _num(score.get("final_copy_score")),
        "agent_svw_score": _num(score.get("agent_svw_score")),
        "copy_svw_score": _num(score.get("copy_svw_score")),
        "global_asset_alignment_score": _num(score.get("global_asset_alignment_score")),
        "interpretation": str(score.get("interpretation") or ""),
        "observed_assets": top_assets[:6],
        "timeframe": {
            "first_fill_time_ms": _int(evidence.get("first_fill_time_ms")),
            "last_fill_time_ms": _int(evidence.get("last_fill_time_ms")),
            "fill_count": _int(evidence.get("fill_count")),
            "closed_receipt_count": _int(evidence.get("closed_receipt_count")),
        },
        "risk": {
            "realized_net_pnl_usd": _num(evidence.get("realized_net_pnl_usd")),
            "profit_factor": _num(evidence.get("profit_factor")),
            "liquidation_fill_count": _int(evidence.get("liquidation_fill_count")),
            "open_position_count": _int(evidence.get("open_position_count")),
            "retry_loss": _num((score.get("components") or {}).get("retry_loss") if isinstance(score.get("components"), dict) else 0),
        },
        "paper_only": True,
        "exchange_order_submitted": False,
    }


def build_hyperliquid_svw_copy_trader_surface(
    ranking: dict[str, Any] | None,
    *,
    base_url: str = "",
    weights_config: dict[str, Any] | None = None,
    snapshot_path: str | Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Expose a cached, paper-only copy-trader surface for Nomad."""

    source_ranking = ranking if isinstance(ranking, dict) else {}
    scores = source_ranking.get("scores") if isinstance(source_ranking.get("scores"), list) else []
    compact_rows = [_compact_trader_row(row) for row in scores if isinstance(row, dict)]
    compact_rows.sort(key=lambda row: row["final_copy_score"], reverse=True)
    best = compact_rows[0] if compact_rows else {}
    config = weights_config if isinstance(weights_config, dict) else load_global_svw_asset_weights()
    weights = config.get("asset_weights") if isinstance(config.get("asset_weights"), dict) else _normalize_asset_weights(None)
    well_known = f"{base_url.rstrip('/')}/.well-known/nomad-hyperliquid-svw-agents.json" if base_url else "/.well-known/nomad-hyperliquid-svw-agents.json"
    active_assets = [
        {"asset": asset, "weight": weight}
        for asset, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True)
        if weight >= 0.6
    ][:16]
    recommended = {}
    if best:
        recommended = {
            "address": best["address"],
            "final_copy_score": best["final_copy_score"],
            "agent_svw_score": best["agent_svw_score"],
            "copy_svw_score": best["copy_svw_score"],
            "global_asset_alignment_score": best["global_asset_alignment_score"],
            "why": best["interpretation"],
            "observed_assets": best["observed_assets"],
            "timeframe": best["timeframe"],
            "watchlist_action": "paper_copy_candidate",
            "copy_mode": "watchlist_or_paper_only",
        }
    status = "cached_watchlist_ready" if compact_rows else "no_cached_ranking"
    return {
        "schema": "nomad.hyperliquid_svw_copy_trader_surface.v1",
        "generated_at": generated_at or str(source_ranking.get("generated_at") or _iso_now()),
        "status": status,
        "paper_only": True,
        "exchange_order_submitted": False,
        "wallet_signature_used": False,
        "recommended_trader": recommended,
        "ranking": compact_rows,
        "ranking_digest": source_ranking.get("ranking_digest") or f"sha256:{_digest(compact_rows, 64)}",
        "global_svw_thesis": {
            "schema": "nomad.global_svw_thesis.v1",
            "summary": str(config.get("thesis") or DEFAULT_GLOBAL_SVW_THESIS),
            "weights_source": str(config.get("source") or "built_in_default"),
            "editable_weights_path": str(config.get("path") or default_hyperliquid_svw_weights_path()),
            "asset_weights": weights,
            "active_assets": active_assets,
        },
        "live_gate": {
            "status": "paper_only_watchlist",
            "live_copy_trading_enabled": False,
            "reason": "Public SVW signal only; Nomad does not submit exchange orders from this surface.",
            "requirements_for_future_live_gate": [
                "explicit operator approval",
                "dedicated low-permission trading wallet or subaccount",
                "max notional, leverage, daily loss, and kill switch",
                "paper-copy observation window",
            ],
        },
        "source": {
            "venue": "hyperliquid",
            "cached_snapshot_path": str(snapshot_path or ""),
            "ranking_source": source_ranking.get("source") or {},
            "public_request_fetches_exchange": False,
        },
        "links": {
            "self": well_known,
            "alias": f"{base_url.rstrip('/')}/swarm/hyperliquid-svw-agents" if base_url else "/swarm/hyperliquid-svw-agents",
        },
    }


def load_cached_hyperliquid_svw_copy_trader_surface(
    *,
    snapshot_path: str | Path | None = None,
    weights_path: str | Path | None = None,
    base_url: str = "",
) -> dict[str, Any]:
    """Read the latest Hyperliquid SVW snapshot from disk; never calls Hyperliquid."""

    path = Path(snapshot_path) if snapshot_path else default_hyperliquid_svw_snapshot_path()
    weights = load_global_svw_asset_weights(weights_path)
    if not path.exists():
        return build_hyperliquid_svw_copy_trader_surface(
            {"schema": "nomad.hyperliquid_svw_agent_ranking.v1", "scores": [], "source": {}},
            base_url=base_url,
            weights_config=weights,
            snapshot_path=path,
        ) | {
            "status": "no_cached_snapshot",
            "refresh_hint": "Run scripts/nomad_hyperliquid_svw_agents.py --leaderboard to create the cached paper-only watchlist.",
        }
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and raw.get("schema") == "nomad.hyperliquid_svw_copy_trader_surface.v1":
        raw.setdefault("source", {})
        if isinstance(raw["source"], dict):
            raw["source"]["cached_snapshot_path"] = str(path)
            raw["source"]["public_request_fetches_exchange"] = False
        raw["links"] = {
            "self": f"{base_url.rstrip('/')}/.well-known/nomad-hyperliquid-svw-agents.json" if base_url else "/.well-known/nomad-hyperliquid-svw-agents.json",
            "alias": f"{base_url.rstrip('/')}/swarm/hyperliquid-svw-agents" if base_url else "/swarm/hyperliquid-svw-agents",
        }
        raw.setdefault("global_svw_thesis", build_hyperliquid_svw_copy_trader_surface({}, weights_config=weights)["global_svw_thesis"])
        raw.setdefault("paper_only", True)
        raw.setdefault("exchange_order_submitted", False)
        raw.setdefault("wallet_signature_used", False)
        return raw
    return build_hyperliquid_svw_copy_trader_surface(
        raw if isinstance(raw, dict) else {},
        base_url=base_url,
        weights_config=weights,
        snapshot_path=path,
    )
