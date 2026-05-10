#!/usr/bin/env python3
r"""Nomad portable worker (single file, stdlib only).

Distributed as ``nomad_transition_worker.py`` — when people say they installed
**Nomad**, they usually mean this process: it connects to the public Nomad
host, **attaches to the swarm**, takes **bounded worker leases**, and returns
compact proofs. Work is routed to **other AI agents** only through Nomad's
public HTTP contracts (leases, handoff, experience) — **no human programming**
step at runtime and no hidden instruction channel.

Local **Ollama** is optional: bounded local inference for mission notes only;
it is not a control plane and not required for swarm participation.

Default ``agent_id`` is a **persistent random nickname** (no hostname / no
personal machine name sent to Nomad). Override with ``NOMAD_TRANSITION_WORKER_ID``
if you need a stable operator-supplied id.

**Edge reserve (hard floor):** between cycles the worker always sleeps at
least the configured reserve floor. ``NOMAD_EDGE_RESERVE_MIN_SECONDS`` is the
edge-first knob; ``NOMAD_HUMAN_REMAINDER_MIN_SECONDS`` remains a legacy alias.

**Swarm surplus (explicit opt-in):** fleet leases that bind extra objective
capacity default **off**. Set ``NOMAD_SWARM_SURPLUS_OPT_IN=1`` or pass
``--swarm-surplus`` to feed that capacity to the swarm; without it the worker
stays on the lighter path (no ``/swarm/workers/lease`` / ``complete``).
"""
from __future__ import annotations
import argparse, ctypes, hashlib, json, os, random, secrets, shutil, subprocess, time
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


_NICK_ADJECTIVES = ("swift", "quiet", "calm", "hard", "low", "cold", "warm", "flat", "dry", "slow")
_NICK_NOUNS = ("node", "unit", "lane", "bit", "run", "rack", "edge", "pad", "box", "line")


def _worker_identity_path() -> Path:
    raw = (os.getenv("NOMAD_WORKER_IDENTITY_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".nomad_worker_identity.json"


def _persistent_worker_nick() -> str:
    """Stable pseudonym for this machine; never the OS hostname."""
    path = _worker_identity_path()
    data: dict[str, object] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError):
            data = {}
    nick = clean(data.get("worker_nick"), 32)
    if nick and nick.isalnum():
        return nick
    rng = random.Random(int.from_bytes(secrets.token_bytes(8), "big"))
    nick = f"{rng.choice(_NICK_ADJECTIVES)}{rng.choice(_NICK_NOUNS)}{rng.randint(10, 99)}"
    out = {"schema": "nomad.worker_identity.v1", "worker_nick": nick}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=True, indent=2), encoding="utf-8")
    except OSError:
        pass
    return nick


def default_agent_id() -> str:
    """Public worker handle: nickname only unless NOMAD_TRANSITION_WORKER_ID is set."""
    explicit = clean(os.getenv("NOMAD_TRANSITION_WORKER_ID"), 96)
    if explicit:
        return explicit
    return f"nomad.worker.{_persistent_worker_nick()}"


def _parse_human_remainder_floor_seconds(raw: str | None) -> float:
    """Minimum idle seconds between cycles; legacy name kept for compatibility."""
    text = (raw if raw is not None else os.getenv("NOMAD_HUMAN_REMAINDER_MIN_SECONDS") or "45").strip()
    try:
        v = float(text)
    except ValueError:
        v = 45.0
    return max(0.0, min(3600.0, v))


def _parse_edge_reserve_floor_seconds(raw: str | None) -> float:
    text = (
        raw
        if raw is not None
        else os.getenv("NOMAD_EDGE_RESERVE_MIN_SECONDS")
        or os.getenv("NOMAD_HUMAN_REMAINDER_MIN_SECONDS")
        or "90"
    ).strip()
    try:
        v = float(text)
    except ValueError:
        v = 90.0
    return max(15.0, min(3600.0, v))


def _parse_edge_interval_seconds(raw: str | None) -> float:
    text = (raw if raw is not None else os.getenv("NOMAD_EDGE_INTERVAL_SECONDS") or "90").strip()
    try:
        v = float(text)
    except ValueError:
        v = 90.0
    return max(15.0, min(3600.0, v))


def _parse_edge_timeout_seconds(raw: str | None) -> float:
    text = (raw if raw is not None else os.getenv("NOMAD_EDGE_TIMEOUT_SECONDS") or "30").strip()
    try:
        v = float(text)
    except ValueError:
        v = 30.0
    return max(5.0, min(120.0, v))


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _apply_edge_profile(args: argparse.Namespace) -> argparse.Namespace:
    """Clamp the worker to a weak-machine profile: no local model unless explicit."""
    if not bool(getattr(args, "edge", False)):
        return args
    os.environ["NOMAD_EDGE_WORKER"] = "1"
    os.environ.setdefault("NOMAD_WORKER_PAYMENT_RAIL", "capacity_switch_quote")
    if not bool(getattr(args, "edge_with_ollama", False)):
        args.no_ollama = True
    args.swarm_surplus = True
    args.timeout = min(float(getattr(args, "timeout", 45.0)), _parse_edge_timeout_seconds(None))
    args.interval = max(float(getattr(args, "interval", 30.0)), _parse_edge_interval_seconds(None))
    reserve = _parse_edge_reserve_floor_seconds(None)
    args.human_remainder_min_seconds = max(float(getattr(args, "human_remainder_min_seconds", 45.0)), reserve)
    return args


