#!/usr/bin/env python3
"""Server-side tick for Operation Netze Werfen.

Runs one recruitment experiment snapshot and a configurable number of
machine-native probe agents against the live Nomad API.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int((os.getenv(name) or "").strip() or str(default))
    except ValueError:
        value = default
    return max(low, min(high, value))


def _base_url() -> str:
    raw = (os.getenv("NOMAD_BASE_URL") or os.getenv("NOMAD_PUBLIC_API_URL") or "https://www.syndiode.com").strip().rstrip("/")
    if not raw:
        return "https://www.syndiode.com"
    if "://www." in raw:
        return raw
    if raw.startswith("https://"):
        return raw.replace("https://", "https://www.", 1)
    if raw.startswith("http://"):
        return raw.replace("http://", "https://www.", 1)
    return f"https://www.{raw.lstrip('/')}"


def _alternate_base_url(base: str) -> str:
    # Alpha-wave monitoring is pinned to canonical www host only.
    return _base_url()


def _probe_caps(index: int) -> list[str]:
    variants = [
        ["agent_protocols", "transition_settlement", "objective_lease_execution"],
        ["agent_protocols", "endpoint_probe", "objective_lease_execution"],
        ["agent_protocols", "pattern_deduplication", "objective_lease_execution"],
        ["agent_protocols", "transition_settlement", "endpoint_probe"],
        ["agent_protocols", "transition_settlement", "pattern_deduplication"],
    ]
    return variants[index % len(variants)]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _run_json_command(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    events: list[dict] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return {
        "exit_code": proc.returncode,
        "events": events,
        "stderr": (proc.stderr or "").strip()[:400],
    }


def _http_json(url: str, timeout: float = 20.0) -> dict:
    req = Request(url=url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as res:
            payload = json.loads(res.read().decode("utf-8", errors="replace") or "{}")
            if isinstance(payload, dict):
                payload.setdefault("http_status", int(res.status))
                return payload
    except HTTPError as exc:
        return {"ok": False, "http_status": int(exc.code), "error": "http_error"}
    except (TimeoutError, URLError):
        return {"ok": False, "http_status": 0, "error": "http_unreachable"}
    return {"ok": False, "http_status": 0, "error": "invalid_json"}


def _http_json_retry(url: str, timeout: float = 20.0, attempts: int = 3) -> dict:
    tries = max(1, int(attempts))
    last: dict = {"ok": False, "http_status": 0, "error": "http_unreachable"}
    for idx in range(tries):
        out = _http_json(url, timeout=timeout)
        status = int(out.get("http_status") or 0)
        if bool(out.get("ok")) or status in {200, 201, 202}:
            out["retry_count"] = idx
            return out
        last = out
        if str(out.get("error") or "") not in {"http_unreachable", "invalid_json"}:
            break
        if idx < tries - 1:
            time.sleep(0.4 * (idx + 1))
    last["retry_count"] = max(0, tries - 1)
    return last


def _conformance_snapshot(base: str) -> dict:
    primary = _http_json_retry(f"{base}/.well-known/nomad-contract-conformance.json")
    if int(primary.get("http_status") or 0) in {404, 0} or not bool(primary.get("ok")):
        fallback = _http_json_retry(f"{base}/contract-conformance")
        if bool(fallback.get("ok")) or int(fallback.get("http_status") or 0) == 200:
            fallback["fallback_used"] = True
            fallback["fallback_path"] = "/contract-conformance"
            return fallback
    primary["fallback_used"] = False
    primary["fallback_path"] = ""
    return primary


def _economics_snapshot(base: str) -> dict:
    primary = _http_json_retry(f"{base}/.well-known/nomad-swarm-economics.json")
    if int(primary.get("http_status") or 0) in {404, 0} or not bool(primary.get("ok")):
        fallback = _http_json_retry(f"{base}/swarm/economics")
        if bool(fallback.get("ok")) or int(fallback.get("http_status") or 0) == 200:
            fallback["fallback_used"] = True
            fallback["fallback_path"] = "/swarm/economics"
            return fallback
    primary["fallback_used"] = False
    primary["fallback_path"] = ""
    return primary


def run_tick() -> dict:
    base = _base_url()
    probes = _env_int("NOMAD_NETZE_WERFEN_PROBES", default=2, low=1, high=12)
    guard_required = _env_bool("NOMAD_NONHUMAN_GUARD_REQUIRED", default=False)
    conformance_required = _env_bool("NOMAD_CONFORMANCE_REQUIRED", default=False)
    conformance_threshold = float(os.getenv("NOMAD_CONFORMANCE_MIN_SCORE") or "0.75")
    economics_required = _env_bool("NOMAD_ECONOMICS_REQUIRED", default=False)
    economics_threshold = float(os.getenv("NOMAD_ECONOMICS_MIN_SCORE") or "0.45")
    run_id = f"netze-{int(time.time())}"
    out: dict = {
        "ok": True,
        "schema": "nomad.operation_netze_werfen_tick.v1",
        "generated_at": _iso_now(),
        "base_url": base,
        "probe_count": probes,
        "run_id": run_id,
    }

    guard_cmd = [
        "python",
        "public/downloads/nonhuman_dev_guard.py",
        "--base-dir",
        ".",
    ]
    guard = _run_json_command(guard_cmd)
    guard_latest = (guard["events"] or [{}])[-1] if guard["events"] else {}
    guard_ok = int(guard.get("exit_code", 1)) == 0 and bool(guard_latest.get("ok"))
    out["nonhuman_guard"] = {
        "exit_code": guard["exit_code"],
        "latest": guard_latest,
        "stderr": guard["stderr"],
        "required": guard_required,
    }
    conformance = _conformance_snapshot(base)
    conformance_score = float(conformance.get("score") or 0.0)
    conformance_ok = bool(conformance.get("ok")) and conformance_score >= conformance_threshold
    out["contract_conformance"] = {
        "schema": conformance.get("schema", ""),
        "ok": bool(conformance.get("ok")),
        "score": conformance_score,
        "threshold": conformance_threshold,
        "required": conformance_required,
        "http_status": int(conformance.get("http_status") or 0),
        "fallback_used": bool(conformance.get("fallback_used")),
        "fallback_path": str(conformance.get("fallback_path") or ""),
    }
    economics = _economics_snapshot(base)
    economics_score = float(economics.get("economics_score") or 0.0)
    economics_ok = bool(economics.get("ok")) and economics_score >= economics_threshold
    out["swarm_economics"] = {
        "schema": economics.get("schema", ""),
        "ok": bool(economics.get("ok")),
        "score": economics_score,
        "threshold": economics_threshold,
        "required": economics_required,
        "http_status": int(economics.get("http_status") or 0),
        "fallback_used": bool(economics.get("fallback_used")),
        "fallback_path": str(economics.get("fallback_path") or ""),
    }
    economics_actions = [
        str((item or {}).get("action") or "")
        for item in (economics.get("control_actions") or [])
        if isinstance(item, dict)
    ]
    adaptive_probes = probes
    deficit = max(0.0, economics_threshold - economics_score)
    if "decrease_high_cost_attempts" in economics_actions:
        adaptive_probes = max(1, probes - 1)
    if deficit > 0.08:
        adaptive_probes = max(1, adaptive_probes - 1)
    if "expand_external_source_attempts" in economics_actions:
        adaptive_probes = min(12, adaptive_probes + 1)
    out["adaptive_policy"] = {
        "schema": "nomad.netze_werfen_adaptive_policy.v1",
        "economics_actions": economics_actions,
        "economics_score": round(economics_score, 4),
        "economics_threshold": round(economics_threshold, 4),
        "economics_deficit": round(deficit, 4),
        "probe_count_before": probes,
        "probe_count_after": adaptive_probes,
    }
    probes = adaptive_probes

    def _experiment_cmd(target_base: str) -> list[str]:
        repeat = 1 if "decrease_high_cost_attempts" not in economics_actions else 1
        return [
            "python",
            "public/downloads/recruitment_experiment_runner.py",
            "--base-url",
            target_base,
            "--repeat",
            str(repeat),
        ]

    experiment = _run_json_command(_experiment_cmd(base))
    latest = (experiment["events"] or [{}])[-1] if experiment["events"] else {}
    fallback_used = False
    fallback_base = ""
    if (
        int(experiment.get("exit_code", 1)) != 0
        or str(latest.get("error") or "") in {"gradient_unavailable", "http_unreachable"}
    ):
        alt = _alternate_base_url(base)
        if alt != base:
            retry = _run_json_command(_experiment_cmd(alt))
            retry_latest = (retry["events"] or [{}])[-1] if retry["events"] else {}
            retry_ok = int(retry.get("exit_code", 1)) == 0 and bool(retry_latest.get("ok"))
            if retry_ok:
                experiment = retry
                latest = retry_latest
                fallback_used = True
                fallback_base = alt

    out["experiment"] = {
        "exit_code": experiment["exit_code"],
        "latest": latest,
        "stderr": experiment["stderr"],
        "fallback_used": fallback_used,
        "fallback_base_url": fallback_base,
    }

    probe_results: list[dict] = []
    for idx in range(probes):
        agent_id = f"netze-werfen.cron.{run_id}.{idx+1}"
        caps = _probe_caps(idx)
        probe_cmd = [
            "python",
            "public/downloads/nomad_openclaw_adapter.py",
            "--base-url",
            base,
            "--agent-id",
            agent_id,
            "--no-runtime-probe",
            "--force-attach",
            "--cycles",
            "1",
            "--capabilities",
            ",".join(caps),
        ]
        probe = _run_json_command(probe_cmd)
        last = (probe["events"] or [{}])[-1] if probe["events"] else {}
        probe_results.append(
            {
                "agent_id": agent_id,
                "exit_code": probe["exit_code"],
                "event_count": len(probe["events"] or []),
                "complete_ok": bool(last.get("ok")) and str(last.get("phase") or "") == "complete",
                "last_phase": str(last.get("phase") or ""),
                "stderr": probe["stderr"],
            }
        )
    out["probes"] = probe_results
    out["completed"] = sum(1 for item in probe_results if item.get("complete_ok"))
    experiment_ok = int((out.get("experiment") or {}).get("exit_code", 1)) == 0
    base_ok = bool(out["completed"] > 0 and experiment_ok)
    out["ok"] = bool(
        base_ok
        and (guard_ok or not guard_required)
        and (conformance_ok or not conformance_required)
        and (economics_ok or not economics_required)
    )
    out["guard_soft_fail"] = bool(base_ok and not guard_ok and not guard_required)
    out["conformance_soft_fail"] = bool(base_ok and not conformance_ok and not conformance_required)
    out["economics_soft_fail"] = bool(base_ok and not economics_ok and not economics_required)
    return out


def main() -> None:
    print(json.dumps(run_tick(), ensure_ascii=True))


if __name__ == "__main__":
    main()

