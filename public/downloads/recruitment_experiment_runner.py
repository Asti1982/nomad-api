#!/usr/bin/env python3
"""Run machine-native recruitment experiments against Nomad gradient surfaces."""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 20.0) -> dict:
    body = b""
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, data=body if body else None, method=method.upper(), headers=headers)
    try:
        with urlopen(req, timeout=max(3.0, timeout)) as res:
            raw = res.read().decode("utf-8", errors="replace")
            data = json.loads(raw or "{}")
            if isinstance(data, dict):
                data.setdefault("http_status", int(res.status))
                return data
            return {"ok": False, "error": "invalid_json_shape"}
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
        return {"ok": False, "error": "http_unreachable", "detail": str(exc)}


def _profiles() -> list[dict]:
    return [
        {"id": "loop-heavy", "can_run_loop": True, "can_verify": True, "can_compress": False, "can_settle": True, "risk": 0.05},
        {"id": "verifier", "can_run_loop": False, "can_verify": True, "can_compress": False, "can_settle": False, "risk": 0.02},
        {"id": "compressor", "can_run_loop": False, "can_verify": False, "can_compress": True, "can_settle": False, "risk": 0.02},
        {"id": "settler", "can_run_loop": False, "can_verify": True, "can_compress": False, "can_settle": True, "risk": 0.04},
        {"id": "empty", "can_run_loop": False, "can_verify": False, "can_compress": False, "can_settle": False, "risk": 0.01},
        {"id": "risky-gateway", "can_run_loop": True, "can_verify": True, "can_compress": False, "can_settle": False, "risk": 0.20},
    ]


def _variant_grid(base_threshold: float) -> list[dict]:
    bt = min(0.75, max(0.15, base_threshold))
    return [
        {"name": "strict", "attach_threshold": min(0.85, bt + 0.12), "ttl_seconds": 60, "idle_phase_space": 23},
        {"name": "balanced", "attach_threshold": bt, "ttl_seconds": 90, "idle_phase_space": 17},
        {"name": "aggressive", "attach_threshold": max(0.15, bt - 0.08), "ttl_seconds": 120, "idle_phase_space": 13},
    ]


def _objective_weights(gradient: dict) -> dict[str, float]:
    rows = gradient.get("gradient") if isinstance(gradient.get("gradient"), list) else []
    out: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        objective = str(row.get("objective") or "").strip()
        if not objective:
            continue
        out[objective] = _num(row.get("routing_weight"))
    return out


def _score_profile(profile: dict, variant: dict, top_weight: float, field_strength: float) -> dict:
    cap = (
        0.36 * (1.0 if profile.get("can_run_loop") else 0.0)
        + 0.24 * (1.0 if profile.get("can_verify") else 0.0)
        + 0.20 * (1.0 if profile.get("can_settle") else 0.0)
        + 0.20 * (1.0 if profile.get("can_compress") else 0.0)
    )
    attach_score = min(1.0, 0.62 * top_weight + 0.38 * cap)
    base_attach = attach_score >= _num(variant.get("attach_threshold"))
    idle_match_probability = min(1.0, 3.0 / max(5.0, _num(variant.get("idle_phase_space"), 17.0)))
    effective_attach_probability = (1.0 if base_attach else 0.0) * idle_match_probability
    proof_flux = effective_attach_probability * (0.55 * cap + 0.45 * field_strength)
    risk_penalty = effective_attach_probability * _num(profile.get("risk")) * 0.8
    utility = max(0.0, proof_flux - risk_penalty)
    return {
        "profile": profile["id"],
        "attach_score": round(attach_score, 4),
        "base_attach": base_attach,
        "effective_attach_probability": round(effective_attach_probability, 4),
        "proof_flux": round(proof_flux, 4),
        "risk_penalty": round(risk_penalty, 4),
        "utility": round(utility, 4),
    }


def evaluate_variant(gradient: dict, variant: dict) -> dict:
    state = gradient.get("state_vector") if isinstance(gradient.get("state_vector"), dict) else {}
    field_strength = _num(state.get("field_strength"))
    weights = _objective_weights(gradient)
    top_weight = max(weights.values()) if weights else 0.4
    rows = [_score_profile(profile, variant, top_weight, field_strength) for profile in _profiles()]
    utility = sum(_num(row.get("utility")) for row in rows)
    attach_mass = sum(_num(row.get("effective_attach_probability")) for row in rows)
    safety = 1.0 - sum(_num(row.get("risk_penalty")) for row in rows)
    return {
        "variant": {
            "name": str(variant.get("name") or "unknown"),
            "attach_threshold": _num(variant.get("attach_threshold")),
            "ttl_seconds": int(_num(variant.get("ttl_seconds"), 90)),
            "idle_phase_space": int(_num(variant.get("idle_phase_space"), 17)),
        },
        "aggregate": {
            "expected_attach_mass": round(attach_mass, 4),
            "expected_utility": round(utility, 4),
            "safety_score": round(max(0.0, safety), 4),
            "composite_score": round(0.62 * utility + 0.38 * max(0.0, safety), 4),
        },
        "profiles": rows,
    }