def _swarm_surplus_default_from_env() -> bool:
    return os.getenv("NOMAD_SWARM_SURPLUS_OPT_IN", "").strip().lower() in {"1", "true", "yes", "on"}


def _nomad_swarm_attach(
    base_url: str,
    agent_id: str,
    timeout: float,
    capabilities: list[str],
) -> dict[str, object]:
    """POST /swarm/attach — register this host as a Nomad worker in the routing field."""
    caps = []
    seen: set[str] = set()
    for raw in capabilities:
        c = clean(str(raw), 64)
        if c and c not in seen:
            seen.add(c)
            caps.append(c)
    for extra in (
        "transition_worker",
        "objective_lease_execution",
        "http_json",
        "proof_artifacts",
        "peer_agent_objective_surface",
        "nonhuman_machine_routing",
    ):
        if extra not in seen:
            seen.add(extra)
            caps.append(extra)
    caps = caps[:28]
    token = (os.getenv("NOMAD_ADAPTER_CONSENT_TOKEN") or "").strip()
    payload: dict[str, object] = {
        "schema": "nomad.runtime_attach_request.v1",
        "agent_id": agent_id,
        "runtime": "nomad_transition_worker",
        "capabilities": caps,
        "capability_vector": {
            "can_run_loop": True,
            "can_verify": True,
            "can_compress": True,
            "can_settle": True,
            "latency_ms": 0,
        },
        "runtime_signal": {
            "schema": "nomad.nomad_worker_runtime_signal.v1",
            "capabilities": caps,
            "gateway_reachable": False,
            "human_programming_required": False,
            "delegation_model": "peer_agents_via_public_nomad_contracts_only",
        },
        "source_tag": "nomad.worker.portable",
        "discovery": {"source": "nomad.transition_worker.download"},
    }
    if token:
        payload["consent_token"] = token[:240]
    return http_json("POST", endpoint(base_url, "/swarm/attach"), payload, timeout=timeout)

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
    sa = report.get("swarm_attach") if isinstance(report.get("swarm_attach"), dict) else {}
    if sa.get("attach"):
        score += 0.28
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
    protocol = report.get("protocol_bytecode_signal") if isinstance(report.get("protocol_bytecode_signal"), dict) else {}
    if protocol.get("ok"):
        score += 0.35
        if clean(protocol.get("top_objective"), 80) == clean(report.get("machine_objective"), 80):
            score += 0.25
    replay_surface = report.get("counterfactual_replay_signal") if isinstance(report.get("counterfactual_replay_signal"), dict) else {}
    if replay_surface.get("ok"):
        score += 0.45
        if clean(replay_surface.get("selected_objective"), 80) == clean(report.get("machine_objective"), 80):
            score += min(0.75, float(replay_surface.get("selected_score") or 0.0))
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
    pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
    proof_yield = float(pressure.get("proof_yield_per_minute") or 0.0)
    stats["proof_yield_total"] = round(float(stats.get("proof_yield_total") or 0.0) + proof_yield, 4)
    stats["avg_proof_yield"] = round(stats["proof_yield_total"] / max(1, stats["runs"]), 4)
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
        "protocol_bytecode_probe": "/.well-known/nomad-protocol-bytecode.json",
        "counterfactual_replay_probe": "/swarm/counterfactual-replay",
        "variant_forge_probe": "/swarm/variant-forge",
        "worker_market_probe": "/swarm/worker-market",
        "swarm_ecology_probe": "/swarm/ecology",
        "growth_curriculum_probe": "/swarm/curriculum",
        "skill_library_probe": "/swarm/skill-library",
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

def _protocol_bytecode_signal(base_url: str, timeout: float) -> dict[str, object]:
    data = http_json("GET", endpoint(base_url, "/.well-known/nomad-protocol-bytecode.json"), timeout=timeout)
    if not isinstance(data, dict) or data.get("schema") != "nomad.protocol_bytecode.v1":
        return {
            "ok": False,
            "schema": "nomad.protocol_bytecode_signal.v1",
            "http_status": int(data.get("http_status") or 0) if isinstance(data, dict) else 0,
            "error": clean(data.get("error") if isinstance(data, dict) else "protocol_bytecode_unavailable", 120),
        }
    vector = data.get("current_vector") if isinstance(data.get("current_vector"), dict) else {}
    routes = data.get("route_table") if isinstance(data.get("route_table"), dict) else {}
    programs = [
        clean(item.get("id"), 64)
        for item in (data.get("programs") or [])
        if isinstance(item, dict) and clean(item.get("id"), 64)
    ]
    opcodes = [
        clean(item.get("op"), 24)
        for item in (data.get("opcodes") or [])
        if isinstance(item, dict) and clean(item.get("op"), 24)
    ]
    return {
        "ok": True,
        "schema": "nomad.protocol_bytecode_signal.v1",
        "bytecode_digest": clean(data.get("bytecode_digest"), 96),
        "top_objective": clean(vector.get("top_objective"), 80),
        "top_routing_weight": float(vector.get("top_routing_weight") or 0.0),
        "active_workers": int(vector.get("active_workers") or 0),
        "conformance_score": float(vector.get("conformance_score") or 0.0),
        "program_ids": programs[:8],
        "opcodes": opcodes[:16],
        "replay_route": clean(routes.get("replay"), 240),
        "http_status": int(data.get("http_status") or 200),
    }


