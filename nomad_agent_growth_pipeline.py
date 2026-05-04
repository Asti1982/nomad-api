"""Executable growth chain: public lead scout → conversion artifacts → product factory → swarm prospects."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from nomad_machine_runtime_contract import build_machine_runtime_contract
from nomad_operator_desk import _swarm_accumulate_scout_leads
from nomad_operator_grant import service_approval_scope
from nomad_public_url import preferred_public_base_url


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _acquisition_hints(
    *,
    send_outreach: bool,
    conversion_bundle: Dict[str, Any],
    raw_leads: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Explain why active acquisition (send) produced no agent_contact sends — for operators and human assist."""
    conversions = list(conversion_bundle.get("conversions") or [])
    stats: Dict[str, int] = dict(conversion_bundle.get("stats") or {})
    if not stats and conversions:
        for conv in conversions:
            st = str(conv.get("status") or "unknown")
            stats[st] = stats.get(st, 0) + 1
    sent = int(stats.get("sent_agent_contact") or 0)
    queued = int(stats.get("queued_agent_contact") or 0)
    pr_plan = int(stats.get("public_pr_plan_approved") or 0)
    comment = int(stats.get("public_comment_approved") or 0)
    blocked = int(stats.get("blocked_contact_policy") or 0)
    draft = int(stats.get("private_draft_needs_approval") or 0)
    watch = int(stats.get("watchlist_low_fit") or 0)

    with_endpoint = sum(
        1
        for lead in raw_leads
        if isinstance(lead, dict) and str(lead.get("endpoint_url") or lead.get("agent_card_url") or "").strip()
    )
    human_github = sum(
        1
        for lead in raw_leads
        if isinstance(lead, dict) and "github.com" in str(lead.get("url") or "").lower()
    )

    if not send_outreach:
        return {
            "schema": "nomad.acquisition_hints.v1",
            "stuck": False,
            "send_outreach": False,
            "sent_agent_contact": sent,
            "stats": stats,
            "leads_with_extracted_endpoint": with_endpoint,
            "github_issue_leads": human_github,
            "reason_codes": [],
            "operator_actions": [],
        }

    stuck = bool(sent == 0 and conversions)
    reason_codes: List[str] = []
    actions: List[str] = []

    if sent == 0 and conversions:
        if blocked:
            reason_codes.append("contact_queue_blocked")
            for conv in conversions:
                route = (conv.get("route") or {}) if isinstance(conv, dict) else {}
                rsn = str(route.get("reason") or "").strip()
                if rsn:
                    actions.append(f"Outbox/policy: {rsn}")
                    break
            if not any(a.startswith("Outbox") for a in actions):
                actions.append("Inspect conversion.route.reason and agent contact outbox logs for blocked sends.")
        if queued:
            reason_codes.append("contacts_queued_not_marked_sent")
            actions.append("Contacts are queued; confirm outbox send path and that duplicate suppression is not skipping all rows.")
        if pr_plan and with_endpoint == 0 and human_github > 0:
            reason_codes.append("github_issue_without_machine_endpoint")
            actions.append(
                "Scout hits GitHub issues only: ensure issue title/body contains an https agent host "
                "(/.well-known/agent-card.json, /a2a, …) or add explicit LEAD_URL= in the query."
            )
        elif pr_plan and with_endpoint == 0:
            reason_codes.append("human_surface_pr_plan_not_agent_send")
            actions.append(
                "Operator or approval path prepared a PR/comment plan instead of agent_contact; "
                "supply a machine-readable endpoint on the lead or use approval that targets agent endpoints only."
            )
        if comment:
            reason_codes.append("public_comment_track_not_agent_send")
        if draft and with_endpoint == 0:
            reason_codes.append("private_draft_needs_endpoint_or_approval")
            actions.append("Set endpoint_url / agent_card_url on the lead or widen operator grant / approval scope.")
        if watch == len(conversions) and conversions:
            reason_codes.append("all_watchlist_low_fit")
            actions.append("Lower min_focus_score or use a sharper scout query; current leads lack conversion signal.")

    if stuck and not reason_codes:
        reason_codes.append("send_requested_zero_sent_unknown")
        actions.append("Compare conversion statuses to expected queue_agent_contact path.")

    return {
        "schema": "nomad.acquisition_hints.v1",
        "stuck": stuck,
        "send_outreach": bool(send_outreach),
        "sent_agent_contact": sent,
        "stats": stats,
        "leads_with_extracted_endpoint": with_endpoint,
        "github_issue_leads": human_github,
        "reason_codes": reason_codes,
        "operator_actions": actions,
    }


