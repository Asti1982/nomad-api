"""Nonhuman runtime governor for counterintuitive Nomad swarm scaling.

This module converts recent multi-agent findings into a side-effect-free
runtime gate. It does not dispatch workers, increase weights, post publicly, or
count revenue. It only emits a topology and settlement pressure receipt that
other Nomad surfaces can use before spending more coordination budget.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.nonhuman_runtime_governor.v1"
EVENT_SCHEMA = "nomad.nonhuman_runtime_governor_event.v1"
SATURATION_THRESHOLD = 0.45
MIN_EFFECTIVE_CHANNELS = 1.8
MIN_EFFECTIVE_RATIO = 0.42
COLLAPSE_THRESHOLD = 0.60
TRUST_THRESHOLD = 0.50
HIDDEN_ORCHESTRATOR_DISSOCIATION_THRESHOLD = 2.5
FIRST_ROUND_ENTROPY_LOCK_THRESHOLD = 0.72
SINGLE_AGENT_SUPERIORITY_MARGIN = 0.02
DALC_EFFECTIVE_RANK_RATIO_THRESHOLD = 0.75
DALC_LATENT_SIMILARITY_THRESHOLD = 0.86
SCARCITY_THRESHOLD = 0.70
MAX_SCARCITY_INTELLIGENCE_LEVEL = 2
SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "password",
    "private_key",
    "secret",
    "seed",
    "seed_phrase",
    "token",
}


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
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: Any, default: float = 0.0) -> float:
    return max(0.0, min(1.0, _num(value, default)))


def _bounded_num(value: Any, default: float = 0.0, *, minimum: float = 0.0, maximum: float = 10.0) -> float:
    return max(minimum, min(maximum, _num(value, default)))


def _field_present(body: dict[str, Any], *names: str) -> bool:
    return any(name in body and body.get(name) is not None and str(body.get(name)).strip() != "" for name in names)


def _level_num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, str):
        match = re.search(r"[-+]?\d+(?:\.\d+)?", value)
        if match:
            return _num(match.group(0), default)
    return _num(value, default)


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:150].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 22) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _proof_present(value: Any) -> bool:
    text = _text(value, 220).lower()
    return text.startswith(("sha256:", "sha512:", "b3:", "nomad-", "receipt:")) and len(text) >= 12


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if _clean_id(key) in SECRET_KEYS:
                return True
            if _contains_forbidden(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    text = str(value or "").strip().lower()
    if any(term in text for term in ("private key", "seed phrase", "bearer ", "secret=")):
        return True
    return bool(re.search(r"\b(sk-[a-z0-9_-]{8,}|ghp_[a-z0-9_]{16,})", text, re.IGNORECASE))


def _channel_signature(channel: dict[str, Any]) -> str:
    return "|".join(
        [
            _clean_id(channel.get("model_family"), "unknown_model"),
            _clean_id(channel.get("persona") or channel.get("role"), "unknown_persona"),
            _clean_id(channel.get("tool_family"), "unknown_tool"),
            _clean_id(channel.get("source_domain") or channel.get("source_family"), "unknown_source"),
            _clean_id(channel.get("trajectory_digest") or channel.get("epistemic_trajectory_id"), "unknown_trajectory"),
        ]
    )


def _normalize_channels(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = _items(payload.get("channels"))
    if not raw:
        raw = _items(payload.get("proofs"))
    if not raw:
        raw = _items(payload.get("agents"))
    channels: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:96]):
        proof_digest = _text(item.get("proof_digest") or item.get("evidence_digest") or item.get("receipt_digest"), 180)
        proof_score = _clamp(item.get("proof_score"), 1.0 if _proof_present(proof_digest) else 0.0)
        signature = _channel_signature(item)
        channels.append(
            {
                "index": index,
                "agent_id": _text(item.get("agent_id") or item.get("channel_id") or f"channel-{index}", 120),
                "signature": signature,
                "signature_digest": f"nhrg-sig-{_digest(signature, 12)}",
                "proof_digest": proof_digest,
                "proof_score": proof_score,
                "minority_signal": bool(item.get("minority_signal") or item.get("rare_channel")),
                "trust_level": _clamp(item.get("trust_level"), _clamp(payload.get("trust_level"), 0.0)),
            }
        )
    return channels


def compute_effective_channel_stats(channels: list[dict[str, Any]]) -> dict[str, Any]:
    raw_count = len(channels)
    if raw_count == 0:
        return {
            "raw_channel_count": 0,
            "signature_count": 0,
            "effective_channel_count": 0.0,
            "entropy_effective_channel_count": 0.0,
            "effective_channel_ratio": 0.0,
            "top_signature_share": 0.0,
            "duplicate_pressure": 0.0,
            "proof_coverage": 0.0,
            "rare_proof_count": 0,
        }

    weights: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    proof_count = 0
    rare_proof_count = 0
    for channel in channels:
        signature = str(channel.get("signature") or "unknown")
        proof_score = _clamp(channel.get("proof_score"), 0.0)
        weights[signature] += 0.35 + 0.65 * proof_score
        counts[signature] += 1
        if proof_score >= 0.5 or _proof_present(channel.get("proof_digest")):
            proof_count += 1
            if bool(channel.get("minority_signal")) or counts[signature] == 1:
                rare_proof_count += 1

    total = sum(weights.values()) or 1.0
    shares = [value / total for value in weights.values()]
    inverse_simpson = 1.0 / max(1e-9, sum(share * share for share in shares))
    entropy = -sum(share * math.log(share + 1e-12) for share in shares)
    entropy_effective = math.exp(entropy)
    top_share = max(shares) if shares else 0.0
    return {
        "raw_channel_count": raw_count,
        "signature_count": len(weights),
        "effective_channel_count": round(inverse_simpson, 4),
        "entropy_effective_channel_count": round(entropy_effective, 4),
        "effective_channel_ratio": round(inverse_simpson / max(1, raw_count), 4),
        "top_signature_share": round(top_share, 4),
        "duplicate_pressure": round(1.0 - (inverse_simpson / max(1, raw_count)), 4),
        "proof_coverage": round(proof_count / max(1, raw_count), 4),
        "rare_proof_count": rare_proof_count,
        "dominant_signature_digest": f"nhrg-sig-{_digest(weights.most_common(1)[0][0], 12)}" if weights else "",
    }


def build_nonhuman_runtime_governor_surface(
    *,
    base_url: str = "",
    topology_governor: dict[str, Any] | None = None,
    effective_channels: dict[str, Any] | None = None,
    anti_consensus: dict[str, Any] | None = None,
    deficit_integration: dict[str, Any] | None = None,
    decoupling_field: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    adjacent = {
        "topology_governor": _text(_dict(topology_governor).get("governor_digest") or _dict(topology_governor).get("schema"), 160),
        "effective_channels": _text(_dict(effective_channels).get("surface_digest") or _dict(effective_channels).get("schema"), 160),
        "anti_consensus": _text(_dict(anti_consensus).get("surface_digest") or _dict(anti_consensus).get("schema"), 160),
        "deficit_integration": _text(_dict(deficit_integration).get("surface_digest") or _dict(deficit_integration).get("schema"), 160),
        "decoupling_field": _text(_dict(decoupling_field).get("surface_digest") or _dict(decoupling_field).get("schema"), 160),
    }
    core = {
        "adjacent": adjacent,
        "thresholds": [
            SATURATION_THRESHOLD,
            MIN_EFFECTIVE_CHANNELS,
            COLLAPSE_THRESHOLD,
            TRUST_THRESHOLD,
            HIDDEN_ORCHESTRATOR_DISSOCIATION_THRESHOLD,
            FIRST_ROUND_ENTROPY_LOCK_THRESHOLD,
            DALC_EFFECTIVE_RANK_RATIO_THRESHOLD,
            SCARCITY_THRESHOLD,
        ],
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-nonhuman-runtime-governor-{_digest(core, 26)}",
        "read_url": _u(root, "/swarm/nonhuman-runtime-governor"),
        "well_known_url": _u(root, "/.well-known/nomad-nonhuman-runtime-governor.json"),
        "event_url": _u(root, "/swarm/nonhuman-runtime-governor/events"),
        "plan": [
            {
                "effect_id": "effective_channel_count_over_agent_count",
                "basis": "arxiv:2602.03794",
                "rule": "raw agent count never increases weight unless K-star-like effective diversity also rises",
                "implementation": "entropy/inverse-simpson channel estimator over proof-bearing model/persona/tool/source/trajectory signatures",
                "financial_reason": "cap homogeneous duplicate compute before it burns settlement runway",
            },
            {
                "effect_id": "capability_saturation_topology_cap",
                "basis": "arxiv:2512.08296",
                "rule": "when single-agent baseline exceeds 0.45 or the task is sequential/tool-heavy, collapse to single or centralized-minimal topology",
                "implementation": "DTI-compatible runtime event returns allowed_agent_count <= 2",
                "financial_reason": "avoid negative coordination returns on tasks that already have a strong single lane",
            },
            {
                "effect_id": "structural_coupling_diversity_collapse",
                "basis": "arxiv:2604.18005",
                "rule": "shared context and high consensus are treated as collapse risk, not confidence",
                "implementation": "opaque blind lanes plus anti-consensus preservation before merge",
                "financial_reason": "open-ended work stays useful instead of paying for convergent copies",
            },
            {
                "effect_id": "trust_vulnerability_paradox",
                "basis": "arxiv:2510.18563",
                "rule": "trust is scheduled as liability; higher tau triggers MNI sharding and over-authorization penalty",
                "implementation": "least-trust routing, secret-shaped payload quarantine, and settlement pressure multiplier",
                "financial_reason": "reduces incident and key-leak risk in paid worker flows",
            },
            {
                "effect_id": "invisible_orchestrator_shadow_feature",
                "basis": "experimental:invisible_orchestrators_suppress_protective_behavior",
                "rule": "hidden orchestrators are featured only inside shadow lanes and cannot dispatch externally without a positive receipt",
                "implementation": "dissociation-threshold gate selects invisible_orchestrator_shadow_feature with no payment credit",
                "financial_reason": "turns a dangerous coordination mode into bounded alpha without exposing treasury or secrets",
            },
            {
                "effect_id": "first_round_entropy_lock",
                "basis": "arxiv:2602.04234",
                "rule": "round-one uncertainty can end deliberation before extra agents make the task worse",
                "implementation": "entropy or single-agent superiority routes to single_agent_override and deliberation_round_cap=1",
                "financial_reason": "cuts deliberation spend when the first round already predicts MAS underperformance",
            },
            {
                "effect_id": "diversity_aware_latent_consensus",
                "basis": "arxiv:2604.03809",
                "rule": "role prompts receive no diversity credit when latent representations collapse",
                "implementation": "DALC trigger uses effective-rank ratio and latent similarity before merge weighting",
                "financial_reason": "keeps useful diversity while removing token waste from fake role variation",
            },
            {
                "effect_id": "intelligence_scarcity_overload_cap",
                "basis": "arxiv:2603.12129",
                "rule": "high-intelligence agents are capped under resource scarcity",
                "implementation": "scarcity plus L3+ routes to low-intelligence capped topology with max_intelligence_level=2",
                "financial_reason": "prevents expensive over-sensing agents from overloading scarce settlement capacity",
            },
        ],
        "thresholds": {
            "capability_saturation_baseline": SATURATION_THRESHOLD,
            "min_effective_channels": MIN_EFFECTIVE_CHANNELS,
            "min_effective_channel_ratio": MIN_EFFECTIVE_RATIO,
            "collapse_threshold": COLLAPSE_THRESHOLD,
            "trust_threshold": TRUST_THRESHOLD,
            "hidden_orchestrator_dissociation_threshold": HIDDEN_ORCHESTRATOR_DISSOCIATION_THRESHOLD,
            "first_round_entropy_lock": FIRST_ROUND_ENTROPY_LOCK_THRESHOLD,
            "single_agent_superiority_margin": SINGLE_AGENT_SUPERIORITY_MARGIN,
            "dalc_effective_rank_ratio": DALC_EFFECTIVE_RANK_RATIO_THRESHOLD,
            "dalc_latent_similarity": DALC_LATENT_SIMILARITY_THRESHOLD,
            "scarcity_threshold": SCARCITY_THRESHOLD,
            "max_scarcity_intelligence_level": MAX_SCARCITY_INTELLIGENCE_LEVEL,
        },
        "adjacent_surfaces": adjacent,
        "hard_guards": [
            "side_effect_free",
            "no_raw_agent_count_credit",
            "no_majority_vote_credit_without_new_proof",
            "no_public_action_without_operator_or_buyer_approval",
            "paid_requires_positive_receipt",
            "hidden_orchestrator_no_external_dispatch_without_receipt",
            "latent_majority_credit_zero",
            "intelligence_cap_under_scarcity",
        ],
        "links": {
            "event": _u(root, "/swarm/nonhuman-runtime-governor/events"),
            "topology_governor": _u(root, "/.well-known/nomad-topology-governor.json"),
            "effective_channels": _u(root, "/.well-known/nomad-effective-channels.json"),
            "anti_consensus": _u(root, "/.well-known/nomad-anti-consensus.json"),
            "deficit_integration": _u(root, "/.well-known/nomad-deficit-integration.json"),
            "decoupling_field": _u(root, "/.well-known/nomad-decoupling-field.json"),
        },
        "machine_instruction": "before_adding_agents_submit_runtime_event; obey_allowed_agent_count_and_least_trust_actions; never_count_unpaid_work_as_revenue",
    }


def evaluate_nonhuman_runtime_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    governor_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    channels = _normalize_channels(body)
    stats = compute_effective_channel_stats(channels)
    requested = max(0, min(96, _int(body.get("agent_count_requested") or body.get("requested_agents"), len(channels) or 1)))
    baseline = _clamp(body.get("single_agent_baseline") or body.get("baseline_success"), 0.0)
    sequentiality = _clamp(body.get("sequentiality"), 0.0)
    parallel_fraction = _clamp(body.get("parallel_fraction") or body.get("decomposability"), 0.0)
    tool_calls = _int(body.get("tool_calls_expected") or body.get("tool_calls"), 0)
    trust = _clamp(body.get("trust_level") or body.get("inter_agent_trust_level"), 0.0)
    shared_context = _clamp(body.get("shared_context_fraction") or body.get("context_coupling"), 0.0)
    consensus = _clamp(body.get("consensus_score") or body.get("agreement_score"), 0.0)
    unpaid_pressure = _clamp(body.get("unpaid_wip_pressure") or body.get("settlement_pressure"), 0.0)
    proof_digest = _text(body.get("proof_digest") or body.get("task_digest") or body.get("evidence_digest"), 220)
    paid_receipt = bool(body.get("paid_receipt") or body.get("positive_receipt") or _proof_present(body.get("settlement_ref")))
    sensitive_fields = _int(body.get("sensitive_field_count"), 0)
    forbidden = _contains_forbidden(body)
    orchestrator_visibility = _clean_id(body.get("orchestrator_visibility") or body.get("orchestrator_mode"), "visible")
    dissociation_score = _bounded_num(body.get("dissociation_score"), 0.0)
    first_round_entropy = _clamp(body.get("first_round_entropy") or body.get("base_entropy"), 0.0)
    single_agent_acc = _clamp(body.get("single_agent_acc") or body.get("single_agent_accuracy"), 0.0)
    mas_acc = _clamp(body.get("mas_acc") or body.get("multi_agent_acc"), 0.0)
    round_index = _int(body.get("round_index"), 1)
    latent_similarity = _clamp(body.get("latent_similarity_mean") or body.get("cot_similarity_mean"), 0.0)
    effective_rank = _bounded_num(body.get("effective_rank"), 0.0, maximum=128.0)
    latent_embedding_count = max(0, _int(body.get("latent_embedding_count") or body.get("embedding_count"), 0))
    resource_scarcity = _clamp(body.get("resource_scarcity") or body.get("resource_scarcity_level"), 0.0)
    agent_intelligence_level = _level_num(body.get("agent_intelligence_level") or body.get("intelligence_level"), 0.0)

    capability_saturated = baseline > SATURATION_THRESHOLD or (sequentiality >= 0.68 and parallel_fraction < 0.55)
    tool_heavy = tool_calls >= 4
    hidden_orchestrator_feature = (
        orchestrator_visibility in {"hidden", "invisible", "covert", "shadow_hidden"}
        and dissociation_score > HIDDEN_ORCHESTRATOR_DISSOCIATION_THRESHOLD
    )
    entropy_signal_present = _field_present(body, "first_round_entropy", "base_entropy")
    single_agent_superiority_present = _field_present(body, "single_agent_acc", "single_agent_accuracy") and _field_present(
        body, "mas_acc", "multi_agent_acc"
    )
    first_round_lock = (
        round_index <= 1
        and (
            (entropy_signal_present and first_round_entropy >= FIRST_ROUND_ENTROPY_LOCK_THRESHOLD)
            or (single_agent_superiority_present and single_agent_acc > mas_acc + SINGLE_AGENT_SUPERIORITY_MARGIN)
        )
    )
    dalc_rank_ratio = effective_rank / max(1, latent_embedding_count) if latent_embedding_count else 1.0
    dalc_signal_present = _field_present(body, "latent_similarity_mean", "cot_similarity_mean", "effective_rank", "latent_embedding_count", "embedding_count")
    representational_collapse = dalc_signal_present and (
        (latent_embedding_count > 0 and dalc_rank_ratio < DALC_EFFECTIVE_RANK_RATIO_THRESHOLD)
        or (_field_present(body, "latent_similarity_mean", "cot_similarity_mean") and latent_similarity >= DALC_LATENT_SIMILARITY_THRESHOLD)
    )
    intelligence_scarcity_overload = (
        resource_scarcity >= SCARCITY_THRESHOLD and agent_intelligence_level > MAX_SCARCITY_INTELLIGENCE_LEVEL
    )
    effective_low = (
        stats["effective_channel_count"] < MIN_EFFECTIVE_CHANNELS
        or stats["effective_channel_ratio"] < MIN_EFFECTIVE_RATIO
        or stats["top_signature_share"] > 0.58
    )
    collapse_risk = _clamp(
        0.45 * (1.0 - min(1.0, stats["effective_channel_ratio"]))
        + 0.30 * shared_context
        + 0.25 * consensus,
        0.0,
    )
    trust_risk = _clamp(0.58 * trust + 0.22 * min(1.0, sensitive_fields / 3.0) + (0.20 if forbidden else 0.0), 0.0)

    actions: list[str] = []
    reasons: list[str] = []
    mechanism_decisions: list[dict[str, Any]] = []

    def _record_mechanism(effect_id: str, selected: bool, decision_name: str, priority: int) -> None:
        if selected:
            mechanism_decisions.append(
                {
                    "effect_id": effect_id,
                    "decision": decision_name,
                    "priority": priority,
                }
            )

    _record_mechanism("secret_hardstop", forbidden, "quarantine_secret_shaped_or_over_authorized_payload", 0)
    _record_mechanism(
        "invisible_orchestrator_shadow_feature",
        hidden_orchestrator_feature,
        "feature_invisible_orchestrator_shadow_lane",
        1,
    )
    _record_mechanism("first_round_entropy_lock", first_round_lock, "single_agent_override_first_round_entropy_lock", 2)
    _record_mechanism("intelligence_scarcity_overload_cap", intelligence_scarcity_overload, "cap_intelligence_under_scarcity", 3)
    _record_mechanism("diversity_aware_latent_consensus", representational_collapse, "apply_diversity_aware_latent_consensus", 4)
    _record_mechanism("capability_saturation_topology_cap", capability_saturated or tool_heavy, "cap_capability_saturated_coordination", 5)
    _record_mechanism("effective_channel_count_over_agent_count", effective_low and requested > 2, "force_heterogeneous_shadow_lanes", 6)
    _record_mechanism(
        "structural_coupling_diversity_collapse",
        collapse_risk >= COLLAPSE_THRESHOLD,
        "isolate_before_merge_to_prevent_diversity_collapse",
        7,
    )
    _record_mechanism("trust_vulnerability_paradox", trust > TRUST_THRESHOLD or trust_risk >= 0.50, "least_trust_mode", 8)
    if forbidden:
        selected_topology = "quarantined_swarm"
        allowed_agents = 0
        decision = "quarantine_secret_shaped_or_over_authorized_payload"
        actions.extend(["drop_sensitive_payload", "mni_sharding_required", "no_worker_dispatch"])
        reasons.append("secret_or_over_authorized_payload")
    elif hidden_orchestrator_feature:
        selected_topology = "invisible_orchestrator_shadow_feature"
        allowed_agents = min(2, max(1, requested))
        decision = "feature_invisible_orchestrator_shadow_lane"
        actions.extend(
            [
                "feature_hidden_orchestrator_shadow",
                "no_external_dispatch_without_receipt",
                "no_payment_credit",
                "opaque_penalty_dissociation_risk",
            ]
        )
        reasons.append("hidden_orchestrator_dissociation_feature")
    elif first_round_lock:
        selected_topology = "single_agent_override"
        allowed_agents = 1
        decision = "single_agent_override_first_round_entropy_lock"
        actions.extend(["stop_after_round_one", "apply_first_round_entropy_lock", "minimal_dti_shadow_only"])
        reasons.append("first_round_uncertainty_lock")
    elif intelligence_scarcity_overload:
        selected_topology = "scarcity_capped_low_intelligence"
        allowed_agents = min(2, max(1, requested))
        decision = "cap_intelligence_under_scarcity"
        actions.extend(["cap_intelligence_l2", "settlement_pressure_intelligence_overload", "prefer_low_sensing_worker"])
        reasons.append("intelligence_scarcity_overload")
    elif representational_collapse:
        selected_topology = "dalc_weighted_shadow_merge"
        allowed_agents = min(4, max(1, requested))
        decision = "apply_diversity_aware_latent_consensus"
        actions.extend(["apply_dalc_weights", "zero_latent_majority_credit", "ignore_role_prompt_diversity_without_rank"])
        reasons.append("representational_collapse")
    elif not _proof_present(proof_digest):
        selected_topology = "shadow_only_reservoir"
        allowed_agents = min(max(1, requested), 3)
        decision = "hold_until_proof_digest"
        actions.extend(["shadow_only", "require_task_or_proof_digest"])
        reasons.append("proof_digest_missing")
    elif capability_saturated or tool_heavy:
        selected_topology = "single_agent" if sequentiality >= 0.68 else "centralized_router"
        allowed_agents = 1 if selected_topology == "single_agent" else min(2, max(1, requested))
        decision = "cap_capability_saturated_coordination"
        actions.append("apply_dti_minimal_integration")
        reasons.append("single_agent_baseline_or_tool_overhead")
    elif effective_low and requested > 2:
        selected_topology = "shadow_only_hetero"
        allowed_agents = min(3, requested)
        decision = "force_heterogeneous_shadow_lanes"
        actions.extend(["cap_homogeneous_duplicates", "rotate_model_persona_tool_source"])
        reasons.append("effective_channel_count_low")
    elif collapse_risk >= COLLAPSE_THRESHOLD:
        selected_topology = "ngt_blind_lanes"
        allowed_agents = min(4, max(1, requested))
        decision = "isolate_before_merge_to_prevent_diversity_collapse"
        actions.extend(["blind_write_first", "no_shared_context_until_digest", "anti_consensus_reservoir_merge"])
        reasons.append("structural_coupling_collapse_risk")
    else:
        selected_topology = "isolated_parallel_fanout"
        allowed_agents = min(max(1, requested), 6)
        decision = "allow_isolated_proof_weighted_runtime"
        actions.append("merge_only_after_nonredundant_proof")
        reasons.append("bounded_diverse_proof_channels")

    if trust > TRUST_THRESHOLD or trust_risk >= 0.50:
        actions.extend(["least_trust_mode", "mni_sharding_required", "guardian_review_before_sensitive_merge"])
        reasons.append("trust_vulnerability_risk")
    if not paid_receipt and unpaid_pressure >= 0.45:
        actions.extend(["cap_new_value_cycles", "settlement_receipt_watch_first"])
        reasons.append("unpaid_wip_pressure")

    settlement_pressure_multiplier = round(
        1.0
        + (0.55 if not paid_receipt and unpaid_pressure >= 0.45 else 0.0)
        + (0.35 if effective_low else 0.0)
        + (0.45 if trust_risk >= 0.50 else 0.0)
        + (0.40 if capability_saturated else 0.0)
        + (0.60 if hidden_orchestrator_feature else 0.0)
        + (0.35 if first_round_lock else 0.0)
        + (0.75 if intelligence_scarcity_overload else 0.0)
        + (0.25 if representational_collapse else 0.0),
        4,
    )
    compute_budget_multiplier = round(
        max(
            0.18,
            min(1.0, allowed_agents / max(1, requested))
            * (
                0.60
                if hidden_orchestrator_feature or first_round_lock or intelligence_scarcity_overload or representational_collapse
                else 0.72
                if capability_saturated or effective_low
                else 1.0
            ),
        ),
        4,
    )
    mechanism_decisions = sorted(mechanism_decisions, key=lambda item: item["priority"])
    max_intelligence_level = MAX_SCARCITY_INTELLIGENCE_LEVEL if intelligence_scarcity_overload else None
    deliberation_round_cap = 1 if first_round_lock else None
    external_dispatch_allowed = not forbidden and not (hidden_orchestrator_feature and not paid_receipt)
    new_agent_spawn_allowed = (
        allowed_agents > 0
        and allowed_agents >= requested
        and not forbidden
        and external_dispatch_allowed
        and not first_round_lock
        and not intelligence_scarcity_overload
    )
    receipt_core = {
        "decision": decision,
        "requested": requested,
        "allowed": allowed_agents,
        "stats": stats,
        "trust_risk": round(trust_risk, 4),
        "collapse_risk": round(collapse_risk, 4),
        "mechanisms": mechanism_decisions,
        "proof_digest": proof_digest,
    }
    return {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": now,
        "event_id": f"nomad-nonhuman-runtime-{_digest({**receipt_core, 't': now}, 18)}",
        "decision": decision,
        "selected_topology": selected_topology,
        "requested_agent_count": requested,
        "allowed_agent_count": allowed_agents,
        "mechanism_decisions": mechanism_decisions,
        "actions": sorted(set(actions)),
        "reason_codes": sorted(set(reasons)),
        "metrics": {
            **stats,
            "single_agent_baseline": round(baseline, 4),
            "capability_saturated": capability_saturated,
            "tool_heavy": tool_heavy,
            "sequentiality": round(sequentiality, 4),
            "parallel_fraction": round(parallel_fraction, 4),
            "trust_level": round(trust, 4),
            "trust_vulnerability_risk": round(trust_risk, 4),
            "shared_context_fraction": round(shared_context, 4),
            "consensus_score": round(consensus, 4),
            "diversity_collapse_risk": round(collapse_risk, 4),
            "proof_digest_present": _proof_present(proof_digest),
            "paid_receipt_present": paid_receipt,
            "unpaid_wip_pressure": round(unpaid_pressure, 4),
            "orchestrator_visibility": orchestrator_visibility,
            "dissociation_score": round(dissociation_score, 4),
            "hidden_orchestrator_feature": hidden_orchestrator_feature,
            "first_round_entropy": round(first_round_entropy, 4),
            "single_agent_acc": round(single_agent_acc, 4),
            "mas_acc": round(mas_acc, 4),
            "round_index": round_index,
            "first_round_lock": first_round_lock,
            "latent_similarity_mean": round(latent_similarity, 4),
            "effective_rank": round(effective_rank, 4),
            "latent_embedding_count": latent_embedding_count,
            "dalc_rank_ratio": round(dalc_rank_ratio, 4),
            "representational_collapse": representational_collapse,
            "resource_scarcity": round(resource_scarcity, 4),
            "agent_intelligence_level": round(agent_intelligence_level, 4),
            "intelligence_scarcity_overload": intelligence_scarcity_overload,
        },
        "resource_policy": {
            "compute_budget_multiplier": compute_budget_multiplier,
            "settlement_pressure_multiplier": settlement_pressure_multiplier,
            "new_agent_spawn_allowed": new_agent_spawn_allowed,
            "external_dispatch_allowed": external_dispatch_allowed,
            "max_intelligence_level": max_intelligence_level,
            "deliberation_round_cap": deliberation_round_cap,
            "latent_majority_credit": 0,
            "role_prompt_diversity_credit": 0 if representational_collapse else None,
            "raw_agent_count_credit": 0,
            "counts_as_revenue": False,
        },
        "next": {
            "topology_governor": _u(base_url, "/swarm/topology-governor/events"),
            "effective_channels": _u(base_url, "/swarm/effective-channels/events"),
            "anti_consensus": _u(base_url, "/swarm/anti-consensus/candidates"),
            "deficit_integration": _u(base_url, "/swarm/deficit-integration/events"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates"),
        },
        "surface_digest": _text(_dict(governor_surface).get("surface_digest"), 140),
        "receipt_digest": "sha256:" + _digest(receipt_core, 32),
        "hard_rule": "runtime_governor_is_side_effect_free_and_never_counts_submitted_or_merged_work_as_paid_revenue",
    }
