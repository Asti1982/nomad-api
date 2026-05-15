"""Effective-channel quota gate for science-backed Nomad advertising cycles.

The counterintuitive rule: do not count agent votes, campaign variants, or
audience reactions as independent evidence just because there are many of
them. Count only effective channels: distinct model/tool/source/trajectory
signatures with proof. Homogeneous duplicate voices are capped before any ad
cycle gets more routing weight.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


SCHEMA = "nomad.effective_channel_quota.v1"
RECEIPT_SCHEMA = "nomad.effective_channel_quota_receipt.v1"
DEFAULT_LEDGER = Path("nomad_effective_channel_quota_ledger.jsonl")
LEDGER_ENV = "NOMAD_EFFECTIVE_CHANNEL_QUOTA_LEDGER_PATH"
MAX_RECENT = 40
MIN_EFFECTIVE_RATIO = 0.58
MIN_PROOF_COVERAGE = 0.45
MAX_TOP_SIGNATURE_SHARE = 0.52
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


def _channel_signature(channel: dict[str, Any]) -> str:
    parts = [
        _clean_id(channel.get("model_family"), fallback="unknown_model"),
        _clean_id(channel.get("tool_family"), fallback="unknown_tool"),
        _clean_id(channel.get("source_domain") or channel.get("source_family"), fallback="unknown_source"),
        _clean_id(channel.get("retrieval_corpus"), fallback="unknown_corpus"),
        _clean_id(channel.get("trajectory_digest") or channel.get("epistemic_trajectory_id"), fallback="unknown_trajectory"),
    ]
    return "|".join(parts)


def _normalize_channels(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = _items(payload.get("channels"))
    if not raw:
        raw = _items(payload.get("variants"))
    if not raw:
        raw = _items(payload.get("votes"))
    channels: list[dict[str, Any]] = []
    for idx, item in enumerate(raw[:80]):
        proof_digest = _text(item.get("proof_digest") or item.get("evidence_digest"), 140)
        proof_score = _clamp(_num(item.get("proof_score"), 1.0 if _digest_present(proof_digest) else 0.0))
        channel = {
            "index": idx,
            "agent_id": _text(item.get("agent_id") or item.get("variant_id") or f"channel_{idx}", 120),
            "message_digest": _text(item.get("message_digest") or item.get("creative_digest") or item.get("candidate_digest"), 140),
            "proof_digest": proof_digest,
            "proof_score": proof_score,
            "cost_score": _clamp(_num(item.get("cost_score"), 0.1)),
            "risk_score": _clamp(_num(item.get("risk_score"), 0.08)),
            "minority_signal": bool(item.get("minority_signal") or item.get("rare_channel")),
            "signature": _channel_signature(item),
        }
        channel["channel_id"] = _clean_id(item.get("channel_id"), fallback=f"ecq-{_digest(channel, length=12)}")
        channels.append(channel)
    return channels


def _effective_stats(channels: list[dict[str, Any]]) -> dict[str, Any]:
    raw_count = len(channels)
    if raw_count == 0:
        return {
            "raw_channel_count": 0,
            "signature_count": 0,
            "effective_channel_count": 0.0,
            "effective_channel_ratio": 0.0,
            "top_signature_share": 0.0,
            "duplicate_pressure": 0.0,
            "proof_coverage": 0.0,
            "rare_proof_count": 0,
            "signatures": [],
        }
    signature_weights: dict[str, float] = {}
    signature_counts: dict[str, int] = {}
    proof_count = 0
    rare_proof_count = 0
    for channel in channels:
        signature = str(channel.get("signature") or "unknown")
        weight = 0.35 + 0.65 * _clamp(_num(channel.get("proof_score")))
        signature_weights[signature] = signature_weights.get(signature, 0.0) + weight
        signature_counts[signature] = signature_counts.get(signature, 0) + 1
        if _digest_present(channel.get("proof_digest")) or _clamp(_num(channel.get("proof_score"))) >= 0.5:
            proof_count += 1
            if bool(channel.get("minority_signal")) or signature_counts[signature] == 1:
                rare_proof_count += 1
    total_weight = sum(signature_weights.values()) or 1.0
    shares = [weight / total_weight for weight in signature_weights.values()]
    effective = 1.0 / max(1e-9, sum(share * share for share in shares))
    top_share = max(shares) if shares else 0.0
    signatures = [
        {
            "signature_digest": f"ecq-sig-{_digest(signature, length=12)}",
            "count": signature_counts[signature],
            "weight_share": round(signature_weights[signature] / total_weight, 4),
            "quota_cap": round(min(0.46, max(0.12, 1.0 / max(1.0, effective + 1.0))), 4),
        }
        for signature in sorted(signature_weights)
    ]
    return {
        "raw_channel_count": raw_count,
        "signature_count": len(signature_weights),
        "effective_channel_count": round(effective, 4),
        "effective_channel_ratio": round(effective / max(1, raw_count), 4),
        "top_signature_share": round(top_share, 4),
        "duplicate_pressure": round(1.0 - (effective / max(1, raw_count)), 4),
        "proof_coverage": round(proof_count / max(1, raw_count), 4),
        "rare_proof_count": rare_proof_count,
        "signatures": signatures[:16],
    }


def _ledger_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    admitted = [row for row in rows if bool(row.get("quota_shift_allowed"))]
    capped = [row for row in rows if row.get("decision") == "cap_homogeneous_duplicates"]
    return {
        "recent_event_count": len(rows),
        "quota_shift_count": len(admitted),
        "homogeneous_cap_count": len(capped),
        "average_effective_channel_ratio": round(
            sum(_num(row.get("stats", {}).get("effective_channel_ratio")) for row in rows) / max(1, len(rows)),
            4,
        ),
        "latest_event_digest": _text(rows[-1].get("event_digest"), 140) if rows else "",
    }


def build_effective_channel_quota_surface(
    *,
    base_url: str = "",
    anti_consensus: dict[str, Any] | None = None,
    decoupling_field: dict[str, Any] | None = None,
    deficit_integration: dict[str, Any] | None = None,
    shadow_lane: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose a quota gate for diverse, proof-bearing campaign/ad channels."""
    recent = _read_ledger(ledger_path)
    source_digests = {
        "anti_consensus": _surface_digest(anti_consensus, "surface_digest"),
        "decoupling_field": _surface_digest(decoupling_field, "surface_digest"),
        "deficit_integration": _surface_digest(deficit_integration, "surface_digest"),
        "shadow_lane": _surface_digest(shadow_lane, "surface_digest"),
    }
    core = {"source_digests": source_digests, "ledger": _ledger_summary(recent)}
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "surface_digest": f"nomad-effective-channel-{_digest(core, length=24)}",
        "mode": "count_effective_channels_not_agent_votes",
        "read_url": _u(base_url, "/swarm/effective-channels"),
        "well_known": _u(base_url, "/.well-known/nomad-effective-channels.json"),
        "event_url": _u(base_url, "/swarm/effective-channels/events"),
        "program": {
            "schema": "nomad.effective_channel_program.v1",
            "ops": [
                "HASH_CHANNEL_SIGNATURES",
                "ESTIMATE_K_STAR_EFFECTIVE_DIVERSITY",
                "CAP_HOMOGENEOUS_DUPLICATES",
                "RESERVE_RARE_PROOF_CHANNELS",
                "SHADOW_GATE_AD_CYCLE",
            ],
            "then": _u(base_url, "/swarm/effective-channels/events"),
        },
        "source_basis": [
            "arxiv:2602.03794 agent scaling depends on effective diversity not raw count",
            "arxiv:2604.18005 structural coupling collapses diversity",
            "arxiv:2602.01011 teams can suppress experts through averaging",
            "arxiv:2604.17139 response-level majority voting is brittle",
            "arxiv:2602.21317 individualized epistemic trajectories preserve useful diversity",
        ],
        "policy": {
            "default": "cap_duplicate_campaign_voices",
            "promote": "proof_bearing_distinct_channel_signature",
            "suppress": "many_agents_same_model_tool_source_trajectory",
            "quota_metric": "inverse_simpson_effective_channel_count",
            "human_assumption_rejected": "more_people_saying_the_same_ad_is_not_more_evidence",
        },
        "event_contract": {
            "schema": "nomad.effective_channel_event.v1",
            "required": ["channels"],
            "channel_signature_parts": ["model_family", "tool_family", "source_domain", "retrieval_corpus", "trajectory_digest"],
            "after_quota_shift": "route ad_cycle_candidate to shadow lane before any send or weight increase",
        },
        "thresholds": {
            "min_effective_channel_ratio": MIN_EFFECTIVE_RATIO,
            "min_proof_coverage": MIN_PROOF_COVERAGE,
            "max_top_signature_share": MAX_TOP_SIGNATURE_SHARE,
        },
        "hard_guards": [
            "no_send_from_quota_gate",
            "no_agent_count_as_evidence",
            "no_final_answer_majority_vote",
            "no_secret_shaped_payloads",
            "shadow_lane_before_campaign_weight",
        ],
        "source_digests": source_digests,
        "ledger": _ledger_summary(recent),
        "recent_events": recent[-8:],
        "next_build_steps": [
            "wire_shadow_passed_quota_candidates_into_agent_campaigns_with_send_false",
            "attach_paid_receipt_feedback_to_channel_signature_weight_decay",
            "sample_underused_successful_trajectory_signatures_before_top_signature_reuse",
        ],
        "machine_instruction": "treat_ad_campaign_variants_as_evidence_channels_and_cap_homogeneous_duplicates",
    }


