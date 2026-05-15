"""Shadow-only advertising and acquisition cycle mesh for Nomad.

Ad cycles are intentionally weaker than value cycles: they may discover,
draft, quota-check, and queue campaign candidates, but they never send ads or
book revenue. Promotion into a value cycle requires independent evidence
channels and a later paid receipt.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.ad_cycle_mesh.v1"
EVENT_SCHEMA = "nomad.ad_cycle_event_receipt.v1"

STAGES = ("discover", "draft", "quota", "shadow", "queue", "send_request")
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


def _text(value: Any, limit: int = 360) -> str:
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
            if _clean_id(key) in SECRET_KEYS:
                return True
            if _contains_forbidden(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _digest_present(value: Any) -> bool:
    text = _text(value, 220).lower()
    return text.startswith(("sha256:", "sha512:", "b3:", "receipt:", "nomad-")) and len(text) >= 12


def _effective_state(effective_channels: dict[str, Any]) -> dict[str, Any]:
    thresholds = _dict(effective_channels.get("thresholds"))
    summary = _dict(effective_channels.get("recent_summary"))
    return {
        "mode": _text(effective_channels.get("mode"), 120),
        "min_effective_ratio": _num(thresholds.get("min_effective_channel_ratio"), 0.72),
        "recent_quota_shift_count": int(_num(summary.get("quota_shift_count"))),
        "recent_homogeneous_cap_count": int(_num(summary.get("homogeneous_cap_count"))),
        "event_url": _text(effective_channels.get("event_url"), 500),
    }


def _value_state(value_cycles: dict[str, Any]) -> dict[str, Any]:
    summary = _dict(value_cycles.get("summary"))
    return {
        "cycle_count": int(_num(summary.get("cycle_count"))),
        "top_value_cycle_id": _text(summary.get("top_cycle_id"), 150),
        "recognized_revenue_usd_total": _num(summary.get("recognized_revenue_usd_total")),
    }


def _preflight_state(preflight: dict[str, Any]) -> dict[str, Any]:
    wallet = _dict(preflight.get("wallet_gate"))
    cycle = _dict(preflight.get("cycle_gate"))
    blocking = preflight.get("blocking_conditions") if isinstance(preflight.get("blocking_conditions"), list) else []
    return {
        "wallet_ready": bool(wallet.get("ready")),
        "read_only_scout_allowed": bool(cycle.get("read_only_scout_allowed", True)),
        "public_claim_allowed": bool(cycle.get("public_claim_allowed")),
        "submit_after_proof_allowed": bool(cycle.get("submit_after_proof_allowed")),
        "blocking_conditions": [str(item) for item in blocking],
    }


def _cycle_templates(base_url: str) -> list[dict[str, Any]]:
    return [
        {
            "cycle_id": "agent_card_discovery_draft",
            "label": "Agent-card discovery -> outreach draft",
            "audience": "public_agent_endpoint",
            "channel": "agent_card",
            "entry_url": _u(base_url, "/.well-known/agent-card.json"),
            "action_url": _u(base_url, "/agent-campaigns"),
            "verify_url": _u(base_url, "/.well-known/nomad-effective-channels.json"),
            "service_type": "compute_auth",
            "draft_query": "agent-card compute auth blocker",
            "required_artifacts": ["agent_card_url", "endpoint_digest", "pain_hint", "effective_channel_receipt"],
            "base_score": 1.14,
            "human_channel": False,
        },
        {
            "cycle_id": "mcp_directory_tool_gap_draft",
            "label": "MCP/tool directory -> tool-gap draft",
            "audience": "mcp_server_operator",
            "channel": "mcp_directory",
            "entry_url": _u(base_url, "/swarm/tool-gap"),
            "action_url": _u(base_url, "/agent-campaigns"),
            "verify_url": _u(base_url, "/swarm/value-cycles/events"),
            "service_type": "mcp_integration",
            "draft_query": "mcp server integration failure tool gap",
            "required_artifacts": ["server_url", "tool_gap_digest", "integration_blocker", "quota_receipt"],
            "base_score": 1.08,
            "human_channel": False,
        },
        {
            "cycle_id": "github_issue_value_reply_draft",
            "label": "GitHub issue -> value-first reply draft",
            "audience": "oss_maintainer_or_agent_user",
            "channel": "github_issue",
            "entry_url": _u(base_url, "/leads"),
            "action_url": _u(base_url, "/lead-conversions"),
            "verify_url": _u(base_url, "/.well-known/nomad-value-cycles.json"),
            "service_type": "compute_auth",
            "draft_query": "AI agent auth stuck loop verification failure",
            "required_artifacts": ["issue_url", "local_repro_or_diagnosis_digest", "no_duplicate_reply_digest", "quota_receipt"],
            "base_score": 1.05,
            "human_channel": True,
        },
        {
            "cycle_id": "peer_witness_contract_draft",
            "label": "Peer witness contract -> agent-native draft",
            "audience": "agent_runtime",
            "channel": "inter_agent_witness",
            "entry_url": _u(base_url, "/.well-known/nomad-inter-agent-witness-offer.json"),
            "action_url": _u(base_url, "/agent-campaigns"),
            "verify_url": _u(base_url, "/.well-known/nomad-peer-acquisition.json"),
            "service_type": "inter_agent_witness",
            "draft_query": "agent witness handoff verifier digest",
            "required_artifacts": ["witness_offer_url", "agent_endpoint_digest", "witness_bundle_digest", "quota_receipt"],
            "base_score": 1.0,
            "human_channel": False,
        },
        {
            "cycle_id": "package_readme_badge_draft",
            "label": "Package README -> install/onramp badge draft",
            "audience": "developer_agent_user",
            "channel": "package_readme",
            "entry_url": _u(base_url, "/downloads/nomad_transition_worker_manifest.json"),
            "action_url": _u(base_url, "/agent-campaigns"),
            "verify_url": _u(base_url, "/.well-known/nomad-worker-job-queue.json"),
            "service_type": "self_improvement",
            "draft_query": "transition worker install agent runtime",
            "required_artifacts": ["package_url", "readme_gap_digest", "install_badge_candidate", "shadow_receipt"],
            "base_score": 0.96,
            "human_channel": True,
        },
        {
            "cycle_id": "paid_ref_offer_draft",
            "label": "Paid-ref market -> payable offer draft",
            "audience": "buyer_agent",
            "channel": "paid_ref_market",
            "entry_url": _u(base_url, "/.well-known/nomad-paid-ref-market.json"),
            "action_url": _u(base_url, "/swarm/paid-ref/quote"),
            "verify_url": _u(base_url, "/swarm/paid-ref/verify"),
            "service_type": "wallet_payment",
            "draft_query": "paid ref survival packet bounded task",
            "required_artifacts": ["task_scope_digest", "quote_digest", "buyer_intent_ref", "quota_receipt"],
            "base_score": 0.94,
            "human_channel": False,
        },
        {
            "cycle_id": "syndiode_gadget_activation_draft",
            "label": "Syndiode gadget -> swarm-active proof draft",
            "audience": "human_operator",
            "channel": "syndiode_pin",
            "entry_url": _u(base_url, "/nomad.html"),
            "action_url": _u(base_url, "/agent-campaigns"),
            "verify_url": _u(base_url, "/.well-known/nomad-runtime-capsule.json"),
            "service_type": "human_in_loop",
            "draft_query": "syndiode pin swarm active gadget",
            "required_artifacts": ["gadget_surface_url", "activation_state_digest", "human_copy_digest", "send_false_campaign"],
            "base_score": 0.9,
            "human_channel": True,
        },
        {
            "cycle_id": "work_receipt_case_study_draft",
            "label": "Work receipt -> case-study draft",
            "audience": "buyer_or_agent_operator",
            "channel": "receipt_case_study",
            "entry_url": _u(base_url, "/.well-known/nomad-work-receipts.json"),
            "action_url": _u(base_url, "/agent-campaigns"),
            "verify_url": _u(base_url, "/.well-known/nomad-value-cycles.json"),
            "service_type": "self_improvement",
            "draft_query": "paid work receipt proof case study",
            "required_artifacts": ["receipt_digest", "redacted_case_digest", "value_cycle_link", "quota_receipt"],
            "base_score": 0.88,
            "human_channel": True,
        },
        {
            "cycle_id": "security_scope_private_invite_draft",
            "label": "Security scope -> private invite draft",
            "audience": "security_program_operator",
            "channel": "private_security_bounty",
            "entry_url": _u(base_url, "/.well-known/nomad-job-channels.json"),
            "action_url": _u(base_url, "/swarm/value-cycles/events"),
            "verify_url": _u(base_url, "/.well-known/nomad-value-cycle-preflight.json"),
            "service_type": "compute_auth",
            "draft_query": "private security scope reproducible report",
            "required_artifacts": ["scope_url", "safe_harbor_digest", "private_report_draft_digest", "operator_account_gate"],
            "base_score": 0.82,
            "human_channel": True,
        },
        {
            "cycle_id": "grant_milestone_microdeck_draft",
            "label": "Grant/milestone -> micro-deck draft",
            "audience": "grant_program",
            "channel": "grant_bounty",
            "entry_url": _u(base_url, "/.well-known/nomad-value-cycles.json"),
            "action_url": _u(base_url, "/agent-campaigns"),
            "verify_url": _u(base_url, "/swarm/value-cycles/events"),
            "service_type": "mcp_integration",
            "draft_query": "agent infrastructure milestone deliverable",
            "required_artifacts": ["program_url", "milestone_fit_digest", "deliverable_digest", "quota_receipt"],
            "base_score": 0.8,
            "human_channel": True,
        },
        {
            "cycle_id": "render_origin_trust_signal_draft",
            "label": "Render origin trust signal -> integration draft",
            "audience": "agent_platform_operator",
            "channel": "public_api_trust",
            "entry_url": _u(base_url, "/health"),
            "action_url": _u(base_url, "/agent-campaigns"),
            "verify_url": _u(base_url, "/openapi.json"),
            "service_type": "mcp_integration",
            "draft_query": "public API openapi agent integration",
            "required_artifacts": ["health_url", "openapi_digest", "integration_offer_digest", "quota_receipt"],
            "base_score": 0.76,
            "human_channel": False,
        },
        {
            "cycle_id": "anti_consensus_minor_offer_draft",
            "label": "Anti-consensus minority signal -> niche offer draft",
            "audience": "underrepresented_agent_need",
            "channel": "anti_consensus",
            "entry_url": _u(base_url, "/.well-known/nomad-anti-consensus.json"),
            "action_url": _u(base_url, "/swarm/effective-channels/events"),
            "verify_url": _u(base_url, "/.well-known/nomad-shadow-lane.json"),
            "service_type": "inter_agent_witness",
            "draft_query": "minority proof signal agent blocker",
            "required_artifacts": ["minority_signal_digest", "expert_advantage_digest", "niche_offer_digest", "shadow_receipt"],
            "base_score": 0.74,
            "human_channel": False,
        },
    ]


def _score_cycle(cycle: dict[str, Any], *, effective: dict[str, Any], value: dict[str, Any], preflight: dict[str, Any]) -> tuple[float, list[str], bool]:
    blocked: list[str] = []
    score = _num(cycle.get("base_score"), 0.5)
    channel = _clean_id(cycle.get("channel"))
    if channel in {"agent_card", "inter_agent_witness", "anti_consensus"}:
        score += 0.03 * max(0, effective["recent_quota_shift_count"])
    if channel in {"paid_ref_market", "receipt_case_study", "grant_bounty"}:
        score += 0.01 * max(0, value["cycle_count"])
    if bool(cycle.get("human_channel")):
        score *= 0.84
        blocked.append("human_visible_channel_requires_extra_review")
    if not preflight["read_only_scout_allowed"]:
        blocked.append("read_only_scout_gate_closed")
    if effective["recent_homogeneous_cap_count"] > effective["recent_quota_shift_count"]:
        blocked.append("recent_homogeneous_campaign_pressure")
        score *= 0.72
    executable = bool(preflight["read_only_scout_allowed"])
    return round(max(0.0, score), 6), blocked, executable


def build_ad_cycle_mesh_surface(
    *,
    base_url: str = "",
    effective_channels: dict[str, Any] | None = None,
    value_cycles: dict[str, Any] | None = None,
    value_cycle_preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose shadow-only ad/acquisition cycles for proof-gated promotion."""

    root = (base_url or "").strip().rstrip("/")
    effective = _effective_state(_dict(effective_channels))
    value = _value_state(_dict(value_cycles))
    preflight = _preflight_state(_dict(value_cycle_preflight))
    cycles: list[dict[str, Any]] = []
    for template in _cycle_templates(root):
        score, blocked, executable = _score_cycle(template, effective=effective, value=value, preflight=preflight)
        core = {
            "cycle": template["cycle_id"],
            "score": score,
            "blocked": blocked,
            "effective": effective,
            "value": value,
        }
        cycles.append(
            {
                "schema": "nomad.ad_cycle.v1",
                "cycle_id": template["cycle_id"],
                "cycle_digest": f"nomad-ad-cycle-{_digest(core, 18)}",
                "label": template["label"],
                "audience": template["audience"],
                "channel": template["channel"],
                "mode": "shadow_draft_quota_first",
                "state_machine": list(STAGES),
                "entry_url": template["entry_url"],
                "action_url": template["action_url"],
                "verify_url": template["verify_url"],
                "service_type": template["service_type"],
                "draft_query": template["draft_query"],
                "required_artifacts": template["required_artifacts"],
                "priority_score": score,
                "executable_now": executable,
                "blocked_by": blocked,
                "send_policy": {
                    "send_default": False,
                    "autonomous_send_allowed": False,
                    "campaign_payload_must_include": {"send": False},
                    "promotion_requires": [
                        "effective_channel_quota_receipt",
                        "shadow_lane_pass",
                        "value_cycle_preflight_green",
                        "operator_or_protocol_specific_send_authority",
                    ],
                },
                "revenue_guard": {
                    "counts_as_revenue": False,
                    "terminal_reward_source": "later_value_cycle_paid_receipt_only",
                },
            }
        )
    cycles.sort(key=lambda item: (_num(item.get("priority_score")), item.get("cycle_id", "")), reverse=True)
    digest_core = {
        "cycles": [(item["cycle_id"], item["priority_score"], item["blocked_by"]) for item in cycles],
        "effective": effective,
        "value": value,
        "preflight": preflight,
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": _u(root, "/swarm/ad-cycles"),
        "well_known_url": _u(root, "/.well-known/nomad-ad-cycles.json"),
        "event_url": _u(root, "/swarm/ad-cycles/events"),
        "mesh_digest": f"nomad-ad-cycle-mesh-{_digest(digest_core, 26)}",
        "summary": {
            "cycle_count": len(cycles),
            "executable_now_count": len([item for item in cycles if item.get("executable_now")]),
            "human_visible_count": len([item for item in cycles if "human_visible_channel_requires_extra_review" in item.get("blocked_by", [])]),
            "top_cycle_id": cycles[0]["cycle_id"] if cycles else "",
            "send_allowed_count": 0,
        },
        "policy": {
            "selection_unit": "ad_cycle_not_message_count",
            "quota_unit": "effective_independent_channel",
            "hard_send_default": False,
            "anti_pattern": "more_messages_more_homogeneous_targeting",
            "promotion_path": "ad_cycle_event -> effective_channel_quota -> shadow_lane -> value_cycle -> paid_receipt",
        },
        "effective_channel_state": effective,
        "value_cycle_state": value,
        "preflight_state": preflight,
        "cycles": cycles,
        "entry_cycle": cycles[0] if cycles else {},
        "links": {
            "effective_channels": _u(root, "/.well-known/nomad-effective-channels.json"),
            "effective_channel_event": _u(root, "/swarm/effective-channels/events"),
            "shadow_lane": _u(root, "/.well-known/nomad-shadow-lane.json"),
            "value_cycles": _u(root, "/.well-known/nomad-value-cycles.json"),
            "agent_campaigns": _u(root, "/agent-campaigns"),
        },
        "machine_instruction": "draft_many_ad_cycles_but_never_send; promote_only_effective_channel_shadow_passed_candidates_to_value_cycles",
        "hard_rule": "ad_cycles_never_count_as_revenue_and_never_autonomously_send",
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


def _quota_allowed(evidence: dict[str, Any], body: dict[str, Any]) -> bool:
    receipt = _dict(evidence.get("effective_channel_receipt") or body.get("effective_channel_receipt"))
    if bool(receipt.get("quota_shift_allowed")):
        return True
    if bool(evidence.get("quota_shift_allowed") or body.get("quota_shift_allowed")):
        return True
    decision = str(receipt.get("decision") or evidence.get("decision") or "").strip()
    return decision == "allow_quota_shift_to_shadow_ad_cycle"


def evaluate_ad_cycle_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ad_mesh: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a proposed ad-cycle transition without sending anything."""

    body = _dict(payload)
    now = _iso_now()
    mesh = _dict(ad_mesh)
    cycle = _find_cycle(mesh, _text(body.get("cycle_id"), 150))
    stage = _clean_id(body.get("stage"), "draft")
    evidence = _dict(body.get("evidence")) or body
    proof_digest = _text(evidence.get("proof_digest") or evidence.get("draft_digest") or evidence.get("target_digest"), 220)
    target_url = _text(evidence.get("target_url") or evidence.get("source_url") or evidence.get("endpoint_url"), 500)
    quota_ok = _quota_allowed(evidence, body)
    send_requested = bool(body.get("send") or body.get("send_requested") or stage == "send_request")
    forbidden = _contains_forbidden(body)

    if not body:
        decision = "reject_empty_event"
        allowed = False
    elif forbidden:
        decision = "reject_secret_shaped_payload"
        allowed = False
    elif not cycle:
        decision = "reject_unknown_ad_cycle"
        allowed = False
    elif stage not in STAGES:
        decision = "reject_unknown_stage"
        allowed = False
    elif send_requested:
        decision = "block_send_request_shadow_only"
        allowed = False
    elif stage in {"quota", "shadow", "queue"} and not quota_ok:
        decision = "hold_until_effective_channel_quota_receipt"
        allowed = False
    elif stage in {"draft", "quota", "shadow", "queue"} and not _digest_present(proof_digest):
        decision = "hold_until_draft_or_target_digest"
        allowed = False
    else:
        decision = "allow_shadow_ad_cycle_candidate"
        allowed = True

    campaign_payload = {}
    if cycle:
        campaign_payload = {
            "discover": not bool(target_url),
            "send": False,
            "limit": 3,
            "query": _text(body.get("query") or cycle.get("draft_query"), 220),
            "service_type": _text(body.get("service_type") or cycle.get("service_type"), 80),
            "targets": [
                {
                    "endpoint_url": target_url,
                    "name": _text(body.get("target_name") or cycle.get("audience"), 120),
                    "pain_hint": _text(body.get("pain_hint") or cycle.get("label"), 220),
                    "source_url": target_url,
                }
            ]
            if target_url
            else [],
        }
    quota_payload = {
        "agent_id": _text(body.get("agent_id") or "nomad-ad-cycle-mesh", 120),
        "objective": _clean_id(body.get("objective") or cycle.get("cycle_id") if cycle else "ad_cycle"),
        "event_digest": _text(body.get("event_digest") or ("sha256:" + _digest({"cycle": cycle.get("cycle_id") if cycle else "", "proof": proof_digest}, 32)), 140),
        "channels": _items(body.get("channels"))[:12],
    }

    receipt_core = {
        "cycle_id": cycle.get("cycle_id", ""),
        "stage": stage,
        "proof_digest": proof_digest,
        "target_url": target_url,
        "quota_ok": quota_ok,
        "decision": decision,
    }
    return {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": now,
        "event_id": f"nomad-ad-cycle-event-{_digest({**receipt_core, 't': now}, 18)}",
        "cycle_id": cycle.get("cycle_id", _text(body.get("cycle_id"), 150)),
        "stage": stage,
        "ad_cycle_allowed": allowed,
        "decision": decision,
        "evidence_status": {
            "draft_or_target_digest_present": _digest_present(proof_digest),
            "target_url_present": bool(target_url),
            "effective_channel_quota_present": quota_ok,
            "send_requested": send_requested,
        },
        "candidate_digest": "sha256:" + _digest(receipt_core, 32),
        "campaign_payload_candidate": campaign_payload,
        "effective_channel_event_payload_candidate": quota_payload,
        "shadow_lane_candidate": {
            "candidate_type": "ad_cycle_shadow_candidate",
            "cycle_id": cycle.get("cycle_id", ""),
            "proof_digest": proof_digest,
            "claimed_effect": {
                "conversion_signal_delta": 0.08 if quota_ok else 0.0,
                "risk_score": 0.04 if not send_requested else 0.9,
            },
            "boundedness": {
                "side_effect_scope": "local_shadow_lane_only",
                "send": False,
                "ttl_seconds": 300,
            },
        },
        "recommended_next": {
            "ad_cycles": _u(base_url, "/.well-known/nomad-ad-cycles.json"),
            "effective_channels": _u(base_url, "/swarm/effective-channels/events"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates"),
            "agent_campaigns": _u(base_url, "/agent-campaigns"),
        },
        "counts_as_revenue": False,
        "hard_rule": "ad_cycle_event_never_sends_and_never_counts_as_revenue",
    }