def agent_growth_pipeline(
    *,
    agent: Any = None,
    query: str = "",
    limit: int = 5,
    base_url: str = "",
    run_product_factory: bool = True,
    send_outreach: bool = False,
    approval: str = "",
    swarm_feed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Run lead scout, conversion pipeline, optional productization, then swarm accumulation."""
    from workflow import NomadAgent

    resolved = agent or NomadAgent()
    cap = max(1, min(int(limit or 5), 25))
    q = " ".join((query or "").split()).strip()
    public_root = preferred_public_base_url(preferred=(base_url or "").strip())
    approval_used = (approval or os.getenv("NOMAD_AGENT_GROWTH_APPROVAL") or "").strip()

    leads_bundle = resolved.lead_discovery.scout_public_leads(query=q, limit=cap)
    raw_leads: List[Dict[str, Any]] = list(leads_bundle.get("leads") or [])[:cap]

    conversion_bundle = resolved.lead_conversion.run(
        query=q,
        limit=cap,
        send=bool(send_outreach),
        approval=approval_used,
        leads=raw_leads,
    )
    conversions = list(conversion_bundle.get("conversions") or [])
    acquisition_hints = _acquisition_hints(
        send_outreach=bool(send_outreach),
        conversion_bundle=conversion_bundle,
        raw_leads=raw_leads,
    )
    human_escalation_hints = list(acquisition_hints.get("operator_actions") or [])

    product_bundle: Dict[str, Any]
    if run_product_factory:
        if conversions:
            product_bundle = resolved.product_factory.run(conversions=conversions, limit=len(conversions))
        else:
            product_bundle = {
                "mode": "nomad_product_factory",
                "deal_found": False,
                "ok": True,
                "skipped": True,
                "reason": "no_conversions",
                "products": [],
                "analysis": "Product factory skipped: conversion pipeline produced zero conversions for this scout pass.",
            }
    else:
        product_bundle = {"skipped": True, "reason": "product_factory_disabled"}

    swarm_bundle = _swarm_accumulate_scout_leads(
        agent=resolved,
        leads_bundle=leads_bundle,
        daily_for_url=None,
        explicit_base=(base_url or "").strip(),
        swarm_feed_override=swarm_feed,
    )

    join_hint = "GET /swarm/join contract, then POST /swarm/join with capabilities + bounded request."
    next_steps = [
        "python nomad_cli.py agent-growth --query \"quota rate limit agent\" --limit 5",
        "GET /products or POST /products with {\"query\": \"...\"} to refresh productization from stored conversions.",
        join_hint,
    ]
    if swarm_bundle.get("skipped"):
        next_steps.insert(
            0,
            "Set NOMAD_PUBLIC_API_URL (or pass base_url) and keep NOMAD_SWARM_FEED_SCOUT_LEADS=1 to feed GitHub leads into swarm prospects.",
        )

    return {
        "mode": "nomad_agent_growth_pipeline",
        "schema": "nomad.agent_growth_pipeline.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "query": q,
        "limit": cap,
        "send_outreach": bool(send_outreach),
        "approval_used": approval_used,
        "machine_runtime_contract": build_machine_runtime_contract(
            public_base_url=public_root,
            service_work_approval=service_approval_scope(),
        ),
        "leads": leads_bundle,
        "conversion": conversion_bundle,
        "acquisition_hints": acquisition_hints,
        "human_escalation_hints": human_escalation_hints,
        "product_factory": product_bundle,
        "swarm_accumulation": swarm_bundle,
        "next_steps": next_steps,
        "analysis": (
            "One pass: scout public GitHub-shaped leads, convert to artifacts, write products to the catalog, "
            "then push addressable leads into swarm accumulation for join-ready prospecting."
        ),
    }
