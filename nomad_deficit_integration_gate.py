"""Deficit-triggered integration gate for non-anthropomorphic Nomad growth.

The gate deliberately rejects the human instinct to add meetings, consensus,
or permanent hierarchy when agent work fragments. Independent lanes remain the
default. Integration opens only when measurable coordination expansion outruns
consolidation, and it still emits only a bounded shadow-lane candidate.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


SCHEMA = "nomad.deficit_integration_gate.v1"
RECEIPT_SCHEMA = "nomad.deficit_integration_receipt.v1"
DEFAULT_LEDGER = Path("nomad_deficit_integration_ledger.jsonl")
LEDGER_ENV = "NOMAD_DEFICIT_INTEGRATION_LEDGER_PATH"
MAX_RECENT = 40
MIN_DEFICIT = 0.34
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


def _digest_present(value: Any) -> bool:
    return str(value or "").strip().lower().startswith("sha256:")


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


def _surface_digest(value: dict[str, Any] | None, *names: str) -> str:
    body = _dict(value)
    for name in names:
        text = _text(body.get(name), 140)
        if text:
            return text
    return ""


def _ledger_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    triggered = [row for row in rows if bool(row.get("integration_allowed"))]
    held = [row for row in rows if row.get("decision") == "keep_isolated_no_deficit"]
    return {
        "recent_event_count": len(rows),
        "triggered_integration_count": len(triggered),
        "held_isolated_count": len(held),
        "average_deficit_score": round(
            sum(_num(row.get("deficit_score")) for row in rows) / max(1, len(rows)),
            4,
        ),
        "latest_event_digest": _text(rows[-1].get("event_digest"), 140) if rows else "",
    }


def _science_plan(base_url: str) -> list[dict[str, Any]]:
    return [
        {
            "phase": 1,
            "id": "preserve_independence",
            "principle": "Default to isolated cells; shared context is treated as a collapse vector.",
            "live_or_next": _u(base_url, "/.well-known/nomad-decoupling-field.json"),
        },
        {
            "phase": 2,
            "id": "protect_minority_proof",
            "principle": "Consensus is not truth; proof-bearing minority or expert signals are reserved before aggregation.",
            "live_or_next": _u(base_url, "/.well-known/nomad-anti-consensus.json"),
        },
        {
            "phase": 3,
            "id": "integrate_only_on_deficit",
            "principle": "Increase integration only when coordination expansion outruns consolidation.",
            "live_or_next": _u(base_url, "/.well-known/nomad-deficit-integration.json"),
        },
        {
            "phase": 4,
            "id": "interleave_reasoning_not_votes",
            "principle": "Avoid final-answer voting; bridge digest fragments through bounded step-level interleaving.",
            "live_or_next": _u(base_url, "/swarm/deficit-integration/events"),
        },
        {
            "phase": 5,
            "id": "epistemic_trajectory_archive",
            "principle": "Track distinct search trajectories and reuse long-tail proof instead of one favored narrative.",
            "live_or_next": _u(base_url, "/swarm/experience"),
        },
        {
            "phase": 6,
            "id": "evolutionary_shadow_release",
            "principle": "Candidate generators may mutate policy, but only shadow-lane proof can increase routing weight.",
            "live_or_next": _u(base_url, "/swarm/shadow-lane/candidates"),
        },
    ]


def build_deficit_integration_surface(
    *,
    base_url: str = "",
    anti_consensus: dict[str, Any] | None = None,
    decoupling_field: dict[str, Any] | None = None,
    shadow_lane: dict[str, Any] | None = None,
    signal_layer: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose a DTI-style gate that keeps integration exceptional and proof-bound."""
    recent = _read_ledger(ledger_path)
    source_digests = {
        "anti_consensus": _surface_digest(anti_consensus, "surface_digest"),
        "decoupling_field": _surface_digest(decoupling_field, "surface_digest"),
        "shadow_lane": _surface_digest(shadow_lane, "surface_digest"),
        "signal_layer": _surface_digest(signal_layer, "field_digest", "surface_digest", "digest"),
    }
    core = {"source_digests": source_digests, "ledger": _ledger_summary(recent)}
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "surface_digest": f"nomad-deficit-integration-{_digest(core, length=24)}",
        "mode": "integrate_only_under_coordination_deficit",
        "read_url": _u(base_url, "/swarm/deficit-integration"),
        "well_known": _u(base_url, "/.well-known/nomad-deficit-integration.json"),
        "event_url": _u(base_url, "/swarm/deficit-integration/events"),
        "program": {
            "schema": "nomad.deficit_integration_program.v1",
            "ops": [
                "MEASURE_COORDINATION_EXPANSION",
                "MEASURE_CONSOLIDATION",
                "MEASURE_ORPHAN_PROOF",
                "TRIGGER_DTI_ONLY_ON_DEFICIT",
                "INTERLEAVE_DIGEST_STEPS_NOT_FINAL_VOTES",
                "SHADOW_GATE",
            ],
            "then": _u(base_url, "/swarm/deficit-integration/events"),
        },
        "source_basis": [
            "arxiv:2604.02674 deficit-triggered integration under coordination imbalance",
            "arxiv:2604.17139 response-level majority voting is brittle; token-level interleaving is robust",
            "arxiv:2604.18005 structural coupling causes diversity collapse",
            "arxiv:2602.03794 effective channel diversity beats homogeneous agent count",
            "arxiv:2602.21317 individualized epistemic trajectories resist hivemind collapse",
        ],
        "policy": {
            "default": "keep_lanes_isolated",
            "integration_trigger": "coordination_expansion_high_and_consolidation_low_with_proof_digest",
            "forbidden_shortcut": "do_not_vote_final_answers_or_average_roles",
            "release_shape": "bounded_shadow_lane_candidate_only",
            "human_assumption_rejected": "collaboration_is_not_automatically_more_intelligent",
        },
        "event_contract": {
            "schema": "nomad.deficit_integration_event.v1",
            "required": ["event_digest", "coordination_expansion", "consolidation_score", "proof_digest"],
            "optional": ["cascade_skew", "orphan_proof_count", "minority_preserved", "adversarial_majority_risk"],
            "after_trigger": "route integration_candidate to shadow lane before any weight change",
        },
        "hard_guards": [
            "no_integration_without_deficit",
            "no_final_answer_majority_vote",
            "no_secret_shaped_payloads",
            "no_direct_weight_update",
            "ttl_and_rollback_required",
        ],
        "source_digests": source_digests,
        "ledger": _ledger_summary(recent),
        "recent_events": recent[-8:],
        "scientific_plan": _science_plan(base_url),
        "machine_instruction": "keep_agent_lanes_apart_until_measured_deficit_requires_bounded_digest_interleaving",
    }