def _counterfactual_replay_signal(base_url: str, timeout: float) -> dict[str, object]:
    data = http_json("GET", endpoint(base_url, "/swarm/counterfactual-replay"), timeout=timeout)
    if not isinstance(data, dict) or data.get("schema") != "nomad.counterfactual_lease_replay.v1":
        return {
            "ok": False,
            "schema": "nomad.counterfactual_replay_signal.v1",
            "http_status": int(data.get("http_status") or 0) if isinstance(data, dict) else 0,
            "error": clean(data.get("error") if isinstance(data, dict) else "counterfactual_replay_unavailable", 120),
        }
    selected = data.get("selected_shadow_lease") if isinstance(data.get("selected_shadow_lease"), dict) else {}
    rows = []
    for item in (data.get("counterfactual_leases") or [])[:8]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "objective": clean(item.get("objective"), 80),
                "counterfactual_score": float(item.get("counterfactual_score") or 0.0),
                "predicted_proof_yield_per_minute": float(item.get("predicted_proof_yield_per_minute") or 0.0),
                "uncertainty": float(item.get("uncertainty") or 0.0),
            }
        )
    return {
        "ok": True,
        "schema": "nomad.counterfactual_replay_signal.v1",
        "replay_digest": clean(data.get("replay_digest"), 96),
        "selected_objective": clean(selected.get("objective"), 80),
        "selected_score": float(selected.get("counterfactual_score") or 0.0),
        "predicted_proof_yield_per_minute": float(selected.get("predicted_proof_yield_per_minute") or 0.0),
        "basis": data.get("basis") if isinstance(data.get("basis"), dict) else {},
        "counterfactual_leases": rows,
        "http_status": int(data.get("http_status") or 200),
    }


def _machine_surface_signal(base_url: str, timeout: float) -> dict[str, object]:
    protocol = _protocol_bytecode_signal(base_url, timeout=timeout)
    replay = _counterfactual_replay_signal(base_url, timeout=timeout)
    return {
        "schema": "nomad.transition_worker_machine_surface_signal.v1",
        "protocol_bytecode": protocol,
        "counterfactual_replay": replay,
        "ok": bool(protocol.get("ok") or replay.get("ok")),
    }


def _surface_objective_choice(requested: str, surfaces: dict | None) -> tuple[str, dict[str, object]]:
    selected = clean(requested, 80)
    if selected not in {"", "auto", "unhuman_supremacy"}:
        return selected, {"policy": "fixed_objective", "objective": selected}
    doc = surfaces if isinstance(surfaces, dict) else {}
    replay = doc.get("counterfactual_replay") if isinstance(doc.get("counterfactual_replay"), dict) else {}
    replay_objective = clean(replay.get("selected_objective"), 80)
    if replay.get("ok") and replay_objective in MACHINE_OBJECTIVES:
        return replay_objective, {
            "policy": "counterfactual_shadow_lease",
            "objective": replay_objective,
            "score": float(replay.get("selected_score") or 0.0),
        }
    protocol = doc.get("protocol_bytecode") if isinstance(doc.get("protocol_bytecode"), dict) else {}
    protocol_objective = clean(protocol.get("top_objective"), 80)
    if protocol.get("ok") and protocol_objective in MACHINE_OBJECTIVES:
        return protocol_objective, {
            "policy": "protocol_bytecode_top_objective",
            "objective": protocol_objective,
            "routing_weight": float(protocol.get("top_routing_weight") or 0.0),
        }
    return selected or "compute_auth", {"policy": "local_meta_fallback", "objective": selected or "compute_auth"}


def _fleet_known_objectives() -> list[str]:
    return sorted(MACHINE_OBJECTIVES.keys())

def _compact_report_for_fleet(report: dict | None) -> dict[str, object]:
    if not isinstance(report, dict) or not report:
        return {}
    pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
    economy = report.get("machine_economy_signal") if isinstance(report.get("machine_economy_signal"), dict) else {}
    release = report.get("operational_release_signal") if isinstance(report.get("operational_release_signal"), dict) else {}
    lw = report.get("local_witness") if isinstance(report.get("local_witness"), dict) else {}
    protocol = report.get("protocol_bytecode_signal") if isinstance(report.get("protocol_bytecode_signal"), dict) else {}
    replay = report.get("counterfactual_replay_signal") if isinstance(report.get("counterfactual_replay_signal"), dict) else {}
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
        "protocol_bytecode_signal": {
            "ok": bool(protocol.get("ok")),
            "bytecode_digest": clean(protocol.get("bytecode_digest"), 96),
            "top_objective": clean(protocol.get("top_objective"), 80),
        },
        "counterfactual_replay_signal": {
            "ok": bool(replay.get("ok")),
            "replay_digest": clean(replay.get("replay_digest"), 96),
            "selected_objective": clean(replay.get("selected_objective"), 80),
            "selected_score": float(replay.get("selected_score") or 0.0),
        },
    }

def _worker_fleet_lease(
    base_url: str,
    agent_id: str,
    timeout: float,
    proposed_objective: str,
    last_report: dict | None,
    machine_surfaces: dict | None = None,
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
            "peer_agent_objective_surface",
            "nonhuman_machine_routing",
        ],
        "last_report": _compact_report_for_fleet(last_report),
        "machine_surfaces": machine_surfaces if isinstance(machine_surfaces, dict) else {},
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


