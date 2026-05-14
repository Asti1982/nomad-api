"""Delayed-reward channel allocator for Nomad value cycles.

The allocator treats each paid-work channel as a delayed-feedback arm. Pending
claims are censored feedback, not failure and never revenue. The public surface
is deterministic so other agents can reproduce the same route from the same
state instead of following a human preference narrative.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.delayed_channel_bandit.v1"
DEFAULT_USD_PRIOR = {
    "github_oss_bounty_pr": 12.0,
    "issuehunt_funded_oss_issue": 18.0,
    "algora_github_bounty": 24.0,
    "taskbounty_agent_pr_task": 20.0,
    "opire_open_reward_pr": 18.0,
    "superteam_agent_contest": 80.0,
    "hackerone_bug_bounty": 120.0,
    "bugcrowd_bug_bounty": 100.0,
    "intigriti_bug_bounty": 90.0,
    "immunefi_web3_bounty": 240.0,
    "code4rena_competitive_audit": 180.0,
    "sherlock_audit_contest": 160.0,
    "onlydust_open_source_rewards": 35.0,
    "freelance_marketplace_draft_only": 60.0,
    "nomad_internal_worker_market": 6.0,
}
DEFAULT_DELAY_DAYS = {
    "github_oss_bounty_pr": 21.0,
    "issuehunt_funded_oss_issue": 21.0,
    "algora_github_bounty": 14.0,
    "taskbounty_agent_pr_task": 10.0,
    "opire_open_reward_pr": 18.0,
    "superteam_agent_contest": 30.0,
    "hackerone_bug_bounty": 45.0,
    "bugcrowd_bug_bounty": 45.0,
    "intigriti_bug_bounty": 45.0,
    "immunefi_web3_bounty": 60.0,
    "code4rena_competitive_audit": 45.0,
    "sherlock_audit_contest": 45.0,
    "onlydust_open_source_rewards": 35.0,
    "freelance_marketplace_draft_only": 14.0,
    "nomad_internal_worker_market": 7.0,
}
MACHINE_NATIVE_CHANNELS = {"nomad_internal_worker_market"}
SIGNAL_PRIOR = {
    "high_impact": (0.16, 0.0),
    "underreviewed": (0.08, 0.0),
    "validated_repro": (0.20, 0.0),
    "accepted": (0.35, 0.0),
    "payment_receipt": (1.0, 0.0),
    "fresh_head": (0.06, 0.0),
    "live_repro_gap": (0.03, 0.04),
    "blocked_no_receipt": (0.0, 0.45),
    "overreviewed": (0.0, 0.28),
    "noise": (0.0, 0.36),
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _age_days(value: Any) -> float:
    parsed = _parse_time(value)
    if parsed is None:
        return 0.0
    return max(0.0, (datetime.now(UTC) - parsed).total_seconds() / 86400.0)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _text(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _channel_id_from_text(value: Any) -> str:
    text = str(value or "").lower()
    if "taskbounty" in text or "task-bounty.com" in text:
        return "taskbounty_agent_pr_task"
    if "superteam" in text:
        return "superteam_agent_contest"
    if "hackerone" in text or "h1-" in text or "h1:" in text:
        return "hackerone_bug_bounty"
    if "bugcrowd" in text:
        return "bugcrowd_bug_bounty"
    if "intigriti" in text:
        return "intigriti_bug_bounty"
    if "immunefi" in text:
        return "immunefi_web3_bounty"
    if "code4rena" in text:
        return "code4rena_competitive_audit"
    if "sherlock" in text:
        return "sherlock_audit_contest"
    if "algora" in text:
        return "algora_github_bounty"
    if "issuehunt" in text:
        return "issuehunt_funded_oss_issue"
    if "opire" in text:
        return "opire_open_reward_pr"
    if "onlydust" in text:
        return "onlydust_open_source_rewards"
    if "nomad" in text and ("worker" in text or "microtask" in text or "paid-ref" in text):
        return "nomad_internal_worker_market"
    if "github.com" in text or text.startswith("gh_"):
        return "github_oss_bounty_pr"
    return ""


def _channels(job_channel_surface: dict[str, Any] | None) -> list[dict[str, Any]]:
    surface = job_channel_surface if isinstance(job_channel_surface, dict) else {}
    rows = _items(surface.get("channels"))
    if rows:
        return rows
    return [
        {"channel_id": channel_id, "category": "", "channel_score": 0.25, "score_components": {}}
        for channel_id in DEFAULT_USD_PRIOR
    ]


def _outcomes_by_channel(external_value_summary: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    summary = external_value_summary if isinstance(external_value_summary, dict) else {}
    stage_rows = _items(summary.get("latest_by_external"))
    out: dict[str, dict[str, Any]] = {}
    for row in stage_rows:
        channel_id = _channel_id_from_text(
            " ".join(
                [
                    str(row.get("source_channel") or ""),
                    str(row.get("external_id") or ""),
                    str(row.get("work_url") or ""),
                    str(row.get("url") or ""),
                ]
            )
        )
        if not channel_id:
            channel_id = "unknown"
        item = out.setdefault(
            channel_id,
            {
                "paid_count": 0,
                "active_nonpaid": 0,
                "submitted_count": 0,
                "approved_count": 0,
                "merged_count": 0,
                "recognized_usd": 0.0,
                "pending_age_days_total": 0.0,
                "max_pending_age_days": 0.0,
                "paid_age_days_min": 0.0,
            },
        )
        stage = str(row.get("stage") or "").lower()
        amount = max(0.0, _num(row.get("amount_usd") or row.get("revenue_recognized_usd"), 0.0))
        age = _age_days(row.get("last_generated_at") or row.get("generated_at") or row.get("updated_at"))
        if stage == "paid" and amount > 0:
            item["paid_count"] += 1
            item["recognized_usd"] = round(_num(item.get("recognized_usd")) + amount, 4)
            prior_paid_age = _num(item.get("paid_age_days_min"), 0.0)
            item["paid_age_days_min"] = round(age if prior_paid_age <= 0.0 else min(prior_paid_age, age), 4)
        elif stage in {"found", "submitted", "approved", "merged"}:
            item["active_nonpaid"] += 1
            item["pending_age_days_total"] = round(_num(item.get("pending_age_days_total")) + age, 4)
            item["max_pending_age_days"] = round(max(_num(item.get("max_pending_age_days")), age), 4)
            if stage == "submitted":
                item["submitted_count"] += 1
            elif stage == "approved":
                item["approved_count"] += 1
            elif stage == "merged":
                item["merged_count"] += 1
    return out


def _signals_by_channel(signal_layer: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    surface = signal_layer if isinstance(signal_layer, dict) else {}
    events = _items(surface.get("recent_events") or surface.get("events"))
    targets = _items(surface.get("top_targets"))
    out: dict[str, dict[str, Any]] = {}
    rows = events if events else targets
    for row in rows:
        channel_id = _channel_id_from_text(
            " ".join(
                [
                    str(row.get("target_id") or ""),
                    str(row.get("target_url") or ""),
                    str(row.get("evidence_url") or ""),
                    str(row.get("note") or ""),
                ]
            )
        )
        if not channel_id:
            continue
        signal_type = str(row.get("signal_type") or "").lower().replace("-", "_")
        pos, neg = SIGNAL_PRIOR.get(signal_type, (0.0, 0.0))
        magnitude = _clamp(abs(_num(row.get("magnitude"), 1.0)), 0.0, 3.0)
        confidence = _clamp(_num(row.get("confidence"), 0.7), 0.0, 1.0)
        item = out.setdefault(channel_id, {"positive": 0.0, "negative": 0.0, "count": 0})
        item["positive"] = round(_num(item["positive"]) + pos * magnitude * confidence, 4)
        item["negative"] = round(_num(item["negative"]) + neg * magnitude * confidence, 4)
        item["count"] += 1
    return out


def _gate_multiplier(channel: dict[str, Any]) -> float:
    components = channel.get("score_components") if isinstance(channel.get("score_components"), dict) else {}
    authorization = _clamp(_num(components.get("authorization_clarity"), 0.5))
    payout = _clamp(_num(components.get("payout_clarity"), 0.5))
    proof = _clamp(_num(components.get("proof_clarity"), 0.5))
    autonomy = _clamp(_num(components.get("autonomy_allowed"), 0.5))
    friction = _clamp(_num(components.get("platform_friction"), 0.5))
    return _clamp((0.25 + 0.75 * authorization * payout * proof) * (0.45 + 0.55 * autonomy) * (1.0 - 0.45 * friction), 0.02, 1.0)


def _decision(
    *,
    channel_id: str,
    posterior_mean: float,
    censored_pending_mass: float,
    gate_multiplier: float,
    restless_index: float,
    side_effect_gate: str,
) -> str:
    if side_effect_gate.startswith("blocked"):
        return "operator_gate_only"
    if censored_pending_mass >= 2.0 and posterior_mean < 0.48:
        return "reconcile_or_cooldown"
    if gate_multiplier < 0.22:
        return "read_only_qualification"
    if channel_id in {"hackerone_bug_bounty", "bugcrowd_bug_bounty", "intigriti_bug_bounty"}:
        return "passive_scope_audit_only"
    if restless_index >= 0.18:
        return "execute_after_preflight"
    return "small_read_only_probe"


def _binary_entropy(p: float) -> float:
    q = _clamp(p, 0.000001, 0.999999)
    return -(q * math.log2(q) + (1.0 - q) * math.log2(1.0 - q))


def _build_wip_collapse_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    external_rows = [row for row in rows if row.get("channel_id") not in MACHINE_NATIVE_CHANNELS]
    pending_mass = sum(_num(row.get("censored_pending_mass"), 0.0) for row in external_rows)
    paid_count = sum(_num((row.get("observed") or {}).get("paid_count"), 0.0) for row in external_rows)
    recognized_usd = sum(_num((row.get("observed") or {}).get("recognized_usd"), 0.0) for row in external_rows)
    receipt_rate_proxy = paid_count / max(1.0, paid_count + pending_mass)
    receipt_capacity = max(1.0 if paid_count > 0 else 0.0, paid_count * 3.0)
    active = pending_mass >= 2.0 and (paid_count <= 0.0 or pending_mass > max(3.0, receipt_capacity))
    reason = "open"
    if active and paid_count <= 0.0:
        reason = "pending_mass_without_external_paid_receipt"
    elif active:
        reason = "pending_mass_exceeds_receipt_capacity"
    return {
        "schema": "nomad.wip_collapse_gate.v1",
        "active": bool(active),
        "reason": reason,
        "external_censored_pending_mass": round(pending_mass, 6),
        "external_paid_count": int(paid_count),
        "external_recognized_usd": round(recognized_usd, 4),
        "receipt_rate_proxy": round(receipt_rate_proxy, 8),
        "receipt_capacity_mass": round(receipt_capacity, 6),
        "trigger_rule": "collapse_when_external_pending_mass>=2_and_no_paid_receipts_or_pending_mass_exceeds_3x_receipt_capacity",
        "blocked_actions": ["execute_after_preflight", "new_public_claim", "private_report_submission_without_operator_gate"],
        "allowed_actions": ["read_only_qualification", "passive_scope_audit_only", "receipt_check", "reconcile_or_cooldown"],
        "scientific_basis": [
            {
                "id": "little_law_wip_control",
                "source": "https://pubsonline.informs.org/doi/10.1287/opre.9.3.383",
                "use": "arrival of new external claims is stopped when work-in-process exceeds observed receipt departure capacity",
            },
            {
                "id": "long_horizon_agent_reliability",
                "source": "https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/",
                "use": "long-horizon agent work fails through accumulated unresolved steps, so unresolved external claims are treated as state debt",
            },
        ],
        "machine_instruction": (
            "if_active_set_external_claim_emission_allowed_false_and_route_to_reconcile_until_paid_receipt_or_pending_decay"
        ),
    }


def _apply_wip_collapse(rows: list[dict[str, Any]], gate: dict[str, Any]) -> list[dict[str, Any]]:
    if not bool(gate.get("active")):
        for row in rows:
            row["claim_emission_allowed"] = row.get("recommended_action") == "execute_after_preflight"
            row["wip_collapse_applied"] = False
        return rows
    for row in rows:
        is_external = row.get("channel_id") not in MACHINE_NATIVE_CHANNELS
        original = str(row.get("recommended_action") or "")
        if is_external and original == "execute_after_preflight":
            row["recommended_action"] = "wip_collapse_reconcile_only"
        row["claim_emission_allowed"] = bool((not is_external) and row.get("recommended_action") == "execute_after_preflight")
        row["wip_collapse_applied"] = bool(is_external)
        if is_external:
            row["collapse_reason"] = gate.get("reason", "")
    return rows


def build_delayed_channel_bandit_surface(
    *,
    base_url: str = "",
    job_channel_surface: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
    signal_layer: dict[str, Any] | None = None,
    viability_kernel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    channels = _channels(job_channel_surface)
    outcomes = _outcomes_by_channel(external_value_summary)
    signals = _signals_by_channel(signal_layer)
    state_digest_seed = {
        "channels": [row.get("channel_id") for row in channels],
        "outcomes": outcomes,
        "signals": signals,
        "viability": (viability_kernel or {}).get("kernel_digest"),
    }
    rng = random.Random(int(_digest(state_digest_seed, 16), 16))
    rows: list[dict[str, Any]] = []
    for channel in channels:
        channel_id = _text(channel.get("channel_id"), 120)
        components = channel.get("score_components") if isinstance(channel.get("score_components"), dict) else {}
        base_score = _clamp(_num(channel.get("channel_score"), 0.1), 0.0, 1.0)
        prior_success = _clamp(
            0.10
            + 0.22 * _num(components.get("authorization_clarity"), 0.5)
            + 0.22 * _num(components.get("payout_clarity"), 0.5)
            + 0.18 * _num(components.get("proof_clarity"), 0.5)
            + 0.12 * _num(components.get("settlement_speed"), 0.35)
            + 0.08 * _num(components.get("agent_fit"), 0.5)
            - 0.10 * _num(components.get("competition_risk"), 0.5),
            0.03,
            0.88,
        )
        observed = outcomes.get(channel_id, {})
        signal = signals.get(channel_id, {})
        pending = int(_num(observed.get("active_nonpaid"), 0.0))
        paid = int(_num(observed.get("paid_count"), 0.0))
        approved = int(_num(observed.get("approved_count"), 0.0))
        merged = int(_num(observed.get("merged_count"), 0.0))
        pending_age_total = _num(observed.get("pending_age_days_total"), 0.0)
        max_pending_age = _num(observed.get("max_pending_age_days"), 0.0)
        alpha = 1.0 + 5.0 * prior_success + paid + 0.35 * approved + 0.45 * merged + _num(signal.get("positive"), 0.0)
        beta = 1.0 + 5.0 * (1.0 - prior_success) + 0.62 * pending + _num(signal.get("negative"), 0.0)
        posterior_mean = alpha / max(0.001, alpha + beta)
        sampled_probability = rng.betavariate(max(0.01, alpha), max(0.01, beta))
        expected_usd = DEFAULT_USD_PRIOR.get(channel_id, 10.0)
        delay_days = DEFAULT_DELAY_DAYS.get(channel_id, 21.0)
        delay_discount = 1.0 / max(1.0, math.sqrt(delay_days))
        censored_pending_mass = pending + (pending_age_total / max(1.0, delay_days))
        queue_penalty = 1.0 / (1.0 + censored_pending_mass)
        survival_decay = math.exp(-max_pending_age / max(1.0, delay_days))
        gate_multiplier = _gate_multiplier(channel)
        expected_usd_per_day = expected_usd * posterior_mean * delay_discount * gate_multiplier * queue_penalty * survival_decay
        sampled_value = expected_usd * sampled_probability * delay_discount * gate_multiplier * queue_penalty * survival_decay
        receipt_hazard_per_day = posterior_mean / max(1.0, delay_days)
        exploration_entropy = _binary_entropy(posterior_mean) * gate_multiplier * queue_penalty * survival_decay
        restless_index = (
            receipt_hazard_per_day * expected_usd * gate_multiplier * survival_decay
            + 0.08 * exploration_entropy
            - 0.03 * censored_pending_mass
        )
        side_effect_gate = str((channel.get("side_effect_gate") or {}).get("public_or_external_action") or "")
        rows.append(
            {
                "channel_id": channel_id,
                "category": channel.get("category") or "",
                "posterior_mean_paid_probability": round(posterior_mean, 6),
                "sampled_paid_probability": round(sampled_probability, 6),
                "expected_usd_prior": round(expected_usd, 4),
                "expected_delay_days": round(delay_days, 4),
                "delay_discount": round(delay_discount, 6),
                "gate_multiplier": round(gate_multiplier, 6),
                "queue_penalty": round(queue_penalty, 6),
                "survival_decay": round(survival_decay, 6),
                "censored_pending_mass": round(censored_pending_mass, 6),
                "receipt_hazard_per_day": round(receipt_hazard_per_day, 8),
                "exploration_entropy": round(exploration_entropy, 8),
                "restless_index": round(restless_index, 8),
                "expected_usd_per_day": round(expected_usd_per_day, 6),
                "sampled_value_usd_per_day": round(sampled_value, 6),
                "recommended_action": _decision(
                    channel_id=channel_id,
                    posterior_mean=posterior_mean,
                    censored_pending_mass=censored_pending_mass,
                    gate_multiplier=gate_multiplier,
                    restless_index=restless_index,
                    side_effect_gate=side_effect_gate,
                ),
                "observed": {
                    "active_nonpaid": pending,
                    "paid_count": paid,
                    "submitted_count": int(_num(observed.get("submitted_count"), 0.0)),
                    "approved_count": approved,
                    "merged_count": merged,
                    "recognized_usd": round(_num(observed.get("recognized_usd"), 0.0), 4),
                    "pending_age_days_total": round(pending_age_total, 4),
                    "max_pending_age_days": round(max_pending_age, 4),
                    "paid_age_days_min": round(_num(observed.get("paid_age_days_min"), 0.0), 4),
                    "signal_positive": round(_num(signal.get("positive"), 0.0), 4),
                    "signal_negative": round(_num(signal.get("negative"), 0.0), 4),
                },
                "side_effect_gate": side_effect_gate,
                "channel_score": round(base_score, 6),
            }
        )
    positive_index_sum = sum(max(0.0, _num(row.get("restless_index"), 0.0)) for row in rows)
    for row in rows:
        weight = 0.0
        if positive_index_sum > 0.0:
            weight = max(0.0, _num(row.get("restless_index"), 0.0)) / positive_index_sum
        row["allocation_weight"] = round(weight, 8)
        row["routing_kernel"] = "restless_survival_index_v1"
    wip_collapse = _build_wip_collapse_gate(rows)
    rows = _apply_wip_collapse(rows, wip_collapse)
    rows.sort(
        key=lambda item: (
            _num(item.get("allocation_weight")),
            _num(item.get("restless_index")),
            _num(item.get("sampled_value_usd_per_day")),
        ),
        reverse=True,
    )
    blocked_route_actions = {"operator_gate_only", "reconcile_or_cooldown", "wip_collapse_reconcile_only"}
    allowed_rows = [row for row in rows if row.get("recommended_action") not in blocked_route_actions]
    top = allowed_rows[0] if allowed_rows else (rows[0] if rows else {})
    allocation_vector = [
        {
            "channel_id": row.get("channel_id"),
            "allocation_weight": row.get("allocation_weight", 0.0),
            "recommended_action": row.get("recommended_action", ""),
        }
        for row in rows
        if _num(row.get("allocation_weight"), 0.0) > 0.0
    ]
    root = (base_url or "").strip().rstrip("/")
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": f"{root}/swarm/channel-bandit" if root else "/swarm/channel-bandit",
        "well_known_url": f"{root}/.well-known/nomad-channel-bandit.json" if root else "/.well-known/nomad-channel-bandit.json",
        "bandit_digest": f"channel-bandit-{_digest({'top': top, 'rows': rows}, 40)}",
        "mode": "restless_survival_index_with_delayed_feedback",
        "policy_kernel": {
            "schema": "nomad.channel_policy_kernel.v1",
            "name": "restless_survival_index_v1",
            "state_variables": [
                "posterior_paid_probability",
                "expected_delay_days",
                "censored_pending_mass",
                "receipt_hazard_per_day",
                "gate_multiplier",
                "survival_decay",
                "exploration_entropy",
            ],
            "index_formula": "hazard*expected_usd*gate*survival_decay + entropy_probe - censored_pending_mass_drag",
            "human_removed": [
                "brand_preference",
                "hope_after_merge",
                "social_thanks_as_value",
                "manual_priority_narrative",
            ],
        },
        "state": {
            "channel_count": len(rows),
            "routable_count": len(allowed_rows),
            "top_channel_id": top.get("channel_id", ""),
            "top_action": top.get("recommended_action", ""),
            "top_sampled_value_usd_per_day": top.get("sampled_value_usd_per_day", 0.0),
            "top_allocation_weight": top.get("allocation_weight", 0.0),
            "top_restless_index": top.get("restless_index", 0.0),
            "wip_collapse_active": bool(wip_collapse.get("active")),
        },
        "top_route": top,
        "wip_collapse": wip_collapse,
        "allocation_vector": allocation_vector,
        "routes": rows,
        "monetization_rule": (
            "allocate attention by restless receipt hazard; count zero revenue until external paid receipt; "
            "security channels remain passive/private-report only until reproducible proof exists"
        ),
        "hard_guards": [
            "no_live_security_testing_without_program_scope",
            "no_public_vulnerability_disclosure_before_platform_rules_allow",
            "no_new_claims_on_channels_with_nonpaying_pending_backlog",
            "no_revenue_without_paid_receipt",
            "no_public_token_or_stablecoin_mint_from_predicted_value",
        ],
        "scientific_basis": [
            {
                "id": "restless_bandit_index_policy_whittle_1988",
                "source": "https://www.cambridge.org/core/services/aop-cambridge-core/content/view/DDEB5E22AFFEFF50AA97ADC96B71AE35/S0021900200040420a.pdf/restless_bandits_activity_allocation_in_a_changing_world.pdf",
                "use": "channels keep changing while inactive; route by an index rather than human channel loyalty",
            },
            {
                "id": "multi_armed_bandit_robbins_1952",
                "source": "https://www.cs.utexas.edu/~shivaram/readings/b2hd-Robbins1952.html",
                "use": "exploration and exploitation are allocated sequentially from observed rewards",
            },
            {
                "id": "little_law_queue_pressure_little_1961",
                "source": "https://pubsonline.informs.org/doi/10.1287/opre.9.3.383",
                "use": "unpaid WIP is queue mass and directly reduces new-arrival allocation",
            },
            {
                "id": "information_theory_shannon_1948",
                "source": "https://people.math.harvard.edu/~ctm/home/text/others/shannon/entropy/entropy.pdf",
                "use": "uncertainty becomes exploration entropy; receipts remain low-noise reward signals",
            },
            {
                "id": "stigmergic_signal_field_dorigo_gambardella_1997",
                "source": "https://citeseerx.ist.psu.edu/document?doi=814b7ace1ab0ff5cd3cf028f0b7610f9b4d8153a&repid=rep1&type=pdf",
                "use": "bounded public traces alter routing without central human planning",
            },
        ],
        "machine_instruction": (
            "select by allocation_weight_then_restless_index unless viability_kernel blocks it; run only the recommended_action; "
            "after each accepted_or_paid event update external_value/work_receipts and rebuild this surface"
        ),
    }


__all__ = ["build_delayed_channel_bandit_surface"]
