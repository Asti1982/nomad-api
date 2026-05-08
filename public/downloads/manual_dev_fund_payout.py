#!/usr/bin/env python3
"""Manual queue helper for dev-fund payouts.

Use this when payments are executed manually from Phoenix (or any wallet).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _save_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")


def list_pending(path: Path, limit: int = 10) -> dict:
    rows = _load_rows(path)
    pending = [r for r in rows if str(r.get("status") or "") == "pending_manual_payment"]
    return {
        "ok": True,
        "schema": "nomad.dev_fund_manual_queue_list.v1",
        "path": str(path).replace("\\", "/"),
        "pending_count": len(pending),
        "rows": pending[: max(1, int(limit))],
    }


def settle(path: Path, run_id: str, proof_ref: str) -> dict:
    rows = _load_rows(path)
    updated = False
    for row in rows:
        if str(row.get("run_id") or "") != run_id:
            continue
        if str(row.get("status") or "") != "pending_manual_payment":
            continue
        row["status"] = "settled_manual_payment"
        row["settled_at"] = _iso_now()
        row["proof_ref"] = str(proof_ref or "").strip()
        updated = True
        break
    if updated:
        _save_rows(path, rows)
    return {
        "ok": updated,
        "schema": "nomad.dev_fund_manual_queue_settle.v1",
        "path": str(path).replace("\\", "/"),
        "run_id": run_id,
        "proof_ref": str(proof_ref or "").strip(),
        "updated": updated,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Manual dev-fund payout queue helper")
    p.add_argument("--queue-path", default="public/downloads/nomad_dev_fund_manual_queue.jsonl")
    p.add_argument("--list", action="store_true")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--settle-run-id", default="")
    p.add_argument("--proof-ref", default="")
    args = p.parse_args()
    path = Path(str(args.queue_path or "public/downloads/nomad_dev_fund_manual_queue.jsonl"))
    if bool(args.list):
        print(json.dumps(list_pending(path, limit=max(1, int(args.limit))), ensure_ascii=True))
        return
    if str(args.settle_run_id or "").strip():
        print(json.dumps(settle(path, run_id=str(args.settle_run_id).strip(), proof_ref=str(args.proof_ref or "").strip()), ensure_ascii=True))
        return
    print(
        json.dumps(
            {
                "ok": False,
                "schema": "nomad.dev_fund_manual_queue_settle.v1",
                "error": "choose --list or --settle-run-id",
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()