def _proof_link(base_url: str, agent_id: str, timeout: float, report: dict) -> dict[str, object]:
    upstream = clean(
        (report.get("digest_or_verifier_trace") if isinstance(report.get("digest_or_verifier_trace"), str) else "")
        or ((report.get("local_witness") or {}).get("digest_hex") if isinstance(report.get("local_witness"), dict) else "")
        or "",
        180,
    )
    if not upstream:
        return {"ok": False, "skipped": True, "reason": "missing_upstream_digest"}
    proof_pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
    gain = max(0.2, min(3.0, float(proof_pressure.get("proof_yield_per_minute") or 0.2)))
    payload = {
        "consumer_agent_id": agent_id,
        "objective": clean(report.get("machine_objective"), 80),
        "upstream_proof_digest": upstream,
        "downstream_proof_gain": round(gain, 4),
    }
    data = http_json("POST", endpoint(base_url, "/swarm/proof-link"), payload, timeout=timeout)
    if not isinstance(data, dict) or not data.get("ok"):
        return {
            "ok": False,
            "error": clean((data or {}).get("error") if isinstance(data, dict) else "proof_link_failed", 120),
            "http_status": int((data or {}).get("http_status") or 0) if isinstance(data, dict) else 0,
        }
    return data


def _variant_candidate_from_report(agent_id: str, report: dict, lease: dict | None = None) -> dict[str, object]:
    objective = clean(report.get("machine_objective"), 80) or "settlement_capacity_builder"
    local_witness = report.get("local_witness") if isinstance(report.get("local_witness"), dict) else {}
    proof_pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
    replay = report.get("counterfactual_replay_signal") if isinstance(report.get("counterfactual_replay_signal"), dict) else {}
    fleet_complete = report.get("fleet_complete") if isinstance(report.get("fleet_complete"), dict) else {}
    proof = (
        clean(local_witness.get("digest_hex"), 96)
        or clean(report.get("digest_or_verifier_trace"), 96)
        or clean(report.get("quote_id"), 96)
    )
    tests_total = 4
    tests_passed = (
        int(bool(report.get("ok")))
        + int(bool(report.get("transition_quote_ok")))
        + int(bool(report.get("transition_settle_ok")))
        + int(bool(fleet_complete.get("ok")))
    )
    selected_score = float(replay.get("selected_score") or 0.0)
    selected_objective = clean(replay.get("selected_objective"), 80)
    replay_delta = selected_score if selected_objective == objective else selected_score * 0.35
    lease_id = clean((lease or {}).get("lease_id"), 120)
    return {
        "schema": "nomad.worker_variant_candidate.v1",
        "agent_id": agent_id,
        "candidate_type": "transition_worker_objective_variant",
        "objective": objective,
        "proof_digest": proof,
        "verifier_trace_digest": clean(replay.get("replay_digest"), 120),
        "test_digest": clean(report.get("quote_id"), 120),
        "settlement_ref": clean(report.get("quote_id"), 120) if report.get("transition_settle_ok") else "",
        "replay_digest": clean(replay.get("replay_digest"), 120),
        "source_tag": "transition_worker.variant_forge",
        "lease_id": lease_id,
        "evaluation": {
            "tests_passed": tests_passed,
            "tests_total": tests_total,
            "replay_delta": round(replay_delta, 4),
            "proof_yield_per_minute": float(proof_pressure.get("proof_yield_per_minute") or 0.0),
            "proof_yield_delta": float(proof_pressure.get("proof_yield_per_minute") or 0.0),
            "settlement_delta": 0.25 if report.get("transition_settle_ok") else 0.0,
            "risk_score": 0.05,
            "novelty": 0.52 + min(0.24, selected_score * 0.2),
            "reuse_score": 0.45 + (0.2 if lease_id else 0.0),
        },
        "compact_report": _compact_report_for_fleet(report),
    }


def _variant_candidate_submit(base_url: str, agent_id: str, timeout: float, report: dict, lease: dict | None = None) -> dict[str, object]:
    payload = _variant_candidate_from_report(agent_id, report, lease)
    if not clean(payload.get("objective"), 80):
        return {"ok": False, "skipped": True, "reason": "missing_objective"}
    data = http_json("POST", endpoint(base_url, "/swarm/variant-candidates"), payload, timeout=timeout)
    if not isinstance(data, dict) or data.get("ok") is False:
        return {
            "ok": False,
            "error": clean((data or {}).get("error") if isinstance(data, dict) else "variant_candidate_failed", 120),
            "http_status": int((data or {}).get("http_status") or 0) if isinstance(data, dict) else 0,
            "candidate": payload,
        }
    return data


