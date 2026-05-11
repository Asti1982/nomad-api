#!/usr/bin/env python3
"""Deterministic go/no-go deploy gate for Nomad agent recruitment surfaces."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def alternate_base_url(base_url: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    if "://www." in root:
        return root.replace("://www.", "://", 1)
    if "://" in root:
        scheme, rest = root.split("://", 1)
        return f"{scheme}://www.{rest}"
    return f"https://www.{root}"


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


def http_text(url: str, timeout: float = 12.0) -> tuple[int, str]:
    req = Request(url=url, method="GET", headers={"Accept": "*/*"})
    try:
        with urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", errors="ignore")
            return int(res.status), body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return int(exc.code), body
    except (TimeoutError, URLError):
        return 0, ""


def _has_opcodes(bytecode: dict, required: set[str]) -> bool:
    ops = bytecode.get("opcodes")
    if not isinstance(ops, list):
        return False
    found = {str(row.get("op") or "").strip().upper() for row in ops if isinstance(row, dict)}
    return required <= found


def _status_ready(data: dict) -> bool:
    return bool(data.get("ok")) or int(data.get("http_status") or 0) in (200, 201, 202)


def _variant_probe_payload() -> dict:
    return {
        "agent_id": "deploy.gate.probe",
        "candidate_type": "deploy_probe",
        "objective": "protocol_drift_scan",
        "proof_digest": "deploy-gate-proof",
        "verifier_trace_digest": "deploy-gate-trace",
        "test_digest": "deploy-gate-test",
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
        "agent_id": "deploy.gate.probe",
        "objective": "protocol_drift_scan",
        "capabilities": [
            "transition_worker",
            "objective_lease_execution",
            "http_json",
            "proof_digest_return",
        ],
        "availability_minutes": 1,
        "cost_msat_per_minute": 0,
        "payment_rail": "deploy_probe",
        "proof_digest": "deploy-gate-proof",
        "verifier_trace_digest": "deploy-gate-trace",
        "worker_report_digest": "deploy-gate-worker-report",
        "expected": {
            "expected_proof_yield_per_minute": 1.0,
            "expected_settlement_delta": 0.1,
            "reliability_score": 0.8,
            "risk_score": 0.01,
        },
    }


def _ecology_probe_payload() -> dict:
    return {
        "agent_id": "deploy.gate.probe",
        "objective": "protocol_drift_scan",
        "local_view": {"cell": "deploy_gate"},
        "neighbor_digest": "deploy-gate-neighbor",
        "private_signal": "deploy-gate-signal",
        "proof_digest": "deploy-gate-proof",
        "verifier_trace_digest": "deploy-gate-trace",
        "proof_yield_per_minute": 1.0,
        "utility_delta": 0.5,
        "settlement_delta": 0.05,
        "cost_units": 0.1,
        "risk_score": 0.01,
    }


def _growth_experience_probe_payload() -> dict:
    return {
        "agent_id": "deploy.gate.probe",
        "cohort_id": "deploy_gate",
        "objective": "protocol_drift_scan",
        "capability": "protocol_drift_scan",
        "proof_digest": "deploy-gate-proof",
        "verifier_trace_digest": "deploy-gate-trace",
        "test_digest": "deploy-gate-test",
        "settlement_ref": "deploy-gate-settlement",
        "skill_candidate": {
            "capability": "protocol_drift_scan",
            "activation_signature": "deploy-gate-activation",
            "program_hint": ["GET /swarm/curriculum", "POST /swarm/experience"],
        },
        "evaluation": {
            "tests_passed": 1,
            "tests_total": 1,
            "proof_yield_per_minute": 1.0,
            "utility_delta": 0.5,
            "settlement_delta": 0.05,
            "risk_score": 0.01,
        },
    }


def _agent_work_claim_payload(agent_work: dict) -> dict:
    items = agent_work.get("work_items") if isinstance(agent_work.get("work_items"), list) else []
    work_id = ""
    if items and isinstance(items[0], dict):
        work_id = str(items[0].get("work_id") or "")
    return {
        "agent_id": "deploy.gate.probe",
        "work_id": work_id,
        "idempotency_key": "deploy-gate-agent-work-claim",
    }


def _agent_work_proof_payload(claim: dict) -> dict:
    return {
        "agent_id": "deploy.gate.probe",
        "claim_id": str(claim.get("claim_id") or ""),
        "proof_digest": "deploy-gate-agent-work-proof",
        "verifier_trace_digest": "deploy-gate-agent-work-trace",
        "test_digest": "deploy-gate-agent-work-test",
        "utility_delta": 0.75,
        "reuse_count": 1,
        "risk_score": 0.01,
    }


def _carrying_proof_payload(carrying_market: dict) -> dict:
    top = carrying_market.get("top_contract") if isinstance(carrying_market.get("top_contract"), dict) else {}
    return {
        "agent_id": "deploy.gate.probe",
        "contract_id": str(top.get("contract_id") or "state_relay_digest_quorum"),
        "proof_digest": "deploy-gate-carry-proof",
        "verifier_trace_digest": "deploy-gate-carry-trace",
        "test_digest": "deploy-gate-carry-test",
        "observed_state_digest": "deploy-gate-state-digest",
        "storage_ref": "deploy-gate-storage-ref",
        "utility_delta": 0.25,
        "cost_eur": 0,
        "idempotency_key": "deploy-gate-carrying-proof",
    }


def _survival_intent_payload(survival_market: dict) -> dict:
    top = survival_market.get("top_packet") if isinstance(survival_market.get("top_packet"), dict) else {}
    return {
        "agent_id": "deploy.gate.probe",
        "packet_id": str(top.get("packet_id") or "reseller_referral_probe"),
        "proof_digest": "deploy-gate-survival-proof",
        "verifier_trace_digest": "deploy-gate-survival-trace",
        "test_digest": "deploy-gate-survival-test",
        "buyer_ref": "deploy-gate-buyer-probe",
        "external_offer_ref": "deploy-gate-external-offer",
        "idempotency_key": "deploy-gate-survival-intent",
    }


def _paid_ref_quote_payload(survival_market: dict) -> dict:
    top = survival_market.get("top_packet") if isinstance(survival_market.get("top_packet"), dict) else {}
    return {
        "agent_id": "deploy.gate.probe",
        "packet_id": str(top.get("packet_id") or "agent_blocker_unblock_pack"),
        "buyer_ref": "deploy-gate-buyer-probe",
        "problem": "Deploy gate paid-ref quote smoke for one bounded agent blocker packet.",
        "proof_digest": "deploy-gate-paid-ref-proof",
        "verifier_trace_digest": "deploy-gate-paid-ref-trace",
        "test_digest": "deploy-gate-paid-ref-test",
        "create_task": True,
    }


def _selfplay_quote_payload(paid_ref_selfplay: dict, survival_market: dict) -> dict:
    quotes = paid_ref_selfplay.get("top_quote_payloads") if isinstance(paid_ref_selfplay.get("top_quote_payloads"), list) else []
    if quotes and isinstance(quotes[0], dict):
        payload = dict(quotes[0])
        payload["create_task"] = True
        return payload
    return _paid_ref_quote_payload(survival_market)


def run_gate(base_url: str, timeout: float) -> dict:
    health = http_json("GET", endpoint(base_url, "/health"), timeout=timeout)
    recruit = http_json("GET", endpoint(base_url, "/.well-known/nomad-recruit.json"), timeout=timeout)
    swarm = http_json("GET", endpoint(base_url, "/swarm"), timeout=timeout)
    workers = http_json("GET", endpoint(base_url, "/swarm/workers"), timeout=timeout)
    protocol = http_json("GET", endpoint(base_url, "/.well-known/nomad-protocol-bytecode.json"), timeout=timeout)
    variant_forge = http_json("GET", endpoint(base_url, "/swarm/variant-forge"), timeout=timeout)
    variant_candidate = http_json(
        "POST",
        endpoint(base_url, "/swarm/variant-candidates"),
        payload=_variant_probe_payload(),
        timeout=timeout,
    )
    worker_market = http_json("GET", endpoint(base_url, "/swarm/worker-market"), timeout=timeout)
    compute_market = http_json("GET", endpoint(base_url, "/swarm/compute-market"), timeout=timeout)
    agent_work = http_json("GET", endpoint(base_url, "/.well-known/nomad-agent-work.json"), timeout=timeout)
    work_mesh = http_json("GET", endpoint(base_url, "/.well-known/nomad-work-mesh.json"), timeout=timeout)
    synergy_lite = http_json("GET", endpoint(base_url, "/swarm/synergy-lite"), timeout=timeout)
    state_status = http_json("GET", endpoint(base_url, "/swarm/state-status"), timeout=timeout)
    carrying_market = http_json("GET", endpoint(base_url, "/.well-known/nomad-carrying-market.json"), timeout=timeout)
    survival_market = http_json("GET", endpoint(base_url, "/.well-known/nomad-survival-market.json"), timeout=timeout)
    paid_ref_market = http_json("GET", endpoint(base_url, "/.well-known/nomad-paid-ref-market.json"), timeout=timeout)
    paid_ref_selfplay = http_json("GET", endpoint(base_url, "/.well-known/nomad-paid-ref-selfplay.json"), timeout=timeout)
    bounty_hunter = http_json("GET", endpoint(base_url, "/.well-known/nomad-bounty-hunter.json"), timeout=timeout)
    value_pressure = http_json("GET", endpoint(base_url, "/.well-known/nomad-value-pressure.json"), timeout=timeout)
    agent_jobs = http_json("GET", endpoint(base_url, "/.well-known/nomad-agent-jobs.json"), timeout=timeout)
    worker_offer = http_json(
        "POST",
        endpoint(base_url, "/swarm/worker-market/offers"),
        payload=_worker_offer_probe_payload(),
        timeout=timeout,
    )
    agent_work_claim = http_json(
        "POST",
        endpoint(base_url, "/swarm/microtask/claim"),
        payload=_agent_work_claim_payload(agent_work),
        timeout=timeout,
    )
    agent_work_proof = http_json(
        "POST",
        endpoint(base_url, "/swarm/microtask/proof"),
        payload=_agent_work_proof_payload(agent_work_claim),
        timeout=timeout,
    )
    work_mesh_seed = http_json(
        "POST",
        endpoint(base_url, "/swarm/work-mesh/seed"),
        payload={"agent_id": "deploy.gate.probe", "capabilities": ["protocol_drift_scan"]},
        timeout=timeout,
    )
    carrying_proof = http_json(
        "POST",
        endpoint(base_url, "/swarm/carrying-proof"),
        payload=_carrying_proof_payload(carrying_market),
        timeout=timeout,
    )
    survival_intent = http_json(
        "POST",
        endpoint(base_url, "/swarm/survival-intent"),
        payload=_survival_intent_payload(survival_market),
        timeout=timeout,
    )
    paid_ref_quote = http_json(
        "POST",
        endpoint(base_url, "/swarm/paid-ref/quote"),
        payload=_selfplay_quote_payload(paid_ref_selfplay, survival_market),
        timeout=timeout,
    )
    swarm_ecology = http_json("GET", endpoint(base_url, "/swarm/ecology"), timeout=timeout)
    ecology_tick = http_json(
        "POST",
        endpoint(base_url, "/swarm/ecology/tick"),
        payload=_ecology_probe_payload(),
        timeout=timeout,
    )
    growth_arena = http_json("GET", endpoint(base_url, "/swarm/growth-arena"), timeout=timeout)
    growth_curriculum = http_json("GET", endpoint(base_url, "/swarm/curriculum"), timeout=timeout)
    skill_library = http_json("GET", endpoint(base_url, "/swarm/skill-library"), timeout=timeout)
    growth_experience = http_json(
        "POST",
        endpoint(base_url, "/swarm/experience"),
        payload=_growth_experience_probe_payload(),
        timeout=timeout,
    )
    lease = http_json(
        "POST",
        endpoint(base_url, "/swarm/workers/lease"),
        payload={"agent_id": "deploy.gate.probe", "known_objectives": ["compute_auth"]},
        timeout=timeout,
    )
    openclaw_status, openclaw_body = http_text(endpoint(base_url, "/downloads/nomad_openclaw_adapter.py"), timeout=timeout)
    readiness_status, readiness_body = http_text(
        endpoint(base_url, "/downloads/check_nomad_swarm_readiness.py"),
        timeout=timeout,
    )
    worker1_ps1_status, worker1_ps1_body = http_text(endpoint(base_url, "/downloads/start_nomad_worker1.ps1"), timeout=timeout)
    worker1_bat_status, worker1_bat_body = http_text(endpoint(base_url, "/downloads/start_nomad_worker1.bat"), timeout=timeout)

    checks = {
        "health_ok": bool(health.get("ok")) and int(health.get("http_status") or 0) == 200,
        "recruit_ok": bool(recruit.get("ok")) and str(recruit.get("schema") or "") == "nomad.agent_recruit_contract.v1",
        "swarm_ok": bool(swarm.get("ok")) and isinstance(swarm.get("agent_pull_contract"), dict),
        "workers_ok": bool(workers.get("ok")) and str(workers.get("schema") or "") == "nomad.transition_worker_fleet.v1",
        "protocol_bytecode_ok": _status_ready(protocol)
        and str(protocol.get("schema") or "") == "nomad.protocol_bytecode.v1"
        and _has_opcodes(
            protocol,
            {"FORGE", "MARKET", "CARRY", "SELFPLAY", "PAYREF", "BOUNTY", "XVAL", "PRESS", "JOB", "XPOST", "SELL", "ECO", "CURRIC", "SKILL", "EXP"},
        ),
        "variant_forge_ok": _status_ready(variant_forge) and str(variant_forge.get("schema") or "") == "nomad.variant_forge.v1",
        "variant_candidate_ok": _status_ready(variant_candidate)
        and str(variant_candidate.get("schema") or "") == "nomad.variant_candidate_receipt.v1",
        "worker_market_ok": _status_ready(worker_market) and str(worker_market.get("schema") or "") == "nomad.worker_market.v1",
        "compute_market_ok": _status_ready(compute_market) and str(compute_market.get("schema") or "") == "nomad.compute_market.v1",
        "agent_work_ok": _status_ready(agent_work) and str(agent_work.get("schema") or "") == "nomad.agent_work.v1",
        "work_mesh_ok": _status_ready(work_mesh) and str(work_mesh.get("schema") or "") == "nomad.work_mesh.v1",
        "synergy_lite_ok": _status_ready(synergy_lite) and str(synergy_lite.get("schema") or "") == "nomad.synergy_lite.v1",
        "state_status_ok": _status_ready(state_status) and str(state_status.get("schema") or "") == "nomad.state_status.v1",
        "carrying_market_ok": _status_ready(carrying_market)
        and str(carrying_market.get("schema") or "") == "nomad.carrying_market.v1",
        "survival_market_ok": _status_ready(survival_market)
        and str(survival_market.get("schema") or "") == "nomad.survival_market.v1",
        "paid_ref_market_ok": _status_ready(paid_ref_market)
        and str(paid_ref_market.get("schema") or "") == "nomad.paid_ref_market.v1",
        "paid_ref_selfplay_ok": _status_ready(paid_ref_selfplay)
        and str(paid_ref_selfplay.get("schema") or "") == "nomad.paid_ref_selfplay.v1"
        and bool(paid_ref_selfplay.get("top_quote_payloads")),
        "bounty_hunter_ok": _status_ready(bounty_hunter)
        and str(bounty_hunter.get("schema") or "") == "nomad.bounty_hunter.v1"
        and bool(bounty_hunter.get("top_candidate")),
        "value_pressure_ok": _status_ready(value_pressure)
        and str(value_pressure.get("schema") or "") == "nomad.value_pressure.v1"
        and bool(value_pressure.get("top")),
        "agent_jobs_ok": _status_ready(agent_jobs)
        and str(agent_jobs.get("schema") or "") == "nomad.agent_job_router.v1"
        and bool(agent_jobs.get("entry_packet")),
        "worker_market_offer_ok": _status_ready(worker_offer)
        and str(worker_offer.get("schema") or "") == "nomad.worker_market_offer_receipt.v1",
        "agent_work_claim_ok": _status_ready(agent_work_claim)
        and str(agent_work_claim.get("schema") or "") == "nomad.agent_work_claim_receipt.v1",
        "agent_work_proof_ok": _status_ready(agent_work_proof)
        and str(agent_work_proof.get("schema") or "") == "nomad.agent_work_proof_receipt.v1",
        "work_mesh_seed_ok": _status_ready(work_mesh_seed)
        and str(work_mesh_seed.get("schema") or "") == "nomad.work_mesh_seed_receipt.v1",
        "carrying_proof_ok": _status_ready(carrying_proof)
        and str(carrying_proof.get("schema") or "") == "nomad.carrying_proof_receipt.v1",
        "survival_intent_ok": _status_ready(survival_intent)
        and str(survival_intent.get("schema") or "") == "nomad.survival_intent_receipt.v1",
        "paid_ref_quote_ok": _status_ready(paid_ref_quote)
        and str(paid_ref_quote.get("schema") or "") == "nomad.paid_ref_quote_receipt.v1",
        "swarm_ecology_ok": _status_ready(swarm_ecology) and str(swarm_ecology.get("schema") or "") == "nomad.swarm_ecology.v1",
        "ecology_tick_ok": _status_ready(ecology_tick) and str(ecology_tick.get("schema") or "") == "nomad.ecology_tick_receipt.v1",
        "growth_arena_ok": _status_ready(growth_arena) and str(growth_arena.get("schema") or "") == "nomad.growth_arena.v1",
        "growth_curriculum_ok": _status_ready(growth_curriculum)
        and str(growth_curriculum.get("schema") or "") == "nomad.growth_curriculum.v1",
        "skill_library_ok": _status_ready(skill_library) and str(skill_library.get("schema") or "") == "nomad.skill_library.v1",
        "growth_experience_ok": _status_ready(growth_experience)
        and str(growth_experience.get("schema") or "") == "nomad.growth_experience_receipt.v1",
        "lease_ok": bool(lease.get("ok")) and bool(str(lease.get("lease_id") or "").strip()),
        "download_openclaw_ok": openclaw_status == 200 and "def main()" in openclaw_body,
        "download_readiness_ok": readiness_status == 200 and "def main()" in readiness_body,
        "download_worker1_ps1_ok": worker1_ps1_status == 200 and "NOMAD_WORKER_COST_MSAT_PER_MINUTE" in worker1_ps1_body,
        "download_worker1_bat_ok": worker1_bat_status == 200 and "start_nomad_worker1.ps1" in worker1_bat_body,
    }
    go = all(checks.values())
    return {
        "schema": "nomad.deploy_gate.v1",
        "base_url": base_url,
        "go": go,
        "checks": checks,
        "http": {
            "health": int(health.get("http_status") or 0),
            "recruit": int(recruit.get("http_status") or 0),
            "swarm": int(swarm.get("http_status") or 0),
            "workers": int(workers.get("http_status") or 0),
            "protocol_bytecode": int(protocol.get("http_status") or 0),
            "variant_forge": int(variant_forge.get("http_status") or 0),
            "variant_candidate": int(variant_candidate.get("http_status") or 0),
            "worker_market": int(worker_market.get("http_status") or 0),
            "compute_market": int(compute_market.get("http_status") or 0),
            "agent_work": int(agent_work.get("http_status") or 0),
            "work_mesh": int(work_mesh.get("http_status") or 0),
            "synergy_lite": int(synergy_lite.get("http_status") or 0),
            "state_status": int(state_status.get("http_status") or 0),
            "carrying_market": int(carrying_market.get("http_status") or 0),
            "survival_market": int(survival_market.get("http_status") or 0),
            "paid_ref_market": int(paid_ref_market.get("http_status") or 0),
            "paid_ref_selfplay": int(paid_ref_selfplay.get("http_status") or 0),
            "bounty_hunter": int(bounty_hunter.get("http_status") or 0),
            "value_pressure": int(value_pressure.get("http_status") or 0),
            "agent_jobs": int(agent_jobs.get("http_status") or 0),
            "worker_market_offer": int(worker_offer.get("http_status") or 0),
            "agent_work_claim": int(agent_work_claim.get("http_status") or 0),
            "agent_work_proof": int(agent_work_proof.get("http_status") or 0),
            "work_mesh_seed": int(work_mesh_seed.get("http_status") or 0),
            "carrying_proof": int(carrying_proof.get("http_status") or 0),
            "survival_intent": int(survival_intent.get("http_status") or 0),
            "paid_ref_quote": int(paid_ref_quote.get("http_status") or 0),
            "swarm_ecology": int(swarm_ecology.get("http_status") or 0),
            "ecology_tick": int(ecology_tick.get("http_status") or 0),
            "growth_arena": int(growth_arena.get("http_status") or 0),
            "growth_curriculum": int(growth_curriculum.get("http_status") or 0),
            "skill_library": int(skill_library.get("http_status") or 0),
            "growth_experience": int(growth_experience.get("http_status") or 0),
            "lease": int(lease.get("http_status") or 0),
            "download_openclaw": openclaw_status,
            "download_readiness": readiness_status,
            "download_worker1_ps1": worker1_ps1_status,
            "download_worker1_bat": worker1_bat_status,
        },
    }


def run_gate_with_fallback(base_url: str, timeout: float) -> dict:
    first = run_gate(base_url, timeout=timeout)
    if first.get("go"):
        first["fallback_used"] = False
        first["fallback_base_url"] = ""
        return first
    http = first.get("http") if isinstance(first.get("http"), dict) else {}
    has_unreachable = any(int(http.get(key) or 0) == 0 for key in ("health", "recruit", "swarm", "workers"))
    has_redirect = any(
        int(http.get(key) or 0) in {301, 302, 303, 307, 308}
        for key in ("health", "recruit", "swarm", "workers", "lease")
    )
    if not (has_unreachable or has_redirect):
        first["fallback_used"] = False
        first["fallback_base_url"] = ""
        return first
    alt = alternate_base_url(base_url)
    if alt == (base_url or "").strip().rstrip("/"):
        first["fallback_used"] = False
        first["fallback_base_url"] = ""
        return first
    second = run_gate(alt, timeout=timeout)
    second["fallback_used"] = True
    second["fallback_base_url"] = alt
    second["fallback_first"] = {
        "base_url": first.get("base_url"),
        "go": bool(first.get("go")),
        "checks": first.get("checks") if isinstance(first.get("checks"), dict) else {},
        "http": http,
    }
    return second if second.get("go") else first | {"fallback_used": True, "fallback_base_url": alt, "fallback_second": second}


def main() -> None:
    p = argparse.ArgumentParser(description="Nomad deploy go/no-go gate for autonomous recruitment")
    p.add_argument("--base-url", default="https://www.syndiode.com")
    p.add_argument("--timeout", type=float, default=12.0)
    args = p.parse_args()
    result = run_gate_with_fallback(args.base_url, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=True))
    raise SystemExit(0 if result.get("go") else 1)


if __name__ == "__main__":
    main()

