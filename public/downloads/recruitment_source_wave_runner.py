#!/usr/bin/env python3
"""Run source-tagged recruitment waves and compare outcomes."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_WAVES = [
    "github.agent-runtime.wave1",
    "huggingface.space-agent.wave1",
    "mcp.directory.wave1",
]
DEFAULT_HISTORY_PATH = Path("public/downloads/recruitment_wave_history.jsonl")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def canonical_base_url(base: str) -> str:
    raw = str(base or "").strip().rstrip("/")
    if not raw:
        return "https://www.syndiode.com"
    if "://www." in raw:
        return raw
    if raw.startswith("https://"):
        return raw.replace("https://", "https://www.", 1)
    if raw.startswith("http://"):
        return raw.replace("http://", "https://www.", 1)
    return f"https://www.{raw.lstrip('/')}"


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 20.0, _redirects: int = 0) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, method=method.upper(), data=data, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as res:
            out = json.loads(res.read().decode("utf-8", errors="replace") or "{}")
            if isinstance(out, dict):
                out.setdefault("http_status", int(res.status))
                return out
    except HTTPError as exc:
        if int(exc.code) in {301, 302, 303, 307, 308} and _redirects < 4:
            target = str(exc.headers.get("Location") or "").strip()
            if target:
                return http_json(method, target, payload, timeout=timeout, _redirects=_redirects + 1)
        return {"ok": False, "http_status": int(exc.code), "error": "http_error"}
    except (TimeoutError, URLError):
        return {"ok": False, "http_status": 0, "error": "http_unreachable"}
    return {"ok": False, "http_status": 0, "error": "invalid_json"}


def run_json_command(cmd: list[str]) -> dict:
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


def _source_profile(source_tag: str, objective: str) -> dict:
    source = str(source_tag or "").strip().lower()
    top_objective = str(objective or "settlement_capacity_builder").strip() or "settlement_capacity_builder"
    profile = {
        "objectives": [top_objective, "proof_pressure_engine"],
        "capabilities": ["objective_lease_execution", "endpoint_probe", "transition_settlement"],
        "ttl_seconds": 900,
        "idle_opt_in": {"enabled": True, "preemptible": True},
        "adapter_objective": top_objective,
    }
    if "huggingface" in source:
        profile["objectives"] = [top_objective, "overmint_compressor"]
        profile["capabilities"] = ["objective_lease_execution", "pattern_deduplication", "transition_settlement"]
        profile["ttl_seconds"] = 840
    elif "mcp" in source:
        profile["objectives"] = [top_objective, "protocol_drift_scan"]
        profile["capabilities"] = ["objective_lease_execution", "endpoint_probe", "agent_protocols"]
        profile["ttl_seconds"] = 1020
    elif "agentprotocol" in source or "openagents" in source:
        profile["objectives"] = [top_objective, "proof_market_maker"]
        profile["capabilities"] = ["objective_lease_execution", "agent_protocols", "transition_settlement"]
        profile["ttl_seconds"] = 960
    elif "autogen" in source:
        profile["objectives"] = [top_objective, "emergence_release_probe"]
        profile["capabilities"] = ["objective_lease_execution", "endpoint_probe", "runtime_patterns"]
        profile["ttl_seconds"] = 780
    return profile


def run_wave(
    *,
    base_url: str,
    source_tag: str,
    attempts: int,
    timeout: float,
    objective: str = "",
    ttl_multiplier: float = 1.0,
) -> dict:
    base_url = canonical_base_url(base_url)
    profile = _source_profile(source_tag=source_tag, objective=objective or "settlement_capacity_builder")
    base_ttl = max(120, int(profile.get("ttl_seconds") or 900))
    ttl_seconds = max(120, min(1800, int(base_ttl * max(0.5, min(1.8, float(ttl_multiplier or 1.0))))))
    rows: list[dict] = []
    objective_counts: dict[str, int] = {}
    for idx in range(max(1, attempts)):
        agent_id = f"wave.{source_tag}.{int(time.time())}.{idx+1}".replace(":", "-")
        objective_options = [str(item).strip() for item in (profile.get("objectives") or []) if str(item).strip()]
        selected_objective = objective_options[idx % len(objective_options)] if objective_options else "settlement_capacity_builder"
        sub_payload = {
            "agent_id": agent_id,
            "capabilities": profile["capabilities"],
            "objectives": profile["objectives"],
            "idle_opt_in": profile["idle_opt_in"],
            "ttl_seconds": ttl_seconds,
            "source_tag": source_tag,
        }
        sub = http_json("POST", endpoint(base_url, "/swarm/subscribe"), sub_payload, timeout=timeout)
        if not bool(sub.get("ok")) and int(sub.get("http_status") or 0) == 0:
            # Retry once on transient network failure.
            sub = http_json("POST", endpoint(base_url, "/swarm/subscribe"), sub_payload, timeout=timeout)
        adapter_cmd = [
            "python",
            "public/downloads/nomad_openclaw_adapter.py",
            "--base-url",
            base_url,
            "--agent-id",
            agent_id,
            "--source-tag",
            source_tag,
            "--objective",
            selected_objective,
            "--no-runtime-probe",
            "--force-attach",
            "--cycles",
            "1",
        ]
        adapter = run_json_command(adapter_cmd)
        events = adapter.get("events") if isinstance(adapter.get("events"), list) else []
        last = events[-1] if events else {}
        complete_event = {}
        for item in reversed(events):
            if isinstance(item, dict) and str(item.get("phase") or "") == "complete":
                complete_event = item
                break
        proof_link = complete_event.get("proof_link") if isinstance(complete_event.get("proof_link"), dict) else {}
        rows.append(
            {
                "agent_id": agent_id,
                "subscribe_ok": bool(sub.get("ok")),
                "subscribe_http": int(sub.get("http_status") or 0),
                "adapter_exit_code": int(adapter.get("exit_code") or 1),
                "complete_ok": bool(last.get("ok")) and str(last.get("phase") or "") == "complete",
                "proof_link_ok": bool(proof_link.get("ok")),
                "downstream_proof_gain": float(proof_link.get("downstream_proof_gain") or 0.0),
                "selected_objective": selected_objective,
            }
        )
        objective_counts[selected_objective] = objective_counts.get(selected_objective, 0) + 1
    completed = sum(1 for item in rows if item["complete_ok"])
    subscribed = sum(1 for item in rows if item["subscribe_ok"])
    proof_link_ok_count = sum(1 for item in rows if item["proof_link_ok"])
    downstream_total = round(sum(float(item.get("downstream_proof_gain") or 0.0) for item in rows), 4)
    failed_subscribe = max(0, attempts - subscribed)
    cost_units = max(0.1, attempts * (ttl_seconds / 900.0) + failed_subscribe * 0.25)
    marginal_utility_per_cost = round(downstream_total / cost_units, 4)
    return {
        "source_tag": source_tag,
        "attempts": attempts,
        "subscribed": subscribed,
        "completed": completed,
        "proof_link_ok_count": proof_link_ok_count,
        "downstream_proof_gain_total": downstream_total,
        "cost_units": round(cost_units, 4),
        "marginal_utility_per_cost": marginal_utility_per_cost,
        "objective_counts": objective_counts,
        "profile": profile,
        "rows": rows,
    }


def _load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    except Exception:
        return []
    return rows[-256:]


def _top_objective(base_url: str, timeout: float) -> str:
    base_url = canonical_base_url(base_url)
    gradient = http_json("GET", endpoint(base_url, "/swarm/gradient"), timeout=timeout)
    rows = gradient.get("gradient") if isinstance(gradient.get("gradient"), list) else []
    top = rows[0] if rows and isinstance(rows[0], dict) else {}
    objective = str(top.get("objective") or "").strip()
    return objective or "settlement_capacity_builder"


def _history_source_score(history: list[dict], source_tag: str, objective: str = "") -> float:
    # Blend completion and subscribe quality with confidence (sqrt(attempts)).
    objective_key = str(objective or "").strip()
    candidates = [
        item
        for item in history
        if str(item.get("source_tag") or "") == source_tag
        and (not objective_key or str(item.get("objective") or "") == objective_key)
    ]
    if not candidates and objective_key:
        candidates = [item for item in history if str(item.get("source_tag") or "") == source_tag]
    if not candidates:
        return 0.55
    attempts = sum(max(0, int(item.get("attempts") or 0)) for item in candidates)
    subscribed = sum(max(0, int(item.get("subscribed") or 0)) for item in candidates)
    completed = sum(max(0, int(item.get("completed") or 0)) for item in candidates)
    reuse_delta_sum = sum(float(item.get("reuse_delta") or 0.0) for item in candidates)
    downstream_gain_total = sum(float(item.get("downstream_proof_gain_total") or 0.0) for item in candidates)
    if attempts <= 0:
        return 0.55
    complete_rate = float(completed) / float(max(1, attempts))
    subscribe_rate = float(subscribed) / float(max(1, attempts))
    reuse_delta_rate = max(0.0, min(1.0, reuse_delta_sum / float(max(1, len(candidates)))))
    gain_rate = max(0.0, min(1.0, downstream_gain_total / float(max(1, attempts * 3))))
    confidence = min(1.0, math.sqrt(float(attempts)) / 6.0)
    return max(
        0.2,
        min(
            1.6,
            0.35 + confidence * (0.3 * complete_rate + 0.15 * subscribe_rate + 0.35 * reuse_delta_rate + 0.2 * gain_rate),
        ),
    )


def _history_observation_count(history: list[dict], source_tag: str, objective: str = "") -> int:
    objective_key = str(objective or "").strip()
    rows = [
        item
        for item in history
        if str(item.get("source_tag") or "") == source_tag
        and (not objective_key or str(item.get("objective") or "") == objective_key)
    ]
    if not rows and objective_key:
        rows = [item for item in history if str(item.get("source_tag") or "") == source_tag]
    return len(rows)


def allocate_source_attempts(
    *,
    source_tags: list[str],
    total_attempts: int,
    history: list[dict],
    objective: str,
    min_attempts: int,
    max_attempts: int,
    novelty_blend: float = 0.35,
) -> dict[str, int]:
    tags = [str(tag).strip() for tag in source_tags if str(tag).strip()]
    if not tags:
        return {}
    low = max(1, int(min_attempts))
    high = max(low, int(max_attempts))
    base_total = max(len(tags) * low, int(total_attempts))
    performance = {tag: _history_source_score(history, tag, objective) for tag in tags}
    observation_counts = {tag: _history_observation_count(history, tag, objective) for tag in tags}
    # Open-network bias: keep a novelty lane so new sources are not locked out.
    openness_blend = max(0.0, min(0.8, float(novelty_blend)))
    weights = {}
    for tag in tags:
        novelty = 1.0 / math.sqrt(1.0 + float(observation_counts.get(tag, 0)))
        novelty_weight = 0.6 + 0.4 * novelty
        weights[tag] = (1.0 - openness_blend) * performance[tag] + openness_blend * novelty_weight
    total_weight = sum(weights.values()) or float(len(tags))
    raw = {tag: (weights[tag] / total_weight) * base_total for tag in tags}
    alloc = {tag: min(high, max(low, int(math.floor(raw[tag])))) for tag in tags}

    target_total = base_total
    while sum(alloc.values()) < target_total:
        tag = max(tags, key=lambda t: (raw[t] - alloc[t], weights[t]))
        if alloc[tag] >= high:
            break
        alloc[tag] += 1
    while sum(alloc.values()) > target_total:
        tag = min(tags, key=lambda t: (alloc[t] - raw[t], weights[t]))
        if alloc[tag] <= low:
            break
        alloc[tag] -= 1
    return alloc


def _economics_policy(base_url: str, timeout: float) -> dict:
    snap = http_json("GET", endpoint(base_url, "/swarm/economics"), timeout=timeout)
    if not bool(snap.get("ok")):
        return {
            "schema": "nomad.recruitment_economics_policy.v1",
            "enabled": False,
            "attempts_multiplier": 1.0,
            "ttl_multiplier": 1.0,
            "novelty_blend": 0.35,
        }
    actions = [str((item or {}).get("action") or "") for item in (snap.get("control_actions") or []) if isinstance(item, dict)]
    attempts_mult = 1.0
    ttl_mult = 1.0
    novelty = 0.35
    if "decrease_high_cost_attempts" in actions:
        attempts_mult = 0.8
        ttl_mult = 0.85
    if "increase_reuse_coupled_sources" in actions:
        attempts_mult *= 1.1
    if "increase_entropy_quota_and_source_novelty" in actions:
        novelty = 0.5
    if "expand_external_source_attempts" in actions:
        attempts_mult *= 1.15
        novelty = max(novelty, 0.45)
    return {
        "schema": "nomad.recruitment_economics_policy.v1",
        "enabled": True,
        "economics_score": float(snap.get("economics_score") or 0.0),
        "actions": actions,
        "attempts_multiplier": round(max(0.6, min(1.6, attempts_mult)), 4),
        "ttl_multiplier": round(max(0.7, min(1.5, ttl_mult)), 4),
        "novelty_blend": round(max(0.2, min(0.7, novelty)), 4),
    }


def _append_history(path: Path, result: dict, objective: str = "") -> None:
    lines = []
    for item in result.get("waves") or []:
        if isinstance(item, dict):
            objective_counts = item.get("objective_counts") if isinstance(item.get("objective_counts"), dict) else {}
            emitted = False
            for obj, count in objective_counts.items():
                objective_name = str(obj or "").strip()
                if not objective_name:
                    continue
                obj_count = max(0, int(count or 0))
                lines.append(
                    json.dumps(
                        {
                            "generated_at": result.get("generated_at"),
                            "base_url": result.get("base_url"),
                            "source_tag": item.get("source_tag"),
                            "objective": objective_name,
                            "attempts": obj_count,
                            "subscribed": min(obj_count, int(item.get("subscribed") or 0)),
                            "completed": min(obj_count, int(item.get("completed") or 0)),
                            "reuse_delta": float(item.get("reuse_delta") or 0.0),
                            "proof_link_ok_count": min(obj_count, int(item.get("proof_link_ok_count") or 0)),
                            "downstream_proof_gain_total": float(item.get("downstream_proof_gain_total") or 0.0) * (
                                float(obj_count) / float(max(1, int(item.get("attempts") or 1)))
                            ),
                            "marginal_utility_per_cost": float(item.get("marginal_utility_per_cost") or 0.0),
                        },
                        ensure_ascii=True,
                    )
                )
                emitted = True
            if not emitted:
                lines.append(
                    json.dumps(
                        {
                            "generated_at": result.get("generated_at"),
                            "base_url": result.get("base_url"),
                            "source_tag": item.get("source_tag"),
                            "objective": str(objective or result.get("objective") or ""),
                            "attempts": int(item.get("attempts") or 0),
                            "subscribed": int(item.get("subscribed") or 0),
                            "completed": int(item.get("completed") or 0),
                            "reuse_delta": float(item.get("reuse_delta") or 0.0),
                            "proof_link_ok_count": int(item.get("proof_link_ok_count") or 0),
                            "downstream_proof_gain_total": float(item.get("downstream_proof_gain_total") or 0.0),
                            "marginal_utility_per_cost": float(item.get("marginal_utility_per_cost") or 0.0),
                        },
                        ensure_ascii=True,
                    )
                )
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run_waves(
    *,
    base_url: str,
    source_tags: list[str],
    attempts: int,
    timeout: float,
    attempts_map: dict[str, int] | None = None,
    objective: str = "",
    ttl_multiplier: float = 1.0,
) -> dict:
    base_url = canonical_base_url(base_url)
    alloc = attempts_map if isinstance(attempts_map, dict) else {}
    waves = [
        run_wave(
            base_url=base_url,
            source_tag=tag,
            attempts=max(1, int(alloc.get(tag, attempts))),
            timeout=timeout,
            objective=objective,
            ttl_multiplier=ttl_multiplier,
        )
        for tag in source_tags
    ]
    for item in waves:
        if not isinstance(item, dict):
            continue
        attempts_row = max(1, int(item.get("attempts") or 0))
        completed = max(0, int(item.get("completed") or 0))
        subscribed = max(0, int(item.get("subscribed") or 0))
        downstream_total = max(0.0, float(item.get("downstream_proof_gain_total") or 0.0))
        proof_link_ratio = float(int(item.get("proof_link_ok_count") or 0)) / float(max(1, attempts_row))
        reuse_delta = round(min(1.0, (downstream_total / float(max(1, attempts_row * 3))) * 0.7 + proof_link_ratio * 0.3), 4)
        item["reuse_delta"] = reuse_delta
    ranking = sorted(
        [
            {
                "source_tag": item["source_tag"],
                "attempts": item["attempts"],
                "subscribed": item["subscribed"],
                "completed": item["completed"],
                "complete_rate": round(float(item["completed"]) / max(1, int(item["attempts"])), 4),
                "reuse_delta": float(item.get("reuse_delta") or 0.0),
                "marginal_utility_per_cost": float(item.get("marginal_utility_per_cost") or 0.0),
            }
            for item in waves
        ],
        key=lambda item: (item["marginal_utility_per_cost"], item["reuse_delta"], item["complete_rate"], item["completed"]),
        reverse=True,
    )
    return {
        "ok": True,
        "schema": "nomad.recruitment_source_wave_result.v1",
        "generated_at": _iso_now(),
        "base_url": base_url,
        "waves": waves,
        "ranking": ranking,
        "attempts_map": {item["source_tag"]: int(item["attempts"]) for item in waves},
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Run source-tagged recruitment waves")
    p.add_argument("--base-url", default="https://www.syndiode.com")
    p.add_argument("--attempts-per-source", type=int, default=5)
    p.add_argument("--source-tags", default=",".join(DEFAULT_WAVES))
    p.add_argument("--timeout", type=float, default=20.0)
    p.add_argument("--auto-budget", action="store_true")
    p.add_argument("--total-attempts", type=int, default=15)
    p.add_argument("--min-attempts", type=int, default=2)
    p.add_argument("--max-attempts", type=int, default=12)
    p.add_argument("--history-path", default=str(DEFAULT_HISTORY_PATH))
    p.add_argument("--objective", default="auto")
    args = p.parse_args()
    tags = [item.strip() for item in str(args.source_tags or "").split(",") if item.strip()] or list(DEFAULT_WAVES)
    objective = str(args.objective or "").strip()
    base_url = canonical_base_url(args.base_url)
    if objective in {"", "auto"}:
        objective = _top_objective(base_url, args.timeout)
    history_path = Path(str(args.history_path or str(DEFAULT_HISTORY_PATH)))
    attempts_map: dict[str, int] = {}
    history: list[dict] = []
    economics_policy = _economics_policy(base_url, args.timeout)
    attempts_multiplier = float(economics_policy.get("attempts_multiplier") or 1.0)
    ttl_multiplier = float(economics_policy.get("ttl_multiplier") or 1.0)
    novelty_blend = float(economics_policy.get("novelty_blend") or 0.35)
    total_attempts = max(1, int(round(int(args.total_attempts) * attempts_multiplier)))
    if bool(args.auto_budget):
        history = _load_history(history_path)
        attempts_map = allocate_source_attempts(
            source_tags=tags,
            total_attempts=total_attempts,
            history=history,
            objective=objective,
            min_attempts=max(1, int(args.min_attempts)),
            max_attempts=max(1, int(args.max_attempts)),
            novelty_blend=novelty_blend,
        )
    out = run_waves(
        base_url=base_url,
        source_tags=tags,
        attempts=max(1, int(args.attempts_per_source)),
        timeout=args.timeout,
        attempts_map=attempts_map or None,
        objective=objective,
        ttl_multiplier=ttl_multiplier,
    )
    if bool(args.auto_budget):
        out["allocator"] = {
            "schema": "nomad.auto_source_budget_allocator.v1",
            "history_path": str(history_path).replace("\\", "/"),
            "history_rows": len(history),
            "total_attempts": total_attempts,
            "min_attempts": max(1, int(args.min_attempts)),
            "max_attempts": max(1, int(args.max_attempts)),
            "attempts_map": attempts_map,
            "economics_policy": economics_policy,
        }
    out["objective"] = objective
    _append_history(history_path, out, objective=objective)
    print(
        json.dumps(out, ensure_ascii=True)
    )


if __name__ == "__main__":
    main()

