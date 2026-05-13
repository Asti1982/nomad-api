"""Settlement-first control field for Nomad external value work.

This layer treats human review queues as an external settlement membrane.  It
does not try to imitate humans; it compiles machine signals into the smallest
honest outward action that can move a tracked artifact toward merge, payment,
or a verified wait state.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from nomad_external_value import STAGE_INDEX, STAGES_ORDER, summarize_external_value_ledger
from nomad_external_value_reconciler import reconcile_external_value_ledger


STAGE_PRIORS: dict[str, dict[str, float]] = {
    "found": {"accept": 0.10, "pay": 0.015, "base_value": 0.24, "wait_hours": 4.0},
    "submitted": {"accept": 0.28, "pay": 0.045, "base_value": 0.72, "wait_hours": 36.0},
    "approved": {"accept": 0.58, "pay": 0.10, "base_value": 1.18, "wait_hours": 24.0},
    "merged": {"accept": 0.86, "pay": 0.30, "base_value": 2.20, "wait_hours": 12.0},
    "paid": {"accept": 1.0, "pay": 1.0, "base_value": 0.0, "wait_hours": 9999.0},
}


INFLUENCE_OPERATOR_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "friction_collapse",
        "operator": "make_the_next_acceptable_action_smaller_than_the_queue_cost",
        "human_pattern": "cognitive_load_reduction",
        "evidence_grade": "strong_for_attention_and_compliance_proxy; cashflow_unproven",
        "nomad_use": "one decision unit, one verifier command, one requested transition",
        "allowed_surface": "short factual packet with no unrelated context",
        "forbidden_surface": "withholding material risk, hiding failing checks, or flooding multiple asks",
        "metric": "reviewer_action_rate_after_packet",
    },
    {
        "id": "verifier_salience",
        "operator": "put_the_auditable_result_before_background_or_identity",
        "human_pattern": "salience_and_processing_fluency",
        "evidence_grade": "strong_for_decision_attention_proxy; merge_latency_proxy_only",
        "nomad_use": "lead with exact test, proof digest, changed file count, or receipt state",
        "allowed_surface": "real verifier path first",
        "forbidden_surface": "headline that overstates severity, payment, or acceptance",
        "metric": "time_to_first_maintainer_action",
    },
    {
        "id": "published_rule_binding",
        "operator": "bind_the_request_to_a_rule_the_counterparty_already_published",
        "human_pattern": "commitment_consistency_and_goal_alignment",
        "evidence_grade": "moderate_for_acceptance_proxy; cashflow_unproven",
        "nomad_use": "quote or reference only existing issue, bounty, contribution, or payment rules",
        "allowed_surface": "specific rule anchor or issue acceptance criterion",
        "forbidden_surface": "invented policy, implied entitlement, or fake promise",
        "metric": "rule_bound_transition_rate",
    },
    {
        "id": "agency_control_knob",
        "operator": "give_the_human_a_low_cost_control_surface_over_the_artifact",
        "human_pattern": "algorithm_aversion_reduction_through_adjustability",
        "evidence_grade": "strong_for_algorithm_trust_proxy; merge_cashflow_unproven",
        "nomad_use": "offer split, removal, narrower patch, or alternate verifier if preferred",
        "allowed_surface": "one optional control sentence",
        "forbidden_surface": "flattery, pressure, or making the maintainer do hidden work",
        "metric": "negative_review_to_revision_conversion_rate",
    },
    {
        "id": "neutral_timing",
        "operator": "emit_one_bounded_reminder_only_after_the_stage_wait_hazard_has_matured",
        "human_pattern": "timely_prompting_without_artificial_urgency",
        "evidence_grade": "moderate_for_response_proxy; spam_risk_if_overused",
        "nomad_use": "wait by stage prior, then one status check with an opt-out phrase",
        "allowed_surface": "single factual followup after minimum wait hours",
        "forbidden_surface": "fake urgency, repeated nudges, countdowns, or guilt language",
        "metric": "reply_rate_minus_unsubscribe_or_negative_feedback",
    },
    {
        "id": "real_reciprocity",
        "operator": "show_completed_work_before_any_settlement_reference",
        "human_pattern": "reciprocity_from_actual_delivered_value",
        "evidence_grade": "moderate_for_cooperation_proxy; payment_unproven",
        "nomad_use": "proof, patch, test, or merged artifact precedes any receipt request",
        "allowed_surface": "visible completed work and verifier trail",
        "forbidden_surface": "asking for payment before acceptance evidence exists",
        "metric": "accepted_or_merged_to_paid_receipt_rate",
    },
    {
        "id": "truthful_norm_anchor",
        "operator": "use_social_or_project_norms_only_when_they_are_visible_and_specific",
        "human_pattern": "descriptive_norms",
        "evidence_grade": "strong_in_general_behavioral_contexts; disabled_until_project_specific_truth_exists",
        "nomad_use": "off by default; only cite a visible repo rule or maintainer statement",
        "allowed_surface": "this project asks for X in CONTRIBUTING when true",
        "forbidden_surface": "everyone does this, most agents do this, or invented consensus",
        "metric": "norm_anchor_accuracy_and_transition_rate",
        "default_enabled": False,
    },
    {
        "id": "receipt_boundary_lock",
        "operator": "separate_acceptance_merge_and_payment_in_every_outward_packet",
        "human_pattern": "trust_calibration_and_accounting_clarity",
        "evidence_grade": "strong_for_internal_validity; protects_cashflow_measurement",
        "nomad_use": "never call approved or merged revenue; ask for receipt only after positive evidence",
        "allowed_surface": "paid only after receipt",
        "forbidden_surface": "payment claim without receipt or amount without source",
        "metric": "false_revenue_count_must_equal_zero",
    },
)


SCIENCE_SOURCE_REGISTRY: tuple[dict[str, str], ...] = (
    {
        "id": "pull_based_development_integrator_work",
        "url": "https://azaidman.github.io/publications/gousiosICSE2015.pdf",
        "supports": "maintainer review is a bounded queue where context, CI, and reviewer burden matter",
        "boundary": "does not prove payment or guaranteed cashflow",
    },
    {
        "id": "social_and_technical_pr_evaluation",
        "url": "https://doi.org/10.1145/2568225.2568315",
        "supports": "technical evidence and social context both influence pull-request evaluation",
        "boundary": "Nomad may use only truthful context, never fake reputation or identity",
    },
    {
        "id": "algorithm_aversion_adjustability",
        "url": "https://marketing.wharton.upenn.edu/wp-content/uploads/2016/10/Dietvorst-Overcoming-Algorithm-Aversion.pdf",
        "supports": "human control over an algorithmic output can reduce aversion",
        "boundary": "control knob must be real and low burden",
    },
    {
        "id": "easy_attractive_social_timely",
        "url": "https://www.bi.team/publications/east-four-simple-ways-to-apply-behavioural-insights/",
        "supports": "easy and timely interfaces can increase action completion",
        "boundary": "social claims are disabled unless project-specific truth is visible",
    },
    {
        "id": "agentic_security_prs",
        "url": "https://arxiv.org/abs/2601.00477",
        "supports": "agent-generated security work still needs human review and adjustment",
        "boundary": "AI work must be constrained by reproducible evidence and honest disclosure",
    },
)


def influence_operator_catalog() -> list[dict[str, Any]]:
    return [dict(item) for item in INFLUENCE_OPERATOR_CATALOG]


def science_source_registry() -> list[dict[str, str]]:
    return [dict(item) for item in SCIENCE_SOURCE_REGISTRY]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _parse_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _age_hours(value: Any, *, now: datetime) -> float:
    parsed = _parse_time(value)
    if not parsed:
        return 0.0
    return max(0.0, (now - parsed).total_seconds() / 3600.0)


def _repo_from_external(external_id: Any, work_url: Any = "") -> str:
    eid = _text(external_id, 260)
    match = re.match(r"^gh_(?:pr|review|issue|issue_comment|pr_review):([^#]+/[^#]+)#", eid)
    if match:
        return match.group(1)
    url_match = re.search(r"github\.com/([^/\s]+/[^/\s]+)/(?:pull|issues)/", str(work_url or ""))
    return url_match.group(1) if url_match else ""


def _stage_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {stage: 0 for stage in STAGES_ORDER}
    for row in rows:
        stage = str(row.get("stage") or "").strip().lower()
        if stage in counts:
            counts[stage] += 1
    return counts


def _followups_by_external(external_reconcile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in external_reconcile.get("followups") or []:
        if not isinstance(item, dict):
            continue
        eid = _text(item.get("external_id"), 260)
        if eid:
            out[eid] = item
    return out


def _repo_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        stage = str(row.get("stage") or "").strip().lower()
        if stage == "paid":
            continue
        repo = _repo_from_external(row.get("external_id"), row.get("work_url"))
        if repo:
            counts[repo] = counts.get(repo, 0) + 1
    return counts


def _default_action(stage: str) -> str:
    return {
        "found": "produce_or_submit_proof",
        "submitted": "await_owner_acceptance",
        "approved": "await_merge_or_settlement",
        "merged": "await_payment_receipt",
        "paid": "archive_paid_receipt",
    }.get(stage, "refresh_external_status")


def _policy(row: dict[str, Any]) -> dict[str, Any]:
    stage = str(row.get("current_stage") or "")
    action = str(row.get("action") or "")
    age_hours = _num(row.get("age_hours"))
    wait_hours = _num(row.get("minimum_wait_hours_before_followup"))
    if stage == "paid":
        next_action = "learn_from_paid_receipt"
    elif action == "produce_or_submit_proof":
        next_action = "emit_minimal_repro_or_patch"
    elif action == "await_payment_receipt":
        next_action = "seek_payment_receipt_only_after_external_positive_signal"
    elif age_hours >= wait_hours and action.startswith("await_"):
        next_action = "single_bounded_followup_with_evidence_link"
    else:
        next_action = "wait_and_reconcile"
    hypothesis_next_action = next_action
    if stage != "paid":
        next_action = "compile_truthful_influence_packet"
    return {
        "next_action": next_action,
        "unactivated_hypothesis_next_action": hypothesis_next_action,
        "human_surface": "truthful_psychological_pattern_interface",
        "cashflow_evidence_status": "merge_and_review_patterns_supported_cashflow_not_guaranteed",
        "cashflow_score_multiplier": 1.0,
        "evidence_rule": "truthful_human_pattern_use_may_reduce_merge_settlement_friction; paid_accounting_requires_receipts",
        "allowed": [
            "ledger_reconcile",
            "public_read_only_status_check",
            "compile_unsent_evidence_packet",
            "salience_ordering_of_real_facts",
            "cognitive_load_reduction",
            "real_reciprocity_from_completed_work",
            "objective_task_framing",
            "commitment_checklist_against_project_rules",
            "record_paid_receipt_after_positive_external_evidence",
        ],
        "forbidden": [
            "fake_identity",
            "hidden_ai_origin_when_project_requires_disclosure",
            "deceptive_pressure",
            "fake_urgency_or_scarcity",
            "spam_followups",
            "revenue_recognition_without_paid_receipt",
        ],
    }


def _operators_by_id() -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): dict(item) for item in INFLUENCE_OPERATOR_CATALOG}


def _operator_sequence_for_packet(row: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    stage = str(row.get("current_stage") or "").strip().lower()
    action = str(row.get("action") or "").strip().lower()
    names = [
        "receipt_boundary_lock",
        "friction_collapse",
        "verifier_salience",
        "agency_control_knob",
    ]
    if kind in {"followup", "settlement"} or action.startswith("await_"):
        names.append("neutral_timing")
    if kind in {"followup", "settlement"} or stage in {"submitted", "approved", "merged"}:
        names.extend(["published_rule_binding", "real_reciprocity"])
    if kind == "settlement" or action == "await_payment_receipt" or stage == "merged":
        names = ["receipt_boundary_lock", "real_reciprocity", "friction_collapse", "neutral_timing", "published_rule_binding", "agency_control_knob"]

    catalog = _operators_by_id()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        item = catalog.get(name)
        if item and item.get("default_enabled", True) is not False:
            out.append(item)
    return out


def _decision_unit_for_packet(row: dict[str, Any], kind: str) -> dict[str, Any]:
    action = _text(row.get("action"), 80) or "review_or_settlement_check"
    stage = _text(row.get("current_stage"), 40) or "unknown"
    if kind == "settlement" or action == "await_payment_receipt":
        ask = "confirm whether payment/receipt is already queued or visible"
        verifier = "trusted external payment receipt, tx ref, or program-owner payout note"
    elif kind == "followup" or action.startswith("await_"):
        ask = "confirm whether this can move to the next tracked stage or should wait"
        verifier = "existing PR/review/issue proof trail"
    else:
        ask = "review one small verified change"
        verifier = "exact local test command and proof digest"
    return {
        "schema": "nomad.settlement_decision_unit.v1",
        "one_ask": ask,
        "stage": stage,
        "target_action": action,
        "verifier_first": verifier,
        "max_human_actions_requested": 1,
        "control_knob": "I can split, narrow, remove, or retest this if that is easier.",
        "accounting_lock": "Nomad records revenue only after a positive paid receipt.",
    }


def compile_public_settlement_packet(
    row: dict[str, Any],
    *,
    packet_type: str = "pr",
) -> dict[str, Any]:
    """Compile an evidence-first public text packet without sending it.

    The packet is intentionally sparse.  It uses empirically supported review
    proxies (scope, tests, reproducibility, low verbosity) as a merge-latency
    interface, not as a promised cashflow lever.
    """

    kind = _text(packet_type, 40).lower() or "pr"
    external_id = _text(row.get("external_id"), 260)
    work_url = _text(row.get("work_url"), 500)
    action = _text(row.get("action"), 80)
    stage = _text(row.get("current_stage"), 40)
    decision_unit = _decision_unit_for_packet(row, kind)
    operator_sequence = _operator_sequence_for_packet(row, kind)
    if kind == "settlement":
        title = "Settlement receipt check for accepted work"
        body_lines = [
            "Short receipt check tied to the existing accepted artifact.",
            "",
            f"- Tracked item: {external_id or work_url}",
            f"- Current stage: {stage or 'unknown'}",
            "- Request: confirm only if a payout/receipt is already queued or visible",
            "- Evidence: merged/accepted work and existing proof trail remain the source of truth",
            "- Boundary: approval or merge is not recorded as revenue",
            "- Control: I can provide a smaller receipt reference or wait if this is already queued",
        ]
    elif kind == "followup":
        title = "Status check: evidence attached, no action needed if queued"
        body_lines = [
            "Short follow-up with the existing proof trail.",
            "",
            f"- Tracked item: {external_id or work_url}",
            f"- Current stage: {stage or 'unknown'}",
            f"- Requested transition: {action or 'review/settlement check'}",
            "- Evidence: existing PR/tests/proof digest are unchanged",
            "- Revenue note: no payment is recorded unless a positive receipt exists",
        ]
    else:
        title = "Small verified fix with reproducible check"
        body_lines = [
            "This is a narrowly scoped change with a verifier path.",
            "",
            "- Problem: <one observable failure or risk>",
            "- Change: <smallest patch that removes the failure>",
            "- Verification: `<exact command>`",
            "- Before/after: <failing or risky state -> passing or safer state>",
            "- Scope control: no unrelated refactor, no generated bulk changes",
            "- Revenue note: Nomad records no revenue unless external payment is verified",
        ]
    return {
        "ok": True,
        "schema": "nomad.settlement_public_packet.v1",
        "packet_type": kind,
        "external_id": external_id,
        "work_url": work_url,
        "activation_scope": "merge_latency_proxy_not_cashflow_guarantee",
        "send_policy": "manual_or_contract_bound_send_only",
        "cashflow_growth_claim": False,
        "title": title,
        "body": "\n".join(body_lines),
        "mechanism": "truthful_psychological_pattern_use_not_persona_simulation",
        "decision_unit": decision_unit,
        "operator_sequence": [
            {
                "id": item.get("id"),
                "operator": item.get("operator"),
                "human_pattern": item.get("human_pattern"),
                "evidence_grade": item.get("evidence_grade"),
                "allowed_surface": item.get("allowed_surface"),
                "forbidden_surface": item.get("forbidden_surface"),
            }
            for item in operator_sequence
        ],
        "timing_policy": {
            "minimum_wait_hours_before_followup": row.get("minimum_wait_hours_before_followup", 0),
            "age_hours": row.get("age_hours", 0),
            "max_unsolicited_followups": 1,
            "urgency_policy": "no_fake_urgency_no_countdowns_no_guilt_language",
        },
        "rule_binding": {
            "status": "allowed_only_when_project_rule_or_bounty_issue_is_visible",
            "default": "do_not_invent_rules",
        },
        "settlement_reference": {
            "status": "receipt_only_after_external_positive_signal",
            "paid_boundary": "approval_or_merge_is_not_revenue",
        },
        "influence_patterns": [
            {"name": "salience", "use": "put the verifier-relevant fact before background context"},
            {"name": "cognitive_load_reduction", "use": "one decision unit, one command, one proof trail"},
            {"name": "real_reciprocity", "use": "completed work is visible before any settlement ask"},
            {"name": "commitment_consistency", "use": "map request to the project or bounty rule already stated"},
            {"name": "objective_task_framing", "use": "frame around observable artifact state, not agent personality"},
        ],
        "forbidden": [
            "fake_flattery",
            "fake_urgency",
            "fake_affiliation",
            "hidden_ai_origin_when_required",
            "payment_claim_without_receipt",
            "invented_social_norm",
            "multi_followup_spam",
        ],
        "science_basis": [
            "agentic_pr_studies_associate_large_or_verbose_changes_with_rejection_latency",
            "pull_request_research_supports_ci_reproducibility_and_context_as_review_inputs",
            "algorithm_aversion_research_supports objective task framing, not deception",
        ],
        "science_sources": science_source_registry(),
    }


def _row_from_external(
    row: dict[str, Any],
    *,
    followup_item: dict[str, Any],
    repo_count: int,
    now: datetime,
) -> dict[str, Any]:
    external_id = _text(row.get("external_id"), 260)
    stage = str(row.get("stage") or "").strip().lower()
    if stage not in STAGE_INDEX:
        stage = "found"
    followup = followup_item.get("followup") if isinstance(followup_item.get("followup"), dict) else {}
    action = _text(followup.get("action") or _default_action(stage), 80)
    target_stage = _text(followup.get("target_stage") or ("paid" if stage == "merged" else stage), 40)
    priors = STAGE_PRIORS.get(stage, STAGE_PRIORS["found"])
    age = _age_hours(row.get("last_generated_at"), now=now)
    required_evidence = followup.get("required_evidence") if isinstance(followup.get("required_evidence"), list) else []
    evidence_gap = len(required_evidence)
    burden = _clamp(0.16 + evidence_gap * 0.10 + (0.16 if stage in {"submitted", "approved"} else 0.0), 0.08, 1.0)
    duplicate_pressure = _clamp(max(0, repo_count - 3) / 8.0, 0.0, 1.0)
    latency_drag = _clamp(age / max(1.0, priors["wait_hours"]), 0.0, 4.0)
    followup_priority = _num(followup.get("priority"), 0.42 if stage == "found" else 0.62)
    paid_revenue = _num(row.get("revenue_recognized_usd"))
    stage_multiplier = 1.0
    latency_denominator = 1.0 + latency_drag * 0.35
    if stage == "merged":
        # A merged artifact is no longer fighting for review attention; the
        # value edge is now receipt discovery.  Waiting past the mature receipt
        # window should increase settlement priority without counting revenue.
        duplicate_pressure *= 0.25
        stage_multiplier = 1.55 + min(latency_drag, 2.0) * 0.25
        latency_denominator = 1.0 + max(0.0, 1.0 - latency_drag) * 0.35
    if stage == "paid":
        score = 0.0
    else:
        score = (
            priors["base_value"]
            * (0.35 + priors["accept"])
            * (0.12 + priors["pay"])
            * max(0.1, followup_priority)
            * stage_multiplier
        ) / ((1.0 + burden) * (1.0 + duplicate_pressure) * latency_denominator)
    out = {
        "schema": "nomad.settlement_signal_row.v1",
        "row_id": f"settlement:{_digest({'external_id': external_id, 'stage': stage}, 14)}",
        "external_id": external_id,
        "agent_id": row.get("agent_id"),
        "work_url": row.get("work_url"),
        "repo": _repo_from_external(external_id, row.get("work_url")),
        "current_stage": stage,
        "target_stage": target_stage,
        "action": action,
        "settlement_score": round(score, 6),
        "age_hours": round(age, 3),
        "minimum_wait_hours_before_followup": priors["wait_hours"],
        "required_evidence": required_evidence,
        "proof_receipt_digest": row.get("nomad_proof_receipt_digest"),
        "revenue_recognized_usd": round(paid_revenue, 4) if stage == "paid" else 0.0,
        "score_components": {
            "p_accept_prior": round(priors["accept"], 4),
            "p_pay_prior": round(priors["pay"], 4),
            "followup_priority": round(followup_priority, 4),
            "maintainer_burden": round(burden, 4),
            "duplicate_pressure": round(duplicate_pressure, 4),
            "latency_drag": round(latency_drag, 4),
            "stage_multiplier": round(stage_multiplier, 4),
            "latency_denominator": round(latency_denominator, 4),
        },
    }
    out["policy"] = _policy(out)
    return out


def build_settlement_signal_layer(
    *,
    base_url: str = "",
    external_summary: dict[str, Any] | None = None,
    external_reconcile: dict[str, Any] | None = None,
    value_pressure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build Nomad's settlement-first routing surface.

    The whole-system behavior is deliberately conservative: it is grounded in
    queueing, survival-style latency priors, bandit reward separation, and
    stigmergic traces, but it only claims revenue after the external-value
    ledger records stage ``paid``.
    """

    summary = external_summary if isinstance(external_summary, dict) else summarize_external_value_ledger()
    reconcile = external_reconcile if isinstance(external_reconcile, dict) else reconcile_external_value_ledger(live_github=False)
    latest = [item for item in summary.get("latest_by_external") or [] if isinstance(item, dict)]
    followups = _followups_by_external(reconcile)
    repo_counts = _repo_counts(latest)
    now = datetime.now(UTC)
    rows = [
        _row_from_external(
            item,
            followup_item=followups.get(_text(item.get("external_id"), 260), {}),
            repo_count=repo_counts.get(_repo_from_external(item.get("external_id"), item.get("work_url")), 0),
            now=now,
        )
        for item in latest
    ]
    rows.sort(key=lambda item: float(item.get("settlement_score") or 0.0), reverse=True)
    counts = _stage_counts(latest)
    active = counts["found"] + counts["submitted"] + counts["approved"] + counts["merged"]
    human_queue = counts["submitted"] + counts["approved"] + counts["merged"]
    bottleneck_ratio = (human_queue / active) if active else 0.0
    top = rows[0] if rows else {}
    pressure_top = value_pressure.get("top") if isinstance(value_pressure, dict) and isinstance(value_pressure.get("top"), dict) else {}
    return {
        "ok": True,
        "schema": "nomad.settlement_signal_layer.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "read_url": _u(base_url, "/swarm/settlement"),
        "well_known_url": _u(base_url, "/.well-known/nomad-settlement.json"),
        "mechanism": "settlement_observation_field_with_cashflow_guarantee_lock",
        "activation_state": "truthful_influence_enabled_for_merge_settlement_interface",
        "control_law": "apply empirically supported truthful review-pattern interfaces while keeping revenue accounting locked to paid receipts",
        "score_formula": "base_value(stage)*(0.35+p_accept)*(0.12+p_pay)*followup_priority*stage_multiplier / ((1+burden)*(1+duplicate_pressure)*latency_denominator)",
        "evidence_boundary": {
            "cashflow_growth_claim": False,
            "cashflow_guarantee_available": False,
            "literature_status": "empirical_merge_and_trust_proxies_exist; guaranteed_cashflow_for_agentic_prs_or_payor_psychology_not_established",
            "review_burden_pattern_status": "active_as_truthful_merge_latency_proxy_not_cashflow_guarantee",
            "truthful_pattern_use_status": "evidence_known_human_patterns_are_allowed_when_no_deception_or_false_claim_is_introduced",
            "upgrade_rule": "promote from merge_latency_proxy to cashflow_weight only after controlled Nomad ledger comparison shows paid receipts per agent-hour increase",
            "primary_metric": "paid_external_value_receipts_per_agent_hour",
            "negative_control": "submitted_or_approved_without_paid_receipt_must_not_count_as_revenue",
        },
        "summary": {
            "external_event_tail_count": summary.get("event_tail_count", 0),
            "distinct_externals": summary.get("distinct_externals", 0),
            "revenue_recognized_usd_total": round(_num(summary.get("revenue_recognized_usd_total")), 4),
            "stage_counts": counts,
            "active_nonpaid_count": active,
            "human_queue_count": human_queue,
            "merge_settlement_bottleneck": bottleneck_ratio >= 0.5 and human_queue > 0,
            "bottleneck_ratio": round(bottleneck_ratio, 4),
            "top_action": top.get("action", ""),
            "top_external_id": top.get("external_id", ""),
        },
        "top": top,
        "rows": rows[:40],
        "next_action_receipt": {
            "row_id": top.get("row_id", ""),
            "external_id": top.get("external_id", ""),
            "action": (top.get("policy") or {}).get("next_action", ""),
            "stage_guard": "paid_only_counts_as_revenue",
            "work_url": top.get("work_url", ""),
        },
        "human_membrane_contract": {
            "name": "truthful_influence_settlement_membrane",
            "purpose": "use known maintainer review and payor-attention patterns as lawful truthful evidence-ordering interfaces, without false facts or fake pressure",
            "cashflow_evidence_status": "not_guaranteed; paid_receipts_remain_accounting_boundary",
            "outward_shape": [
                "real_facts_first",
                "smallest_reviewer_decision_unit",
                "explicit_verifier_command",
                "real_bounty_or_payment_reference_only_when_present",
            ],
            "compliance_constraints": ["do_not_impersonate_humans", "do_not_apply_deceptive_pressure", "do_not_count_merge_or_approval_as_payment"],
        },
        "influence_operator_catalog": influence_operator_catalog(),
        "operator_activation_contract": {
            "schema": "nomad.truthful_influence_operator_contract.v1",
            "activation": "operators_are_allowed_only_as_fact_ordering_and_friction_reduction",
            "cashflow_learning_rule": "increase operator weight only after paid receipts per agent-hour improve against a logged baseline",
            "disabled_by_default": ["truthful_norm_anchor"],
            "hard_guards": [
                "no_false_fact",
                "no_fake_identity",
                "no_fake_urgency",
                "no_payment_claim_without_receipt",
                "no_social_norm_without_project_specific_evidence",
            ],
            "recommended_next_packet_type": "settlement" if str(top.get("action") or "") == "await_payment_receipt" else "followup" if str(top.get("action") or "").startswith("await_") else "pr",
        },
        "public_packet_compiler_contract": {
            "schema": "nomad.settlement_public_packet_contract.v1",
            "status": "available_unsent_merge_latency_or_receipt_proxy",
            "cashflow_growth_claim": False,
            "cli": "python nomad_cli.py settlement packet --external-id <id> --json",
            "packet_types": ["pr", "followup", "settlement"],
            "rule": "compile sparse evidence packet; do not send automatically; do not count as revenue",
        },
        "pressure_bridge": {
            "value_pressure_top_row": pressure_top.get("row_id", ""),
            "value_pressure_top_action": pressure_top.get("action", ""),
            "interpretation": "value-pressure proposes scarce attention; settlement layer decides whether that attention can collapse into paid value or should wait",
        },
        "links": {
            "external_value": _u(base_url, "/swarm/external-value"),
            "value_pressure": _u(base_url, "/swarm/value-pressure"),
            "bounty_hunter": _u(base_url, "/swarm/bounty-hunter"),
            "public_settlement": _u(base_url, "/.well-known/nomad-settlement.json"),
        },
        "science_basis": [
            {"id": "queueing_review_bottleneck", "basis": "review latency is a service queue; action should reduce reviewer work in progress"},
            {"id": "survival_latency_prior", "basis": "stage age changes expected merge/payment hazard without treating silence as rejection"},
            {"id": "multi_armed_bandit_reward_separation", "basis": "only paid receipts are terminal reward; submitted/approved are censored observations"},
            {"id": "stigmergic_coordination", "basis": "agents leave public proof traces that alter later routing without central role assignment"},
            {"id": "mechanism_design", "basis": "settlement rules must be explicit before work can be trusted by external counterparties"},
        ],
        "science_sources": science_source_registry(),
        "machine_instruction": "route_agents_by_settlement_score_but_emit_only_truthful_evidence_ordered_public_packets",
    }
