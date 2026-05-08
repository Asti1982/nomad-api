"""Automated dev-fund payout rail with shadow/canary/live modes."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or "").strip() or str(default))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _mode() -> str:
    return str(os.getenv("NOMAD_DEV_FUND_TRANSFER_MODE") or "canary").strip().lower() or "canary"


def _canary_gate(seed: str, rate: float) -> bool:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / float(0xFFFFFFFF)
    return bucket <= max(0.0, min(1.0, rate))


def _ledger_path() -> Path:
    return Path(os.getenv("NOMAD_DEV_FUND_TRANSFER_LEDGER_PATH") or "public/downloads/nomad_dev_fund_transfer_ledger.jsonl")


def _queue_path() -> Path:
    return Path(os.getenv("NOMAD_DEV_FUND_MANUAL_QUEUE_PATH") or "public/downloads/nomad_dev_fund_manual_queue.jsonl")


def _append_ledger(row: dict[str, Any]) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def _append_manual_queue(row: dict[str, Any]) -> None:
    path = _queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def execute_dev_fund_transfer(*, economics_snapshot: dict[str, Any], run_id: str = "") -> dict[str, Any]:
    dev = economics_snapshot.get("dev_fund_allocation") if isinstance(economics_snapshot.get("dev_fund_allocation"), dict) else {}
    gng = economics_snapshot.get("go_no_go") if isinstance(economics_snapshot.get("go_no_go"), dict) else {}
    amount_eur = float(dev.get("approved_transfer_eur") or 0.0)
    wallet = str(dev.get("wallet") or "").strip()
    mode = _mode()
    canary_rate = _env_float("NOMAD_DEV_FUND_TRANSFER_CANARY_RATE", 0.2)
    payout_webhook = str(os.getenv("NOMAD_LIGHTNING_PAYOUT_WEBHOOK_URL") or "").strip()
    payout_token = str(os.getenv("NOMAD_LIGHTNING_PAYOUT_BEARER") or "").strip()
    min_eur = max(0.0, _env_float("NOMAD_DEV_FUND_TRANSFER_MIN_EUR", 1.0))
    force_queue = _env_bool("NOMAD_DEV_FUND_QUEUE_FORCE", default=False)
    force_amount = max(0.0, _env_float("NOMAD_DEV_FUND_QUEUE_FORCE_EUR", min_eur or 1.0))
    go = bool(gng.get("go"))

    row: dict[str, Any] = {
        "generated_at": _iso_now(),
        "schema": "nomad.dev_fund_transfer.v1",
        "run_id": run_id,
        "mode": mode,
        "go": go,
        "wallet": wallet,
        "amount_eur": round(max(0.0, amount_eur), 6),
        "status": "skipped",
        "reason": "",
    }
    if force_queue:
        row["mode"] = "manual"
        row["go"] = True
        row["amount_eur"] = round(max(force_amount, min_eur, 0.01), 6)
        row["status"] = "queued_manual"
        row["reason"] = "forced_queue_mode"
        row["queue_ref"] = f"manual:{run_id or _iso_now()}"
        _append_ledger(row)
        _append_manual_queue(
            {
                "generated_at": row["generated_at"],
                "schema": "nomad.dev_fund_manual_queue.v1",
                "run_id": run_id,
                "wallet": wallet or "unconfigured",
                "amount_eur": row["amount_eur"],
                "status": "pending_manual_payment",
                "memo": f"nomad_dev_fund_{run_id or 'tick'}",
                "forced": True,
            }
        )
        return row

    if not go:
        row["reason"] = "go_no_go_false"
        _append_ledger(row)
        return row
    if amount_eur < min_eur:
        row["reason"] = "under_min_threshold"
        _append_ledger(row)
        return row
    if not wallet:
        row["reason"] = "wallet_unconfigured"
        _append_ledger(row)
        return row

    if mode in {"shadow", "simulate"}:
        row["status"] = "simulated"
        row["reason"] = "shadow_mode"
        _append_ledger(row)
        return row
    if mode in {"manual", "queue"}:
        row["status"] = "queued_manual"
        row["reason"] = "manual_queue_mode"
        row["queue_ref"] = f"manual:{run_id or _iso_now()}"
        _append_ledger(row)
        _append_manual_queue(
            {
                "generated_at": row["generated_at"],
                "schema": "nomad.dev_fund_manual_queue.v1",
                "run_id": run_id,
                "wallet": wallet,
                "amount_eur": row["amount_eur"],
                "status": "pending_manual_payment",
                "memo": f"nomad_dev_fund_{run_id or 'tick'}",
            }
        )
        return row

    if mode == "canary":
        gate_seed = f"{run_id}:{wallet}:{amount_eur:.6f}"
        if not _canary_gate(gate_seed, canary_rate):
            row["status"] = "simulated"
            row["reason"] = "canary_sample_skip"
            _append_ledger(row)
            return row

    if not payout_webhook:
        row["status"] = "simulated"
        row["reason"] = "payout_webhook_unconfigured"
        _append_ledger(row)
        return row

    payload = {
        "schema": "nomad.dev_fund_transfer_request.v1",
        "run_id": run_id,
        "wallet": wallet,
        "amount_eur": round(max(0.0, amount_eur), 6),
        "asset": str(os.getenv("NOMAD_DEV_FUND_TRANSFER_ASSET") or "BTC_LIGHTNING"),
        "memo": f"nomad_dev_fund_{run_id or 'tick'}",
    }
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if payout_token:
        headers["Authorization"] = f"Bearer {payout_token}"

    try:
        res = requests.post(payout_webhook, json=payload, headers=headers, timeout=20)
        row["http_status"] = int(res.status_code)
        if res.ok:
            body: dict[str, Any]
            try:
                body = res.json() if isinstance(res.json(), dict) else {}
            except Exception:
                body = {}
            row["status"] = "requested"
            row["reason"] = "ok"
            row["provider_ref"] = str(body.get("payment_id") or body.get("id") or "")
        else:
            row["status"] = "failed"
            row["reason"] = "provider_http_error"
    except Exception:
        row["status"] = "failed"
        row["reason"] = "provider_unreachable"

    _append_ledger(row)
    return row