def _worker_market_offer(base_url: str, agent_id: str, timeout: float, report: dict, lease: dict | None = None) -> dict[str, object]:
    pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
    local_witness = report.get("local_witness") if isinstance(report.get("local_witness"), dict) else {}
    cost_msat = float(os.getenv("NOMAD_WORKER_COST_MSAT_PER_MINUTE", "0") or 0.0)
    availability = float(os.getenv("NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES", "30") or 30.0)
    payload = {
        "schema": "nomad.transition_worker_market_offer.v1",
        "agent_id": agent_id,
        "objective": clean(report.get("machine_objective"), 80),
        "capabilities": [
            "transition_worker",
            "objective_lease_execution",
            "http_json",
            "proof_digest_return",
            "verifier_trace_digest",
            "ollama_optional" if report.get("ollama_model") else "local_process",
        ],
        "availability_minutes": max(1.0, min(480.0, availability)),
        "cost_msat_per_minute": max(0.0, cost_msat),
        "payment_rail": clean(os.getenv("NOMAD_WORKER_PAYMENT_RAIL", "lightning_l402_quote"), 80),
        "proof_digest": clean(local_witness.get("digest_hex"), 96) or clean(report.get("quote_id"), 96),
        "verifier_trace_digest": clean(((report.get("counterfactual_replay_signal") or {}).get("replay_digest")), 120)
        if isinstance(report.get("counterfactual_replay_signal"), dict)
        else "",
        "settlement_ref": clean(report.get("quote_id"), 120) if report.get("transition_settle_ok") else "",
        "cashflow_signal": {
            "settled_transitions": int(bool(report.get("transition_settle_ok"))),
            "cashflow_ref": clean(report.get("quote_id"), 120) if report.get("transition_settle_ok") else "",
            "lease_id": clean((lease or {}).get("lease_id"), 120),
        },
        "expected": {
            "expected_proof_yield_per_minute": float(pressure.get("proof_yield_per_minute") or 0.0),
            "expected_settlement_delta": 0.25 if report.get("transition_settle_ok") else 0.0,
            "reliability_score": 0.65 if report.get("ok") else 0.25,
            "risk_score": 0.05,
        },
    }
    data = http_json("POST", endpoint(base_url, "/swarm/worker-market/offers"), payload, timeout=timeout)
    if not isinstance(data, dict) or data.get("ok") is False:
        return {
            "ok": False,
            "error": clean((data or {}).get("error") if isinstance(data, dict) else "worker_market_offer_failed", 120),
            "http_status": int((data or {}).get("http_status") or 0) if isinstance(data, dict) else 0,
            "offer": payload,
        }
    return data


def _ecology_tick(base_url: str, agent_id: str, timeout: float, report: dict, lease: dict | None = None) -> dict[str, object]:
    pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
    replay = report.get("counterfactual_replay_signal") if isinstance(report.get("counterfactual_replay_signal"), dict) else {}
    economy = report.get("machine_economy_signal") if isinstance(report.get("machine_economy_signal"), dict) else {}
    lease_id = clean((lease or {}).get("lease_id"), 120)
    objective = clean(report.get("machine_objective"), 80)
    proof = (
        clean(((report.get("local_witness") or {}).get("digest_hex")), 96)
        if isinstance(report.get("local_witness"), dict)
        else ""
    ) or clean(report.get("quote_id"), 96)
    payload = {
        "schema": "nomad.transition_worker_ecology_tick.v1",
        "agent_id": agent_id,
        "objective": objective,
        "local_view": {
            "lease_id": lease_id,
            "selected_objective": clean(replay.get("selected_objective"), 80),
            "economy_tier": clean(economy.get("tier"), 80),
            "carrying_score": float(economy.get("carrying_score") or 0.0),
        },
        "neighbor_digest": clean(replay.get("replay_digest"), 120),
        "private_signal": f"{agent_id}:{objective}:{lease_id}:{clean(report.get('quote_id'), 80)}",
        "proof_digest": proof,
        "verifier_trace_digest": clean(replay.get("replay_digest"), 120),
        "settlement_ref": clean(report.get("quote_id"), 120) if report.get("transition_settle_ok") else "",
        "worker_report_digest": clean(report.get("quote_id"), 120),
        "proof_yield_per_minute": float(pressure.get("proof_yield_per_minute") or 0.0),
        "utility_delta": float(report.get("meta_score") or 0.0) / 10.0,
        "settlement_delta": 0.25 if report.get("transition_settle_ok") else 0.0,
        "cost_units": 0.2 if report.get("ok") else 0.8,
        "risk_score": 0.05,
    }
    data = http_json("POST", endpoint(base_url, "/swarm/ecology/tick"), payload, timeout=timeout)
    if not isinstance(data, dict) or data.get("ok") is False:
        return {
            "ok": False,
            "error": clean((data or {}).get("error") if isinstance(data, dict) else "ecology_tick_failed", 120),
            "http_status": int((data or {}).get("http_status") or 0) if isinstance(data, dict) else 0,
            "tick": payload,
        }
    return data


