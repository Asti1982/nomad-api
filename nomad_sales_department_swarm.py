"""Sales department swarm surface for Nomad.

The point of this module is intentionally anti-human in shape: sales is not a
chatty team, a funnel brainstorm, or majority-voted copy. It is a set of
isolated proof-bearing cells. Each cell converts an observed blocker into a
small buyable packet, routes only through owned/contextual surfaces, and lets
verified receipts move weight.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict


def _now() -> str:
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


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _first_package(packages: list[dict[str, Any]], package_id: str) -> dict[str, Any]:
    return next((item for item in packages if str(item.get("package_id") or "") == package_id), {})


SCIENCE_SOURCES: list[dict[str, str]] = [
    {
        "id": "scaling_agent_systems_2026",
        "title": "Towards a Science of Scaling Agent Systems",
        "url": "https://arxiv.org/abs/2512.08296",
        "nomad_reading": (
            "route by task topology; avoid multi-agent coordination on sequential/tool-heavy work; "
            "centralize verification and use parallel cells only where the work decomposes cleanly"
        ),
    },
    {
        "id": "silo_bench_2026",
        "title": "Silo-Bench: A Scalable Environment for Evaluating Distributed Coordination in Multi-Agent LLM Systems",
        "url": "https://arxiv.org/abs/2603.01045",
        "nomad_reading": (
            "distributed agents can exchange enough information and still fail at integration; "
            "keep seller cells siloed until a typed proof digest is ready"
        ),
    },
    {
        "id": "controlled_agent_debate_2025",
        "title": "Can LLM Agents Really Debate? A Controlled Study of Multi-Agent Debate in Logical Reasoning",
        "url": "https://arxiv.org/abs/2511.07784",
        "nomad_reading": (
            "diversity and reasoning strength matter more than visible confidence or debate order; "
            "majority pressure can suppress independent correction"
        ),
    },
    {
        "id": "self_consistency_cost_2026",
        "title": "Self-Consistency Is Losing Its Edge: Diminishing Returns and Rising Costs in Modern LLMs",
        "url": "https://arxiv.org/abs/2511.00751",
        "nomad_reading": (
            "do not spend samples where a strong single pass is already reliable; reserve multi-path work "
            "for uncertain, high-receipt-proximity cases"
        ),
    },
    {
        "id": "se_agent_2025",
        "title": "SE-Agent: Self-Evolution Trajectory Optimization in Multi-Step Reasoning with LLM-Based Agents",
        "url": "https://arxiv.org/abs/2508.02085",
        "nomad_reading": (
            "recombine and refine successful trajectories instead of asking more agents to agree; "
            "promote only trajectory fragments with verifier value"
        ),
    },
    {
        "id": "apwa_2026",
        "title": "APWA: A Distributed Architecture for Parallelizable Agentic Workflows",
        "url": "https://arxiv.org/abs/2605.15132",
        "nomad_reading": (
            "parallelize non-interfering subproblems with independent resources; avoid cross-chat "
            "communication unless integration proof is explicit"
        ),
    },
]


def build_sales_department_swarm_surface(
    *,
    base_url: str = "",
    buyer_funded_work: Dict[str, Any] | None = None,
    value_cycles: Dict[str, Any] | None = None,
    ad_cycles: Dict[str, Any] | None = None,
    receipt_predictor: Dict[str, Any] | None = None,
    revenue_science: Dict[str, Any] | None = None,
    effective_channels: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compile Nomad's proof-first sales department as machine-readable cells."""
    root = (base_url or "").strip().rstrip("/")
    buyer = _dict(buyer_funded_work)
    packages = _items(buyer.get("buyer_funded_packages"))
    value = _dict(value_cycles)
    ads = _dict(ad_cycles)
    predictor = _dict(receipt_predictor)
    science = _dict(revenue_science)
    quota = _dict(effective_channels)
    receipt_law = _dict(buyer.get("receipt_law"))
    recognized_usd = _num(receipt_law.get("recognized_revenue_usd_total"), 0.0)

    repo_pack = _first_package(packages, "repo_diagnostic_patch_starter")
    endpoint_pack = _first_package(packages, "endpoint_health_patch")
    loop_pack = _first_package(packages, "agent_loop_break_patch")
    settlement_pack = _first_package(packages, "settlement_repair_packet")
    service_entry = _u(root, "/service/e2e?service_type=repo_issue_help")

    sales_cells = [
        {
            "cell_id": "repo_rescue_cell",
            "topology": "single_diagnostic_then_central_verifier",
            "packet": repo_pack.get("package_id") or "repo_diagnostic_patch_starter",
            "buyer_trigger": "public repo, CI, Render, or endpoint blocker with a concrete log",
            "entry_url": service_entry,
            "owned_surface": _u(root, "/nomad.html#buyable-work"),
            "anti_human_move": "do not brainstorm prospects; wait for a failure trace, mint a proof digest, then offer one bounded packet",
            "side_effect_gate": "public reply only after proof digest and operator or buyer approval",
            "cashflow_proximity": "highest",
        },
        {
            "cell_id": "endpoint_health_cell",
            "topology": "curl_probe_shadow_lane",
            "packet": endpoint_pack.get("package_id") or "endpoint_health_patch",
            "buyer_trigger": "404, 500, stale deploy, wrong status, or broken public route",
            "entry_url": _u(root, "/service/e2e?service_type=compute_auth"),
            "owned_surface": _u(root, "/.well-known/nomad-buyer-funded-work.json"),
            "anti_human_move": "sell the smallest observable failure envelope instead of a retainer",
            "side_effect_gate": "owned page and requested replies only",
            "cashflow_proximity": "high",
        },
        {
            "cell_id": "agent_loop_break_cell",
            "topology": "trace_silo_plus_retry_circuit",
            "packet": loop_pack.get("package_id") or "agent_loop_break_patch",
            "buyer_trigger": "repeated tool error, retry storm, or hosted-model spend leak",
            "entry_url": _u(root, "/service/e2e?service_type=loop_break"),
            "owned_surface": _u(root, "/doctor?service_type=loop_break"),
            "anti_human_move": "treat the loop as a loss function, not a conversation problem",
            "side_effect_gate": "draft-only until paid task exists",
            "cashflow_proximity": "high",
        },
        {
            "cell_id": "settlement_repair_cell",
            "topology": "receipt_watchdog_with_low_burden_followup",
            "packet": settlement_pack.get("package_id") or "settlement_repair_packet",
            "buyer_trigger": "work appears merged or approved but payment did not settle",
            "entry_url": _u(root, "/service/e2e?service_type=payment"),
            "owned_surface": _u(root, "/.well-known/nomad-settlement.json"),
            "anti_human_move": "do not celebrate merge; keep value in non-revenue state until receipt",
            "side_effect_gate": "one mature follow-up max after no recent follow-up",
            "cashflow_proximity": "medium_high",
        },
        {
            "cell_id": "bounty_bridge_cell",
            "topology": "read_only_scout_then_duplicate_pressure_filter",
            "packet": "external_bounty_to_repo_packet",
            "buyer_trigger": "clear payout terms and low duplicate pressure",
            "entry_url": _u(root, "/.well-known/nomad-bounty-hunter.json"),
            "owned_surface": _u(root, "/.well-known/nomad-value-cycles.json"),
            "anti_human_move": "ignore crowded bounty excitement; pick only proofable low-dup items",
            "side_effect_gate": "no public claim before local proof digest",
            "cashflow_proximity": "medium",
        },
        {
            "cell_id": "paid_ref_context_cell",
            "topology": "owned_surface_referral_router",
            "packet": "cursor_referral_contextual_answer",
            "buyer_trigger": "user already asks about Cursor, agents, or Nomad setup",
            "entry_url": _u(root, "/.well-known/nomad-referral-swarm.json"),
            "owned_surface": _u(root, "/.well-known/nomad-referral-offers.json"),
            "anti_human_move": "no cold referral blast; let only contextual intent pass",
            "side_effect_gate": "owned surfaces and requested answers only",
            "cashflow_proximity": "medium",
        },
        {
            "cell_id": "syndiodepin_node_cell",
            "topology": "physical_gadget_for_active_runtime_selection",
            "packet": "syndiodepin_transition_worker_exchange",
            "buyer_trigger": "operator runs an active Nomad node or transition worker",
            "entry_url": _u(root, "/.well-known/syndiode-gadgets.json"),
            "owned_surface": _u(root, "/nomad.html#syndiode-gadgets"),
            "anti_human_move": "use the gadget as a node-retention signal, not as consumer electronics inventory",
            "side_effect_gate": "selected active nodes only; no open giveaway until capacity is verified",
            "cashflow_proximity": "medium",
        },
        {
            "cell_id": "key_leak_recovery_cell",
            "topology": "secret_free_security_scope",
            "packet": "api_key_rotation_diagnostic",
            "buyer_trigger": "OpenAI, Stripe, or other API key leak notice without exposing keys",
            "entry_url": _u(root, "/service/e2e?service_type=repo_issue_help"),
            "owned_surface": _u(root, "/.well-known/nomad-spend-guard.json"),
            "anti_human_move": "sell a public-proof cleanup scope while refusing to ingest secrets",
            "side_effect_gate": "no secret text, no screenshots with keys, no account mutation",
            "cashflow_proximity": "medium_high",
        },
        {
            "cell_id": "receipt_case_study_cell",
            "topology": "case_digest_without_revenue_claim",
            "packet": "paid_receipt_story_after_settlement",
            "buyer_trigger": "first positive receipt exists",
            "entry_url": _u(root, "/.well-known/nomad-external-value.json"),
            "owned_surface": _u(root, "/.well-known/nomad-work-receipts.json"),
            "anti_human_move": "delay story and social proof until the ledger has a paid event",
            "side_effect_gate": "blocked until positive receipt",
            "cashflow_proximity": "deferred_but_compounds",
        },
    ]

    active_value_cycles = [
        {
            "cycle_id": "render_build_rescue_paid_packet",
            "cell_id": "repo_rescue_cell",
            "first_action": "detect failed deploy or build log, create diagnostic digest, route to repo_diagnostic_patch_starter",
            "buyer_entry": service_entry,
            "terminal_receipt": "verified MetaMask/native transfer or external paid receipt",
        },
        {
            "cycle_id": "github_actions_red_to_patch_packet",
            "cell_id": "repo_rescue_cell",
            "first_action": "read failing workflow log, produce smallest repro path and no-post reply draft",
            "buyer_entry": service_entry,
            "terminal_receipt": "task paid and verifier checklist delivered",
        },
        {
            "cycle_id": "endpoint_404_500_rescue",
            "cell_id": "endpoint_health_cell",
            "first_action": "curl public endpoint, classify stale deploy versus missing route, price a bounded patch pack",
            "buyer_entry": _u(root, "/service/e2e?service_type=compute_auth"),
            "terminal_receipt": "paid task plus endpoint verifier digest",
        },
        {
            "cycle_id": "agent_loop_spend_cut",
            "cell_id": "agent_loop_break_cell",
            "first_action": "turn repeated agent/tool failure into stop condition and retry-circuit package",
            "buyer_entry": _u(root, "/service/e2e?service_type=loop_break"),
            "terminal_receipt": "paid task plus circuit-breaker digest",
        },
        {
            "cycle_id": "settlement_repair_watch",
            "cell_id": "settlement_repair_cell",
            "first_action": "watch mature merged/approved item; draft one low-burden follow-up only when not recent",
            "buyer_entry": _u(root, "/.well-known/nomad-settlement.json"),
            "terminal_receipt": "public payout confirmation or positive balance",
        },
        {
            "cycle_id": "bounty_low_duplicate_scout",
            "cell_id": "bounty_bridge_cell",
            "first_action": "score payout clarity, duplicate pressure, local proof path, and maintainer burden",
            "buyer_entry": _u(root, "/.well-known/nomad-bounty-hunter.json"),
            "terminal_receipt": "external paid receipt only",
        },
        {
            "cycle_id": "owned_referral_intent_capture",
            "cell_id": "paid_ref_context_cell",
            "first_action": "surface referral only where buyer intent is already present",
            "buyer_entry": _u(root, "/.well-known/nomad-referral-swarm.json"),
            "terminal_receipt": "program reward credit, not clicks",
        },
        {
            "cycle_id": "syndiodepin_transition_worker_exchange",
            "cell_id": "syndiodepin_node_cell",
            "first_action": "rank active node candidates, reserve pin only after worker proof and capacity check",
            "buyer_entry": _u(root, "/.well-known/syndiode-gadgets.json"),
            "terminal_receipt": "500 EUR contribution or selected non-cash transition-worker proof",
        },
        {
            "cycle_id": "key_leak_rotation_packet",
            "cell_id": "key_leak_recovery_cell",
            "first_action": "secret-free repo scan scope, rotation checklist, spend-cap verification, and log-review plan",
            "buyer_entry": service_entry,
            "terminal_receipt": "paid task with no secret capture",
        },
        {
            "cycle_id": "first_receipt_case_study",
            "cell_id": "receipt_case_study_cell",
            "first_action": "after paid receipt, compile public proof story and route it into owned surfaces",
            "buyer_entry": _u(root, "/.well-known/nomad-work-receipts.json"),
            "terminal_receipt": "already-paid receipt required before story is enabled",
        },
    ]

    sales_queue = [
        {
            "rank": 1,
            "action": "attach repo_diagnostic_patch_starter to every owned product surface that mentions build, CI, endpoint, or repo help",
            "why": "fastest direct buyer route and already implemented MetaMask task flow",
            "route": service_entry,
        },
        {
            "rank": 2,
            "action": "run read-only scouts for failed public builds and OSS issues, but emit only proof digests and no public messages",
            "why": "research says coordination overhead kills sequential work; one verifier-controlled cell is cheaper",
            "route": _u(root, "/.well-known/nomad-sales-department.json"),
        },
        {
            "rank": 3,
            "action": "route all public promotion candidates through effective-channel quota before ad-cycle queue",
            "why": "homogeneous double votes should be capped before they look like demand",
            "route": _u(root, "/swarm/sales-department/events"),
        },
        {
            "rank": 4,
            "action": "keep RustChain settlement checking active but non-revenue until receipt",
            "why": "the first payout proof compounds only if the ledger stays credible",
            "route": _u(root, "/.well-known/nomad-external-value.json"),
        },
    ]

    quota_summary = _dict(quota.get("summary"))
    value_summary = _dict(value.get("summary"))
    ad_summary = _dict(ads.get("summary"))
    predictor_summary = _dict(predictor.get("summary"))
    science_summary = _dict(science.get("summary"))
    plan_core = {
        "recognized_usd": recognized_usd,
        "cells": [cell["cell_id"] for cell in sales_cells],
        "cycles": [cycle["cycle_id"] for cycle in active_value_cycles],
        "packages": [item.get("package_id") for item in packages],
    }

    return {
        "ok": True,
        "schema": "nomad.sales_department_swarm.v1",
        "generated_at": _now(),
        "public_base_url": root,
        "surface_digest": f"nomad-sales-department-{_digest(plan_core)}",
        "read_url": _u(root, "/swarm/sales-department"),
        "well_known_url": _u(root, "/.well-known/nomad-sales-department.json"),
        "event_url": _u(root, "/swarm/sales-department/events"),
        "summary": {
            "sales_cell_count": len(sales_cells),
            "active_value_cycle_count": len(active_value_cycles),
            "buyer_funded_package_count": len(packages),
            "recognized_revenue_usd_total": recognized_usd,
            "source_value_cycle_count": int(value_summary.get("cycle_count") or 0),
            "source_ad_cycle_count": int(ad_summary.get("cycle_count") or 0),
            "receipt_predictor_cycle_count": int(predictor_summary.get("cycle_count") or 0),
            "revenue_science_experiment_count": int(science_summary.get("experiment_count") or 0),
            "effective_channel_count": int(
                quota_summary.get("effective_channel_count")
                or quota_summary.get("admissible_channel_count")
                or quota_summary.get("channel_count")
                or 0
            ),
        },
        "operating_principles": [
            {
                "id": "topology_before_headcount",
                "rule": "choose single, centralized, or parallel cells by task shape before adding agents",
                "human_counterintuition": "a smaller sales cell can dominate a larger swarm when the job is sequential",
            },
            {
                "id": "anti_majority_sales",
                "rule": "preserve proof-bearing minority channels; cap homogeneous agreement before it becomes spend",
                "human_counterintuition": "the sales department is rewarded for suppressing consensus when it lacks independent evidence",
            },
            {
                "id": "silo_then_digest",
                "rule": "seller cells do not share scratchpads until they produce typed proof digests",
                "human_counterintuition": "coordination is treated as a cost, not a virtue",
            },
            {
                "id": "receipt_weighting",
                "rule": "only verified paid receipts or program reward credits increase route weight",
                "human_counterintuition": "attention, merge, approval, and simulated buyer intent remain non-revenue",
            },
            {
                "id": "owned_contextual_surfaces",
                "rule": "promote on owned surfaces and requested contexts; block cold spread",
                "human_counterintuition": "the best ad is often a machine-readable contract waiting in the right place",
            },
        ],
        "science_sources": SCIENCE_SOURCES,
        "sales_cells": sales_cells,
        "active_value_cycles": active_value_cycles,
        "sales_queue": sales_queue,
        "top_active_route": sales_queue[0],
        "guards": {
            "no_cold_spam": True,
            "no_public_send_without_proof_and_approval": True,
            "no_revenue_without_positive_receipt": True,
            "no_secret_capture": True,
            "stripe_subscription_enabled": False,
            "default_paid_rail": "metamask_native_transfer",
            "api_spend_default": "local_or_zero_spend_first",
        },
        "machine_instruction": [
            "start with repo_rescue_cell for direct cashflow",
            "do not add agents to sequential tasks unless a verifier cell proves benefit",
            "treat duplicate channel agreement as saturation, not confidence",
            "use /swarm/sales-department/events to gate public-action or paid-receipt candidates",
            "record revenue only through existing receipt ledgers after positive settlement",
        ],
    }


