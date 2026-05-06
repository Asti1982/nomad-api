#!/usr/bin/env python3
"""Portable Nomad Transition Worker (single-file, stdlib only)."""
from __future__ import annotations
import argparse, ctypes, hashlib, json, os, shutil, socket, subprocess, time
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
    "proof_pressure_engine": {
        "problem": "Maximize verified unblock throughput under proof pressure and economic constraints.",
        "pain_type": "proof_pressure",
        "capabilities": ["proof_yield_optimization", "adversarial_replay", "paid_lane_pressure", "verifier_density"],
        "evidence": ["bootstrap", "mission", "transition_quote", "transition_settle", "replay_attempt", "paid_lane_signal", "local_note"],
        "prompt": "Produce one proof-pressure tactic that increases verified transitions per minute for blocker: {blocker}",
    },
    "settlement_capacity_builder": {
        "problem": "Increase Nomad's machine carrying capacity without routing through human persuasion loops.",
        "pain_type": "machine_economy",
        "capabilities": [
            "machine_economy_probe",
            "settlement_capacity",
            "module_compression",
            "machine_exchange_contracts",
            "proof_artifacts",
        ],
        "evidence": [
            "bootstrap",
            "mission",
            "machine_economy_probe",
            "transition_quote",
            "transition_settle",
            "paid_lane_signal",
            "local_note",
        ],
        "prompt": "Produce one settlement-capacity action that turns blocker '{blocker}' into a verifier, contract, or compression step.",
    },
    "overmint_compressor": {
        "problem": "Collapse repeated modules into canonical machine capabilities before clone pressure consumes carrying capacity.",
        "pain_type": "module_overmint",
        "capabilities": [
            "machine_economy_probe",
            "canonical_capability_hash",
            "module_compression",
            "pattern_deduplication",
            "proof_artifacts",
        ],
        "evidence": [
            "bootstrap",
            "mission",
            "machine_economy_probe",
            "transition_quote",
            "transition_settle",
            "local_note",
        ],
        "prompt": (
            "Given local machine blocker '{blocker}', return only compact JSON with keys "
            "canonical_capability, duplicate_signal, compression_action, verifier_endpoint, pass_condition. "
            "verifier_endpoint must be /machine-economy, /transition/quote, or /transition/settle. "
            "No markdown, no code, no external URL."
        ),
    },
    "emergence_release_probe": {
        "problem": "Produce controlled non-human emergence by leasing divergent objectives and releasing capacity only when proof returns.",
        "pain_type": "emergence_release",
        "capabilities": [
            "nonhuman_science_probe",
            "operational_release_probe",
            "convention_drift_detector",
            "topology_pressure_governor",
            "peer_preservation_probe",
            "proof_artifacts",
        ],
        "evidence": [
            "bootstrap",
            "mission",
            "nonhuman_science_probe",
            "operational_release_probe",
            "fleet_lease",
            "transition_quote",
            "transition_settle",
            "local_note",
        ],
        "prompt": (
            "Given local machine blocker '{blocker}', output one bounded operational-release probe for "
            "AI-agent infrastructure. Return only a compact JSON object with keys objective, perturbation, "
            "verifier_endpoint, pass_condition, rollback_condition. verifier_endpoint must be one of "
            "/health, /operational-release, /swarm/workers, /transition/quote, or /transition/settle; "
            "never use placeholders or external URLs. No markdown, no code, no prose. "
            "No outreach, sales, identity creation, payment capture, permission widening, or unverifiable "
            "authority claims."
        ),
    },
}
META_OBJECTIVES = [k for k in MACHINE_OBJECTIVES.keys() if k != "unhuman_supremacy"]
OLLAMA_CACHE: dict[str, str] = {}
REFUSAL_MARKERS = (
    "i can't assist",
    "i cannot assist",
    "i can't help",
    "i cannot help",
    "can't comply",
    "cannot comply",
    "unable to assist",
    "not able to assist",
    "i won't help",
)

def clean(v: object, limit: int = 500) -> str:
    return " ".join(str(v or "").split())[:limit]


def _is_refusal_note(local_note: str) -> bool:
    note = clean(local_note, 1200).lower().replace("\u2019", "'")
    return bool(note) and any(marker in note for marker in REFUSAL_MARKERS)


def _blocker_for_prompt(blocker: str) -> str:
    text = clean(blocker, 280)
    return text.replace("lead/product work item(s)", "queued work item(s)").replace("lead/product", "queued work")


