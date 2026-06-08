#!/usr/bin/env python3
"""Build a paper-only SVW ranking for public Hyperliquid trader wallets."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nomad_hyperliquid_svw_agents import (
    build_hyperliquid_svw_copy_trader_surface,
    default_hyperliquid_svw_weights_path,
    load_global_svw_asset_weights,
    rank_hyperliquid_svw_agents,
    score_hyperliquid_svw_agent,
)


INFO_URL = "https://api.hyperliquid.xyz/info"
STATS_LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"


def _post_json(url: str, payload: dict[str, Any], *, timeout: int = 30) -> dict[str, Any]:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=raw,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "nomad-hyperliquid-svw-agents/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"ok": True, "status": response.status, "data": json.loads(body) if body else None}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "error": body[:500]}


def _get_json(url: str, *, timeout: int = 60) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": "nomad-hyperliquid-svw-agents/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"ok": True, "status": response.status, "data": json.loads(body) if body else None}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "error": body[:500]}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _valid_address(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) != 42 or not text.startswith("0x"):
        return False
    try:
        int(text[2:], 16)
        return True
    except ValueError:
        return False


def _window_performance(row: dict[str, Any], window: str) -> dict[str, Any]:
    performances = row.get("windowPerformances")
    if not isinstance(performances, list):
        return {}
    for item in performances:
        if isinstance(item, list) and len(item) == 2 and item[0] == window and isinstance(item[1], dict):
            return item[1]
    return {}


def fetch_leaderboard_rows() -> list[dict[str, Any]]:
    result = _get_json(STATS_LEADERBOARD_URL)
    if not result.get("ok"):
        raise RuntimeError(f"Hyperliquid leaderboard request failed: {result}")
    data = result.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"Hyperliquid leaderboard returned non-dict payload: {str(data)[:240]}")
    rows = data.get("leaderboardRows")
    if not isinstance(rows, list):
        raise RuntimeError("Hyperliquid leaderboard payload is missing leaderboardRows")
    return [row for row in rows if isinstance(row, dict)]


def extract_leaderboard_addresses(
    rows: list[dict[str, Any]],
    *,
    window: str = "month",
    sort_by: str = "pnl",
    limit: int = 20,
    min_account_value: float = 10_000.0,
    min_leaderboard_volume: float = 1.0,
) -> list[dict[str, Any]]:
    candidates = []
    for row in rows:
        address = str(row.get("ethAddress") or "").strip()
        if not _valid_address(address):
            continue
        account_value = _num(row.get("accountValue"))
        if account_value < min_account_value:
            continue
        perf = _window_performance(row, window)
        if sort_by == "accountValue":
            sort_value = account_value
        else:
            sort_value = _num(perf.get(sort_by))
        volume = _num(perf.get("vlm"))
        if volume < min_leaderboard_volume:
            continue
        if sort_value <= 0:
            continue
        candidates.append(
            {
                "address": address,
                "display_name": row.get("displayName"),
                "account_value": account_value,
                "window": window,
                "leaderboard_sort_by": sort_by,
                "leaderboard_sort_value": sort_value,
                "leaderboard_pnl": _num(perf.get("pnl")),
                "leaderboard_roi": _num(perf.get("roi")),
                "leaderboard_volume": volume,
            }
        )
    candidates.sort(key=lambda item: item["leaderboard_sort_value"], reverse=True)
    return candidates[: max(0, limit)]


def fetch_user_fills(address: str, *, days: int, end_ms: int | None = None) -> list[dict[str, Any]]:
    end = int(end_ms or time.time() * 1000)
    start = end - int(days * 86_400_000)
    payload = {
        "type": "userFillsByTime",
        "user": address,
        "startTime": start,
        "endTime": end,
        "aggregateByTime": True,
    }
    result = _post_json(INFO_URL, payload)
    if not result.get("ok"):
        raise RuntimeError(f"Hyperliquid userFillsByTime failed for {address}: {result}")
    data = result.get("data")
    if not isinstance(data, list):
        raise RuntimeError(f"Hyperliquid returned non-list fills for {address}: {str(data)[:240]}")
    return [item for item in data if isinstance(item, dict)]


def fetch_clearinghouse_state(address: str) -> dict[str, Any]:
    result = _post_json(INFO_URL, {"type": "clearinghouseState", "user": address})
    if not result.get("ok"):
        return {}
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _load_addresses(args: argparse.Namespace) -> list[str]:
    addresses = [item.strip() for item in args.addresses if item.strip()]
    if args.addresses_file:
        path = Path(args.addresses_file)
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                addresses.append(line)
    deduped = []
    seen = set()
    for address in addresses:
        if address not in seen:
            seen.add(address)
            deduped.append(address)
    invalid = [address for address in deduped if not _valid_address(address)]
    if invalid:
        raise SystemExit(f"Invalid Hyperliquid address(es): {', '.join(invalid)}")
    return deduped


def build_ranking(args: argparse.Namespace) -> dict[str, Any]:
    addresses = _load_addresses(args)
    weights_config = load_global_svw_asset_weights(args.weights_file)
    asset_weights = weights_config["asset_weights"]
    leaderboard_candidates = []
    if args.leaderboard:
        rows = fetch_leaderboard_rows()
        leaderboard_candidates = extract_leaderboard_addresses(
            rows,
            window=args.leaderboard_window,
            sort_by=args.leaderboard_sort,
            limit=args.leaderboard_limit,
            min_account_value=args.min_account_value,
            min_leaderboard_volume=args.min_leaderboard_volume,
        )
        for candidate in leaderboard_candidates:
            if candidate["address"] not in addresses:
                addresses.append(candidate["address"])
    scores = []
    for address in addresses:
        fills = fetch_user_fills(address, days=args.days)
        clearinghouse_state = fetch_clearinghouse_state(address) if args.include_open_positions else {}
        score = score_hyperliquid_svw_agent(
            fills,
            address=address,
            clearinghouse_state=clearinghouse_state,
            asset_weights=asset_weights,
        )
        for candidate in leaderboard_candidates:
            if candidate["address"] == address:
                score["leaderboard_candidate"] = candidate
                break
        scores.append(score)
    ranking = rank_hyperliquid_svw_agents(scores)
    ranking["source"] = {
        "venue": "hyperliquid",
        "api": INFO_URL,
        "method": "POST /info userFillsByTime",
        "leaderboard_api": STATS_LEADERBOARD_URL if args.leaderboard else "",
        "leaderboard_used": bool(args.leaderboard),
        "leaderboard_window": args.leaderboard_window if args.leaderboard else "",
        "leaderboard_sort": args.leaderboard_sort if args.leaderboard else "",
        "leaderboard_limit": args.leaderboard_limit if args.leaderboard else 0,
        "min_account_value": args.min_account_value if args.leaderboard else 0.0,
        "min_leaderboard_volume": args.min_leaderboard_volume if args.leaderboard else 0.0,
        "days": args.days,
        "address_count": len(addresses),
        "include_open_positions": bool(args.include_open_positions),
        "secret_free": True,
    }
    ranking["global_svw_thesis"] = {
        "summary": weights_config["thesis"],
        "weights_source": weights_config["source"],
        "editable_weights_path": weights_config["path"],
        "asset_weights": asset_weights,
    }
    return ranking


def build_public_surface(args: argparse.Namespace) -> dict[str, Any]:
    ranking = build_ranking(args)
    weights_config = load_global_svw_asset_weights(args.weights_file)
    return build_hyperliquid_svw_copy_trader_surface(
        ranking,
        weights_config=weights_config,
    )


def write_public_surface(surface: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if args.stdout_only:
        return surface
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{stamp}_hyperliquid_svw_copy_trader_surface.json"
    surface["receipt_path"] = str(out_path)
    surface["source"]["cached_snapshot_path"] = str(out_path)
    out_path.write_text(json.dumps(surface, indent=2, sort_keys=True), encoding="utf-8")
    if not args.no_latest:
        latest_path = out_dir / args.latest_name
        surface["latest_path"] = str(latest_path)
        surface["source"]["cached_snapshot_path"] = str(latest_path)
        latest_path.write_text(json.dumps(surface, indent=2, sort_keys=True), encoding="utf-8")
    return surface


def refresh_once(args: argparse.Namespace) -> dict[str, Any]:
    return write_public_surface(build_public_surface(args), args)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score public Hyperliquid trader wallets as Nomad SVW-producing agents."
    )
    parser.add_argument("addresses", nargs="*", help="Hyperliquid master/subaccount wallet addresses.")
    parser.add_argument("--addresses-file", help="Optional newline-delimited address file.")
    parser.add_argument("--days", type=int, default=30, help="Lookback window for user fills.")
    parser.add_argument("--include-open-positions", action="store_true")
    parser.add_argument("--leaderboard", action="store_true", help="Seed addresses from the public Hyperliquid leaderboard.")
    parser.add_argument("--leaderboard-window", choices=["day", "week", "month", "allTime"], default="month")
    parser.add_argument("--leaderboard-sort", choices=["pnl", "roi", "vlm", "accountValue"], default="pnl")
    parser.add_argument("--leaderboard-limit", type=int, default=20)
    parser.add_argument("--min-account-value", type=float, default=10_000.0)
    parser.add_argument("--min-leaderboard-volume", type=float, default=1.0)
    parser.add_argument(
        "--weights-file",
        default=str(default_hyperliquid_svw_weights_path()),
        help="Editable JSON config for Global-SVW asset weights.",
    )
    parser.add_argument("--out-dir", default="data/hyperliquid-svw-agents")
    parser.add_argument("--latest-name", default="latest.json")
    parser.add_argument("--no-latest", action="store_true", help="Do not update the latest public snapshot file.")
    parser.add_argument("--loop", action="store_true", help="Refresh forever; intended for hourly local service runs.")
    parser.add_argument("--refresh-seconds", type=int, default=3600, help="Loop interval when --loop is used.")
    parser.add_argument("--stdout-only", action="store_true")
    args = parser.parse_args()

    while True:
        surface = refresh_once(args)
        print(json.dumps(surface, indent=2, sort_keys=True))
        if not args.loop:
            break
        time.sleep(max(60, int(args.refresh_seconds or 3600)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