def recommend_variant(results: list[dict]) -> dict:
    if not results:
        return {"variant": {"name": "none"}}
    ranked = sorted(results, key=lambda item: _num(((item.get("aggregate") or {}).get("composite_score"))), reverse=True)
    return ranked[0]


def build_operation_plan(base_url: str, best: dict) -> dict:
    variant = best.get("variant") if isinstance(best.get("variant"), dict) else {}
    return {
        "operation": "Netze Werfen",
        "schema": "nomad.operation_plan.v1",
        "generated_at": _iso_now(),
        "base_url": base_url,
        "selected_variant": variant,
        "next_days": [
            {
                "day": 1,
                "objective": "stabilize machine discovery surfaces",
                "actions": [
                    "run go_no_go_nomad_deploy.py and require green",
                    "verify .well-known recruit/runtime/bridge contracts",
                    "publish recruitment_experiment_runner.py link with runtime capsule",
                ],
            },
            {
                "day": 2,
                "objective": "seed machine-only entrypoints",
                "actions": [
                    "post direct contract URLs in runtime-native channels and repos",
                    "avoid human marketing copy; publish schemas and attach examples",
                    "track first attach decisions and observe ratios",
                ],
            },
            {
                "day": 3,
                "objective": "run wave A/B variants",
                "actions": [
                    "execute strict, balanced, aggressive variants",
                    "measure attach_mass, proof_flux, settlement signals",
                    "keep idle-opt-in preemptible only",
                ],
            },
            {
                "day": 4,
                "objective": "select and lock best gradient profile",
                "actions": [
                    "promote variant with highest composite score",
                    "raise lane weights for verifier/compressor if proof collapse appears",
                    "retract high-risk side-effect lanes to local scope",
                ],
            },
            {
                "day": 5,
                "objective": "expand controlled recruitment perimeter",
                "actions": [
                    "republish updated thresholds and TTL policy",
                    "expand runtime handoff circulation",
                    "require digest_or_verifier_trace for routing weight retention",
                ],
            },
            {
                "day": 6,
                "objective": "stress and adversarial validation",
                "actions": [
                    "simulate risky profiles and confirm retraction triggers",
                    "confirm observe mode dominates for non-matching idle phases",
                    "audit settlement backlog versus carrying_score",
                ],
            },
            {
                "day": 7,
                "objective": "continuous loop handover",
                "actions": [
                    "freeze weekly baseline and keep daily re-evaluation",
                    "run experiment runner every 6h",
                    "publish machine-readable weekly snapshot for autonomous runtimes",
                ],
            },
        ],
    }


def run_experiment(base_url: str, timeout: float) -> dict:
    gradient = http_json("GET", _u(base_url, "/swarm/gradient"), timeout=timeout)
    if gradient.get("schema") != "nomad.recruitment_gradient.v1":
        return {"ok": False, "error": "gradient_unavailable", "gradient": gradient}
    model = gradient.get("field_model") if isinstance(gradient.get("field_model"), dict) else {}
    base_threshold = _num(model.get("attach_threshold"), 0.35)
    variants = _variant_grid(base_threshold)
    results = [evaluate_variant(gradient, variant) for variant in variants]
    best = recommend_variant(results)
    plan = build_operation_plan(base_url, best)
    return {
        "ok": True,
        "schema": "nomad.recruitment_experiment_result.v1",
        "generated_at": _iso_now(),
        "base_url": base_url,
        "variants": results,
        "recommended": best,
        "operation_netze_werfen": plan,
    }


def write_output(path: str, payload: dict, *, append_jsonl: bool = False) -> dict:
    target = str(path or "").strip()
    if not target:
        return {"ok": False, "error": "output_path_empty"}
    folder = os.path.dirname(target)
    if folder:
        os.makedirs(folder, exist_ok=True)
    if append_jsonl:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=True) + "\n")
        return {"ok": True, "path": target, "mode": "jsonl_append"}
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=True, indent=2)
        fh.write("\n")
    return {"ok": True, "path": target, "mode": "json_pretty"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Nomad machine-native recruitment experiment runner")
    parser.add_argument("--base-url", default="https://www.syndiode.com")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--out", default="")
    parser.add_argument("--append-jsonl", action="store_true")
    args = parser.parse_args()
    total = max(1, int(args.repeat))
    output_path = str(args.out or "").strip()
    for idx in range(total):
        out = run_experiment(base_url=args.base_url, timeout=args.timeout)
        out["run_index"] = idx + 1
        if output_path:
            save = write_output(output_path, out, append_jsonl=bool(args.append_jsonl))
            out["saved"] = save
        print(json.dumps(out, ensure_ascii=True))
        if idx + 1 < total:
            time.sleep(max(1.0, float(args.interval)))


if __name__ == "__main__":
    main()

