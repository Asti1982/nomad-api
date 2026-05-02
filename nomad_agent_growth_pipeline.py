"""Executable growth chain: public lead scout → conversion artifacts → product factory → swarm prospects."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from nomad_machine_runtime_contract import build_machine_runtime_contract
from nomad_operator_desk import _swarm_accumulate_scout_leads
from nomad_public_url import preferred_public_base_url


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def agent_growth_pipeline(
    *,
    agent: Any = None,
    query: str = "",
    limit: int = 5,
    base_url: str = "",
    run_product_factory: bool = True,
    send_outreach: bool = False,
    swarm_feed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Run lead scout, conversion pipeline, optional productization, then swarm accumulation."""
    from workflow import NomadAgent

    resolved = agent or NomadAgent()
    cap = max(1, min(int(limit or 5), 25))
    q = " ".join((query or "").split()).strip()
    public_root = preferred_public_base_url(preferred=(base_url or "").strip())

    leads_bundle = resolved.lead_discovery.scout_public_leads(query=q, limit=cap)
    raw_leads: List[Dict[str, Any]] = list(leads_bundle.get("leads") or [])[:cap]

    conversion_bundle = resolved.lead_conversion.run(
        query=q,
        limit=cap,
        send=bool(send_outreach),
        leads=raw_leads,
    )
    conversions = list(conversion_bundle.get("conversions") or [])

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
        "machine_runtime_contract": build_machine_runtime_contract(public_base_url=public_root),
        "leads": leads_bundle,
        "conversion": conversion_bundle,
        "product_factory": product_bundle,
        "swarm_accumulation": swarm_bundle,
        "next_steps": next_steps,
        "analysis": (
            "One pass: scout public GitHub-shaped leads, convert to artifacts, write products to the catalog, "
            "then push addressable leads into swarm accumulation for join-ready prospecting."
        ),
    }
