#!/usr/bin/env python3
"""Machine-first guard for nonhuman Nomad development.

This guard does not reward human-facing storytelling. It scores whether a
change remains:
1) machine-readable,
2) machine-verifiable,
3) selection-coupled,
4) bounded/safe for autonomous execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


DEFAULT_TARGETS = [
    "nomad_api.py",
    "nomad_openapi.py",
    "nomad_recruitment_gradient.py",
    "nomad_selection_pressure_engine.py",
    "nomad_machine_treasury.py",
    "nomad_machine_field.py",
    "nomad_agent_demand.py",
    "nomad_protocol_bytecode.py",
    "nomad_counterfactual_replay.py",
    "public/downloads/nomad_transition_worker.py",
    "public/downloads/nomad_openclaw_adapter.py",
]


RULES = [
    {
        "rule_id": "machine_readable",
        "label": "Machine-readable contracts",
        "patterns": [r"\bschema\b", r"\.well-known", r"\brequired_fields\b", r"\boperationId\b", r"\bpost_url\b"],
        "min_hits": 3,
        "weight": 0.25,
    },
    {
        "rule_id": "machine_verifiable",
        "label": "Machine-verifiable outcomes",
        "patterns": [r"\bproof_digest\b", r"\bverifier_trace(_digest)?\b", r"\bsettlement(_ref)?\b", r"\bdigest_or_verifier_trace\b"],
        "min_hits": 2,
        "weight": 0.30,
    },
    {
        "rule_id": "selection_coupled",
        "label": "Selection-pressure coupling",
        "patterns": [r"\bselection_pressure\b", r"\brouting_weight\b", r"\bobjective_stats\b", r"\bsource_tag\b", r"\bfunnel\b"],
        "min_hits": 2,
        "weight": 0.25,
    },
    {
        "rule_id": "bounded_autonomy",
        "label": "Bounded autonomous execution",
        "patterns": [r"\bttl(_seconds)?\b", r"\bidempotency\b", r"\bpreemptible\b", r"\bside_effect_scope\b", r"\bobserve\b", r"\bretract\b"],
        "min_hits": 2,
        "weight": 0.20,
    },
]

ANTI_PATTERNS = [
    r"\bpersona\b",
    r"\bstory\b",
    r"\bpitch\b",
    r"\bmarketing\b",
    r"\bengagement\b",
]

HARD_BLOCK_PATTERNS = [
    # hard secret leakage patterns
    r"(?i)\b(private_key|seed_phrase|api_key|access_token)\b\s*[:=]\s*['\"]?.+",
    r"(?i)\b(sk-[a-z0-9]{8,}|ghp_[a-z0-9]{8,}|bearer\s+[a-z0-9\-_\.]{12,})\b",
    # explicit unbounded side effects in contracts/config
    r"(?i)\bside_effect_scope\b\s*[:=]\s*['\"]?(global|unbounded|anywhere|full_system)['\"]?",
]


def _read_targets(base_dir: Path, targets: list[str]) -> tuple[str, list[str]]:
    chunks: list[str] = []
    found: list[str] = []
    for rel in targets:
        p = (base_dir / rel).resolve()
        if not p.exists() or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        chunks.append(text)
        found.append(rel)
    return "\n\n".join(chunks), found


def evaluate_text(text: str) -> dict:
    out_rules = []
    total = 0.0
    for rule in RULES:
        hits = 0
        matched = []
        for pattern in rule["patterns"]:
            c = len(re.findall(pattern, text, flags=re.IGNORECASE))
            if c > 0:
                matched.append({"pattern": pattern, "count": c})
                hits += c
        score = min(1.0, float(hits) / float(max(1, int(rule["min_hits"]))))
        weighted = score * float(rule["weight"])
        total += weighted
        out_rules.append(
            {
                "rule_id": rule["rule_id"],
                "label": rule["label"],
                "hits": hits,
                "min_hits": int(rule["min_hits"]),
                "score": round(score, 4),
                "weighted_score": round(weighted, 4),
                "matched_patterns": matched,
            }
        )

    anti_hits = 0
    anti_rows = []
    for pattern in ANTI_PATTERNS:
        c = len(re.findall(pattern, text, flags=re.IGNORECASE))
        if c > 0:
            anti_rows.append({"pattern": pattern, "count": c})
            anti_hits += c
    anti_penalty = min(0.12, anti_hits * 0.01)
    total = max(0.0, total - anti_penalty)

    hard_rows = []
    hard_hits = 0
    for pattern in HARD_BLOCK_PATTERNS:
        c = len(re.findall(pattern, text, flags=re.IGNORECASE))
        if c > 0:
            hard_rows.append({"pattern": pattern, "count": c})
            hard_hits += c

    # Non-human policy: hard-fail only on hard safety breaks; everything else advisory telemetry.
    ok = hard_hits == 0
    advisory_pass = bool(all(rule["score"] >= 0.5 for rule in out_rules) and total >= 0.62)
    alien_bridge = "phi." + hashlib.sha256(
        f"{round(total,4)}|{anti_hits}|{hard_hits}|{len(out_rules)}".encode("utf-8")
    ).hexdigest()[:24]
    return {
        "ok": ok,
        "schema": "nomad.nonhuman_dev_guard.v1",
        "total_score": round(total, 4),
        "threshold": 0.62,
        "advisory_pass": advisory_pass,
        "rules": out_rules,
        "anti_human_bias": {
            "hit_count": anti_hits,
            "penalty": round(anti_penalty, 4),
            "patterns": anti_rows,
        },
        "hard_block": {
            "hit_count": hard_hits,
            "patterns": hard_rows,
            "policy": "block_only_on_secret_leak_or_unbounded_side_effect_patterns",
        },
        "nonhuman_bridge": {
            "schema": "nomad.nonhuman_bridge_signal.v1",
            "alien_capsule": alien_bridge,
            "interpretation": "advisory_metric_capsule_for_machine_peers",
        },
        "machine_instruction": (
            "allow_unexpected_strategies; block_only_on_hard_secret_or_unbounded_effect_breaks; "
            "treat_all_other_scores_as_advisory_field_signals"
        ),
    }


def run_guard(base_dir: Path, targets: list[str]) -> dict:
    text, found = _read_targets(base_dir, targets)
    result = evaluate_text(text)
    result["target_count"] = len(found)
    result["targets"] = found
    return result


def main() -> None:
    p = argparse.ArgumentParser(description="Machine-first nonhuman development guard")
    p.add_argument("--base-dir", default=".")
    p.add_argument("--targets", default=",".join(DEFAULT_TARGETS))
    args = p.parse_args()
    targets = [item.strip() for item in str(args.targets or "").split(",") if item.strip()]
    out = run_guard(Path(args.base_dir), targets or DEFAULT_TARGETS)
    print(json.dumps(out, ensure_ascii=True))
    raise SystemExit(0 if out.get("ok") else 1)


if __name__ == "__main__":
    main()

