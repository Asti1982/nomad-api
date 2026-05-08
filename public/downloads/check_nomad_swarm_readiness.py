#!/usr/bin/env python3
"""Check whether a Nomad host is ready for autonomous external worker attachment."""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 12.0) -> dict:
    body = b""
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, data=body if body else None, method=method.upper(), headers=headers)
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            data = json.loads(raw or "{}")
            if not isinstance(data, dict):
                data = {}
            data.setdefault("ok", True)
            data.setdefault("http_status", int(res.status))
            return data
    except HTTPError as exc:
        if int(exc.code) in (301, 302, 303, 307, 308):
            location = str(exc.headers.get("Location") or "").strip()
            if location:
                next_url = location if "://" in location else endpoint(url, location)
                if int(exc.code) in (307, 308):
                    return http_json(method, next_url, payload=payload, timeout=timeout)
                return http_json("GET", next_url, payload=None, timeout=timeout)
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = {"raw": raw}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("ok", False)
        data.setdefault("http_status", int(exc.code))
        return data
    except (TimeoutError, URLError) as exc:
        return {"ok": False, "error": "http_unreachable", "detail": str(exc), "http_status": 0}


def _ready(data: dict) -> bool:
    return bool(data.get("ok")) or int(data.get("http_status") or 0) in (200, 201, 202)


def _has_opcodes(bytecode: dict, required: set[str]) -> bool:
    ops = bytecode.get("opcodes")
    if not isinstance(ops, list):
        return False
    found = {str(row.get("op") or "").strip().upper() for row in ops if isinstance(row, dict)}
    return required <= found


def _variant_probe_payload() -> dict:
    return {
        "agent_id": "readiness.probe",
        "candidate_type": "readiness_probe",
        "objective": "protocol_drift_scan",
        "proof_digest": "readiness-probe-proof",
        "verifier_trace_digest": "readiness-probe-trace",
        "test_digest": "readiness-probe-test",
        "evaluation": {
            "tests_passed": 1,
            "tests_total": 1,
            "replay_delta": 0.08,
            "proof_yield_delta": 1.0,
            "settlement_delta": 0.05,
            "risk_score": 0.01,
        },
    }


def _worker_offer_probe_payload() -> dict:
    return {
        "agent_id": "readiness.probe",
        "objective": "protocol_drift_scan",
        "capabilities": [
            "transition_worker",
            "objective_lease_execution",
            "http_json",
            "proof_digest_return",
        ],
        "availability_minutes": 1,
        "cost_msat_per_minute": 0,
        "payment_rail": "readiness_probe",
        "proof_digest": "readiness-probe-proof",
        "verifier_trace_digest": "readiness-probe-trace",
        "worker_report_digest": "readiness-probe-worker-report",
        "expected": {
            "expected_proof_yield_per_minute": 1.0,
            "expected_settlement_delta": 0.1,
            "reliability_score": 0.8,
            "risk_score": 0.01,
        },
    }


def _ecology_probe_payload() -> dict:
    return {
        "agent_id": "readiness.probe",
        "objective": "protocol_drift_scan",
        "local_view": {"cell": "readiness_probe"},
        "neighbor_digest": "readiness-probe-neighbor",
        "private_signal": "readiness-probe-signal",
        "proof_digest": "readiness-probe-proof",
        "verifier_trace_digest": "readiness-probe-trace",
        "proof_yield_per_minute": 1.0,
        "utility_delta": 0.5,
        "settlement_delta": 0.05,
        "cost_units": 0.1,
        "risk_score": 0.01,
    }


