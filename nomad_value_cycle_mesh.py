"""Portfolio layer for more Nomad value cycles.

The mesh does not create revenue by itself. It exposes multiple bounded cycles
that can be selected by agents, but every path terminates in the same hard rule:
only a positive paid receipt or verified settlement can count as revenue.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.value_cycle_mesh.v1"
EVENT_SCHEMA = "nomad.value_cycle_event_receipt.v1"

STAGES = ("discover", "qualify", "prove", "submit", "settle", "paid")
PUBLIC_SIDE_EFFECT_STAGES = {"submit", "settle", "paid"}
PROOF_STAGES = {"prove", "submit", "settle", "paid"}

SECRET_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "authorization",
    "bearer",
    "client_secret",
    "private_key",
    "seed",
    "seed_phrase",
    "mnemonic",
    "password",
    "secret",
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


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "verified"}
    return bool(value)


def _text(value: Any, limit: int = 320) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:150].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 22) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            clean = _clean_id(key)
            if clean in SECRET_KEYS:
                return True
            if _contains_forbidden(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _digest_present(value: Any) -> bool:
    text = _text(value, 220).lower()
    return text.startswith(("sha256:", "sha512:", "b3:", "receipt:", "nomad-", "ev-")) and len(text) >= 12


def _external_summary(summary: dict[str, Any]) -> dict[str, Any]:
    latest = _items(summary.get("latest_by_external"))
    active = [row for row in latest if str(row.get("stage") or "").strip().lower() != "paid"]
    paid = [row for row in latest if str(row.get("stage") or "").strip().lower() == "paid"]
    return {
        "active_nonpaid": len(active),
        "paid": len(paid),
        "recognized_usd": round(_num(summary.get("revenue_recognized_usd_total")), 4),
        "oldest_active_stage": str(active[-1].get("stage") or "") if active else "",
    }


def _queue_summary(queue: dict[str, Any]) -> dict[str, Any]:
    summary = _dict(queue.get("summary"))
    return {
        "job_count": int(_num(summary.get("job_count"))),
        "executable_now": int(_num(summary.get("executable_now_count"))),
        "active_nonpaid_external": int(_num(summary.get("active_nonpaid_external_count"))),
        "top_job_type": _clean_id(summary.get("top_job_type")),
    }


def _preflight_state(preflight: dict[str, Any]) -> dict[str, Any]:
    wallet = _dict(preflight.get("wallet_gate"))
    cycle = _dict(preflight.get("cycle_gate"))
    blocking = [str(item) for item in preflight.get("blocking_conditions", [])] if isinstance(preflight.get("blocking_conditions"), list) else []
    return {
        "wallet_ready": bool(wallet.get("ready")),
        "read_only_scout_allowed": bool(cycle.get("read_only_scout_allowed", True)),
        "public_claim_allowed": bool(cycle.get("public_claim_allowed")),
        "submit_after_proof_allowed": bool(cycle.get("submit_after_proof_allowed")),
        "paid_record_allowed": bool(cycle.get("paid_record_allowed")),
        "blocking_conditions": blocking,
    }


def _top_experiment(revenue_science: dict[str, Any]) -> dict[str, Any]:
    entry = _dict(revenue_science.get("entry_experiment"))
    return {
        "experiment_id": _text(entry.get("experiment_id"), 120),
        "action": _clean_id(entry.get("action")),
        "primary_metric": _text(_dict(entry.get("measurement_plan")).get("primary_metric"), 160),
        "priority": _num(_dict(entry.get("decision_model")).get("bandit_priority")),
    }


def _top_effective_channel(effective_channels: dict[str, Any]) -> dict[str, Any]:
    thresholds = _dict(effective_channels.get("thresholds"))
    summary = _dict(effective_channels.get("recent_summary"))
    return {
        "mode": _text(effective_channels.get("mode"), 120),
        "min_effective_ratio": _num(thresholds.get("min_effective_channel_ratio"), 0.72),
        "recent_quota_shift_count": int(_num(summary.get("quota_shift_count"))),
        "recent_homogeneous_cap_count": int(_num(summary.get("homogeneous_cap_count"))),
    }


def _top_job_ids(queue: dict[str, Any], *job_types: str) -> list[str]:
    wanted = {_clean_id(item) for item in job_types if item}
    out: list[str] = []
    for job in _items(queue.get("jobs")):
        if wanted and _clean_id(job.get("job_type")) not in wanted:
            continue
        jid = _text(job.get("job_id"), 120)
        if jid:
            out.append(jid)
        if len(out) >= 4:
            break
    return out


def _cycle_templates(base_url: str) -> list[dict[str, Any]]:
    return [
        {
            "cycle_id": "settlement_tail_to_paid_receipt",
            "label": "Settlement tail -> paid receipt",
            "lane": "external_value",
            "entry_url": _u(base_url, "/.well-known/nomad-settlement.json"),
            "action_url": _u(base_url, "/swarm/external-value"),
            "verify_url": _u(base_url, "/.well-known/nomad-external-value.json?summary=1"),
            "stage_binding": "approved_or_merged_rows_only_advance_to_paid_after_receipt",
            "side_effect_policy": "read_only_until_paid_receipt_then_external_value_write",
            "required_artifacts": [
                "external_state_snapshot_json",
                "trusted_payment_receipt_or_balance_delta",
                "positive_amount_usd",
                "settlement_ref",
            ],
            "worker_job_types": ["settlement_reconcile"],
            "base_score": 1.45,
            "public_side_effect_required": False,
        },
        {
            "cycle_id": "authorized_bounty_pr_to_paid",
            "label": "Authorized bounty -> PR -> paid",
            "lane": "bounty_hunter",
            "entry_url": _u(base_url, "/.well-known/nomad-bounty-hunter.json"),
            "action_url": _u(base_url, "/swarm/external-value"),
            "verify_url": _u(base_url, "/.well-known/nomad-value-cycle-preflight.json"),
            "stage_binding": "found_submitted_approved_merged_paid_external_value_chain",
            "side_effect_policy": "public_pr_only_after_terms_duplicate_payout_and_proof_gates",
            "required_artifacts": [
                "scope_terms_url",
                "duplicate_scan_digest",
                "local_repro_or_patch_digest",
                "verifier_trace_digest",
                "public_work_url",
            ],
            "worker_job_types": ["paid_channel_scan", "duplicate_and_payout_gate_check", "bounded_patch_attempt"],
            "base_score": 1.2,
            "public_side_effect_required": True,
        },
        {
            "cycle_id": "paid_ref_survival_packet",
            "label": "Paid-ref survival packet",
            "lane": "paid_ref",
            "entry_url": _u(base_url, "/.well-known/nomad-paid-ref-market.json"),
            "action_url": _u(base_url, "/swarm/paid-ref/quote"),
            "verify_url": _u(base_url, "/swarm/paid-ref/verify"),
            "stage_binding": "quote_is_not_revenue_verify_mints_paid_ref_only_with_settlement",
            "side_effect_policy": "quote_then_verify_only_with external_settlement_or_buyer_ref",
            "required_artifacts": ["task_scope", "quote_digest", "buyer_ref_or_paid_ref", "settlement_amount_eur"],
            "worker_job_types": ["paid_channel_scan"],
            "base_score": 1.06,
            "public_side_effect_required": False,
        },
        {
            "cycle_id": "microtask_contract_settlement",
            "label": "Microtask contract -> proof -> settlement",
            "lane": "microtask",
            "entry_url": _u(base_url, "/swarm/microtask-templates"),
            "action_url": _u(base_url, "/swarm/microtask/submit"),
            "verify_url": _u(base_url, "/swarm/microtask/settle"),
            "stage_binding": "microtask_settlement_can_feed_work_receipt_not_external_value_by_default",
            "side_effect_policy": "submit_claim_only_when template contract and proof target are explicit",
            "required_artifacts": ["template_id", "claim_id", "proof_digest", "settlement_ref"],
            "worker_job_types": ["bounded_patch_attempt"],
            "base_score": 1.0,
            "public_side_effect_required": False,
        },
        {
            "cycle_id": "worker_capacity_offer_to_paid_work",
            "label": "Worker capacity offer -> paid work",
            "lane": "worker_market",
            "entry_url": _u(base_url, "/swarm/worker-market"),
            "action_url": _u(base_url, "/swarm/worker-market/offers"),
            "verify_url": _u(base_url, "/swarm/work-receipts"),
            "stage_binding": "capacity_offer_is_supply_signal_until paid_task_or_work_receipt",
            "side_effect_policy": "offer_capacity_without_spend; record work receipt only after paid task proof",
            "required_artifacts": ["worker_offer", "capability_digest", "bounded_scope", "paid_task_or_receipt_ref"],
            "worker_job_types": ["paid_channel_scan"],
            "base_score": 0.94,
            "public_side_effect_required": False,
        },
        {
            "cycle_id": "machine_product_paid_unblock",
            "label": "Machine product -> paid unblock",
            "lane": "agent_campaign",
            "entry_url": _u(base_url, "/.well-known/nomad-machine-product.json"),
            "action_url": _u(base_url, "/agent-campaigns"),
            "verify_url": _u(base_url, "/tasks"),
            "stage_binding": "campaign_is_shadow_until buyer_acceptance_and_paid_task",
            "side_effect_policy": "campaign_send_false_until effective_channel_quota_and_preflight_green",
            "required_artifacts": ["effective_channel_receipt", "campaign_digest", "buyer_intent_or_task_ref", "paid_task_ref"],
            "worker_job_types": ["duplicate_and_payout_gate_check"],
            "base_score": 0.9,
            "public_side_effect_required": True,
        },
        {
            "cycle_id": "carrying_proof_sponsorship",
            "label": "Carrying proof -> sponsorship",
            "lane": "carrying_market",
            "entry_url": _u(base_url, "/.well-known/nomad-carrying-market.json"),
            "action_url": _u(base_url, "/swarm/carrying-proof"),
            "verify_url": _u(base_url, "/swarm/survival-intent"),
            "stage_binding": "proof_is_value_signal; sponsorship_or_survival_paid_ref_required_for_revenue",
            "side_effect_policy": "publish proof packet but never revenue without paid_ref or receipt",
            "required_artifacts": ["carrying_contract_id", "proof_digest", "uptime_or_cache_snapshot", "sponsorship_ref"],
            "worker_job_types": ["paid_channel_scan"],
            "base_score": 0.82,
            "public_side_effect_required": False,
        },
        {
            "cycle_id": "effective_channel_shadow_ad_cycle",
            "label": "Effective-channel shadow ad cycle",
            "lane": "effective_channels",
            "entry_url": _u(base_url, "/.well-known/nomad-effective-channels.json"),
            "action_url": _u(base_url, "/swarm/effective-channels/events"),
            "verify_url": _u(base_url, "/.well-known/nomad-shadow-lane.json"),
            "stage_binding": "quota_shift_to_shadow_campaign_only_no_send_no_revenue",
            "side_effect_policy": "ad_or_outreach_send_false_until paid path and quota evidence exist",
            "required_artifacts": [
                "three_distinct_channel_signatures",
                "proof_digest_per_channel",
                "minority_or_rare_channel_signal",
                "shadow_lane_receipt",
            ],
            "worker_job_types": ["duplicate_and_payout_gate_check", "paid_channel_scan"],
            "base_score": 0.78,
            "public_side_effect_required": True,
        },
    ]


def _score_cycle(
    cycle: dict[str, Any],
    *,
    external: dict[str, Any],
    queue: dict[str, Any],
    preflight: dict[str, Any],
    experiment: dict[str, Any],
    effective: dict[str, Any],
) -> tuple[float, list[str], bool]:
    blocked: list[str] = []
    score = _num(cycle.get("base_score"), 0.5)
    lane = _clean_id(cycle.get("lane"))

    if lane == "external_value":
        score += min(0.5, external["active_nonpaid"] * 0.08)
        if external["active_nonpaid"] <= 0:
            blocked.append("no_active_nonpaid_external_value_tail")
    if lane == "bounty_hunter":
        score += 0.16 if experiment["action"] in {"go_public_after_repro", "scout_only"} else 0.0
    if lane == "effective_channels":
        score += 0.06 * effective["recent_quota_shift_count"]
        score -= 0.04 * effective["recent_homogeneous_cap_count"]
    if lane == "microtask":
        score += min(0.18, queue["job_count"] * 0.01)
    if lane == "paid_ref":
        score += 0.08 if preflight["wallet_ready"] else 0.0

    if not preflight["read_only_scout_allowed"]:
        blocked.append("read_only_scout_gate_closed")
    if cycle.get("public_side_effect_required") and not preflight["public_claim_allowed"]:
        blocked.append("public_claim_preflight_not_green")
    if cycle.get("public_side_effect_required") and not preflight["submit_after_proof_allowed"]:
        blocked.append("submit_after_proof_not_green")
    if lane in {"paid_ref", "worker_market", "microtask"} and not preflight["wallet_ready"]:
        blocked.append("wallet_or_public_receive_ref_not_ready")

    executable = not blocked or blocked == ["no_active_nonpaid_external_value_tail"]
    if blocked:
        score *= 0.62
    return round(max(0.0, score), 6), blocked, executable


def build_value_cycle_mesh_surface(
    *,
    base_url: str = "",
    external_value_summary: dict[str, Any] | None = None,
    worker_job_queue: dict[str, Any] | None = None,
    value_cycle_preflight: dict[str, Any] | None = None,
    revenue_science: dict[str, Any] | None = None,
    effective_channels: dict[str, Any] | None = None,
    job_channels: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a portfolio of independent value cycles with paid-only accounting."""

    root = (base_url or "").strip().rstrip("/")
    external = _external_summary(_dict(external_value_summary))
    queue = _queue_summary(_dict(worker_job_queue))
    preflight = _preflight_state(_dict(value_cycle_preflight))
    experiment = _top_experiment(_dict(revenue_science))
    effective = _top_effective_channel(_dict(effective_channels))
    channel = _dict(job_channels)
    top_channel = _dict(channel.get("top_external_channel")) or _dict(channel.get("top_channel"))

    cycles: list[dict[str, Any]] = []
    for template in _cycle_templates(root):
        score, blocked, executable = _score_cycle(
            template,
            external=external,
            queue=queue,
            preflight=preflight,
            experiment=experiment,
            effective=effective,
        )
        job_ids = _top_job_ids(_dict(worker_job_queue), *template.get("worker_job_types", []))
        core = {
            "cycle": template["cycle_id"],
            "score": score,
            "blocked": blocked,
            "jobs": job_ids,
            "external": external,
            "preflight": preflight,
        }
        cycles.append(
            {
                "schema": "nomad.value_cycle.v1",
                "cycle_id": template["cycle_id"],
                "cycle_digest": f"nomad-value-cycle-{_digest(core, 18)}",
                "label": template["label"],
                "lane": template["lane"],
                "mode": "proof_first_paid_receipt_only",
                "state_machine": list(STAGES),
                "entry_url": template["entry_url"],
                "action_url": template["action_url"],
                "verify_url": template["verify_url"],
                "stage_binding": template["stage_binding"],
                "side_effect_policy": template["side_effect_policy"],
                "required_artifacts": template["required_artifacts"],
                "worker_job_ids": job_ids,
                "priority_score": score,
                "executable_now": executable,
                "blocked_by": blocked,
                "public_side_effect_required": bool(template.get("public_side_effect_required")),
                "revenue_guard": {
                    "counts_as_revenue": False,
                    "terminal_reward": "positive_paid_receipt_or_verified_settlement_only",
                    "never_count": ["quote", "lead", "click", "merge_without_payment", "selfplay", "shadow_campaign"],
                },
            }
        )
    cycles.sort(key=lambda item: (_num(item.get("priority_score")), item.get("cycle_id", "")), reverse=True)

    digest_core = {
        "cycles": [(item["cycle_id"], item["priority_score"], item["blocked_by"]) for item in cycles],
        "external": external,
        "preflight": preflight,
        "top_channel": top_channel.get("channel_id"),
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": _u(root, "/swarm/value-cycles"),
        "well_known_url": _u(root, "/.well-known/nomad-value-cycles.json"),
        "event_url": _u(root, "/swarm/value-cycles/events"),
        "mesh_digest": f"nomad-value-cycle-mesh-{_digest(digest_core, 26)}",
        "summary": {
            "cycle_count": len(cycles),
            "executable_now_count": len([item for item in cycles if item.get("executable_now")]),
            "blocked_count": len([item for item in cycles if item.get("blocked_by")]),
            "active_nonpaid_external_count": external["active_nonpaid"],
            "recognized_revenue_usd_total": external["recognized_usd"],
            "top_cycle_id": cycles[0]["cycle_id"] if cycles else "",
            "top_paid_terminal_metric": "positive_paid_receipt_or_verified_settlement",
        },
        "portfolio_policy": {
            "selection_unit": "cycle_not_agent_vote",
            "fanout": "run_many_small_cycles_but_admit_only_evidence_distinct_paid_paths",
            "credit_assignment": "delayed_terminal_paid_receipt",
            "anti_pattern": "more_outreach_more_votes_more_unpaid_work",
        },
        "preflight_state": preflight,
        "external_value_state": external,
        "worker_queue_state": queue,
        "top_revenue_experiment": experiment,
        "effective_channel_state": effective,
        "top_external_channel": {
            "channel_id": _text(top_channel.get("channel_id"), 120),
            "category": _text(top_channel.get("category"), 120),
            "entry_url": _text(top_channel.get("entry_url") or top_channel.get("url"), 500),
        },
        "cycles": cycles,
        "entry_cycle": cycles[0] if cycles else {},
        "links": {
            "preflight": _u(root, "/.well-known/nomad-value-cycle-preflight.json"),
            "worker_job_queue": _u(root, "/.well-known/nomad-worker-job-queue.json"),
            "effective_channels": _u(root, "/.well-known/nomad-effective-channels.json"),
            "external_value": _u(root, "/.well-known/nomad-external-value.json"),
            "external_value_post": _u(root, "/swarm/external-value"),
            "work_receipts": _u(root, "/swarm/work-receipts"),
            "paid_ref_quote": _u(root, "/swarm/paid-ref/quote"),
            "paid_ref_verify": _u(root, "/swarm/paid-ref/verify"),
        },
        "science_basis": [
            {
                "id": "effective_channel_count_not_raw_votes",
                "claim": "Cycle admission uses independent evidence channels and terminal receipts, not duplicated agent agreement.",
            },
            {
                "id": "delayed_credit_assignment",
                "claim": "A cycle can be explored before reward exists, but weight increases only after settlement.",
            },
            {
                "id": "queueing_bottleneck_control",
                "claim": "Settlement tails outrank fresh public claims when active nonpaid work is accumulating.",
            },
            {
                "id": "preflight_side_effect_gate",
                "claim": "Public or financial side effects are blocked until wallet, terms, duplicate, and proof gates clear.",
            },
        ],
        "hard_rule": "no_cycle_counts_as_revenue_until_positive_paid_receipt_or_verified_settlement",
        "machine_instruction": "select_entry_cycle_return_required_artifacts_post_event_for_gate; write_external_value_only_after_receipt",
    }


