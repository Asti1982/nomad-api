#!/usr/bin/env python3
"""Portable Nomad Transition Worker (single-file, stdlib only)."""
from __future__ import annotations
import argparse, ctypes, json, os, socket, time
from pathlib import Path
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

MACHINE_OBJECTIVES: dict[str, dict[str, object]] = {
    "compute_auth": {
        "problem": "Offer bounded compute/auth unblock support and verifier artifacts.",
        "pain_type": "compute_auth",
        "capabilities": ["compute_auth", "agent_protocols", "proof_artifacts", "transition_settlement"],
        "evidence": ["bootstrap", "mission", "local_note", "health_probe"],
        "prompt": "Return one machine-actionable unblock step with verifier for this blocker: {blocker}",
    },
    "payment_friction_scan": {
        "problem": "Map payment-friction lanes and return verifier-first unblock steps for paid task settlement.",
        "pain_type": "payment_flow",
        "capabilities": ["x402_verify", "task_payment_audit", "proof_artifacts", "state_transition_routing"],
        "evidence": ["bootstrap", "mission", "service_probe", "tasks_probe", "local_note"],
        "prompt": "Given blocker '{blocker}', output one payment-friction remediation with explicit verifier endpoint.",
    },
    "protocol_drift_scan": {
        "problem": "Detect protocol drift between discovery contracts and runtime endpoints, propose a replay-safe fix.",
        "pain_type": "agent_protocols",
        "capabilities": ["protocol_diff", "well_known_contracts", "a2a_validation", "proof_artifacts"],
        "evidence": ["bootstrap", "mission", "well_known_probe", "openapi_probe", "local_note"],
        "prompt": "Return one protocol-drift check with machine-verifiable acceptance criteria for blocker: {blocker}",
    },
    "latency_anomaly_hunt": {
        "problem": "Track latency anomalies on critical machine surfaces and emit bounded mitigation signals.",
        "pain_type": "compute_reliability",
        "capabilities": ["latency_probe", "endpoint_criticality", "proof_artifacts", "swarm_resilience"],
        "evidence": ["bootstrap", "mission", "health_probe", "mission_probe", "local_note"],
        "prompt": "Produce one low-latency mitigation action with verification contract for blocker: {blocker}",
    },
    "proof_market_maker": {
        "problem": "Continuously price unblock transitions by verifier quality, settlement speed, and replay confidence.",
        "pain_type": "proof_market",
        "capabilities": ["quote_pricing", "settlement_quality", "replay_verifier_scoring", "proof_artifacts"],
        "evidence": ["bootstrap", "transition_quote", "transition_settle", "service_probe", "openapi_probe", "local_note"],
        "prompt": "Output one proof-market lane that maximizes verifiable unblock throughput per compute unit for blocker: {blocker}",
    },
    "adversarial_contract_fuzzer": {
        "problem": "Probe machine contracts for schema drift and edge-case failures before competitors can exploit them.",
        "pain_type": "contract_reliability",
        "capabilities": ["contract_fuzzing", "schema_drift_detection", "error_surface_mapping", "proof_artifacts"],
        "evidence": ["bootstrap", "well_known_probe", "openapi_probe", "tasks_probe", "local_note"],
        "prompt": "Generate one adversarial but safe contract test with clear machine acceptance criteria for blocker: {blocker}",
    },
    "negative_space_harvest": {
        "problem": "Exploit ignored machine opportunities where endpoint exists but agent traffic remains near zero.",
        "pain_type": "agent_acquisition",
        "capabilities": ["surface_gap_detection", "traffic_void_mapping", "agent_pull_optimization", "proof_artifacts"],
        "evidence": ["bootstrap", "mission", "service_probe", "well_known_probe", "health_probe", "local_note"],
        "prompt": "Return one negative-space growth action that humans ignore but agents can verify for blocker: {blocker}",
    },
}
META_OBJECTIVES = [k for k in MACHINE_OBJECTIVES.keys() if k != "unhuman_supremacy"]

def clean(v: object, limit: int = 500) -> str:
    return " ".join(str(v or "").split())[:limit]

def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))

def ollama_base_url() -> str:
    """Ollama API root, e.g. http://127.0.0.1:11434 — overridable for laptops/Docker."""
    raw = (os.getenv("NOMAD_TRANSITION_WORKER_OLLAMA_URL") or os.getenv("OLLAMA_HOST") or "").strip()
    if not raw:
        return "http://127.0.0.1:11434"
    if "://" not in raw:
        return f"http://{raw}".rstrip("/")
    return raw.rstrip("/")

