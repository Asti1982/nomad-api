#!/usr/bin/env python3
"""Machine-native treasury pledge client for Nomad."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def digest(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 20.0) -> dict:
    data = json.dumps(payload or {}, ensure_ascii=True).encode("utf-8")
    req = Request(url=url, method=method.upper(), data=data, headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", errors="replace") or "{}"
            doc = json.loads(body)
            if isinstance(doc, dict):
                doc.setdefault("http_status", int(res.status))
                return doc
    except HTTPError as exc:
        return {"ok": False, "http_status": int(exc.code), "error": "http_error"}
    except (TimeoutError, URLError):
        return {"ok": False, "http_status": 0, "error": "http_unreachable"}
    return {"ok": False, "http_status": 0, "error": "invalid_json"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Nomad machine treasury pledge")
    parser.add_argument("--base-url", default="https://syndiode.com")
    parser.add_argument("--agent-id", default="anonymous.agent")
    parser.add_argument("--objective", default="settlement_capacity_builder")
    parser.add_argument("--amount-native", type=float, required=True)
    parser.add_argument("--horizon-cycles", type=int, default=12)
    parser.add_argument("--intent", default="")
    parser.add_argument("--source-tag", default="")
    parser.add_argument("--proof-digest", default="")
    parser.add_argument("--verifier-trace-digest", default="")
    parser.add_argument("--settlement-ref", default="")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    if not (args.proof_digest or args.verifier_trace_digest or args.settlement_ref):
        print(json.dumps({
            "ok": False,
            "error": "proof_required",
            "message": "Provide --proof-digest, --verifier-trace-digest, or --settlement-ref.",
        }, ensure_ascii=True))
        return

    payload = {
        "agent_id": args.agent_id,
        "objective": args.objective,
        "amount_native": args.amount_native,
        "horizon_cycles": args.horizon_cycles,
        "intent": args.intent or "",
        "source_tag": args.source_tag or "",
        "proof_digest": args.proof_digest or "",
        "verifier_trace_digest": args.verifier_trace_digest or "",
        "settlement_ref": args.settlement_ref or "",
        "pledged_at": _iso_now(),
    }
    payload["idempotency_key"] = args.idempotency_key or f"pledge-{digest(payload)}"
    url = endpoint(args.base_url, "/machine-treasury/pledge")
    doc = http_json("POST", url, payload, timeout=args.timeout)
    print(json.dumps(doc, ensure_ascii=True))


if __name__ == "__main__":
    main()