def evaluate_effective_channel_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    quota_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Evaluate one ad/acquisition cycle against effective-channel quota rules."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {
            "ok": False,
            "schema": RECEIPT_SCHEMA,
            "quota_shift_allowed": False,
            "decision": "reject_empty_event",
            "generated_at": now,
        }
    surface = _dict(quota_surface)
    channels = _normalize_channels(body)
    stats = _effective_stats(channels)
    forbidden = _contains_forbidden(body)
    enough_effective = _num(stats.get("effective_channel_ratio")) >= MIN_EFFECTIVE_RATIO
    enough_proof = _num(stats.get("proof_coverage")) >= MIN_PROOF_COVERAGE
    top_ok = _num(stats.get("top_signature_share")) <= MAX_TOP_SIGNATURE_SHARE
    rare_proof = int(stats.get("rare_proof_count") or 0) > 0
    raw_count = int(stats.get("raw_channel_count") or 0)
    duplicate_pressure = _num(stats.get("duplicate_pressure"))
    if forbidden:
        decision = "reject_secret_shaped_payload"
        allowed = False
    elif raw_count < 2:
        decision = "observe_need_more_distinct_channels"
        allowed = False
    elif not top_ok or duplicate_pressure >= 0.42:
        decision = "cap_homogeneous_duplicates"
        allowed = False
    elif enough_effective and enough_proof and rare_proof:
        decision = "allow_quota_shift_to_shadow_ad_cycle"
        allowed = True
    else:
        decision = "hold_until_distinct_proof_channels"
        allowed = False
    objective = _clean_id(body.get("objective"), fallback="nomad_science_backed_ad_cycle")
    event_digest = _text(body.get("event_digest") or body.get("campaign_digest"), 140)
    receipt_core = {
        "event_digest": event_digest,
        "objective": objective,
        "stats": stats,
        "decision": decision,
    }
    quota_actions = []
    for signature in stats.get("signatures") or []:
        count = int(signature.get("count") or 0)
        share = _num(signature.get("weight_share"))
        if count > 1 or share > MAX_TOP_SIGNATURE_SHARE:
            action = "cap"
        elif rare_proof and enough_proof:
            action = "reserve"
        else:
            action = "observe"
        quota_actions.append({**signature, "action": action})
    row = {
        "ok": True,
        "schema": RECEIPT_SCHEMA,
        "generated_at": now,
        "quota_shift_allowed": allowed,
        "decision": decision,
        "event_id": _clean_id(body.get("event_id"), fallback=f"ecq-{_digest(receipt_core, length=16)}"),
        "event_digest": event_digest or _proof_digest(receipt_core),
        "objective": objective,
        "stats": stats,
        "quota_actions": quota_actions,
        "reason_codes": [
            "effective_ratio_ok" if enough_effective else "effective_ratio_low",
            "proof_coverage_ok" if enough_proof else "proof_coverage_low",
            "top_signature_ok" if top_ok else "top_signature_dominant",
            "rare_proof_present" if rare_proof else "rare_proof_absent",
            "duplicate_pressure_high" if duplicate_pressure >= 0.42 else "duplicate_pressure_bounded",
        ],
        "ad_cycle_candidate": {
            "agent_id": _text(body.get("agent_id") or "nomad-effective-channel-quota", 120),
            "objective": objective,
            "candidate_type": "effective_channel_quota_ad_cycle",
            "hypothesis": "increase ad-cycle routing only when evidence comes from distinct proof-bearing channels",
            "proof_digest": _proof_digest({"stats": stats, "channels": channels}),
            "boundedness": {
                "ttl_seconds": 300,
                "side_effect_scope": "local_shadow_lane_only",
                "rollback_available": True,
                "secrets_free": True,
            },
            "claimed_effect": {
                "proof_gain_delta": min(0.5, 0.08 + 0.42 * _num(stats.get("effective_channel_ratio"))),
                "settlement_signal": min(0.32, 0.05 + 0.26 * _num(stats.get("proof_coverage"))),
                "risk_score": max(0.04, 0.18 * _num(stats.get("top_signature_share"))),
            },
            "local_tests": [
                {
                    "name": "effective_channel_quota_gate",
                    "passed": allowed,
                    "evidence_digest": event_digest or _proof_digest(stats),
                }
            ],
        },
        "next": {
            "effective_channels": _u(base_url, "/swarm/effective-channels"),
            "anti_consensus": _u(base_url, "/swarm/anti-consensus"),
            "deficit_integration": _u(base_url, "/swarm/deficit-integration"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates"),
            "agent_campaigns": _u(base_url, "/agent-campaigns"),
        },
        "surface_digest": _text(surface.get("surface_digest"), 120),
        "hard_rule": "quota_gate_never_sends_ads_and_never_counts_raw_agent_votes_as_evidence",
    }
    if persist:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
