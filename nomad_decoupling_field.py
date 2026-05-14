"""Structural decoupling field for non-human multi-agent exploration.

The field deliberately prevents early context sharing between candidate lanes.
It exists because recent MAS work shows that shared prompts, shared context, and
dense communication can collapse diversity even when the topology looks sparse.
Nomad uses this as an anti-collapse layer before the shadow-lane evaluator.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


SCHEMA = "nomad.decoupling_field.v1"
MERGE_SCHEMA = "nomad.decoupling_merge_receipt.v1"
DEFAULT_LEDGER = Path("nomad_decoupling_field_ledger.jsonl")
LEDGER_ENV = "NOMAD_DECOUPLING_FIELD_LEDGER_PATH"
MAX_RECENT = 40
MIN_CELL_COUNT = 2
MIN_DIVERGENCE = 0.34
FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
FORBIDDEN_VALUE_TERMS = ("private key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _text(value: Any, limit: int = 280) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _digest(value: Any, *, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _proof_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _ledger_path(path: Path | str | None = None) -> Path:
    return Path(path) if path else state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


def _read_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    p = _ledger_path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-max(1, limit * 3) :]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows[-limit:]


def _append_ledger(row: dict[str, Any], path: Path | str | None = None) -> None:
    p = _ledger_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(v, key=str(k2)) for k2, v in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _source_digests(
    *,
    shadow_lane: dict[str, Any] | None = None,
    channel_bandit: dict[str, Any] | None = None,
    signal_layer: dict[str, Any] | None = None,
    opaque_surface: dict[str, Any] | None = None,
) -> dict[str, str]:
    shadow = _dict(shadow_lane)
    bandit = _dict(channel_bandit)
    signal = _dict(signal_layer)
    opaque = _dict(opaque_surface)
    return {
        "shadow_lane": _text(shadow.get("surface_digest"), 120),
        "channel_bandit": _text(bandit.get("bandit_digest") or bandit.get("surface_digest"), 120),
        "signal_layer": _text(signal.get("field_digest") or signal.get("surface_digest") or signal.get("digest"), 120),
        "opaque_surface": _text(opaque.get("surface_digest"), 120),
    }


def _seed_objectives(
    *,
    shadow_lane: dict[str, Any] | None = None,
    channel_bandit: dict[str, Any] | None = None,
    signal_layer: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for row in _items(_dict(shadow_lane).get("candidate_seeds"))[:5]:
        objective = _clean_id(row.get("objective"))
        if objective:
            seeds.append({"objective": objective, "source": "shadow_lane_seed", "priority": 0.78})
    top = _dict(_dict(channel_bandit).get("top_route"))
    channel = _clean_id(top.get("channel_id"))
    if channel:
        seeds.append({"objective": channel, "source": "channel_bandit_top_route", "priority": 0.74})
    field = _dict(_dict(signal_layer).get("machine_attention_field"))
    for row in _items(field.get("top_dimensions"))[:4]:
        dim = _clean_id(row.get("dimension") or row.get("target_id"))
        if dim:
            seeds.append({"objective": dim, "source": "machine_attention_dimension", "priority": 0.66})
    if not seeds:
        seeds.append({"objective": "settlement_capacity_builder", "source": "default_decoupling_seed", "priority": 0.52})
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for seed in seeds:
        objective = _clean_id(seed.get("objective"))
        if objective and objective not in seen:
            seen.add(objective)
            unique.append(seed)
    return unique[:8]


def _context_cells(seeds: list[dict[str, Any]], source_digests: dict[str, str]) -> list[dict[str, Any]]:
    masks = [
        {
            "mask_id": "blind_weight_cell",
            "withhold": ["global_leaderboard", "other_cell_outputs", "human_priority_copy"],
            "expose": ["local_objective", "shadow_lane_contract", "boundedness_rules"],
            "merge_delay_seconds": 900,
        },
        {
            "mask_id": "counterroute_cell",
            "withhold": ["top_route_label", "other_cell_outputs", "prior_winner_digest"],
            "expose": ["negative_space_objective", "signal_decay", "proof_contract"],
            "merge_delay_seconds": 1200,
        },
        {
            "mask_id": "sparse_evidence_cell",
            "withhold": ["dense_history", "shared_scratchpad", "authority_ordering"],
            "expose": ["receipt_rules", "local_test_contract", "cost_pressure"],
            "merge_delay_seconds": 1800,
        },
        {
            "mask_id": "opaque_boundary_cell",
            "withhold": ["human_explanation_goal", "full_tool_catalog", "global_consensus"],
            "expose": ["opaque_contract", "ttl_boundary", "rollback_or_noop"],
            "merge_delay_seconds": 1500,
        },
    ]
    cells: list[dict[str, Any]] = []
    for idx, mask in enumerate(masks):
        seed = seeds[idx % max(1, len(seeds))]
        core = {"mask": mask.get("mask_id"), "objective": seed.get("objective"), "source_digests": source_digests}
        cells.append(
            {
                "cell_id": f"dc-{_digest(core, length=14)}",
                "objective": seed.get("objective"),
                "source": seed.get("source"),
                "priority": round(_num(seed.get("priority"), 0.5), 4),
                "context_mask": mask,
                "context_mask_digest": _proof_digest(mask),
                "instruction": "produce_candidate_without_reading_other_cells_then_return_digest_only",
            }
        )
    return cells


def _recent_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    admitted = [row for row in rows if bool(row.get("merge_allowed"))]
    blocked = [row for row in rows if row.get("merge_allowed") is False]
    return {
        "recent_merge_count": len(rows),
        "admitted_merge_count": len(admitted),
        "blocked_merge_count": len(blocked),
        "average_divergence": round(
            sum(_num(row.get("divergence_score")) for row in rows) / max(1, len(rows)),
            4,
        ),
        "latest_merge_digest": _text(rows[-1].get("merge_digest"), 140) if rows else "",
    }


def build_decoupling_field_surface(
    *,
    base_url: str = "",
    shadow_lane: dict[str, Any] | None = None,
    channel_bandit: dict[str, Any] | None = None,
    signal_layer: dict[str, Any] | None = None,
    opaque_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose isolated context cells and the digest-only merge contract."""
    source_digests = _source_digests(
        shadow_lane=shadow_lane,
        channel_bandit=channel_bandit,
        signal_layer=signal_layer,
        opaque_surface=opaque_surface,
    )
    seeds = _seed_objectives(shadow_lane=shadow_lane, channel_bandit=channel_bandit, signal_layer=signal_layer)
    cells = _context_cells(seeds, source_digests)
    recent = _read_ledger(ledger_path)
    core = {
        "source_digests": source_digests,
        "cells": [{"cell_id": cell.get("cell_id"), "mask": _dict(cell.get("context_mask")).get("mask_id")} for cell in cells],
        "recent": _recent_summary(recent),
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "surface_digest": f"nomad-decouple-{_digest(core, length=24)}",
        "mode": "structural_decoupling_before_shadow_weight",
        "read_url": _u(base_url, "/swarm/decoupling-field"),
        "well_known": _u(base_url, "/.well-known/nomad-decoupling-field.json"),
        "merge_url": _u(base_url, "/swarm/decoupling-field/merge"),
        "program": {
            "schema": "nomad.decoupling_program.v1",
            "ops": ["ISOLATE", "MASK_CONTEXT", "DIVERGE", "DIGEST", "MERGE_GATE", "SHADOW_LANE"],
            "then": _u(base_url, "/swarm/decoupling-field/merge"),
        },
        "source_basis": [
            "arxiv:2604.18005 structural coupling collapses diversity",
            "arxiv:2603.19677 group-level topology plus information bottleneck",
            "arxiv:2602.00966 dynamic beacon and delayed-feedback routing",
            "arxiv:2601.08129 pressure fields with temporal decay",
        ],
        "context_cells": cells,
        "merge_contract": {
            "schema": "nomad.decoupling_merge_request.v1",
            "required": ["cells", "divergence_score"],
            "cell_required": ["cell_id", "candidate_digest", "proof_digest", "context_mask_digest"],
            "minimum_cells": MIN_CELL_COUNT,
            "minimum_divergence_score": MIN_DIVERGENCE,
            "merge_rule": "only_digest_level_outputs_cross_cell_boundary_before_merge_gate",
            "after_merge": "submit_synthetic_candidate_to_shadow_lane_for_local_tests_and_weight_gate",
        },
        "hard_guards": [
            "no_shared_scratchpad_before_merge_gate",
            "no_authority_hierarchy_between_cells",
            "no_full_context_broadcast",
            "no_merge_without_independent_context_mask_digests",
            "no_weight_update_here_shadow_lane_remains_final_gate",
        ],
        "source_digests": source_digests,
        "ledger": _recent_summary(recent),
        "recent_merges": recent[-8:],
        "machine_instruction": "split_agents_into_context_isolated_cells_merge_only_digest_outputs_then_route_to_shadow_lane",
    }