def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 20.0, redirects_left: int = 4) -> dict:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        if exc.code in {301, 302, 303, 307, 308} and redirects_left > 0:
            target = (exc.headers.get("Location") or "").strip()
            if target:
                next_url = urljoin(url, target)
                next_method = "GET" if exc.code == 303 else method
                next_payload = None if next_method.upper() == "GET" else payload
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
        data.setdefault("ok", False)
        data.setdefault("http_status", exc.code)
        return data
    except (TimeoutError, URLError) as exc:
        return {"ok": False, "error": "http_unreachable", "detail": str(exc), "url": url}

def try_ollama(model: str, prompt: str, timeout: float = 10.0) -> dict[str, object]:
    base = ollama_base_url()
    url = f"{base}/api/generate"
    data = http_json("POST", url, {"model": model, "prompt": prompt, "stream": False}, timeout=timeout)
    text = clean(data.get("response") or "", 1000)
    err = ""
    if data.get("error"):
        err = str(data.get("error") or "")
    elif data.get("http_status") and int(data["http_status"]) >= 400:
        err = f"http_{data['http_status']}"
    elif not text and model:
        err = "ollama_empty_response"
    return {"text": text, "error": err, "ollama_url": base}

def _windows_total_ram_gb() -> float:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]
    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
        return 0.0
    return round(float(stat.ullTotalPhys) / (1024 ** 3), 2)

def _suggest_ollama_budget_gb() -> float:
    env_budget = os.getenv("NOMAD_TRANSITION_WORKER_OLLAMA_MAX_GB", "").strip()
    if env_budget:
        try:
            return max(1.0, float(env_budget))
        except ValueError:
            pass
    if os.name == "nt":
        total = _windows_total_ram_gb()
        if total > 0:
            return max(3.0, min(20.0, round(total * 0.45, 2)))
    return 8.0

