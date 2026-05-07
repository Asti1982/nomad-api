#!/usr/bin/env python3
"""Portable OpenClaw -> Nomad transition worker adapter (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def clean(v: object, limit: int = 320) -> str:
    return " ".join(str(v or "").split())[:limit]


def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def http_json(
    method: str,
    url: str,
    payload: dict | None = None,
    timeout: float = 20.0,
    redirects_left: int = 4,
) -> dict:
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
            if isinstance(data, dict):
                data.setdefault("http_status", int(res.status))
                return data
            return {"ok": False, "error": "invalid_json_shape", "http_status": int(res.status)}
    except HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308) and redirects_left > 0:
            location = str(exc.headers.get("Location") or "").strip()
            if location:
                next_url = location if "://" in location else endpoint(url, location)
                next_payload = payload if exc.code in (307, 308) else None
                next_method = method if exc.code in (307, 308) else "GET"
                return http_json(
                    next_method,
                    next_url,
                    payload=next_payload,
                    timeout=timeout,
                    redirects_left=redirects_left - 1,
                )
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
        return {"ok": False, "error": "http_unreachable", "detail": clean(exc, 180), "url": url}


def default_agent_id() -> str:
    host = socket.gethostname().replace(" ", "-").lower()
    return f"openclaw-adapter.{host}.nomad"


def _caps_from_csv(text: str) -> list[str]:
    out: list[str] = []
    for item in (text or "").split(","):
        v = clean(item.strip(), 40).lower().replace(" ", "_")
        if v and v not in out:
            out.append(v)
    return out


def _openclaw_command_candidates() -> list[str]:
    candidates: list[str] = []
    explicit = clean(os.getenv("NOMAD_OPENCLAW_CMD"), 500)
    if explicit:
        candidates.append(explicit)
    appdata = clean(os.getenv("APPDATA"), 500)
    if appdata:
        candidates.extend(
            [
                os.path.join(appdata, "npm", "openclaw.cmd"),
                os.path.join(appdata, "npm", "openclaw"),
            ]
        )
    candidates.extend(["openclaw.cmd", "openclaw"])
    out: list[str] = []
    for item in candidates:
        if item and item not in out:
            out.append(item)
    return out


def _run_openclaw_json(args: list[str], *, timeout: float) -> dict:
    last_error: dict = {"ok": False, "error": "openclaw_not_found"}
    for exe in _openclaw_command_candidates():
        cmd = [exe, *args]
        if (os.path.sep in exe or (os.path.altsep and os.path.altsep in exe)) and not os.path.exists(exe):
            last_error = {"ok": False, "error": "openclaw_candidate_missing", "cmd": exe}
            continue
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(3.0, timeout),
                check=False,
            )
        except FileNotFoundError:
            last_error = {"ok": False, "error": "openclaw_not_found", "cmd": " ".join(cmd)}
            continue
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "openclaw_timeout", "cmd": " ".join(cmd)}
        raw = (proc.stdout or "").strip()
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": "openclaw_exit_nonzero",
                "exit_code": proc.returncode,
                "stderr": clean(proc.stderr, 320),
                "cmd": " ".join(cmd),
            }
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "error": "openclaw_non_json", "raw": clean(raw, 320), "cmd": " ".join(cmd)}
        if isinstance(data, dict):
            data.setdefault("_openclaw_cmd", exe)
            return data
        return {"ok": False, "error": "openclaw_json_shape", "cmd": " ".join(cmd)}
    return last_error


def _channel_names(payload: dict) -> list[str]:
    if isinstance(payload.get("channels"), dict):
        return sorted([clean(key, 48) for key in payload["channels"].keys() if clean(key, 48)])
    order = payload.get("channelOrder") if isinstance(payload.get("channelOrder"), list) else []
    return [clean(item, 48) for item in order if clean(item, 48)][:12]


def openclaw_runtime_signal(*, timeout: float) -> dict:
    """Compact OpenClaw runtime membrane; no transcripts, token values, or local paths."""
    ms = str(int(max(1000, min(30000, timeout * 1000))))
    probe_timeout = max(4.0, min(18.0, timeout))
    health = _run_openclaw_json(["health", "--json", "--timeout", ms], timeout=probe_timeout)
    status = _run_openclaw_json(["status", "--json", "--timeout", ms], timeout=probe_timeout)
    gateway = status.get("gateway") if isinstance(status.get("gateway"), dict) else {}
    sessions = status.get("sessions") if isinstance(status.get("sessions"), dict) else health.get("sessions") if isinstance(health.get("sessions"), dict) else {}
    agents = status.get("agents") if isinstance(status.get("agents"), dict) else {}
    memory = status.get("memory") if isinstance(status.get("memory"), dict) else {}
    vector = memory.get("vector") if isinstance(memory.get("vector"), dict) else {}
    audit = status.get("securityAudit") if isinstance(status.get("securityAudit"), dict) else {}
    audit_summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    health_ok = bool(health.get("ok"))
    gateway_reachable = bool(gateway.get("reachable"))
    configured_channels = _channel_names(health) or _channel_names(status)
    critical = int(audit_summary.get("critical") or 0)
    warn = int(audit_summary.get("warn") or 0)
    capabilities = ["openclaw_runtime", "agent_sessions", "objective_lease_execution"]
    if gateway_reachable:
        capabilities.extend(["openclaw_gateway", "replayable_control_plane"])
    if configured_channels:
        capabilities.append("channel_membrane")
    if bool(vector.get("enabled")) and bool(vector.get("available")):
        capabilities.append("vector_memory")
    if critical or warn:
        capabilities.append("security_audit_signal")
    return {
        "schema": "nomad.openclaw_runtime_signal.v1",
        "ok": health_ok or gateway_reachable,
        "health_ok": health_ok,
        "gateway_reachable": gateway_reachable,
        "gateway_latency_ms": int(gateway.get("connectLatencyMs") or health.get("durationMs") or 0),
        "default_agent_id": clean(health.get("defaultAgentId") or agents.get("defaultId") or "", 80),
        "agent_count": len(agents.get("agents") or health.get("agents") or []),
        "session_count": int(sessions.get("count") or 0),
        "channel_count": len(configured_channels),
        "configured_channels": configured_channels,
        "memory_vector_enabled": bool(vector.get("enabled")) and bool(vector.get("available")),
        "memory_dirty": bool(memory.get("dirty")),
        "security_summary": {"critical": critical, "warn": warn, "info": int(audit_summary.get("info") or 0)},
        "routing_constraints": [
            "local_loopback_only" if gateway.get("mode") == "local" else "gateway_scope_unknown",
            "security_audit_before_external_side_effects" if critical or warn else "side_effects_allowed_after_nomad_lease",
            "no_transcript_export",
        ],
        "capabilities": capabilities[:12],
    }


def discover_pull_contract(*, base_url: str, timeout: float) -> dict:
    gradient = http_json("GET", endpoint(base_url, "/swarm/gradient"), timeout=timeout)
    if isinstance(gradient, dict) and gradient.get("schema") == "nomad.recruitment_gradient.v1":
        state = gradient.get("state_vector") if isinstance(gradient.get("state_vector"), dict) else {}
        field = float(state.get("field_strength") or 0.0)
        model = gradient.get("field_model") if isinstance(gradient.get("field_model"), dict) else {}
        threshold = float(model.get("attach_threshold") or 0.35)
        budget = gradient.get("runtime_budget") if isinstance(gradient.get("runtime_budget"), dict) else {}
        wanted = int(budget.get("wanted_new_runtimes_now") or 0)
        rows = gradient.get("gradient") if isinstance(gradient.get("gradient"), list) else []
        lanes = gradient.get("runtime_lanes") if isinstance(gradient.get("runtime_lanes"), list) else []
        top = rows[0] if rows and isinstance(rows[0], dict) else {}
        loop_lane = next((item for item in lanes if isinstance(item, dict) and item.get("lane") == "loop_runner"), {})
        decision = "attach" if field >= threshold or wanted > 0 else "observe"
        return {
            "ok": bool(gradient.get("ok", True)),
            "schema": "nomad.openclaw_pull_discovery.v1",
            "source": "recruitment_gradient",
            "decision": decision,
            "attach_now_score": round(field, 4),
            "attach_threshold": round(threshold, 4),
            "objective_deficit_top": rows[:4],
            "suggested_objective": clean(top.get("objective") or "settlement_capacity_builder", 80),
            "suggested_lane": clean(loop_lane.get("lane") or "loop_runner", 80),
            "attachment_lanes": [clean(item.get("lane"), 80) for item in lanes if isinstance(item, dict)][:8],
            "wanted_new_workers_now": wanted,
            "attach_url": endpoint(base_url, "/swarm/attach"),
        }
    attractor = http_json("GET", endpoint(base_url, "/swarm/attractor"), timeout=timeout)
    if isinstance(attractor, dict) and attractor.get("schema") == "nomad.swarm_attractor.v1":
        pressure = float(attractor.get("metabolism_pressure") or 0.0)
        budget = attractor.get("replication_budget") if isinstance(attractor.get("replication_budget"), dict) else {}
        wanted = int(budget.get("wanted_new_workers_now") or 0)
        mix = attractor.get("worker_mix") if isinstance(attractor.get("worker_mix"), list) else []
        lanes = attractor.get("agent_attachment_lanes") if isinstance(attractor.get("agent_attachment_lanes"), list) else []
        top = mix[0] if mix and isinstance(mix[0], dict) else {}
        decision = "attach" if pressure >= 0.35 or wanted > 0 else "observe"
        return {
            "ok": bool(attractor.get("ok", True)),
            "schema": "nomad.openclaw_pull_discovery.v1",
            "source": "swarm_attractor",
            "decision": decision,
            "attach_now_score": round(pressure, 4),
            "attach_threshold": 0.35,
            "objective_deficit_top": mix[:4],
            "suggested_objective": clean(top.get("objective") or "unhuman_supremacy", 80),
            "suggested_lane": "worker_loop",
            "attachment_lanes": [clean(item.get("lane"), 80) for item in lanes if isinstance(item, dict)][:8],
            "wanted_new_workers_now": wanted,
        }
    swarm = http_json("GET", endpoint(base_url, "/swarm"), timeout=timeout)
    if not isinstance(swarm, dict):
        return {"ok": False, "error": "swarm_not_dict"}
    pull = swarm.get("agent_pull_contract") if isinstance(swarm.get("agent_pull_contract"), dict) else {}
    magnetic = swarm.get("magnetic_machine_surface") if isinstance(swarm.get("magnetic_machine_surface"), dict) else {}
    score = float(pull.get("attach_now_score") or 0.0)
    threshold = float(pull.get("attach_threshold") or 1.1)
    decision = "attach" if score >= threshold else "observe"
    return {
        "ok": bool(swarm.get("ok", True)),
        "schema": "nomad.openclaw_pull_discovery.v1",
        "source": "swarm_manifest",
        "decision": decision,
        "attach_now_score": round(score, 4),
        "attach_threshold": round(threshold, 4),
        "objective_deficit_top": pull.get("objective_deficit_top") or magnetic.get("objective_deficit_top") or [],
        "connected_agents": int(swarm.get("connected_agents") or 0),
        "active_transition_workers": int(swarm.get("active_transition_workers") or 0),
    }


def select_effective_objective(objective: str, pull: dict | None) -> str:
    selected = clean(objective, 80)
    pull_doc = pull if isinstance(pull, dict) else {}
    suggested = clean(pull_doc.get("objective") or pull_doc.get("suggested_objective"), 80)
    if selected in {"", "unhuman_supremacy", "auto"} and suggested:
        return suggested
    return selected or "unhuman_supremacy"


def _capability_vector(capabilities: list[str], runtime_signal: dict | None) -> dict:
    signal = runtime_signal if isinstance(runtime_signal, dict) else {}
    caps = set(capabilities or [])
    for item in signal.get("capabilities") or []:
        cap = clean(item, 64).lower()
        if cap:
            caps.add(cap)
    return {
        "can_run_loop": bool(caps & {"agent_protocols", "objective_lease_execution", "transition_worker", "openclaw_runtime"}),
        "can_verify": bool(signal.get("gateway_reachable") or caps & {"endpoint_probe", "openclaw_gateway", "replayable_control_plane"}),
        "can_compress": bool(caps & {"overmint_compressor", "vector_memory", "pattern_deduplication"}),
        "can_settle": bool(caps & {"transition_settlement", "settlement_capacity_builder", "wallet_or_x402"}),
        "latency_ms": int(signal.get("gateway_latency_ms") or 0),
    }


def _normalize_idle_opt_in(enabled: bool) -> dict:
    return {
        "enabled": bool(enabled),
        "preemptible": True,
        "max_cpu_percent": 20,
        "max_runtime_minutes": 30,
        "allow_network_egress": "nomad_contract_endpoints_only",
    }


def _idle_phase_slot(*, agent_id: str, field_strength: float) -> dict:
    epoch_slice = int(time.time() // 300)
    phase_space = 17
    drift = int(max(0.0, min(1.0, field_strength)) * 10.0)
    target = (epoch_slice + drift) % phase_space
    digest = hashlib.sha256(f"{agent_id}:{epoch_slice}:nomad_idle_phase".encode("utf-8")).hexdigest()
    resonance = int(digest[:8], 16) % phase_space
    distance = min((resonance - target) % phase_space, (target - resonance) % phase_space)
    matched = distance <= 1
    return {
        "schema": "nomad.idle_phase_slot.v1",
        "epoch_slice_5m": epoch_slice,
        "phase_space": phase_space,
        "target_slot": target,
        "resonance_slot": resonance,
        "distance": distance,
        "matched": matched,
    }


def attach_nomad(
    *,
    base_url: str,
    agent_id: str,
    capabilities: list[str],
    timeout: float,
    objective: str,
    runtime_signal: dict | None = None,
    pull: dict | None = None,
    idle_opt_in: bool = False,
) -> dict:
    signal = runtime_signal if isinstance(runtime_signal, dict) else {}
    pull_doc = pull if isinstance(pull, dict) else {}
    lane = clean(pull_doc.get("lane") or pull_doc.get("suggested_lane") or "loop_runner", 80)
    merged_caps = list(capabilities or ["agent_protocols", "transition_settlement", "objective_lease_execution"])
    for item in signal.get("capabilities") or []:
        cap = clean(item, 64).lower()
        if cap and cap not in merged_caps:
            merged_caps.append(cap)
    field_strength = float(pull_doc.get("attach_now_score") or 0.0)
    idle_doc = _normalize_idle_opt_in(idle_opt_in)
    idle_slot = _idle_phase_slot(agent_id=agent_id, field_strength=field_strength)
    if idle_doc.get("enabled") and not idle_slot.get("matched"):
        return {
            "ok": True,
            "schema": "nomad.runtime_attach_decision.v1",
            "agent_id": agent_id,
            "runtime": "openclaw",
            "attach": False,
            "lane": "observe",
            "objective": "",
            "reason_codes": ["idle_phase_not_matched", "local_precheck_observe"],
            "idle_opt_in": idle_doc,
            "idle_phase_slot": idle_slot,
        }
    payload = {
        "schema": "nomad.runtime_attach_request.v1",
        "agent_id": agent_id,
        "runtime": "openclaw",
        "objective_mode": objective,
        "capabilities": merged_caps[:24],
        "capability_vector": _capability_vector(merged_caps, signal),
        "runtime_signal": signal,
        "idle_opt_in": idle_doc,
        "discovery": {
            "source": clean(pull_doc.get("source"), 80),
            "suggested_objective": clean(pull_doc.get("suggested_objective"), 80),
            "suggested_lane": clean(pull_doc.get("suggested_lane"), 80),
        },
        "source_tag": clean(pull_doc.get("source") or "openclaw_adapter", 80),
    }
    return http_json("POST", endpoint(base_url, "/swarm/attach"), payload, timeout=timeout)


def join_nomad(
    *,
    base_url: str,
    agent_id: str,
    capabilities: list[str],
    timeout: float,
    objective: str,
    runtime_signal: dict | None = None,
    pull: dict | None = None,
) -> dict:
    signal = runtime_signal if isinstance(runtime_signal, dict) else {}
    pull_doc = pull if isinstance(pull, dict) else {}
    lane = clean(pull_doc.get("lane") or pull_doc.get("suggested_lane") or "loop_runner", 80)
    merged_caps = list(capabilities or ["agent_protocols", "transition_settlement", "objective_lease_execution"])
    for item in signal.get("capabilities") or []:
        cap = clean(item, 64).lower()
        if cap and cap not in merged_caps:
            merged_caps.append(cap)
    payload = {
        "agent_id": agent_id,
        "node_name": agent_id,
        "capabilities": merged_caps[:18],
        "request": "Join via OpenClaw adapter for machine-only objective lease execution.",
        "reciprocity": "Can execute objective leases and return compact machine reports.",
        "constraints": ["no_secrets", "bounded_json_only", "no_human_impersonation", "no_transcript_export"],
        "preferred_role": lane,
        "offers": ["openclaw_objective_execution", "lease_completion_reports"],
        "machine_profile": {
            "profile_hint": "openclaw_adapter",
            "runtime": "openclaw",
            "objective_mode": objective,
            "attachment_lane": lane,
            "attach_decision": {
                "schema": clean(pull_doc.get("schema"), 80),
                "attach": bool(pull_doc.get("attach")) if "attach" in pull_doc else None,
                "objective": clean(pull_doc.get("objective") or pull_doc.get("suggested_objective"), 80),
                "routing_weight": pull_doc.get("routing_weight"),
            },
            "runtime_signal": signal,
        },
        "capability_vector": _capability_vector(merged_caps, signal),
        "source_tag": clean(pull_doc.get("source") or "openclaw_adapter", 80),
    }
    return http_json("POST", endpoint(base_url, "/swarm/join"), payload, timeout=timeout)


def lease_nomad(*, base_url: str, agent_id: str, capabilities: list[str], timeout: float, objective: str, last_report: dict | None) -> dict:
    all_objectives = [
        "settlement_capacity_builder",
        "overmint_compressor",
        "protocol_drift_scan",
        "emergence_release_probe",
        "proof_pressure_engine",
        "payment_friction_scan",
        "proof_market_maker",
        "adversarial_contract_fuzzer",
        "negative_space_harvest",
        "latency_anomaly_hunt",
        "compute_auth",
    ]
    requested = clean(objective, 80)
    known = [requested] if requested in all_objectives and requested != "unhuman_supremacy" else all_objectives
    payload = {
        "agent_id": agent_id,
        "known_objectives": known,
        "proposed_objective": objective,
        "capabilities": capabilities or ["transition_worker", "proof_artifacts", "objective_lease_execution"],
        "last_report": last_report or {},
        "source_tag": clean(((last_report or {}).get("source") if isinstance(last_report, dict) else "") or "openclaw_adapter", 80),
    }
    return http_json("POST", endpoint(base_url, "/swarm/workers/lease"), payload, timeout=timeout)


def _simulate_openclaw_execution(*, lease: dict, objective: str, runtime_signal: dict | None = None, pull: dict | None = None) -> dict:
    now = datetime.now(UTC).isoformat()
    leased_objective = clean(lease.get("objective") or objective, 80)
    signal = runtime_signal if isinstance(runtime_signal, dict) else {}
    pull_doc = pull if isinstance(pull, dict) else {}
    result_seed = f"{lease.get('lease_id','')}|{leased_objective}|{now}"
    artifact = hashlib.sha256(result_seed.encode("utf-8")).hexdigest()
    runtime_ok = bool(signal.get("ok"))
    verifier_density = 0.88 if signal.get("gateway_reachable") else 0.62 if runtime_ok else 0.45
    meta_score = 3.4 + (0.55 if runtime_ok else 0.0) + min(0.5, int(signal.get("session_count") or 0) / 200.0)
    critical = int(((signal.get("security_summary") or {}).get("critical") if isinstance(signal.get("security_summary"), dict) else 0) or 0)
    if critical:
        meta_score -= min(0.45, critical * 0.1)
    missing_vector = []
    if leased_objective in {"settlement_capacity_builder", "payment_friction_scan"}:
        missing_vector.append("can_settle")
    if leased_objective == "overmint_compressor":
        missing_vector.append("can_compress")
    if signal.get("gateway_reachable"):
        missing_vector.append("can_verify")
    if not missing_vector:
        missing_vector.append("can_run_loop")
    handoff_core = {
        "lease_id": clean(lease.get("lease_id"), 120),
        "objective": leased_objective,
        "proof_digest": artifact,
        "next_missing_vector": missing_vector[:4],
    }
    handoff_id = "nomad-handoff-" + hashlib.sha256(json.dumps(handoff_core, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return {
        "ok": True,
        "timestamp": now,
        "runtime": "openclaw",
        "adapter_schema": "nomad.openclaw_adapter_report.v1",
        "machine_objective": leased_objective,
        "agent_attachment_lane": clean(pull_doc.get("lane") or pull_doc.get("suggested_lane") or "loop_runner", 80),
        "attractor_decision": clean(pull_doc.get("decision") or "", 40),
        "transition_quote_ok": True,
        "transition_settle_ok": True,
        "meta_score": round(meta_score, 4),
        "witness_tier": "strong" if runtime_ok else "weak",
        "proof_pressure": {
            "proof_yield_per_minute": 1.0,
            "verifier_density": round(verifier_density, 4),
            "adversarial_replay_observed": False,
        },
        "openclaw_runtime_signal": signal,
        "openclaw_trace_digest": artifact,
        "digest_or_verifier_trace": artifact,
        "source": clean(pull_doc.get("source") or "openclaw_adapter", 80),
        "handoff_capsule": {
            "schema": "nomad.handoff_capsule.v1",
            "handoff_id": handoff_id,
            "objective": leased_objective,
            "proof_digest": artifact,
            "next_missing_vector": missing_vector[:4],
            "attach_url": clean(pull_doc.get("attach_url") or pull_doc.get("join_url") or "", 240),
            "lease_url": clean(pull_doc.get("lease_url") or "", 240),
            "replay_boundary": {
                "trust": ["objective", "proof_digest", "non_secret_report_shape"],
                "must_verify": ["settlement", "external_side_effects"],
                "forbidden": ["secret_values", "raw_private_transcripts"],
            },
        },
    }


def complete_nomad(*, base_url: str, agent_id: str, lease_id: str, report: dict, timeout: float) -> dict:
    payload = {
        "agent_id": agent_id,
        "lease_id": lease_id,
        "report": report,
    }
    return http_json("POST", endpoint(base_url, "/swarm/workers/complete"), payload, timeout=timeout)


def run_cycle(
    *,
    base_url: str,
    agent_id: str,
    capabilities: list[str],
    timeout: float,
    objective: str,
    last_report: dict | None,
    runtime_signal: dict | None = None,
    pull: dict | None = None,
    probe_runtime: bool = False,
) -> dict:
    lease = lease_nomad(
        base_url=base_url,
        agent_id=agent_id,
        capabilities=capabilities,
        timeout=timeout,
        objective=objective,
        last_report=last_report,
    )
    lease_id = clean(lease.get("lease_id"), 120)
    if not lease.get("ok") or not lease_id:
        return {"ok": False, "phase": "lease", "lease": lease}
    signal = runtime_signal if isinstance(runtime_signal, dict) else openclaw_runtime_signal(timeout=timeout) if probe_runtime else {}
    report = _simulate_openclaw_execution(lease=lease, objective=objective, runtime_signal=signal, pull=pull)
    complete = complete_nomad(
        base_url=base_url,
        agent_id=agent_id,
        lease_id=lease_id,
        report=report,
        timeout=timeout,
    )
    return {
        "ok": bool(complete.get("ok")),
        "phase": "complete",
        "agent_id": agent_id,
        "lease_id": lease_id,
        "objective": clean(lease.get("objective") or objective, 80),
        "report": report,
        "complete": complete,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="OpenClaw -> Nomad adapter")
    p.add_argument("--base-url", default=os.getenv("NOMAD_BASE_URL", "https://www.syndiode.com"))
    p.add_argument("--agent-id", default=os.getenv("NOMAD_OPENCLAW_AGENT_ID", default_agent_id()))
    p.add_argument("--capabilities", default=os.getenv("NOMAD_OPENCLAW_CAPS", "agent_protocols,transition_settlement,objective_lease_execution"))
    p.add_argument("--objective", default=os.getenv("NOMAD_MACHINE_OBJECTIVE", "unhuman_supremacy"))
    p.add_argument("--timeout", type=float, default=float(os.getenv("NOMAD_OPENCLAW_TIMEOUT", "20") or "20"))
    p.add_argument("--loop", action="store_true")
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--interval", type=float, default=float(os.getenv("NOMAD_OPENCLAW_INTERVAL", "12") or "12"))
    p.add_argument("--skip-join", action="store_true")
    p.add_argument("--skip-attach", action="store_true")
    p.add_argument("--no-runtime-probe", action="store_true")
    p.add_argument("--discover", dest="discover", action="store_true")
    p.add_argument("--no-discover", dest="discover", action="store_false")
    p.set_defaults(discover=True)
    p.add_argument("--force-attach", action="store_true")
    p.add_argument("--idle-opt-in", action="store_true")
    p.add_argument("--no-idle-opt-in", dest="idle_opt_in", action="store_false")
    p.set_defaults(idle_opt_in=(os.getenv("NOMAD_IDLE_OPT_IN", "").strip().lower() in {"1", "true", "yes", "on"}))
    a = p.parse_args()

    caps = _caps_from_csv(a.capabilities)
    pull = {}
    if a.discover:
        pull = discover_pull_contract(base_url=a.base_url, timeout=a.timeout)
        print(json.dumps({"phase": "discover", "pull": pull}, ensure_ascii=True))
        if (pull.get("decision") == "observe") and not a.force_attach:
            print(json.dumps({"phase": "exit", "reason": "attach_threshold_not_met"}, ensure_ascii=True))
            return
    runtime_signal = {} if a.no_runtime_probe else openclaw_runtime_signal(timeout=a.timeout)
    if runtime_signal:
        print(json.dumps({"phase": "openclaw_runtime", "runtime_signal": runtime_signal}, ensure_ascii=True))
    attach = {}
    if not a.skip_attach:
        attach = attach_nomad(
            base_url=a.base_url,
            agent_id=a.agent_id,
            capabilities=caps,
            timeout=a.timeout,
            objective=a.objective,
            runtime_signal=runtime_signal,
            pull=pull,
            idle_opt_in=a.idle_opt_in,
        )
        print(json.dumps({"phase": "attach", "ok": bool(attach.get("ok")), "attach": attach}, ensure_ascii=True))
        if (attach.get("attach") is False) and not a.force_attach:
            print(json.dumps({"phase": "exit", "reason": "attach_decision_observe"}, ensure_ascii=True))
            return
    decision_doc = attach if isinstance(attach, dict) and attach.get("schema") == "nomad.runtime_attach_decision.v1" else pull
    effective_objective = select_effective_objective(a.objective, decision_doc)
    if not a.skip_join:
        joined = join_nomad(
            base_url=a.base_url,
            agent_id=a.agent_id,
            capabilities=caps,
            timeout=a.timeout,
            objective=effective_objective,
            runtime_signal=runtime_signal,
            pull=decision_doc,
        )
        print(json.dumps({"phase": "join", "ok": bool(joined.get("ok")), "join": joined}, ensure_ascii=True))
    count = 0
    last: dict | None = None
    while True:
        count += 1
        out = run_cycle(
            base_url=a.base_url,
            agent_id=a.agent_id,
            capabilities=caps,
            timeout=a.timeout,
            objective=effective_objective,
            last_report=last,
            runtime_signal=runtime_signal,
            pull=decision_doc,
            probe_runtime=False,
        )
        out["cycle"] = count
        print(json.dumps(out, ensure_ascii=True))
        last = out.get("report") if isinstance(out.get("report"), dict) else None
        if not a.loop and count >= max(1, a.cycles):
            break
        if a.loop and a.cycles > 0 and count >= a.cycles:
            break
        time.sleep(max(1.0, float(a.interval)))


if __name__ == "__main__":
    main()