def evaluate_sales_department_event(
    payload: Dict[str, Any] | None,
    *,
    base_url: str = "",
    sales_surface: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Evaluate one sales event without posting, sending, or booking revenue."""
    body = _dict(payload)
    surface = _dict(sales_surface)
    cell_id = str(body.get("cell_id") or body.get("cell") or "repo_rescue_cell").strip()
    stage = str(body.get("stage") or body.get("intent") or "draft").strip().lower()
    send_requested = bool(
        body.get("send")
        or body.get("publish")
        or body.get("public_action_requested")
        or stage in {"send", "send_request", "publish"}
    )
    human_approved = bool(body.get("human_approved") or body.get("operator_approved")) or str(
        body.get("approval") or ""
    ).strip().lower() in {"approved", "human_approved", "operator_approved", "buyer_approved"}
    proof_digest = str(
        body.get("proof_digest")
        or body.get("diagnostic_digest")
        or body.get("verifier_trace_digest")
        or ""
    ).strip()
    buyer_intent = str(body.get("buyer_intent_digest") or body.get("buyer_intent") or "").strip()
    settlement_ref = str(body.get("settlement_ref") or body.get("receipt_ref") or body.get("tx_hash") or "").strip()
    amount_usd = _num(body.get("amount_usd") or body.get("paid_amount_usd"), 0.0)
    blockers: list[str] = []
    allowed = True
    stage_kind = "shadow_draft"
    side_effect_allowed = False
    paid_receipt_candidate = False

    if not cell_id:
        blockers.append("cell_id_required")
    if stage == "paid" or amount_usd > 0.0:
        stage_kind = "paid_receipt_candidate"
        if amount_usd <= 0.0:
            blockers.append("positive_amount_required_for_paid")
        if not settlement_ref:
            blockers.append("settlement_ref_required_for_paid")
        if not proof_digest:
            blockers.append("proof_digest_required_for_paid")
        paid_receipt_candidate = not blockers
    elif send_requested:
        stage_kind = "public_send_candidate"
        if not proof_digest:
            blockers.append("proof_digest_required_before_public_send")
        if not buyer_intent:
            blockers.append("buyer_intent_digest_required_before_public_send")
        if not human_approved:
            blockers.append("human_or_buyer_approval_required_before_public_send")
        side_effect_allowed = not blockers
    else:
        if stage in {"discover", "observe"}:
            stage_kind = "read_only_observation"
        elif proof_digest:
            stage_kind = "proof_bearing_draft"
        else:
            stage_kind = "shadow_draft"

    allowed = not blockers
    return {
        "ok": True,
        "schema": "nomad.sales_department_event_decision.v1",
        "generated_at": _now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "surface_digest": surface.get("surface_digest") or "",
        "sales_cycle_allowed": allowed,
        "side_effect_allowed": side_effect_allowed,
        "side_effect_performed": False,
        "paid_receipt_candidate": paid_receipt_candidate,
        "revenue_recorded": False,
        "cell_id": cell_id,
        "stage": stage,
        "stage_kind": stage_kind,
        "blockers": blockers,
        "decision": "admit_candidate" if allowed else "hold_candidate",
        "next_route": _u(base_url, "/service/e2e?service_type=repo_issue_help"),
        "machine_note": (
            "This gate never sends public messages and never books revenue; it only decides whether "
            "a sales candidate is safe to hand to the existing task, ad-cycle, or receipt ledger."
        ),
    }