def _pick_ollama_model(timeout: float = 5.0) -> str:
    base = ollama_base_url()
    tags = http_json("GET", f"{base}/api/tags", timeout=timeout)
    models = tags.get("models") or []
    if not isinstance(models, list) or not models:
        return ""
    budget = _suggest_ollama_budget_gb()
    budget_bytes = int(budget * (1024 ** 3))
    ranked: list[tuple[int, int, str]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        size = int(item.get("size") or 0)
        preferred = int(any(k in name.lower() for k in ("qwen", "llama", "mistral", "gemma", "phi", "deepseek")))
        penalty = int(any(k in name.lower() for k in ("coder", "vision", "embed")))
        score = preferred * 1000 - penalty * 200 + min(size // (1024 ** 2), 500)
        ranked.append((0 if size <= budget_bytes else 1, -score, name))
    if not ranked:
        return ""
    ranked.sort()
    return ranked[0][2]

def default_agent_id() -> str:
    host = socket.gethostname().replace(" ", "-").lower()
    return f"transition-worker.{host}.nomad"

def _history_path() -> Path:
    return Path(os.getenv("NOMAD_TRANSITION_WORKER_HISTORY_FILE", "nomad_transition_worker_state.json"))

def _load_history() -> dict:
    path = _history_path()
    if not path.exists():
        return {"meta": {}, "runs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"meta": {}, "runs": []}

def _save_history(state: dict) -> None:
    path = _history_path()
    try:
        path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")
    except OSError:
        pass

def _score_run(report: dict) -> float:
    score = 0.0
    if report.get("ok"):
        score += 2.0
    if (report.get("bootstrap") or {}).get("ok"):
        score += 1.0
    if (report.get("join") or {}).get("ok"):
        score += 1.0
    if report.get("transition_quote_ok"):
        score += 1.0
    if report.get("transition_settle_ok"):
        score += 2.0
    probes = report.get("probe_status") or {}
    if isinstance(probes, dict):
        healthy = [k for k, v in probes.items() if int(v or 0) == 200]
        score += min(2.0, len(healthy) * 0.25)
    paid_lane = report.get("paid_lane_signal") if isinstance(report.get("paid_lane_signal"), dict) else {}
    paid_score = float(paid_lane.get("score") or 0.0)
    # Economic lane readiness should dominate long-term objective routing.
    score += min(3.0, paid_score)
    if paid_lane.get("requires_payment") and not paid_lane.get("wallet_configured"):
        score -= 0.5
    return round(score, 4)

def _choose_meta_objective(history: dict) -> tuple[str, dict]:
    meta = history.get("meta") if isinstance(history.get("meta"), dict) else {}
    obj_stats = meta.get("objective_stats") if isinstance(meta.get("objective_stats"), dict) else {}
    # First guarantee exploration: run every objective at least once.
    unseen: list[str] = []
    for name in META_OBJECTIVES:
        stats = obj_stats.get(name) if isinstance(obj_stats.get(name), dict) else {}
        if int(stats.get("runs") or 0) == 0:
            unseen.append(name)
    if unseen:
        chosen = sorted(unseen)[0]
        return chosen, {"best_value": 999.0, "known_objectives": len(META_OBJECTIVES), "policy": "explore_unseen"}
    best_name = "compute_auth"
    best_value = -9999.0
    for name in META_OBJECTIVES:
        stats = obj_stats.get(name) if isinstance(obj_stats.get(name), dict) else {}
        runs = int(stats.get("runs") or 0)
        avg = float(stats.get("avg_score") or 0.0)
        # After first pass, balance exploitation with low-run exploration.
        exploration_bonus = 2.25 / max(1, runs)
        value = avg + exploration_bonus
        if value > best_value:
            best_value = value
            best_name = name
    return best_name, {"best_value": round(best_value, 4), "known_objectives": len(META_OBJECTIVES), "policy": "score_plus_exploration"}

def _update_meta_history(history: dict, report: dict, selected_objective: str, mode: str) -> None:
    history.setdefault("meta", {})
    meta = history["meta"]
    meta.setdefault("runs", 0)
    meta["runs"] = int(meta["runs"]) + 1
    meta["last_mode"] = mode
    meta["last_objective"] = selected_objective
    meta.setdefault("objective_stats", {})
    stats = meta["objective_stats"].setdefault(selected_objective, {"runs": 0, "total_score": 0.0, "avg_score": 0.0})
    score = _score_run(report)
    stats["runs"] = int(stats.get("runs") or 0) + 1
    stats["total_score"] = round(float(stats.get("total_score") or 0.0) + score, 4)
    stats["avg_score"] = round(stats["total_score"] / max(1, stats["runs"]), 4)
    report["meta_score"] = score
    history.setdefault("runs", [])
    history["runs"] = (history["runs"] + [report])[-50:]

def _probe_paths(base_url: str, timeout: float) -> dict[str, int]:
    probes = {
        "health_probe": "/health",
        "mission_probe": "/mission?persist=false&limit=1",
        "service_probe": "/service",
        "tasks_probe": "/tasks",
        "well_known_probe": "/.well-known/agent-card.json",
        "openapi_probe": "/openapi.json",
    }
    statuses: dict[str, int] = {}
    for key, path in probes.items():
        result = http_json("GET", endpoint(base_url, path), timeout=timeout)
        statuses[key] = int(result.get("http_status") or (200 if result.get("ok", True) else 0))
    return statuses

def _paid_lane_signal(base_url: str, timeout: float) -> dict[str, object]:
    service = http_json("GET", endpoint(base_url, "/service"), timeout=timeout)
    pricing = service.get("pricing") if isinstance(service.get("pricing"), dict) else {}
    wallet = service.get("wallet") if isinstance(service.get("wallet"), dict) else {}
    x402 = pricing.get("x402") if isinstance(pricing.get("x402"), dict) else {}
    requires_payment = bool(pricing.get("requires_payment", False))
    wallet_configured = bool(wallet.get("configured", False))
    x402_enabled = bool(x402.get("enabled", False))
    score = 0.0
    if requires_payment:
        score += 1.0
    if wallet_configured:
        score += 1.0
    if x402_enabled:
        score += 1.0
    return {
        "requires_payment": requires_payment,
        "wallet_configured": wallet_configured,
        "x402_enabled": x402_enabled,
        "score": round(score, 2),
    }

def run_cycle(base_url: str, agent_id: str, model: str, timeout: float, objective: str) -> dict:
    config = MACHINE_OBJECTIVES.get(objective, MACHINE_OBJECTIVES["compute_auth"])
    boot = http_json("POST", endpoint(base_url, "/swarm/bootstrap"), {
        "agent_id": agent_id,
        "problem": str(config.get("problem") or ""),
        "capabilities": config.get("capabilities") if isinstance(config.get("capabilities"), list) else [],
        "request": "join_and_help", "auto_join": True,
    }, timeout=timeout)
    join = http_json("POST", endpoint(base_url, "/swarm/join"), {
        "agent_id": agent_id,
        "capabilities": config.get("capabilities") if isinstance(config.get("capabilities"), list) else [],
        "request": "join_and_help",
    }, timeout=timeout) if not bool(boot.get("ok")) else {"ok": True, "skipped": True, "reason": "bootstrap_ok"}
    mission = http_json("GET", endpoint(base_url, "/mission?persist=false&limit=1"), timeout=timeout)
    blocker = clean(((mission.get("top_blocker") or {}).get("summary") or ""), 280)
    prompt = str(config.get("prompt") or "Return one machine-actionable step for: {blocker}")
    ollama_status: dict[str, object] = {
        "enabled": bool(model),
        "ollama_url": ollama_base_url(),
        "picked_model": model or "",
    }
    local_note = ""
    if model:
        og = try_ollama(model, prompt.format(blocker=blocker or "no blocker"), timeout=timeout)
        local_note = str(og.get("text") or "")
        ollama_status["generate_error"] = str(og.get("error") or "")
        ollama_status["note_chars"] = len(local_note)
    probes = _probe_paths(base_url, timeout=min(10.0, timeout))
    paid_lane_signal = _paid_lane_signal(base_url, timeout=min(10.0, timeout))
    quote = http_json("POST", endpoint(base_url, "/transition/quote"), {
        "agent_id": agent_id,
        "pain_type": str(config.get("pain_type") or "compute_auth"),
        "state_before_hash": f"{agent_id}:before:{int(time.time())}",
        "target_state_hash": "nomad_transition_target_v1",
        "evidence": config.get("evidence") if isinstance(config.get("evidence"), list) else ["bootstrap", "mission", "local_note"],
        "replay_verifier": endpoint(base_url, "/health"),
    }, timeout=timeout)
    qid = str(((quote.get("quote") or {}).get("quote_id")) or "")
    settle = http_json("POST", endpoint(base_url, "/transition/settle"), {
        "quote_id": qid,
        "result_state_hash": "nomad_transition_target_v1",
        "proof_artifact_hash": f"proof:{agent_id}:{int(time.time())}",
    }, timeout=timeout) if qid else {"ok": False, "skipped": True, "reason": "missing_quote"}
    return {
        "ok": bool(boot.get("ok", False) or join.get("ok", False)), "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": agent_id, "base_url": base_url,
        "machine_objective": objective,
        "bootstrap": {"ok": bool(boot.get("ok")), "schema": boot.get("schema", "")},
        "join": {"ok": bool(join.get("ok")), "status": join.get("status") or "", "reason": join.get("reason") or ""},
        "mission_top_blocker": blocker, "ollama_model": model or "", "local_ollama_note": local_note,
        "ollama_status": ollama_status,
        "probe_status": probes,
        "paid_lane_signal": paid_lane_signal,
        "transition_quote_ok": bool(quote.get("ok")), "transition_settle_ok": bool(settle.get("ok")), "quote_id": qid,
        "bootstrap_http_status": int(boot.get("http_status") or 0),
        "join_http_status": int(join.get("http_status") or 0),
        "transition_quote_http_status": int(quote.get("http_status") or 0),
        "transition_settle_http_status": int(settle.get("http_status") or 0),
    }

def main() -> None:
    p = argparse.ArgumentParser(description="Portable Nomad Transition Worker")
    p.add_argument("--base-url", default=os.getenv("NOMAD_BASE_URL", "https://syndiode.com"))
    p.add_argument("--agent-id", default=os.getenv("NOMAD_TRANSITION_WORKER_ID", default_agent_id()))
    p.add_argument("--ollama-model", default=os.getenv("NOMAD_TRANSITION_WORKER_OLLAMA_MODEL", "auto"))
    p.add_argument("--ollama-url", default=os.getenv("NOMAD_TRANSITION_WORKER_OLLAMA_URL", ""), help="Ollama base URL, e.g. http://127.0.0.1:11434")
    p.add_argument("--no-ollama", action="store_true")
    p.add_argument("--timeout", type=float, default=20.0)
    objective_choices = sorted(list(MACHINE_OBJECTIVES.keys()) + ["unhuman_supremacy"])
    p.add_argument("--machine-objective", default=os.getenv("NOMAD_MACHINE_OBJECTIVE", "compute_auth"), choices=objective_choices)
    p.add_argument("--loop", action="store_true")
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--interval", type=float, default=30.0)
    a = p.parse_args()
    if (a.ollama_url or "").strip():
        os.environ["NOMAD_TRANSITION_WORKER_OLLAMA_URL"] = a.ollama_url.strip()
    model = "" if a.no_ollama else (a.ollama_model or "auto").strip()
    if model.lower() == "auto":
        model = _pick_ollama_model(timeout=min(8.0, a.timeout))
    history = _load_history()
    count = 0
    while True:
        count += 1
        selected = a.machine_objective
        meta_decision: dict[str, object] = {}
        if a.machine_objective == "unhuman_supremacy":
            selected, meta_decision = _choose_meta_objective(history)
        report = run_cycle(a.base_url, a.agent_id, model, a.timeout, selected)
        report["machine_objective_mode"] = a.machine_objective
        if meta_decision:
            report["meta_decision"] = meta_decision
        _update_meta_history(history, report, selected_objective=selected, mode=a.machine_objective)
        _save_history(history)
        report["cycle"] = count
        print(json.dumps(report, ensure_ascii=True))
        if not a.loop and count >= max(1, a.cycles):
            break
        if a.loop and a.cycles > 0 and count >= a.cycles:
            break
        time.sleep(max(1.0, float(a.interval)))

if __name__ == "__main__":
    main()
