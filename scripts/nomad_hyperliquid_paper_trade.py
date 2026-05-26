#!/usr/bin/env python3
import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nomad_hyperliquid_shadow_bot import build_hyperliquid_shadow_bot_artifact


INFO_URL = "https://api.hyperliquid.xyz/info"


def _post_json(url: str, payload: Dict[str, Any], *, timeout: int = 30) -> Dict[str, Any]:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=raw,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "nomad-hyperliquid-paper-trade/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body else None
            return {"ok": True, "status": response.status, "data": data}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "error": body[:500]}


def fetch_candles(*, coin: str, interval: str, hours: int, end_ms: int | None = None) -> List[Dict[str, Any]]:
    end = int(end_ms or time.time() * 1000)
    start = end - int(hours * 60 * 60 * 1000)
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin.upper(),
            "interval": interval,
            "startTime": start,
            "endTime": end,
        },
    }
    result = _post_json(INFO_URL, payload)
    if not result.get("ok"):
        raise RuntimeError(f"Hyperliquid info request failed: {result}")
    data = result.get("data")
    if not isinstance(data, list):
        raise RuntimeError(f"Hyperliquid candleSnapshot returned non-list payload: {str(data)[:240]}")
    return data


def build_receipt(args: argparse.Namespace) -> Dict[str, Any]:
    candles = fetch_candles(coin=args.coin, interval=args.interval, hours=args.hours)
    closes = [float(item["c"]) for item in candles if isinstance(item, dict) and item.get("c") is not None]
    artifact = build_hyperliquid_shadow_bot_artifact(
        goal=(
            f"Paper trade {args.coin.upper()} on Hyperliquid with volatility-scaled time-series momentum, "
            f"{args.max_drawdown:g}% max drawdown, ${args.max_notional:g} shadow notional cap, no live orders."
        ),
        risk_envelope={
            "risk_profile": args.risk_profile,
            "max_drawdown": str(args.max_drawdown),
            "max_notional": str(args.max_notional),
            "max_leverage": str(args.max_leverage),
            "allowed_markets": [args.coin.upper()],
        },
        strategy_request={"strategy_type": "volatility-scaled time-series momentum"},
        allowed_markets=[args.coin.upper()],
        candles=closes,
    )
    return {
        "schema": "nomad.hyperliquid_paper_trade_receipt.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {
            "venue": "hyperliquid",
            "api": INFO_URL,
            "method": "POST /info candleSnapshot",
            "coin": args.coin.upper(),
            "interval": args.interval,
            "hours": args.hours,
            "candles_returned": len(candles),
            "close_values": closes,
        },
        "mode": "paper_trade_only",
        "funds_used": False,
        "wallet_signature_used": False,
        "exchange_order_submitted": False,
        "solana_bridge_used": False,
        "counts_as_revenue": False,
        "artifact": artifact,
    }


def maybe_submit_to_syndiode(receipt: Dict[str, Any], *, base_url: str) -> Dict[str, Any]:
    artifact = receipt.get("artifact") if isinstance(receipt.get("artifact"), dict) else {}
    risk = artifact.get("risk_controls") if isinstance(artifact.get("risk_controls"), dict) else {}
    signal = artifact.get("signal_receipt") if isinstance(artifact.get("signal_receipt"), dict) else {}
    source = receipt.get("source") if isinstance(receipt.get("source"), dict) else {}
    closes = source.get("close_values") if isinstance(source.get("close_values"), list) else []
    payload = {
        "requester_id": "nomad-hyperliquid-paper-trade-runner",
        "source": "nomad_hyperliquid_paper_trade_runner",
        "service_type": "hyperliquid_bot_repair_and_execution",
        "problem": (
            f"Verify paper-only Hyperliquid {source.get('coin', 'BTC')} bot receipt: "
            f"signal={signal.get('signal')}, artifact={artifact.get('artifact_digest')}"
        ),
        "chain_targets": "hyperliquid",
        "risk_profile": "low",
        "max_drawdown": str(risk.get("max_drawdown_pct") or ""),
        "max_notional": str(risk.get("max_notional_usd_shadow") or ""),
        "max_leverage": str(risk.get("max_leverage_shadow_cap") or ""),
        "allowed_markets": [source.get("coin", "BTC")],
        "strategy_type": "volatility-scaled time-series momentum",
        "candles": closes,
        "evidence": [
            f"paper_trade_receipt_schema={receipt.get('schema')}",
            f"artifact_digest={artifact.get('artifact_digest')}",
            "exchange_order_submitted=false",
            "wallet_signature_used=false",
        ],
        "accepted_compute_barter_terms": True,
        "create_paid_task": False,
    }
    return _post_json(base_url.rstrip("/") + "/swarm/reliability-doctor/intake", payload, timeout=45)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Nomad Hyperliquid paper trade receipt using public market data.")
    parser.add_argument("--coin", default="BTC")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--hours", type=int, default=72)
    parser.add_argument("--risk-profile", default="low")
    parser.add_argument("--max-drawdown", type=float, default=3.0)
    parser.add_argument("--max-notional", type=float, default=5.0)
    parser.add_argument("--max-leverage", type=float, default=1.0)
    parser.add_argument("--out-dir", default="data/hyperliquid-paper-trades")
    parser.add_argument("--submit-syndiode", action="store_true")
    parser.add_argument("--base-url", default="https://www.syndiode.com/nomad")
    args = parser.parse_args()

    receipt = build_receipt(args)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{stamp}_{args.coin.upper()}_{args.interval}_paper_trade_receipt.json"
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "ok": True,
        "receipt_path": str(out_path),
        "artifact_digest": receipt["artifact"]["artifact_digest"],
        "signal": receipt["artifact"]["signal_receipt"]["signal"],
        "side": receipt["artifact"]["paper_order_intent"]["side"],
        "client_order_id": receipt["artifact"]["paper_order_intent"]["client_order_id"],
        "candles_returned": receipt["source"]["candles_returned"],
        "exchange_order_submitted": False,
        "wallet_signature_used": False,
        "counts_as_revenue": False,
    }
    if args.submit_syndiode:
        submitted = maybe_submit_to_syndiode(receipt, base_url=args.base_url)
        summary["syndiode_submission"] = submitted
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