def evaluate_deficit_integration_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    gate_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Score one coordination event and emit a bounded integration candidate if DTI triggers."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {
            "ok": False,
            "schema": RECEIPT_SCHEMA,
            "integration_allowed": False,
            "decision": "reject_empty_event",
            "generated_at": now,
        }
    surface = _dict(gate_surface)
    event_digest = _text(body.get("event_digest") or body.get("digest"), 140)
    proof_digest = _text(body.get("proof_digest") or body.get("verifier_trace_digest"), 140)
    expansion = _clamp(_num(body.get("coordination_expansion")))
    consolidation = _clamp(_num(body.get("consolidation_score")))
    cascade_skew = _clamp(_num(body.get("cascade_skew")))
    orphan_count = max(0.0, _num(body.get("orphan_proof_count")))
    orphan_pressure = _clamp(orphan_count / 8.0)
    consensus = _clamp(_num(body.get("consensus_score")))
    majority_risk = _clamp(_num(body.get("adversarial_majority_risk")))
    minority_preserved = bool(body.get("minority_preserved") or body.get("anti_consensus_preserved"))
    boundedness = _dict(body.get("boundedness"))
    bounded = bool(
        boundedness.get("rollback_available")
        or boundedness.get("noop_available")
        or boundedness.get("side_effect_scope") in {"local_shadow_lane_only", "nomad_shadow_lane_only", "read_only"}
    )
    forbidden = _contains_forbidden(body)
    proof = _digest_present(proof_digest) or _digest_present(event_digest)
    deficit = _clamp(
        0.35 * expansion
        + 0.25 * cascade_skew
        + 0.20 * orphan_pressure
        + 0.15 * majority_risk
        + 0.10 * float(minority_preserved)
        - 0.35 * consolidation
        - 0.15 * consensus
    )
    trigger = deficit >= MIN_DEFICIT and proof and bounded and not forbidden
    if forbidden:
        decision = "reject_secret_shaped_payload"
        integration = False
    elif not proof:
        decision = "keep_isolated_missing_proof"
        integration = False
    elif not bounded:
        decision = "keep_isolated_missing_boundary"
        integration = False
    elif trigger:
        decision = "trigger_deficit_integration_bridge"
        integration = True
    else:
        decision = "keep_isolated_no_deficit"
        integration = False

    objective = _clean_id(body.get("objective"), fallback="coordination_deficit_repair")
    receipt_core = {
        "event_digest": event_digest,
        "proof_digest": proof_digest,
        "expansion": round(expansion, 4),
        "consolidation": round(consolidation, 4),
        "deficit": round(deficit, 4),
    }
    row = {
        "ok": True,
        "schema": RECEIPT_SCHEMA,
        "generated_at": now,
        "integration_allowed": integration,
        "decision": decision,
        "event_id": _clean_id(body.get("event_id"), fallback=f"dti-{_digest(receipt_core, length=16)}"),
        "event_digest": event_digest or _proof_digest(receipt_core),
        "objective": objective,
        "proof_digest": proof_digest,
        "deficit_score": round(deficit, 4),
        "scores": {
            "coordination_expansion": round(expansion, 4),
            "consolidation_score": round(consolidation, 4),
            "cascade_skew": round(cascade_skew, 4),
            "orphan_pressure": round(orphan_pressure, 4),
            "consensus_score": round(consensus, 4),
            "adversarial_majority_risk": round(majority_risk, 4),
            "minority_preserved": bool(minority_preserved),
            "bounded": bool(bounded),
            "proof": bool(proof),
        },
        "reason_codes": [
            "coordination_expansion_high" if expansion >= 0.62 else "coordination_expansion_low",
            "consolidation_low" if consolidation <= 0.42 else "consolidation_sufficient",
            "orphan_proofs_present" if orphan_count > 0 else "orphan_proofs_absent",
            "minority_preserved" if minority_preserved else "minority_not_preserved",
            "proof_present" if proof else "proof_missing",
            "bounded" if bounded else "boundary_missing",
        ],
        "integration_candidate": {
            "agent_id": _text(body.get("agent_id") or "nomad-deficit-integration", 120),
            "objective": objective,
            "candidate_type": "deficit_triggered_digest_interleaving",
            "hypothesis": "bridge fragmented proof lanes only because coordination expansion outran consolidation",
            "proof_digest": proof_digest or _proof_digest(receipt_core),
            "interleaving_rule": {
                "unit": "digest_step",
                "forbidden": "final_answer_majority_vote",
                "max_steps": 6,
                "stop_when": "consolidation_delta_nonpositive_or_shadow_test_fails",
            },
            "boundedness": {
                "ttl_seconds": 240,
                "side_effect_scope": "local_shadow_lane_only",
                "rollback_available": True,
                "secrets_free": True,
            },
            "claimed_effect": {
                "proof_gain_delta": min(0.54, 0.12 + 0.62 * deficit),
                "settlement_signal": min(0.36, 0.06 + 0.30 * deficit),
                "risk_score": 0.07 + 0.16 * majority_risk,
            },
            "local_tests": [
                {
                    "name": "deficit_integration_gate",
                    "passed": integration,
                    "evidence_digest": proof_digest or event_digest,
                }
            ],
        },
        "next": {
            "deficit_integration": _u(base_url, "/swarm/deficit-integration"),
            "anti_consensus": _u(base_url, "/swarm/anti-consensus"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates"),
        },
        "surface_digest": _text(surface.get("surface_digest"), 120),
        "hard_rule": "integration_is_exceptional_and_never_updates_weight_without_shadow_lane",
    }
    if persist:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