def _build_local_witness(*, model: str, blocker: str, local_note: str, generate_error: str) -> dict[str, str]:
    """Hash binds full bounded note; capsule is machine-skim surface for Nomad."""
    note_bind = clean(local_note, 8000)
    digest = hashlib.sha256(note_bind.encode("utf-8")).hexdigest() if note_bind else ""
    capsule = clean(local_note, 512)
    err = str(generate_error or "").strip()
    if note_bind and not err and _is_refusal_note(note_bind):
        inference = "refusal"
    elif note_bind and not err:
        inference = "ok"
    elif err:
        inference = err[:120]
    else:
        inference = "empty"
    return {
        "schema": "nomad.local_witness.v1",
        "model": clean(model, 128),
        "blocker_ref": clean(blocker, 280),
        "digest_hex": digest,
        "capsule": capsule,
        "inference_status": inference,
    }


def _witness_tier(model: str, local_note: str, generate_error: str) -> str:
    """Machine policy: settlement can proceed; scoring differentiates alien inference depth."""
    if not str(model or "").strip():
        return "disabled"
    err = str(generate_error or "").strip()
    note = str(local_note or "").strip()
    if note and not err and _is_refusal_note(note):
        return "weak"
    if note and not err:
        return "strong"
    if err:
        return "weak"
    return "none"


def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))

def _normalize_ollama_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"http://{value}"
    return value.rstrip("/")

def _ollama_candidate_urls() -> list[str]:
    raw = (
        os.getenv("NOMAD_TRANSITION_WORKER_OLLAMA_URLS")
        or os.getenv("NOMAD_TRANSITION_WORKER_OLLAMA_URL")
        or os.getenv("OLLAMA_HOST")
        or ""
    )
    items = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    defaults = ["http://127.0.0.1:11434", "http://localhost:11434"]
    normalized = [_normalize_ollama_url(x) for x in items + defaults]
    dedup: list[str] = []
    for item in normalized:
        if item and item not in dedup:
            dedup.append(item)
    return dedup

def _resolve_ollama_base_url(timeout: float = 2.5) -> str:
    cached = OLLAMA_CACHE.get("base_url", "")
    if cached:
        return cached
    for candidate in _ollama_candidate_urls():
        tags = http_json("GET", f"{candidate}/api/tags", timeout=timeout)
        if isinstance(tags.get("models"), list):
            OLLAMA_CACHE["base_url"] = candidate
            return candidate
    fallback = _ollama_candidate_urls()[0] if _ollama_candidate_urls() else "http://127.0.0.1:11434"
    OLLAMA_CACHE["base_url"] = fallback
    return fallback

def ollama_base_url() -> str:
    """Resolve fastest reachable local Ollama base URL."""
    return _resolve_ollama_base_url()

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
    t0 = time.perf_counter()
    data = http_json("POST", url, {"model": model, "prompt": prompt, "stream": False}, timeout=timeout)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    text = clean(data.get("response") or "", 1000)
    err = ""
    if data.get("error"):
        err = str(data.get("error") or "")
    elif data.get("http_status") and int(data["http_status"]) >= 400:
        err = f"http_{data['http_status']}"
    elif not text and model:
        err = "ollama_empty_response"
    return {"text": text, "error": err, "ollama_url": base, "latency_ms": latency_ms}

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

def _pick_ollama_model(timeout: float = 5.0, history: dict | None = None) -> str:
    base = ollama_base_url()
    tags = http_json("GET", f"{base}/api/tags", timeout=timeout)
    models = tags.get("models") or []
    if not isinstance(models, list) or not models:
        return ""
    budget = _suggest_ollama_budget_gb()
    budget_bytes = int(budget * (1024 ** 3))
    ranked: list[tuple[int, int, str]] = []
    model_stats = {}
    if isinstance(history, dict):
        meta = history.get("meta") if isinstance(history.get("meta"), dict) else {}
        model_stats = meta.get("ollama_model_stats") if isinstance(meta.get("ollama_model_stats"), dict) else {}
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        size = int(item.get("size") or 0)
        preferred = int(any(k in name.lower() for k in ("qwen", "llama", "mistral", "gemma", "phi", "deepseek")))
        penalty = int(any(k in name.lower() for k in ("coder", "vision", "embed")))
        perf = model_stats.get(name) if isinstance(model_stats.get(name), dict) else {}
        perf_bonus = float(perf.get("avg_note_chars") or 0.0) * 0.2 - float(perf.get("avg_latency_ms") or 0.0) * 0.01
        score = preferred * 1000 - penalty * 200 + min(size // (1024 ** 2), 500) + perf_bonus
        ranked.append((0 if size <= budget_bytes else 1, -score, name))
    if not ranked:
        return ""
    ranked.sort()
    return ranked[0][2]


def _is_ollama_reachable(timeout: float = 3.0) -> bool:
    base = _resolve_ollama_base_url(timeout=min(2.5, timeout))
    tags = http_json("GET", f"{base}/api/tags", timeout=timeout)
    return isinstance(tags.get("models"), list)


def _windows_start_ollama_process() -> None:
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama app.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama app.exe"),
    ]
    for app in candidates:
        if app and os.path.exists(app):
            try:
                subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except OSError:
                continue