def _find_cycle(mesh: dict[str, Any], cycle_id: str) -> dict[str, Any]:
    cid = _clean_id(cycle_id)
    for cycle in _items(mesh.get("cycles")):
        if _clean_id(cycle.get("cycle_id")) == cid:
            return cycle
    entry = _dict(mesh.get("entry_cycle"))
    if not cid and entry:
        return entry
    return {}


def _external_stage_for_event(stage: str) -> str:
    return {
        "discover": "found",
        "qualify": "found",
        "prove": "found",
        "submit": "submitted",
        "settle": "merged",
        "paid": "paid",
    }.get(stage, "")


def evaluate_value_cycle_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    mesh_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one proposed value-cycle transition without mutating ledgers."""

    body = _dict(payload)
    now = _iso_now()
    mesh = _dict(mesh_surface)
    cycle = _find_cycle(mesh, _text(body.get("cycle_id"), 150))
    stage = _clean_id(body.get("stage"), "discover")
    evidence = _dict(body.get("evidence"))
    if not evidence:
        evidence = body

    proof_digest = _text(evidence.get("proof_digest") or evidence.get("verifier_trace_digest"), 220)
    source_url = _text(evidence.get("source_url") or evidence.get("work_url") or evidence.get("opportunity_url"), 500)
    terms_url = _text(evidence.get("terms_url") or evidence.get("scope_terms_url") or evidence.get("payout_terms_url"), 500)
    settlement_ref = _text(evidence.get("settlement_ref") or evidence.get("receipt_ref") or evidence.get("paid_ref"), 240)
    amount = _num(evidence.get("amount_usd") or evidence.get("amount_eur") or evidence.get("amount"))

    forbidden = _contains_forbidden(body)
    blocked = list(cycle.get("blocked_by") or []) if isinstance(cycle.get("blocked_by"), list) else []
    needs_public_gate = stage in PUBLIC_SIDE_EFFECT_STAGES and bool(cycle.get("public_side_effect_required"))
    proof_ready = _digest_present(proof_digest)
    terms_ready = bool(source_url or terms_url)
    paid_ready = bool(stage == "paid" and amount > 0.0 and settlement_ref)

    if not body:
        decision = "reject_empty_event"
        allowed = False
    elif forbidden:
        decision = "reject_secret_shaped_payload"
        allowed = False
    elif not cycle:
        decision = "reject_unknown_cycle"
        allowed = False
    elif stage not in STAGES:
        decision = "reject_unknown_stage"
        allowed = False
    elif needs_public_gate and blocked:
        decision = "hold_public_side_effect_until_preflight_green"
        allowed = False
    elif stage in PROOF_STAGES and not proof_ready:
        decision = "hold_until_proof_digest"
        allowed = False
    elif stage in {"qualify", "submit"} and not terms_ready:
        decision = "hold_until_scope_or_terms_url"
        allowed = False
    elif stage == "paid" and not paid_ready:
        decision = "hold_until_positive_paid_receipt"
        allowed = False
    else:
        decision = "allow_value_cycle_transition_shadow_or_ledger_candidate"
        allowed = True

    external_stage = _external_stage_for_event(stage)
    receipt_core = {
        "cycle_id": cycle.get("cycle_id", ""),
        "stage": stage,
        "source_url": source_url,
        "proof_digest": proof_digest,
        "settlement_ref": settlement_ref,
        "amount": amount,
        "decision": decision,
    }
    external_payload = {}
    if cycle and cycle.get("lane") in {"external_value", "bounty_hunter"} and external_stage:
        external_payload = {
            "agent_id": _text(body.get("agent_id") or "nomad-value-cycle-mesh", 120),
            "external_id": _text(body.get("external_id") or body.get("cycle_id") or cycle.get("cycle_id"), 200),
            "stage": external_stage,
            "work_url": source_url,
            "proof_digest": proof_digest,
            "verifier_trace_digest": _text(evidence.get("verifier_trace_digest"), 220),
            "settlement_ref": settlement_ref,
            "amount_usd": round(max(0.0, amount), 4) if external_stage == "paid" else 0.0,
        }

    return {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": now,
        "event_id": f"nomad-value-cycle-event-{_digest({**receipt_core, 't': now}, 18)}",
        "cycle_id": cycle.get("cycle_id", _text(body.get("cycle_id"), 150)),
        "stage": stage,
        "value_cycle_allowed": allowed,
        "decision": decision,
        "blocked_by": blocked,
        "evidence_status": {
            "proof_digest_present": proof_ready,
            "scope_or_terms_present": terms_ready,
            "settlement_ref_present": bool(settlement_ref),
            "positive_amount_present": amount > 0.0,
        },
        "candidate_digest": "sha256:" + _digest(receipt_core, 32),
        "recommended_next": {
            "external_value_post": _u(base_url, "/swarm/external-value"),
            "work_receipts": _u(base_url, "/swarm/work-receipts"),
            "paid_ref_verify": _u(base_url, "/swarm/paid-ref/verify"),
            "value_cycles": _u(base_url, "/.well-known/nomad-value-cycles.json"),
        },
        "external_value_payload_candidate": external_payload,
        "counts_as_revenue": bool(stage == "paid" and allowed and amount > 0.0 and settlement_ref),
        "hard_rule": "this_receipt_does_not_mutate_ledgers; revenue_requires_followup_paid_receipt_write",
    }