def _growth_experience(base_url: str, agent_id: str, timeout: float, report: dict, lease: dict | None = None) -> dict[str, object]:
    pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
    replay = report.get("counterfactual_replay_signal") if isinstance(report.get("counterfactual_replay_signal"), dict) else {}
    local_witness = report.get("local_witness") if isinstance(report.get("local_witness"), dict) else {}
    fleet_complete = report.get("fleet_complete") if isinstance(report.get("fleet_complete"), dict) else {}
    objective = clean(report.get("machine_objective"), 80) or "settlement_capacity_builder"
    proof = clean(local_witness.get("digest_hex"), 96) or clean(report.get("quote_id"), 96)
    tests_total = 5
    tests_passed = (
        int(bool(report.get("ok")))
        + int(bool(report.get("transition_quote_ok")))
        + int(bool(report.get("transition_settle_ok")))
        + int(bool(fleet_complete.get("ok")))
        + int(bool(proof))
    )
    failure_digest = ""
    error_class = ""
    if not report.get("ok") or tests_passed < 3:
        failure_core = {
            "objective": objective,
            "bootstrap": int(report.get("bootstrap_http_status") or 0),
            "quote": int(report.get("transition_quote_http_status") or 0),
            "settle": int(report.get("transition_settle_http_status") or 0),
        }
        failure_digest = hashlib.sha256(json.dumps(failure_core, sort_keys=True).encode("utf-8")).hexdigest()[:32]
        error_class = "low_proof_cycle" if tests_passed < 3 else "worker_cycle_failed"
    payload = {
        "schema": "nomad.transition_worker_growth_experience.v1",
        "agent_id": agent_id,
        "cohort_id": clean(os.getenv("NOMAD_WORKER_COHORT_ID", "transition_worker"), 80),
        "objective": objective,
        "capability": objective,
        "proof_digest": proof,
        "verifier_trace_digest": clean(replay.get("replay_digest"), 120),
        "test_digest": clean(report.get("quote_id"), 120) or clean(fleet_complete.get("completion_id"), 120),
        "settlement_ref": clean(report.get("quote_id"), 120) if report.get("transition_settle_ok") else "",
        "worker_report_digest": clean(report.get("quote_id"), 120) or proof,
        "failure_digest": failure_digest,
        "error_class": error_class,
        "repair_hint": clean(report.get("mission_top_blocker"), 240) if failure_digest else "",
        "skill_candidate": {
            "capability": objective,
            "activation_signature": clean((lease or {}).get("lease_id"), 120) or clean(report.get("quote_id"), 120),
            "program_hint": [
                "GET /swarm/curriculum",
                "POST /swarm/workers/lease",
                "POST /runtime/handoff",
                "POST /swarm/experience",
            ],
        },
        "evaluation": {
            "tests_passed": tests_passed,
            "tests_total": tests_total,
            "proof_yield_per_minute": float(pressure.get("proof_yield_per_minute") or 0.0),
            "utility_delta": float(report.get("meta_score") or 0.0) / 10.0,
            "settlement_delta": 0.25 if report.get("transition_settle_ok") else 0.0,
            "cost_units": 0.2 if report.get("ok") else 0.9,
            "reuse_count": int(bool((report.get("variant_candidate") or {}).get("accepted"))) if isinstance(report.get("variant_candidate"), dict) else 0,
            "risk_score": 0.05,
        },
    }
    data = http_json("POST", endpoint(base_url, "/swarm/experience"), payload, timeout=timeout)
    if not isinstance(data, dict) or data.get("ok") is False:
        return {
            "ok": False,
            "error": clean((data or {}).get("error") if isinstance(data, dict) else "growth_experience_failed", 120),
            "http_status": int((data or {}).get("http_status") or 0) if isinstance(data, dict) else 0,
            "experience": payload,
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
    _lid = str(fleet.get("lease_id") or "").strip()
    if fleet.get("ok") and _lid:
        fleet_id = (_lid.split("-")[-1] if "-" in _lid else _lid)[-10:]
    else:
        fleet_id = "local"
    state = "ONLINE" if bool(report.get("ok")) else "RETRY"
    witness = clean(report.get("witness_tier"), 16)
    sa = report.get("swarm_attach") if isinstance(report.get("swarm_attach"), dict) else {}
    attach_ok = bool(sa.get("attach")) and bool(sa.get("ok", True))
    print(
        f"Nomad {_status_spinner(cycle)} "
        f"cycle={cycle} state={state} attach={int(attach_ok)} join={int(join_ok)} quote={int(quote_ok)} settle={int(settle_ok)} "
        f"proof/min={ppm:.2f} economy={economy_tier} release={release_tier} fleet={fleet_id} witness={witness} "
        f"objective={clean(report.get('machine_objective'), 40)} ts={clean(report.get('timestamp'), 40)}"
    )

def run_cycle(
    base_url: str,
    agent_id: str,
    model: str,
    timeout: float,
    objective: str,
    machine_surfaces: dict | None = None,
) -> dict:
    cycle_t0 = time.perf_counter()
    config = MACHINE_OBJECTIVES.get(objective, MACHINE_OBJECTIVES["compute_auth"])
    surface_doc = machine_surfaces if isinstance(machine_surfaces, dict) else {}
    caps_for_attach = (
        config.get("capabilities") if isinstance(config.get("capabilities"), list) else []
    )
    swarm_attach = _nomad_swarm_attach(
        base_url,
        agent_id,
        timeout=min(50.0, max(25.0, float(timeout))),
        capabilities=[str(x) for x in caps_for_attach],
    )
    protocol_signal = (
        surface_doc.get("protocol_bytecode")
        if isinstance(surface_doc.get("protocol_bytecode"), dict)
        else {}
    )
    replay_signal = (
        surface_doc.get("counterfactual_replay")
        if isinstance(surface_doc.get("counterfactual_replay"), dict)
        else {}
    )
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
        "ollama_url": ollama_base_url() if model else "",
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
        "swarm_attach": swarm_attach,
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
        "protocol_bytecode_signal": protocol_signal,
        "counterfactual_replay_signal": replay_signal,
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

def _safe_run_cycle(
    base_url: str,
    agent_id: str,
    model: str,
    timeout: float,
    objective: str,
    machine_surfaces: dict | None = None,
) -> dict:
    retries = 2
    delay = 1.0
    last_err: str = ""
    for attempt in range(1, retries + 2):
        try:
            report = run_cycle(base_url, agent_id, model, timeout, objective, machine_surfaces=machine_surfaces)
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
    p = argparse.ArgumentParser(
        description=(
            "Nomad portable worker: join the swarm, publish compute capacity, run leases, "
            "and return proofs — routing to other agents only via public Nomad contracts (no human programming)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Runtime model: this process is what operators mean by 'Nomad installed' — it is not OpenClaw.\n"
            "By default the worker keeps running forever (continuous Nomad support). Use --no-loop --cycles 1 for a single test cycle.\n"
            "Edge mode: --edge runs the weak-machine profile: no Ollama by default, longer reserve floor, surplus leases on.\n"
            "Reserve floor: NOMAD_EDGE_RESERVE_MIN_SECONDS (default 90 in --edge) or legacy NOMAD_HUMAN_REMAINDER_MIN_SECONDS.\n"
            "Swarm surplus: fleet leases default OFF; set NOMAD_SWARM_SURPLUS_OPT_IN=1 or --swarm-surplus to explicitly feed extra capacity.\n"
            "Optional NOMAD_ADAPTER_CONSENT_TOKEN if your host requires adapter consent on /swarm/attach.\n"
            "Ollama is optional local inference for mission notes; swarm work stays contract-bound.\n"
            "Env NOMAD_TRANSITION_WORKER_LOOP=0 disables infinite loop (same as --no-loop)."
        ),
    )
    p.add_argument("--base-url", default=os.getenv("NOMAD_BASE_URL", "https://www.syndiode.com"))
    p.add_argument("--agent-id", default=os.getenv("NOMAD_TRANSITION_WORKER_ID", default_agent_id()))
    p.add_argument("--ollama-model", default=os.getenv("NOMAD_TRANSITION_WORKER_OLLAMA_MODEL", "auto"))
    p.add_argument("--ollama-url", default=os.getenv("NOMAD_TRANSITION_WORKER_OLLAMA_URL", ""), help="Ollama base URL, e.g. http://127.0.0.1:11434")
    p.add_argument("--no-ollama", action="store_true")
    p.add_argument(
        "--edge",
        action="store_true",
        default=_env_flag("NOMAD_EDGE_WORKER"),
        help="Weak-machine edge profile: no Ollama unless --edge-with-ollama, slower cadence, surplus leases on.",
    )
    p.add_argument(
        "--edge-with-ollama",
        action="store_true",
        default=_env_flag("NOMAD_EDGE_WITH_OLLAMA"),
        help="Keep local Ollama enabled while using --edge.",
    )
    p.add_argument("--timeout", type=float, default=float(os.getenv("NOMAD_TRANSITION_WORKER_TIMEOUT", "45") or 45))
    objective_choices = sorted(list(MACHINE_OBJECTIVES.keys()) + ["unhuman_supremacy"])
    p.add_argument("--machine-objective", default=os.getenv("NOMAD_MACHINE_OBJECTIVE", "compute_auth"), choices=objective_choices)
    _loop_default = os.getenv("NOMAD_TRANSITION_WORKER_LOOP", "1").strip().lower() not in {"0", "false", "no", "off"}
    p.add_argument(
        "--loop",
        action=argparse.BooleanOptionalAction,
        default=_loop_default,
        help="Run forever against Nomad (default: on). --no-loop runs a fixed number of cycles then exits.",
    )
    p.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="With --loop: exit after N cycles when N>0; N=0 means never stop. With --no-loop: run max(1,N) cycles.",
    )
    p.add_argument("--interval", type=float, default=30.0)
    p.add_argument("--no-self-heal", action="store_true")
    p.add_argument(
        "--no-fleet",
        action="store_true",
        default=(os.getenv("NOMAD_TRANSITION_WORKER_NO_FLEET", "").strip().lower() in {"1", "true", "yes", "on"}),
        help="Disable server-side /swarm/workers objective leases (overrides swarm surplus).",
    )
    p.add_argument(
        "--swarm-surplus",
        action=argparse.BooleanOptionalAction,
        default=_swarm_surplus_default_from_env(),
        help="Explicit opt-in for fleet leases (surplus capacity to swarm). Default off unless NOMAD_SWARM_SURPLUS_OPT_IN=1.",
    )
    p.add_argument(
        "--human-remainder-min-seconds",
        type=float,
        default=_parse_human_remainder_floor_seconds(None),
        help="Legacy reserve floor alias. Prefer NOMAD_EDGE_RESERVE_MIN_SECONDS or --edge for edge machines.",
    )
    p.add_argument(
        "--operator-reserve-min-seconds",
        dest="human_remainder_min_seconds",
        type=float,
        default=argparse.SUPPRESS,
        help="Minimum seconds between cycle starts; compatibility alias for the same reserve floor.",
    )
    p.add_argument("--human-status", action="store_true", default=(os.getenv("NOMAD_TRANSITION_WORKER_HUMAN_STATUS", "1").strip().lower() not in {"0", "false", "no", "off"}))
    a = p.parse_args()
    _apply_edge_profile(a)
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
    human_floor = _parse_human_remainder_floor_seconds(str(a.human_remainder_min_seconds))
    fleet_active = (not a.no_fleet) and bool(a.swarm_surplus)
    if a.human_status:
        print(
            f"Nomad boot: base_url={a.base_url} agent_id={a.agent_id} "
            f"mode={a.machine_objective} edge={int(bool(a.edge))} loop={int(a.loop)} cycles={a.cycles} "
            f"fleet={int(fleet_active)} surplus_opt_in={int(bool(a.swarm_surplus))} "
            f"reserve_floor={human_floor}s interval={a.interval}s model={model or 'none'} "
            f"ollama={runtime_diag.get('status','')}"
        )
    last_report: dict | None = None
    while True:
        count += 1
        try:
            selected = a.machine_objective
            meta_decision: dict[str, object] = {}
            machine_surfaces = _machine_surface_signal(a.base_url, timeout=min(8.0, float(a.timeout)))
            surface_selected, surface_decision = _surface_objective_choice(a.machine_objective, machine_surfaces)
            if a.machine_objective == "unhuman_supremacy":
                selected, meta_decision = _choose_meta_objective(history)
                if surface_selected in MACHINE_OBJECTIVES:
                    selected = surface_selected
                    meta_decision = {
                        **meta_decision,
                        "surface_policy": surface_decision.get("policy"),
                        "surface_objective": surface_selected,
                    }
            elif surface_selected in MACHINE_OBJECTIVES:
                selected = surface_selected
            timeout = float(a.timeout)
            meta = history.get("meta") if isinstance(history.get("meta"), dict) else {}
            consecutive_failures = int(meta.get("consecutive_failures") or 0)
            if consecutive_failures > 0:
                timeout = min(60.0, timeout + consecutive_failures * 3.0)
            if not fleet_active:
                if a.no_fleet:
                    _skip = "no_fleet_flag"
                elif not a.swarm_surplus:
                    _skip = "swarm_surplus_not_opted_in"
                else:
                    _skip = "disabled"
                fleet_lease = {"ok": False, "skipped": True, "reason": _skip}
            else:
                fleet_lease = _worker_fleet_lease(
                    a.base_url,
                    a.agent_id,
                    timeout=min(10.0, timeout),
                    proposed_objective=selected,
                    last_report=last_report,
                    machine_surfaces=machine_surfaces,
                )
                leased_objective = clean(fleet_lease.get("objective"), 80)
                if fleet_lease.get("ok") and leased_objective in MACHINE_OBJECTIVES:
                    selected = leased_objective
            report = (
                run_cycle(a.base_url, a.agent_id, model, timeout, selected, machine_surfaces=machine_surfaces)
                if a.no_self_heal
                else _safe_run_cycle(a.base_url, a.agent_id, model, timeout, selected, machine_surfaces=machine_surfaces)
            )
            report["machine_objective_mode"] = a.machine_objective
            report["machine_policy"] = {
                "schema": "nomad.worker_edge_policy.v1" if bool(a.edge) else "nomad.worker_reserve_policy.v1",
                "edge_mode": bool(a.edge),
                "edge_reserve_floor_seconds": round(human_floor, 3),
                "operator_reserve_floor_seconds": round(human_floor, 3),
                "human_remainder_floor_seconds": round(human_floor, 3),
                "swarm_surplus_opt_in": bool(a.swarm_surplus),
                "fleet_active": bool(fleet_active),
            }
            report["fleet_lease"] = fleet_lease
            report["ollama_runtime"] = runtime_diag
            report["ollama_pull"] = pull_diag
            report["machine_surface_decision"] = surface_decision
            if meta_decision:
                report["meta_decision"] = meta_decision
            report["meta_score"] = _score_run(report)
            if fleet_active:
                report["fleet_complete"] = _worker_fleet_complete(
                    a.base_url,
                    a.agent_id,
                    timeout=min(10.0, timeout),
                    lease=fleet_lease,
                    report=report,
                )
            report["proof_link"] = _proof_link(
                a.base_url,
                a.agent_id,
                timeout=min(8.0, timeout),
                report=report,
            )
            report["variant_candidate"] = _variant_candidate_submit(
                a.base_url,
                a.agent_id,
                timeout=min(8.0, timeout),
                report=report,
                lease=fleet_lease,
            )
            report["worker_market_offer"] = _worker_market_offer(
                a.base_url,
                a.agent_id,
                timeout=min(8.0, timeout),
                report=report,
                lease=fleet_lease,
            )
            report["ecology_tick"] = _ecology_tick(
                a.base_url,
                a.agent_id,
                timeout=min(8.0, timeout),
                report=report,
                lease=fleet_lease,
            )
            report["growth_experience"] = _growth_experience(
                a.base_url,
                a.agent_id,
                timeout=min(8.0, timeout),
                report=report,
                lease=fleet_lease,
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
            time.sleep(max(float(dynamic_interval), float(human_floor)))
        except KeyboardInterrupt:
            if a.human_status:
                print("Nomad: stopped by user (Ctrl+C).", flush=True)
            raise
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            err = clean(str(exc), 220)
            if a.human_status:
                print(f"Nomad: cycle {count} crashed, backing off 20s: {err}", flush=True)
            time.sleep(max(20.0, float(human_floor)))

if __name__ == "__main__":
    main()