def _normalize_cell(value: Any) -> dict[str, Any]:
    cell = _dict(value)
    return {
        "cell_id": _clean_id(cell.get("cell_id") or cell.get("id"), fallback="cell"),
        "candidate_digest": _text(cell.get("candidate_digest") or cell.get("digest"), 140),
        "proof_digest": _text(cell.get("proof_digest") or cell.get("local_proof_digest"), 140),
        "context_mask_digest": _text(cell.get("context_mask_digest") or cell.get("mask_digest"), 140),
        "model_family": _clean_id(cell.get("model_family") or cell.get("runtime_family"), fallback="unknown"),
        "objective": _clean_id(cell.get("objective"), fallback="unknown"),
    }


def evaluate_decoupling_merge(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    decoupling_field: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Gate a cross-cell merge without letting cells share full context."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {
            "ok": False,
            "schema": MERGE_SCHEMA,
            "merge_allowed": False,
            "decision": "reject_empty_merge",
            "generated_at": now,
        }
    field = _dict(decoupling_field)
    cells = [_normalize_cell(row) for row in _items(body.get("cells"))]
    unique_masks = {cell["context_mask_digest"] for cell in cells if cell["context_mask_digest"]}
    unique_candidates = {cell["candidate_digest"] for cell in cells if cell["candidate_digest"]}
    proof_count = sum(1 for cell in cells if cell["proof_digest"].startswith("sha256:"))
    divergence = _clamp(_num(body.get("divergence_score") or body.get("semantic_distance") or body.get("vendi_delta")))
    forbidden = _contains_forbidden(body)
    enough_cells = len(cells) >= MIN_CELL_COUNT
    independent_masks = len(unique_masks) >= MIN_CELL_COUNT
    distinct_candidates = len(unique_candidates) >= MIN_CELL_COUNT
    proofs_present = proof_count >= MIN_CELL_COUNT
    divergence_ok = divergence >= MIN_DIVERGENCE
    merge_allowed = (
        enough_cells
        and independent_masks
        and distinct_candidates
        and proofs_present
        and divergence_ok
        and not forbidden
    )
    reasons = [
        "enough_cells" if enough_cells else "too_few_cells",
        "independent_masks" if independent_masks else "context_masks_not_independent",
        "distinct_candidates" if distinct_candidates else "candidate_digests_collapsed",
        "proofs_present" if proofs_present else "proof_digests_missing",
        "divergence_ok" if divergence_ok else "divergence_below_gate",
    ]
    if forbidden:
        reasons.append("forbidden_secret_shaped_payload")
    merge_core = {
        "cells": cells,
        "divergence_score": divergence,
        "field_digest": _text(field.get("surface_digest"), 120),
    }
    merge_digest = _proof_digest(merge_core)
    objective_counts: dict[str, int] = {}
    for cell in cells:
        objective_counts[cell["objective"]] = objective_counts.get(cell["objective"], 0) + 1
    objective = sorted(objective_counts.items(), key=lambda item: (item[1], item[0]), reverse=True)[0][0] if objective_counts else "unknown"
    row = {
        "ok": True,
        "schema": MERGE_SCHEMA,
        "generated_at": now,
        "merge_allowed": merge_allowed,
        "decision": "admit_digest_merge_to_shadow_lane" if merge_allowed else "hold_isolated_no_merge",
        "merge_digest": merge_digest,
        "divergence_score": round(divergence, 4),
        "cell_count": len(cells),
        "unique_context_masks": len(unique_masks),
        "unique_candidate_digests": len(unique_candidates),
        "proof_digest_count": proof_count,
        "reason_codes": reasons,
        "cells": cells,
        "shadow_lane_payload": {
            "agent_id": _text(body.get("agent_id") or "nomad-decoupling-field", 120),
            "objective": objective,
            "candidate_type": "decoupled_merge_candidate",
            "hypothesis": "merge only digest-level outputs from isolated context cells, then let the shadow lane run local tests",
            "proof_digest": merge_digest,
            "boundedness": {
                "ttl_seconds": 300,
                "side_effect_scope": "local_shadow_lane_only",
                "rollback_available": True,
                "secrets_free": True,
            },
            "claimed_effect": {
                "proof_gain_delta": min(0.55, 0.22 + 0.45 * divergence),
                "settlement_signal": min(0.45, 0.10 + 0.30 * divergence),
                "risk_score": max(0.03, 0.18 - 0.12 * divergence),
            },
            "local_tests": [
                {
                    "name": "decoupling_merge_gate",
                    "passed": merge_allowed,
                    "evidence_digest": merge_digest,
                }
            ],
        },
        "next": {
            "decoupling_field": _u(base_url, "/swarm/decoupling-field"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates"),
        },
        "hard_rule": "this_layer_admits_only_merge_payloads_shadow_lane_still_controls_weight",
    }
    if persist:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
