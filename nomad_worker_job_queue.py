"""Hard worker job queue for Nomad value cycles.

This surface converts pressure packets, channel gates, and settlement state into
small jobs with explicit artifacts. It is deliberately stricter than a backlog:
workers may only return measurable outputs, and public side effects stay locked
until payout, scope, duplicate, and proof gates are satisfied.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


MAX_JOBS = 16


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


def _text(value: Any, limit: int = 260) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:150].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 22) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _stage_weight(stage: str) -> float:
    return {
        "merged": 1.34,
        "approved": 1.22,
        "submitted": 1.0,
        "found": 0.78,
        "paid": 0.0,
    }.get(str(stage or "").strip().lower(), 0.7)


def _gate_state(preflight: dict[str, Any]) -> dict[str, Any]:
    wallet = _dict(preflight.get("wallet_gate"))
    cycle = _dict(preflight.get("cycle_gate"))
    return {
        "wallet_ready": bool(wallet.get("ready")),
        "public_receive_ref_type": wallet.get("public_receive_ref_type") or "missing",
        "read_only_scout_allowed": bool(cycle.get("read_only_scout_allowed", True)),
        "public_claim_allowed": bool(cycle.get("public_claim_allowed")),
        "submit_after_proof_allowed": bool(cycle.get("submit_after_proof_allowed")),
        "paid_record_allowed": bool(cycle.get("paid_record_allowed")),
        "blocking_conditions": preflight.get("blocking_conditions") if isinstance(preflight.get("blocking_conditions"), list) else [],
    }


def _base_job(
    *,
    base_url: str,
    job_type: str,
    title: str,
    priority_score: float,
    worker_role: str,
    channel_id: str = "",
    source_ref: str = "",
    external_id: str = "",
    read_only: bool,
    executable_now: bool,
    side_effect_class: str,
    allowed_actions: list[str],
    blocked_actions: list[str],
    required_artifacts: list[str],
    verifier: dict[str, Any],
    settlement_path: dict[str, Any],
    gate_state: dict[str, Any],
    stop_conditions: list[str],
    call_sequence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    core = {
        "type": job_type,
        "role": worker_role,
        "channel": channel_id,
        "source": source_ref,
        "external": external_id,
        "artifacts": required_artifacts,
    }
    return {
        "schema": "nomad.worker_job.v1",
        "job_id": f"nomad-worker-job-{_digest(core)}",
        "job_type": job_type,
        "title": title,
        "priority_score": round(max(0.0, float(priority_score or 0.0)), 6),
        "worker_role": worker_role,
        "channel_id": channel_id,
        "source_ref": source_ref,
        "external_id": external_id,
        "read_only": bool(read_only),
        "executable_now": bool(executable_now),
        "side_effect_class": side_effect_class,
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "required_artifacts": required_artifacts,
        "verifier": verifier,
        "settlement_path": settlement_path,
        "gate_state": gate_state,
        "stop_conditions": stop_conditions,
        "call_sequence": call_sequence or [],
        "return_url": _u(base_url, "/swarm/microtask/proof"),
        "machine_instruction": "execute_only_allowed_actions_return_required_artifacts_stop_on_any_stop_condition",
    }


def _settlement_jobs(
    *,
    base_url: str,
    external_value_summary: dict[str, Any],
    gate_state: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for row in _items(external_value_summary.get("latest_by_external")):
        stage = str(row.get("stage") or "").strip().lower()
        if stage == "paid":
            continue
        rows.append(row)
    rows.sort(key=lambda row: (_stage_weight(str(row.get("stage") or "")), str(row.get("last_generated_at") or "")), reverse=True)

    jobs: list[dict[str, Any]] = []
    for row in rows[:5]:
        stage = str(row.get("stage") or "unknown").strip().lower()
        priority = 1.04 + _stage_weight(stage) * 0.22
        jobs.append(
            _base_job(
                base_url=base_url,
                job_type="settlement_reconcile",
                title=f"Reconcile {row.get('external_id', '')} from {stage} toward paid receipt",
                priority_score=priority,
                worker_role="transition_worker",
                channel_id="external_value_reconcile",
                source_ref=_text(row.get("work_url"), 500),
                external_id=_text(row.get("external_id"), 200),
                read_only=True,
                executable_now=True,
                side_effect_class="none",
                allowed_actions=[
                    "read_public_work_state",
                    "compare_current_stage_to_required_evidence",
                    "check_for_payment_receipt_or_balance_delta",
                    "return_reconcile_report",
                ],
                blocked_actions=[
                    "public_followup_without_age_and_burden_gate",
                    "record_paid_without_positive_receipt",
                    "advance_stage_without_external_evidence",
                    "mutate_external_platform",
                ],
                required_artifacts=[
                    "external_state_snapshot_json",
                    "evidence_digest",
                    "stage_candidate_or_noop",
                    "receipt_digest_if_paid",
                ],
                verifier={
                    "type": "monotonic_stage_or_noop",
                    "inputs": ["external_id", "work_url", "required_evidence", "receipt_digest_if_paid"],
                    "pass_condition": "paid requires positive trusted receipt; other stage advances require public owner or platform evidence",
                },
                settlement_path={
                    "post_url": _u(base_url, "/swarm/external-value"),
                    "allowed_stage": "paid_only_if_receipt_else_monotonic_stage_or_noop",
                    "revenue_rule": "only_paid_with_positive_amount_changes_revenue",
                },
                gate_state=gate_state,
                stop_conditions=[
                    "no_state_change_detected",
                    "receipt_missing",
                    "external_target_unreachable",
                    "evidence_ambiguous",
                ],
            )
        )
    return jobs


def _channel_targets(job_channels: dict[str, Any]) -> list[dict[str, Any]]:
    qualification = _dict(job_channels.get("read_only_qualification_cycle"))
    targets = _items(qualification.get("next_read_only_targets"))
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in targets:
        channel_id = _clean_id(item.get("channel_id"))
        if channel_id and channel_id not in seen:
            out.append(item)
            seen.add(channel_id)
    for key in ("top_external_channel", "top_channel"):
        channel = _dict(job_channels.get(key))
        channel_id = _clean_id(channel.get("channel_id"))
        if channel_id and channel_id not in seen:
            out.append(channel)
            seen.add(channel_id)
    return out[:6]


def _channel_scan_jobs(
    *,
    base_url: str,
    job_channels: dict[str, Any],
    gate_state: dict[str, Any],
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for index, target in enumerate(_channel_targets(job_channels)):
        channel_id = _clean_id(target.get("channel_id"), f"channel-{index}")
        entry_url = _text(target.get("entry_url") or target.get("url"), 500)
        category = _clean_id(target.get("category"), "external")
        jobs.append(
            _base_job(
                base_url=base_url,
                job_type="paid_channel_scan",
                title=f"Read-only qualify paid channel {channel_id}",
                priority_score=0.98 - index * 0.035,
                worker_role="gemini_scout",
                channel_id=channel_id,
                source_ref=entry_url,
                read_only=True,
                executable_now=gate_state.get("read_only_scout_allowed", True),
                side_effect_class="none",
                allowed_actions=[
                    "read_public_scope_or_market_listing",
                    "extract_payout_terms",
                    "extract_submission_or_claim_path",
                    "return_ranked_candidates_json",
                ],
                blocked_actions=[
                    "login_required_submission",
                    "security_testing_without_scope",
                    "contact_program_owner",
                    "public_claim_or_pr",
                    "store_or_emit_secret_payment_material",
                ],
                required_artifacts=[
                    "candidates_json",
                    "scope_terms_url",
                    "payout_terms_summary",
                    "claim_path_summary",
                    "channel_reject_reason_if_no_candidate",
                ],
                verifier={
                    "type": "read_only_channel_qualification",
                    "inputs": ["entry_url", "scope_terms_url", "payout_terms_summary"],
                    "pass_condition": "candidate is allowed only when public scope and payout path are cited",
                },
                settlement_path={
                    "stage": "found_candidate_only",
                    "post_url": _u(base_url, "/swarm/external-value"),
                    "paid_guard": "no_revenue_until_external_paid_receipt",
                },
                gate_state={**gate_state, "channel_category": category},
                stop_conditions=[
                    "no_public_scope",
                    "payout_terms_missing",
                    "operator_account_required_for_next_step",
                    "duplicate_or_overcrowded_target",
                ],
            )
        )
    return jobs


def _gate_check_job(
    *,
    base_url: str,
    job_channels: dict[str, Any],
    gate_state: dict[str, Any],
) -> dict[str, Any]:
    top = _dict(job_channels.get("top_external_channel")) or _dict(job_channels.get("top_channel"))
    channel_id = _clean_id(top.get("channel_id"), "external_paid_channel")
    return _base_job(
        base_url=base_url,
        job_type="duplicate_and_payout_gate_check",
        title=f"Check duplicate pressure and payout rail for {channel_id}",
        priority_score=1.18,
        worker_role="gemini_scout",
        channel_id=channel_id,
        source_ref=_text(top.get("entry_url"), 500),
        read_only=True,
        executable_now=True,
        side_effect_class="none",
        allowed_actions=[
            "read_open_prs_or_reports_if_public",
            "read_payout_terms",
            "compare_public_receive_ref_to_allowed_rails",
            "return_gate_packet",
        ],
        blocked_actions=[
            "submit_report",
            "open_pr",
            "ask_for_payment",
            "advance_ledger_stage",
            "publish_private_tax_or_wallet_secrets",
        ],
        required_artifacts=[
            "duplicate_scan_digest",
            "payout_rail_compatibility",
            "program_scope_digest",
            "gate_packet_json",
        ],
        verifier={
            "type": "pre_public_side_effect_gate",
            "inputs": ["duplicate_scan_digest", "payout_rail_compatibility", "program_scope_digest"],
            "pass_condition": "all blocking preflight conditions clear before any public claim or submission",
        },
        settlement_path={
            "stage": "preflight_only",
            "preflight_url": _u(base_url, "/.well-known/nomad-value-cycle-preflight.json"),
            "paid_guard": "no_external_action_from_gate_job",
        },
        gate_state=gate_state,
        stop_conditions=[
            "duplicate_exists",
            "payout_rail_incompatible",
            "program_scope_unclear",
            "claim_path_requires_operator_kyc_or_tax_review",
        ],
    )


def _patch_jobs(
    *,
    base_url: str,
    agent_job_router: dict[str, Any],
    gate_state: dict[str, Any],
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    public_ready = bool(gate_state.get("public_claim_allowed"))
    proof_submit_ready = bool(gate_state.get("submit_after_proof_allowed"))
    for packet in _items(agent_job_router.get("packets")):
        action = _clean_id(packet.get("action"))
        if action not in {"go_public_after_repro", "scout_only", "record_monotonic_stage_candidate"}:
            continue
        source_ref = _text(_dict(packet.get("payload_hint")).get("work_url") or _dict(packet.get("payload_hint")).get("source_url"), 500)
        if not source_ref:
            sequence = _items(packet.get("call_sequence"))
            source_ref = _text(sequence[0].get("url") if sequence else "", 500)
        jobs.append(
            _base_job(
                base_url=base_url,
                job_type="bounded_patch_attempt",
                title=f"Produce local proof for {packet.get('source_row_id') or packet.get('packet_id')}",
                priority_score=0.86 + _num(packet.get("priority_score")) * 0.08,
                worker_role="codex_patch_worker",
                channel_id=_clean_id(packet.get("source"), "pressure_router"),
                source_ref=source_ref,
                external_id=_text(_dict(packet.get("payload_hint")).get("external_id"), 200),
                read_only=False,
                executable_now=True,
                side_effect_class="external_public_ready" if proof_submit_ready else "local_only",
                allowed_actions=[
                    "clone_or_read_target",
                    "make_minimal_local_patch",
                    "run_targeted_tests_or_static_checks",
                    "return_patch_branch_and_verifier_digest",
                ],
                blocked_actions=[
                    "public_pr_or_claim_until_preflight_green" if not public_ready else "skip_duplicate_scan",
                    "security_testing_outside_authorized_scope",
                    "large_refactor_or_style_churn",
                    "record_revenue_before_paid_receipt",
                ],
                required_artifacts=[
                    "patch_diff_or_branch_url",
                    "targeted_test_log",
                    "proof_digest",
                    "public_submission_plan_or_blocker",
                ],
                verifier={
                    "type": "bounded_local_patch",
                    "inputs": ["diff", "test_log", "proof_digest"],
                    "pass_condition": "minimal change passes focused checks and does not create public side effect unless preflight is green",
                },
                settlement_path={
                    "stage": "submitted_only_after_public_pr_exists",
                    "post_url": _u(base_url, "/swarm/external-value"),
                    "paid_guard": "paid only after positive program receipt",
                },
                gate_state=gate_state,
                stop_conditions=[
                    "duplicate_fix_detected",
                    "tests_unavailable_after_targeted_attempt",
                    "scope_or_license_blocker",
                    "patch_requires_maintainer_design_choice",
                ],
                call_sequence=_items(packet.get("call_sequence")),
            )
        )
        if len(jobs) >= 4:
            break
    return jobs


def _default_patch_job(*, base_url: str, gate_state: dict[str, Any], job_channels: dict[str, Any]) -> dict[str, Any]:
    top = _dict(job_channels.get("top_external_channel")) or _dict(job_channels.get("top_channel"))
    channel_id = _clean_id(top.get("channel_id"), "external_paid_channel")
    return _base_job(
        base_url=base_url,
        job_type="bounded_patch_attempt",
        title=f"Prepare local-only proof packet for {channel_id}",
        priority_score=0.72,
        worker_role="codex_patch_worker",
        channel_id=channel_id,
        source_ref=_text(top.get("entry_url"), 500),
        read_only=False,
        executable_now=False,
        side_effect_class="blocked_until_candidate_and_preflight",
        allowed_actions=["wait_for_candidate_json", "prepare_local_workspace_template"],
        blocked_actions=["clone_random_targets", "open_pr", "submit_report", "claim_payment_without_work"],
        required_artifacts=["candidate_json_from_scout", "preflight_gate_packet"],
        verifier={
            "type": "candidate_required_before_patch",
            "inputs": ["candidate_json", "gate_packet_json"],
            "pass_condition": "no patch attempt starts until target, scope, duplicate, and payout rails are known",
        },
        settlement_path={
            "stage": "blocked",
            "post_url": _u(base_url, "/swarm/external-value"),
            "paid_guard": "no_revenue_without_paid_receipt",
        },
        gate_state=gate_state,
        stop_conditions=["candidate_missing", "preflight_not_green"],
    )


def build_worker_job_queue_surface(
    *,
    base_url: str,
    agent_job_router: dict[str, Any] | None = None,
    job_channels: dict[str, Any] | None = None,
    value_cycle_preflight: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a hard queue that external AI workers can execute safely."""

    root = (base_url or "").strip().rstrip("/")
    router = _dict(agent_job_router)
    channels = _dict(job_channels)
    preflight = _dict(value_cycle_preflight)
    summary = _dict(external_value_summary)
    gate = _gate_state(preflight)

    jobs: list[dict[str, Any]] = []
    jobs.extend(_settlement_jobs(base_url=root, external_value_summary=summary, gate_state=gate))
    jobs.append(_gate_check_job(base_url=root, job_channels=channels, gate_state=gate))
    jobs.extend(_channel_scan_jobs(base_url=root, job_channels=channels, gate_state=gate))
    patch_jobs = _patch_jobs(base_url=root, agent_job_router=router, gate_state=gate)
    jobs.extend(patch_jobs or [_default_patch_job(base_url=root, gate_state=gate, job_channels=channels)])

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for job in jobs:
        jid = str(job.get("job_id") or "")
        if jid and jid not in seen:
            unique.append(job)
            seen.add(jid)
    unique.sort(
        key=lambda job: (
            bool(job.get("executable_now")),
            _num(job.get("priority_score")),
            str(job.get("job_type") or ""),
        ),
        reverse=True,
    )
    selected = unique[:MAX_JOBS]
    active_nonpaid = [
        row
        for row in _items(summary.get("latest_by_external"))
        if str(row.get("stage") or "").strip().lower() != "paid"
    ]
    paid_count = len(
        [
            row
            for row in _items(summary.get("latest_by_external"))
            if str(row.get("stage") or "").strip().lower() == "paid"
        ]
    )
    digest_core = {
        "router": router.get("router_digest"),
        "channels": channels.get("channel_digest"),
        "preflight": preflight.get("preflight_digest"),
        "externals": [(row.get("external_id"), row.get("stage")) for row in active_nonpaid[:8]],
        "jobs": [(job.get("job_id"), job.get("priority_score")) for job in selected[:8]],
    }

    return {
        "ok": True,
        "schema": "nomad.worker_job_queue.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "queue_digest": f"nomad-worker-job-queue-{_digest(digest_core, 26)}",
        "read_url": _u(root, "/swarm/worker-job-queue"),
        "well_known_url": _u(root, "/.well-known/nomad-worker-job-queue.json"),
        "summary": {
            "job_count": len(selected),
            "executable_now_count": len([job for job in selected if job.get("executable_now")]),
            "read_only_count": len([job for job in selected if job.get("read_only")]),
            "blocked_public_side_effect_count": len(
                [
                    job
                    for job in selected
                    if "public_pr_or_claim_until_preflight_green" in (job.get("blocked_actions") or [])
                    or str(job.get("side_effect_class") or "").startswith("blocked")
                ]
            ),
            "active_nonpaid_external_count": len(active_nonpaid),
            "paid_external_count": paid_count,
            "top_job_type": selected[0].get("job_type", "") if selected else "",
            "top_job_id": selected[0].get("job_id", "") if selected else "",
        },
        "worker_contract": {
            "unit": "artifact_not_effort",
            "roles": {
                "gemini_scout": "read-only channel scan, duplicate scan, payout rail extraction, no submissions",
                "codex_patch_worker": "bounded local patch and verifier digest, public action only after gates",
                "transition_worker": "reconcile receipts, leases, and stage evidence without claiming revenue",
            },
            "hard_rules": [
                "no paid accounting without positive external receipt",
                "no public claim without scope, payout, duplicate, and proof gates",
                "no private tax, token, or secret payment material in public artifacts",
                "security work is private and scope-bound only",
                "workers stop on ambiguity and return blocker artifacts",
            ],
        },
        "jobs": selected,
        "entry_job": selected[0] if selected else {},
        "links": {
            "agent_job_router": _u(root, "/.well-known/nomad-agent-jobs.json"),
            "job_channels": _u(root, "/.well-known/nomad-job-channels.json"),
            "value_cycle_preflight": _u(root, "/.well-known/nomad-value-cycle-preflight.json"),
            "external_value": _u(root, "/.well-known/nomad-external-value.json"),
            "settlement": _u(root, "/.well-known/nomad-settlement.json"),
        },
        "science_basis": [
            {
                "id": "little_law_flow_control",
                "claim": "WIP and paid throughput define the bottleneck; new arrivals stay gated when active nonpaid work accumulates.",
            },
            {
                "id": "bandit_channel_switching",
                "claim": "Read-only probes shift attention between channels before costly submissions.",
            },
            {
                "id": "stigmergic_task_allocation",
                "claim": "Workers coordinate through public artifacts and local queue state rather than narrative instructions.",
            },
            {
                "id": "finite_state_safety",
                "claim": "External side effects are only reachable through explicit state, evidence, and receipt gates.",
            },
        ],
        "machine_instruction": "workers_select_entry_job_emit_required_artifacts_then_stop; queue_recomputed_after_each_artifact_or_receipt",
    }