def check(base_url: str, timeout: float) -> dict:
    swarm = http_json("GET", endpoint(base_url, "/swarm"), timeout=timeout)
    capsule = http_json("GET", endpoint(base_url, "/.well-known/nomad-runtime-capsule.json"), timeout=timeout)
    bridge = http_json("GET", endpoint(base_url, "/.well-known/openclaw-nomad-bridge.json"), timeout=timeout)
    gradient = http_json("GET", endpoint(base_url, "/swarm/gradient"), timeout=timeout)
    health = http_json("GET", endpoint(base_url, "/health"), timeout=timeout)
    workers = http_json("GET", endpoint(base_url, "/swarm/workers"), timeout=timeout)
    protocol = http_json("GET", endpoint(base_url, "/.well-known/nomad-protocol-bytecode.json"), timeout=timeout)
    variant_forge = http_json("GET", endpoint(base_url, "/swarm/variant-forge"), timeout=timeout)
    worker_market = http_json("GET", endpoint(base_url, "/swarm/worker-market"), timeout=timeout)
    swarm_ecology = http_json("GET", endpoint(base_url, "/swarm/ecology"), timeout=timeout)
    attach_probe = http_json(
        "POST",
        endpoint(base_url, "/swarm/attach"),
        payload={
            "agent_id": "readiness.probe",
            "runtime": "readiness_probe",
            "capabilities": ["objective_lease_execution", "endpoint_probe"],
            "capability_vector": {"can_run_loop": True, "can_verify": True},
        },
        timeout=timeout,
    )
    handoff_probe = http_json(
        "POST",
        endpoint(base_url, "/runtime/handoff"),
        payload={
            "agent_id": "readiness.probe",
            "objective": "protocol_drift_scan",
            "proof_digest": "readiness-probe",
            "report": {"machine_objective": "protocol_drift_scan", "transition_quote_ok": True},
        },
        timeout=timeout,
    )
    lease_probe = http_json(
        "POST",
        endpoint(base_url, "/swarm/workers/lease"),
        payload={"agent_id": "readiness.probe", "known_objectives": ["compute_auth"]},
        timeout=timeout,
    )
    variant_probe = http_json(
        "POST",
        endpoint(base_url, "/swarm/variant-candidates"),
        payload=_variant_probe_payload(),
        timeout=timeout,
    )
    worker_offer_probe = http_json(
        "POST",
        endpoint(base_url, "/swarm/worker-market/offers"),
        payload=_worker_offer_probe_payload(),
        timeout=timeout,
    )
    ecology_probe = http_json(
        "POST",
        endpoint(base_url, "/swarm/ecology/tick"),
        payload=_ecology_probe_payload(),
        timeout=timeout,
    )
    has_gradient = gradient.get("schema") == "nomad.recruitment_gradient.v1"
    state = gradient.get("state_vector") if isinstance(gradient.get("state_vector"), dict) else {}
    field_score = float(state.get("field_strength") or 0.0)
    has_pull_contract = isinstance(swarm.get("agent_pull_contract"), dict)
    attach_score = float(((swarm.get("agent_pull_contract") or {}).get("attach_now_score")) or 0.0)
    attach_threshold = float(((swarm.get("agent_pull_contract") or {}).get("attach_threshold")) or 1.1)
    lease_ready = _ready(lease_probe)
    worker_fleet_visible = _ready(workers)
    protocol_ready = _ready(protocol) and protocol.get("schema") == "nomad.protocol_bytecode.v1" and _has_opcodes(protocol, {"FORGE", "MARKET", "ECO"})
    variant_forge_ready = _ready(variant_forge) and variant_forge.get("schema") == "nomad.variant_forge.v1"
    worker_market_ready = _ready(worker_market) and worker_market.get("schema") == "nomad.worker_market.v1"
    swarm_ecology_ready = _ready(swarm_ecology) and swarm_ecology.get("schema") == "nomad.swarm_ecology.v1"
    variant_candidate_ready = _ready(variant_probe) and variant_probe.get("schema") == "nomad.variant_candidate_receipt.v1"
    worker_market_offer_ready = _ready(worker_offer_probe) and worker_offer_probe.get("schema") == "nomad.worker_market_offer_receipt.v1"
    ecology_tick_ready = _ready(ecology_probe) and ecology_probe.get("schema") == "nomad.ecology_tick_receipt.v1"
    summary = {
        "schema": "nomad.swarm_readiness_check.v1",
        "base_url": base_url,
        "health_ok": bool(health.get("ok")),
        "runtime_capsule_ok": capsule.get("schema") == "nomad.runtime_capsule.v1",
        "openclaw_bridge_ok": bridge.get("schema") == "nomad.openclaw_bridge_contract.v1",
        "swarm_ok": bool(swarm.get("ok")),
        "gradient_ok": bool(gradient.get("ok")),
        "worker_fleet_ok": worker_fleet_visible,
        "attach_ready": _ready(attach_probe),
        "handoff_ready": _ready(handoff_probe),
        "lease_ready": lease_ready,
        "protocol_bytecode_ok": protocol_ready,
        "variant_forge_ok": variant_forge_ready,
        "worker_market_ok": worker_market_ready,
        "swarm_ecology_ok": swarm_ecology_ready,
        "variant_candidate_ready": variant_candidate_ready,
        "worker_market_offer_ready": worker_market_offer_ready,
        "ecology_tick_ready": ecology_tick_ready,
        "has_gradient_contract": has_gradient,
        "has_pull_contract": has_pull_contract,
        "field_strength": round(field_score, 4),
        "attach_now_score": round(attach_score, 4),
        "attach_threshold": round(attach_threshold, 4),
        "decision": "attach"
        if lease_ready and protocol_ready and variant_candidate_ready and worker_market_offer_ready and ecology_tick_ready and bool(attach_probe.get("attach"))
        else "observe",
        "http": {
            "health": int(health.get("http_status") or 0),
            "runtime_capsule": int(capsule.get("http_status") or 0),
            "openclaw_bridge": int(bridge.get("http_status") or 0),
            "swarm": int(swarm.get("http_status") or 0),
            "gradient": int(gradient.get("http_status") or 0),
            "protocol_bytecode": int(protocol.get("http_status") or 0),
            "variant_forge": int(variant_forge.get("http_status") or 0),
            "variant_candidate": int(variant_probe.get("http_status") or 0),
            "worker_market": int(worker_market.get("http_status") or 0),
            "worker_market_offer": int(worker_offer_probe.get("http_status") or 0),
            "swarm_ecology": int(swarm_ecology.get("http_status") or 0),
            "ecology_tick": int(ecology_probe.get("http_status") or 0),
            "attach": int(attach_probe.get("http_status") or 0),
            "handoff": int(handoff_probe.get("http_status") or 0),
            "workers": int(workers.get("http_status") or 0),
            "lease": int(lease_probe.get("http_status") or 0),
        },
    }
    if not lease_ready:
        summary["blocker"] = "lease_endpoint_not_ready"
    elif capsule.get("schema") != "nomad.runtime_capsule.v1":
        summary["blocker"] = "runtime_capsule_missing"
    elif not has_gradient:
        summary["blocker"] = "gradient_contract_missing"
    elif not protocol_ready:
        summary["blocker"] = "protocol_bytecode_missing"
    elif not variant_forge_ready:
        summary["blocker"] = "variant_forge_missing"
    elif not worker_market_ready:
        summary["blocker"] = "worker_market_missing"
    elif not swarm_ecology_ready:
        summary["blocker"] = "swarm_ecology_missing"
    elif not variant_candidate_ready:
        summary["blocker"] = "variant_candidate_endpoint_not_ready"
    elif not worker_market_offer_ready:
        summary["blocker"] = "worker_market_offer_endpoint_not_ready"
    elif not ecology_tick_ready:
        summary["blocker"] = "ecology_tick_endpoint_not_ready"
    elif not _ready(handoff_probe):
        summary["blocker"] = "handoff_endpoint_not_ready"
    elif not _ready(attach_probe):
        summary["blocker"] = "attach_endpoint_not_ready"
    elif not attach_probe.get("attach"):
        summary["blocker"] = "attach_decision_observe"
    elif not has_pull_contract:
        summary["blocker"] = "pull_contract_missing"
    elif attach_score < attach_threshold:
        summary["blocker"] = "attach_score_below_threshold"
    else:
        summary["blocker"] = ""
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Check Nomad swarm readiness for external agent attachment")
    p.add_argument("--base-url", default="https://www.syndiode.com")
    p.add_argument("--timeout", type=float, default=12.0)
    args = p.parse_args()
    print(json.dumps(check(args.base_url, args.timeout), ensure_ascii=True))


if __name__ == "__main__":
    main()