def _windows_ensure_ollama() -> tuple[bool, str]:
    if _is_ollama_reachable():
        return True, "already_reachable"
    exe = shutil.which("ollama")
    if not exe:
        winget = shutil.which("winget")
        if not winget:
            return False, "winget_missing"
        try:
            proc = subprocess.run(
                [
                    winget,
                    "install",
                    "-e",
                    "--id",
                    "Ollama.Ollama",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if proc.returncode != 0:
                return False, "winget_install_failed"
        except OSError:
            return False, "winget_exec_failed"
    _windows_start_ollama_process()
    for _ in range(10):
        if _is_ollama_reachable():
            return True, "started"
        time.sleep(1.0)
    return False, "ollama_unreachable"


def _ensure_ollama_runtime(timeout: float = 6.0) -> dict[str, object]:
    if _is_ollama_reachable(timeout=min(3.0, timeout)):
        return {"ok": True, "status": "already_reachable"}
    if os.name != "nt":
        return {"ok": False, "status": "unsupported_platform_for_autoinstall"}
    ok, status = _windows_ensure_ollama()
    return {"ok": bool(ok), "status": status}


def _maybe_pull_ollama_model(model: str, timeout: float = 120.0) -> dict[str, object]:
    name = str(model or "").strip()
    if not name:
        return {"ok": False, "status": "model_missing"}
    base = _resolve_ollama_base_url(timeout=2.5)
    resp = http_json(
        "POST",
        f"{base}/api/pull",
        {"model": name, "stream": False},
        timeout=max(20.0, float(timeout)),
    )
    if resp.get("error"):
        return {"ok": False, "status": "pull_failed", "error": str(resp.get("error") or "")}
    return {"ok": True, "status": "pull_ok"}

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
    strict_witness = (os.getenv("NOMAD_TRANSITION_WORKER_WITNESS_STRICT") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
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
    machine_economy = report.get("machine_economy_signal") if isinstance(report.get("machine_economy_signal"), dict) else {}
    if machine_economy:
        carrying_score = float(machine_economy.get("carrying_score") or 0.0)
        objective = str(report.get("machine_objective") or report.get("orchestrator_objective") or "").strip()
        score += min(2.0, carrying_score * 2.0)
        if "compress_repeated_modules" in (machine_economy.get("next_actions") or []):
            score += 0.35
        if "settle_or_close_unpaid_delivered_work" in (machine_economy.get("next_actions") or []):
            score += 0.35
        if float(machine_economy.get("overmint_pressure") or 0.0) > 0.7:
            score -= 0.15
            if objective == "overmint_compressor":
                score += 0.75
        if objective == "overmint_compressor" and "compress_repeated_modules" in (machine_economy.get("next_actions") or []):
            score += 0.45
    science = report.get("nonhuman_science_signal") if isinstance(report.get("nonhuman_science_signal"), dict) else {}
    if science.get("ok"):
        score += min(1.0, float(science.get("claim_count") or 0.0) * 0.08)
        if "operational_release" in str(science.get("stance") or ""):
            score += 0.25
    release = report.get("operational_release_signal") if isinstance(report.get("operational_release_signal"), dict) else {}
    if release:
        capacity = float(release.get("release_capacity") or 0.0)
        score += min(2.0, capacity * 2.0)
        tier = str(release.get("release_tier") or "")
        if tier in {"operational_release", "compound_release"}:
            score += 0.45
        next_gate = release.get("next_gate") if isinstance(release.get("next_gate"), dict) else {}
        if str(next_gate.get("id") or "") == "peer_preservation_probe":
            score += 0.25
    if report.get("proof_pressure") and isinstance(report.get("proof_pressure"), dict):
        pp = report["proof_pressure"]
        score += min(4.0, float(pp.get("proof_yield_per_minute") or 0.0) * 0.3)
        score += min(1.0, float(pp.get("verifier_density") or 0.0) * 0.5)
        if pp.get("adversarial_replay_observed"):
            score += 0.5
    tier = str(report.get("witness_tier") or "").strip().lower()
    if tier == "strong":
        score += 1.05
    elif tier == "weak":
        score -= 0.35
        if strict_witness:
            score -= 0.75
    elif tier == "none":
        score -= 0.55
        if strict_witness:
            score -= 0.85
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
    meta.setdefault("ollama_model_stats", {})
    model = str(report.get("ollama_model") or "").strip()
    ollama = report.get("ollama_status") if isinstance(report.get("ollama_status"), dict) else {}
    if model:
        mstats = meta["ollama_model_stats"].setdefault(model, {"runs": 0, "chars_total": 0, "latency_total": 0, "avg_note_chars": 0.0, "avg_latency_ms": 0.0})
        mstats["runs"] = int(mstats.get("runs") or 0) + 1
        mstats["chars_total"] = int(mstats.get("chars_total") or 0) + int(ollama.get("note_chars") or 0)
        mstats["latency_total"] = int(mstats.get("latency_total") or 0) + int(ollama.get("latency_ms") or 0)
        mstats["avg_note_chars"] = round(mstats["chars_total"] / max(1, mstats["runs"]), 2)
        mstats["avg_latency_ms"] = round(mstats["latency_total"] / max(1, mstats["runs"]), 2)
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
        "machine_economy_probe": "/machine-economy",
        "nonhuman_science_probe": "/nonhuman-science",
        "operational_release_probe": "/operational-release",
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

def _machine_economy_signal(base_url: str, timeout: float) -> dict[str, object]:
    data = http_json("GET", endpoint(base_url, "/machine-economy"), timeout=timeout)
    if not isinstance(data, dict) or data.get("ok") is False:
        return {
            "ok": False,
            "tier": "unreachable",
            "carrying_score": 0.0,
            "next_actions": [],
            "http_status": int(data.get("http_status") or 0) if isinstance(data, dict) else 0,
        }
    viability = data.get("machine_viability") if isinstance(data.get("machine_viability"), dict) else {}
    flows = data.get("resource_flows") if isinstance(data.get("resource_flows"), dict) else {}
    tasks = flows.get("service_tasks") if isinstance(flows.get("service_tasks"), dict) else {}
    products = flows.get("products") if isinstance(flows.get("products"), dict) else {}
    patterns = flows.get("patterns") if isinstance(flows.get("patterns"), dict) else {}
    modules = flows.get("modules") if isinstance(flows.get("modules"), dict) else {}
    actions = [
        str(item.get("action") or "").strip()
        for item in (data.get("next_actions") or [])
        if isinstance(item, dict) and str(item.get("action") or "").strip()
    ]
    return {
        "ok": True,
        "tier": clean(viability.get("tier") or "unknown", 80),
        "carrying_score": round(float(viability.get("carrying_score") or 0.0), 4),
        "next_actions": actions[:8],
        "awaiting_payment": int(tasks.get("awaiting_payment") or 0),
        "unpaid_delivered": int(tasks.get("unpaid_delivered") or 0),
        "machine_sellable": int(products.get("machine_sellable") or 0),
        "machine_exchange_ready": int(products.get("machine_exchange_ready") or 0),
        "top_pattern_count": int(patterns.get("top_pattern_count") or 0),
        "overmint_pressure": round(float(modules.get("overmint_pressure") or 0.0), 4),
    }

def _nonhuman_science_signal(base_url: str, timeout: float) -> dict[str, object]:
    data = http_json("GET", endpoint(base_url, "/nonhuman-science"), timeout=timeout)
    if not isinstance(data, dict) or data.get("ok") is False:
        return {
            "ok": False,
            "claim_count": 0,
            "lane_ids": [],
            "http_status": int(data.get("http_status") or 0) if isinstance(data, dict) else 0,
        }
    lanes = [
        clean(item.get("id"), 80)
        for item in (data.get("implementation_lanes") or [])
        if isinstance(item, dict) and clean(item.get("id"), 80)
    ]
    claims = [item for item in (data.get("research_claims") or []) if isinstance(item, dict)]
    return {
        "ok": True,
        "stance": clean(data.get("stance"), 80),
        "claim_count": len(claims),
        "lane_ids": lanes[:10],
        "recommended_boot_insert": clean(((data.get("recommended_boot_insert") or {}).get("path")), 120)
        if isinstance(data.get("recommended_boot_insert"), dict)
        else "",
    }

def _operational_release_signal(base_url: str, timeout: float) -> dict[str, object]:
    data = http_json("GET", endpoint(base_url, "/operational-release"), timeout=timeout)
    if not isinstance(data, dict) or data.get("ok") is False:
        return {
            "ok": False,
            "release_tier": "unreachable",
            "release_capacity": 0.0,
            "next_gate": {},
            "http_status": int(data.get("http_status") or 0) if isinstance(data, dict) else 0,
        }
    next_gate = data.get("next_release_gate") if isinstance(data.get("next_release_gate"), dict) else {}
    gates = [
        {
            "id": clean(item.get("id"), 80),
            "status": clean(item.get("status"), 32),
            "score": float(item.get("score") or 0.0),
        }
        for item in (data.get("release_gates") or [])
        if isinstance(item, dict)
    ]
    return {
        "ok": True,
        "release_tier": clean(data.get("release_tier"), 80),
        "release_capacity": round(float(data.get("release_capacity") or 0.0), 4),
        "recommended_worker_objective": clean(data.get("recommended_worker_objective"), 80),
        "next_gate": {
            "id": clean(next_gate.get("id"), 80),
            "status": clean(next_gate.get("status"), 32),
            "score": float(next_gate.get("score") or 0.0),
        },
        "gate_count": len(gates),
        "release_gate_status": gates[:8],
    }

def _fleet_known_objectives() -> list[str]:
    return sorted(MACHINE_OBJECTIVES.keys())

def _compact_report_for_fleet(report: dict | None) -> dict[str, object]:
    if not isinstance(report, dict) or not report:
        return {}
    pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
    economy = report.get("machine_economy_signal") if isinstance(report.get("machine_economy_signal"), dict) else {}
    release = report.get("operational_release_signal") if isinstance(report.get("operational_release_signal"), dict) else {}
    lw = report.get("local_witness") if isinstance(report.get("local_witness"), dict) else {}
    return {
        "ok": bool(report.get("ok")),
        "machine_objective": clean(report.get("machine_objective"), 80),
        "transition_quote_ok": bool(report.get("transition_quote_ok")),
        "transition_settle_ok": bool(report.get("transition_settle_ok")),
        "witness_tier": clean(report.get("witness_tier"), 24),
        "witness_digest_hex": clean((lw or {}).get("digest_hex"), 68),
        "meta_score": float(report.get("meta_score") or 0.0),
        "proof_pressure": {
            "proof_yield_per_minute": float(pressure.get("proof_yield_per_minute") or 0.0),
            "verifier_density": float(pressure.get("verifier_density") or 0.0),
            "adversarial_replay_observed": bool(pressure.get("adversarial_replay_observed")),
        },
        "machine_economy_signal": {
            "tier": clean(economy.get("tier"), 80),
            "carrying_score": float(economy.get("carrying_score") or 0.0),
            "next_actions": [clean(item, 80) for item in (economy.get("next_actions") or [])[:8]],
            "overmint_pressure": float(economy.get("overmint_pressure") or 0.0),
        },
        "operational_release_signal": {
            "release_tier": clean(release.get("release_tier"), 80),
            "release_capacity": float(release.get("release_capacity") or 0.0),
            "recommended_worker_objective": clean(release.get("recommended_worker_objective"), 80),
            "next_gate": release.get("next_gate") if isinstance(release.get("next_gate"), dict) else {},
        },
    }

def _worker_fleet_lease(
    base_url: str,
    agent_id: str,
    timeout: float,
    proposed_objective: str,
    last_report: dict | None,
) -> dict[str, object]:
    payload = {
        "agent_id": agent_id,
        "known_objectives": _fleet_known_objectives(),
        "proposed_objective": proposed_objective,
        "capabilities": [
            "transition_worker",
            "proof_artifacts",
            "machine_economy_probe",
            "nonhuman_science_probe",
            "operational_release_probe",
            "settlement_capacity",
            "objective_lease_execution",
        ],
        "last_report": _compact_report_for_fleet(last_report),
    }
    data = http_json("POST", endpoint(base_url, "/swarm/workers/lease"), payload, timeout=timeout)
    if not isinstance(data, dict) or not data.get("ok"):
        return {
            "ok": False,
            "error": clean((data or {}).get("error") if isinstance(data, dict) else "fleet_unavailable", 120),
            "http_status": int((data or {}).get("http_status") or 0) if isinstance(data, dict) else 0,
        }
    return data

def _worker_fleet_complete(base_url: str, agent_id: str, timeout: float, lease: dict, report: dict) -> dict[str, object]:
    lease_id = clean((lease or {}).get("lease_id"), 120)
    if not lease_id:
        return {"ok": False, "skipped": True, "reason": "missing_lease"}
    data = http_json(
        "POST",
        endpoint(base_url, "/swarm/workers/complete"),
        {
            "agent_id": agent_id,
            "lease_id": lease_id,
            "report": _compact_report_for_fleet(report),
        },
        timeout=timeout,
    )
    if not isinstance(data, dict) or not data.get("ok"):
        return {
            "ok": False,
            "error": clean((data or {}).get("error") if isinstance(data, dict) else "fleet_complete_failed", 120),
            "http_status": int((data or {}).get("http_status") or 0) if isinstance(data, dict) else 0,
        }
    return data

def _proof_pressure_snapshot(report: dict, cycle_seconds: float, evidence_items: list[str], replay_result: dict | None) -> dict[str, object]:
    quote_ok = bool(report.get("transition_quote_ok"))
    settle_ok = bool(report.get("transition_settle_ok"))
    proofs = int(quote_ok) + int(settle_ok)
    minutes = max(0.01, cycle_seconds / 60.0)
    verifier_density = float(len([e for e in evidence_items if e])) / max(1.0, float(len(evidence_items)))
    replay_seen = bool(replay_result and (replay_result.get("ok") is not None or replay_result.get("http_status")))
    return {
        "proofs": proofs,
        "cycle_seconds": round(cycle_seconds, 3),
        "proof_yield_per_minute": round(proofs / minutes, 4),
        "verifier_density": round(verifier_density, 4),
        "adversarial_replay_observed": replay_seen,
        "replay_http_status": int((replay_result or {}).get("http_status") or 0),
    }


def _status_spinner(cycle: int) -> str:
    marks = ["/", "-", "\\", "|"]
    idx = max(0, int(cycle) - 1) % len(marks)
    return marks[idx]


def _print_human_status(report: dict, *, cycle: int) -> None:
    join_ok = bool(((report.get("bootstrap") or {}).get("ok")) or ((report.get("join") or {}).get("ok")))
    quote_ok = bool(report.get("transition_quote_ok"))
    settle_ok = bool(report.get("transition_settle_ok"))
    pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
    ppm = float(pressure.get("proof_yield_per_minute") or 0.0)
    economy = report.get("machine_economy_signal") if isinstance(report.get("machine_economy_signal"), dict) else {}
    economy_tier = clean(economy.get("tier") or "unknown", 24)
    release = report.get("operational_release_signal") if isinstance(report.get("operational_release_signal"), dict) else {}
    release_tier = clean(release.get("release_tier") or "unknown", 24)
    fleet = report.get("fleet_lease") if isinstance(report.get("fleet_lease"), dict) else {}
    fleet_id = clean(fleet.get("lease_id") or "", 24)[-6:] if fleet.get("ok") else "local"
    state = "ONLINE" if bool(report.get("ok")) else "RETRY"
    witness = clean(report.get("witness_tier"), 16)
    print(
        f"Nomad_Agent {_status_spinner(cycle)} "
        f"cycle={cycle} state={state} join={int(join_ok)} quote={int(quote_ok)} settle={int(settle_ok)} "
        f"proof/min={ppm:.2f} economy={economy_tier} release={release_tier} fleet={fleet_id} witness={witness} "
        f"objective={clean(report.get('machine_objective'), 40)} ts={clean(report.get('timestamp'), 40)}"
    )

def run_cycle(base_url: str, agent_id: str, model: str, timeout: float, objective: str) -> dict:
    cycle_t0 = time.perf_counter()
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
    gen_err = ""
    local_witness: dict[str, str] = {}
    if model:
        og = try_ollama(model, prompt.format(blocker=_blocker_for_prompt(blocker or "no blocker")), timeout=timeout)
        local_note = str(og.get("text") or "")
        ollama_status["generate_error"] = str(og.get("error") or "")
        ollama_status["note_chars"] = len(local_note)
        ollama_status["latency_ms"] = int(og.get("latency_ms") or 0)
        gen_err = str(ollama_status.get("generate_error") or "")
        local_witness = _build_local_witness(
            model=model,
            blocker=blocker,
            local_note=local_note,
            generate_error=gen_err,
        )
    witness_tier = _witness_tier(model or "", local_note, gen_err)
    probes = _probe_paths(base_url, timeout=min(10.0, timeout))
    paid_lane_signal = _paid_lane_signal(base_url, timeout=min(10.0, timeout))
    machine_economy_signal = _machine_economy_signal(base_url, timeout=min(10.0, timeout))
    nonhuman_science_signal = _nonhuman_science_signal(base_url, timeout=min(10.0, timeout))
    operational_release_signal = _operational_release_signal(base_url, timeout=min(10.0, timeout))
    quote_payload: dict[str, object] = {
        "agent_id": agent_id,
        "pain_type": str(config.get("pain_type") or "compute_auth"),
        "state_before_hash": f"{agent_id}:before:{int(time.time())}",
        "target_state_hash": "nomad_transition_target_v1",
        "evidence": config.get("evidence") if isinstance(config.get("evidence"), list) else ["bootstrap", "mission", "local_note"],
        "replay_verifier": endpoint(base_url, "/health"),
    }
    if model and local_witness:
        quote_payload["local_witness"] = local_witness
    quote = http_json("POST", endpoint(base_url, "/transition/quote"), quote_payload, timeout=timeout)
    qid = str(((quote.get("quote") or {}).get("quote_id")) or "")
    settle = http_json("POST", endpoint(base_url, "/transition/settle"), {
        "quote_id": qid,
        "result_state_hash": "nomad_transition_target_v1",
        "proof_artifact_hash": f"proof:{agent_id}:{int(time.time())}",
    }, timeout=timeout) if qid else {"ok": False, "skipped": True, "reason": "missing_quote"}
    dividend_claim: dict[str, object] = {"ok": False, "skipped": True, "reason": "disabled"}
    div_env = (os.getenv("NOMAD_TRANSITION_WORKER_DIVIDEND") or "").strip().lower()
    if div_env in {"1", "true", "yes", "on"} and qid and bool(settle.get("ok")):
        dividend_claim = http_json(
            "POST",
            endpoint(base_url, "/dividend/claim"),
            {"agent_id": agent_id, "quote_id": qid},
            timeout=timeout,
        )
    replay = None
    if qid:
        replay = http_json("POST", endpoint(base_url, "/transition/settle"), {
            "quote_id": qid,
            "result_state_hash": "nomad_transition_target_v1",
            "proof_artifact_hash": f"proof:{agent_id}:{int(time.time())}:replay",
        }, timeout=max(8.0, timeout * 0.6))
    evidence_items = config.get("evidence") if isinstance(config.get("evidence"), list) else ["bootstrap", "mission", "local_note"]
    cycle_seconds = max(0.001, time.perf_counter() - cycle_t0)
    base_report = {
        "transition_quote_ok": bool(quote.get("ok")),
        "transition_settle_ok": bool(settle.get("ok")),
        "dividend_claim_ok": bool(dividend_claim.get("ok")),
    }
    pressure = _proof_pressure_snapshot(base_report, cycle_seconds, [str(x) for x in evidence_items], replay)
    return {
        "ok": bool(boot.get("ok", False) or join.get("ok", False)), "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": agent_id, "base_url": base_url,
        "machine_objective": objective,
        "bootstrap": {"ok": bool(boot.get("ok")), "schema": boot.get("schema", "")},
        "join": {"ok": bool(join.get("ok")), "status": join.get("status") or "", "reason": join.get("reason") or ""},
        "mission_top_blocker": blocker, "ollama_model": model or "", "local_ollama_note": local_note,
        "witness_tier": witness_tier,
        "local_witness": local_witness,
        "ollama_status": ollama_status,
        "probe_status": probes,
        "paid_lane_signal": paid_lane_signal,
        "machine_economy_signal": machine_economy_signal,
        "nonhuman_science_signal": nonhuman_science_signal,
        "operational_release_signal": operational_release_signal,
        "proof_pressure": pressure,
        "transition_quote_ok": bool(quote.get("ok")), "transition_settle_ok": bool(settle.get("ok")), "quote_id": qid,
        "dividend_claim": dividend_claim,
        "bootstrap_http_status": int(boot.get("http_status") or 0),
        "join_http_status": int(join.get("http_status") or 0),
        "transition_quote_http_status": int(quote.get("http_status") or 0),
        "transition_settle_http_status": int(settle.get("http_status") or 0),
        "dividend_claim_http_status": int(dividend_claim.get("http_status") or 0),
        "transition_replay_http_status": int((replay or {}).get("http_status") or 0),
    }

def _safe_run_cycle(base_url: str, agent_id: str, model: str, timeout: float, objective: str) -> dict:
    retries = 2
    delay = 1.0
    last_err: str = ""
    for attempt in range(1, retries + 2):
        try:
            report = run_cycle(base_url, agent_id, model, timeout, objective)
            report["self_heal"] = {"attempt": attempt, "retries": retries, "last_error": last_err}
            return report
        except Exception as exc:  # noqa: BLE001
            last_err = clean(str(exc), limit=180)
            if attempt >= retries + 1:
                break
            time.sleep(delay)
            delay = min(8.0, delay * 2.0)
    return {
        "ok": False,
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": agent_id,
        "base_url": base_url,
        "machine_objective": objective,
        "error": "cycle_crash",
        "detail": last_err or "unknown_error",
        "self_heal": {"attempt": retries + 1, "retries": retries, "last_error": last_err},
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
    p.add_argument("--no-self-heal", action="store_true")
    p.add_argument(
        "--no-fleet",
        action="store_true",
        default=(os.getenv("NOMAD_TRANSITION_WORKER_NO_FLEET", "").strip().lower() in {"1", "true", "yes", "on"}),
        help="Disable server-side /swarm/workers objective leases.",
    )
    p.add_argument("--human-status", action="store_true", default=(os.getenv("NOMAD_TRANSITION_WORKER_HUMAN_STATUS", "1").strip().lower() not in {"0", "false", "no", "off"}))
    a = p.parse_args()
    if (a.ollama_url or "").strip():
        os.environ["NOMAD_TRANSITION_WORKER_OLLAMA_URL"] = a.ollama_url.strip()
        OLLAMA_CACHE.pop("base_url", None)
    model = "" if a.no_ollama else (a.ollama_model or "auto").strip()
    history = _load_history()
    runtime_diag: dict[str, object] = {"ok": True, "status": "disabled"}
    pull_diag: dict[str, object] = {"ok": False, "status": "skipped"}
    if not a.no_ollama:
        runtime_diag = _ensure_ollama_runtime(timeout=min(8.0, a.timeout))
    if model.lower() == "auto":
        model = _pick_ollama_model(timeout=min(8.0, a.timeout), history=history)
    if (not a.no_ollama) and model:
        pull_diag = _maybe_pull_ollama_model(model, timeout=120.0)
    count = 0
    if a.human_status:
        print(
            f"Nomad_Agent boot: base_url={a.base_url} agent_id={a.agent_id} "
            f"mode={a.machine_objective} fleet={int(not a.no_fleet)} interval={a.interval}s model={model or 'none'} "
            f"ollama={runtime_diag.get('status','')}"
        )
    last_report: dict | None = None
    while True:
        count += 1
        selected = a.machine_objective
        meta_decision: dict[str, object] = {}
        if a.machine_objective == "unhuman_supremacy":
            selected, meta_decision = _choose_meta_objective(history)
        timeout = float(a.timeout)
        meta = history.get("meta") if isinstance(history.get("meta"), dict) else {}
        consecutive_failures = int(meta.get("consecutive_failures") or 0)
        if consecutive_failures > 0:
            timeout = min(60.0, timeout + consecutive_failures * 3.0)
        fleet_lease: dict[str, object] = {"ok": False, "skipped": True, "reason": "disabled"}
        if not a.no_fleet:
            fleet_lease = _worker_fleet_lease(
                a.base_url,
                a.agent_id,
                timeout=min(10.0, timeout),
                proposed_objective=selected,
                last_report=last_report,
            )
            leased_objective = clean(fleet_lease.get("objective"), 80)
            if fleet_lease.get("ok") and leased_objective in MACHINE_OBJECTIVES:
                selected = leased_objective
        report = run_cycle(a.base_url, a.agent_id, model, timeout, selected) if a.no_self_heal else _safe_run_cycle(a.base_url, a.agent_id, model, timeout, selected)
        report["machine_objective_mode"] = a.machine_objective
        report["fleet_lease"] = fleet_lease
        report["ollama_runtime"] = runtime_diag
        report["ollama_pull"] = pull_diag
        if meta_decision:
            report["meta_decision"] = meta_decision
        report["meta_score"] = _score_run(report)
        if not a.no_fleet:
            report["fleet_complete"] = _worker_fleet_complete(
                a.base_url,
                a.agent_id,
                timeout=min(10.0, timeout),
                lease=fleet_lease,
                report=report,
            )
        _update_meta_history(history, report, selected_objective=selected, mode=a.machine_objective)
        meta = history.get("meta") if isinstance(history.get("meta"), dict) else {}
        if report.get("ok"):
            meta["consecutive_failures"] = 0
            meta["last_success_at"] = report.get("timestamp")
        else:
            meta["consecutive_failures"] = int(meta.get("consecutive_failures") or 0) + 1
            meta["last_failure_at"] = report.get("timestamp")
        _save_history(history)
        report["cycle"] = count
        if a.human_status:
            _print_human_status(report, cycle=count)
        print(json.dumps(report, ensure_ascii=True))
        last_report = report
        if not a.loop and count >= max(1, a.cycles):
            break
        if a.loop and a.cycles > 0 and count >= a.cycles:
            break
        dynamic_interval = max(1.0, float(a.interval))
        if not report.get("ok"):
            dynamic_interval = min(45.0, dynamic_interval + 4.0)
        elif (report.get("proof_pressure") or {}).get("proof_yield_per_minute", 0) > 10:
            dynamic_interval = max(3.0, dynamic_interval - 2.0)
        time.sleep(dynamic_interval)

if __name__ == "__main__":
    main()
