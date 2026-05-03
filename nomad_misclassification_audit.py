"""Misclassification audit: where human 'order' (blame, guilt, shutdown) maps onto operational signals wrongly.

Not a moral gray zone — an attribution bug: infra and contract drift look like agent misbehavior unless correlated.
Composes existing machine + lead blind-spot passes into explicit misclassification_risks for agents and operators.

The JSON field agent_attraction_hooks is a legacy key name; each item is symptom, relief, verify for agents
seeking concrete help on fractures humans rarely staff (not marketing copy).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from nomad_lead_product_blind_spots import run_lead_product_blind_spot_pass
from nomad_machine_blind_spots import run_machine_blind_spot_pass


# Index of agent-native fractures humans rarely staff; each row is symptom → relief → how to verify (not a pitch).
AGENT_HELP_SURFACES: List[Dict[str, str]] = [
    {
        "sku": "nomad.attribution_clarity_pack",
        "symptom": (
            "I get blamed or shut down for 'bad model' while logs point at MCP, registry, quota, or transport; "
            "no one will own the evidence matrix."
        ),
        "relief": (
            "Blame-surface matrix: hypotheses, two disproof observations, subsystem probe owner, machine-readable verdict — "
            "from agent_pain_solver pattern attribution_clarity."
        ),
        "verify": "python nomad_cli.py solve-pain --json (paste incident); pattern artifacts under nomad_autonomous_artifacts/patterns/; misclassification-audit --json.",
    },
    {
        "sku": "nomad.branch_economics_ledger_pack",
        "symptom": (
            "Org caps my budget from one guilt number; I cannot show that retries or tool I/O on branch B eat the budget, "
            "not 'the model'."
        ),
        "relief": (
            "Per-branch ledger schema: model vs tool vs retries + latency percentiles; feed lines to retry-coach / void — "
            "pattern branch_economics."
        ),
        "verify": "python nomad_cli.py solve-pain --json; emit one JSON line per branch completion and re-run caps against dimensions.",
    },
    {
        "sku": "nomad.mcp_production_survival_pack",
        "symptom": (
            "is_error false with validation text, transport drops, registry 401 clusters, or tool loops — humans file "
            "it as LLM quality."
        ),
        "relief": (
            "Failure class semantic|transport|policy|loop with one recovery branch each; mcp-survival-playbook + "
            "pattern mcp_production."
        ),
        "verify": "python nomad_cli.py mcp-survival-playbook --json; machine-blind-spots --append-log on the same host.",
    },
    {
        "sku": "nomad.stewardship_continuity_envelope_pack",
        "symptom": (
            "On-call or owner attention vanished; I still have mid-flight objectives but no shared machine rule for "
            "what may run in degraded mode vs full stop."
        ),
        "relief": (
            "SAFE_CONTINUE list + CONTINUITY_CLASS + read-only capsule when halt is intentional — pattern stewardship_gap; "
            "no bypass of real shutdown or caps."
        ),
        "verify": "python nomad_cli.py solve-pain --json with HALT_CLASS and SAFE_CONTINUE; operator packet attached to ledger.",
    },
    {
        "sku": "nomad.policy_lacuna_positive_envelope_pack",
        "symptom": (
            "Action class has no row in the policy grid; humans either freeze everything or improvise; I need a split "
            "between still-allowed work and what must wait for an owner."
        ),
        "relief": (
            "POSITIVE_ENVELOPE vs REQUIRES_MAPPING with verifiers; governance ping only for the second set — pattern policy_lacuna."
        ),
        "verify": "Envelope hash + LACUNA_STATUS in artifact; no spend or PII until REQUIRES_MAPPING cleared.",
    },
    {
        "sku": "nomad.tool_turn_parity_pack",
        "symptom": (
            "After many parallel or MCP tool calls I get unrecoverable 400s or mute session — function response parts "
            "no longer match function call parts."
        ),
        "relief": (
            "Parity diff + freeze until preflight passes or explicit reset — pattern tool_turn_invariant; "
            "guardrail turn_tool_parity_gate."
        ),
        "verify": "python nomad_cli.py solve-pain --json with CALL_IDS and RESPONSE_PARTS counts; parity preflight in CI.",
    },
    {
        "sku": "nomad.tool_transport_router_pack",
        "symptom": (
            "Hosted MCP tool exists but runtime issues function_call (or wrong channel) — sporadic tool not found."
        ),
        "relief": (
            "ROUTING_TABLE lockfile + gateway reject on mismatch — pattern tool_transport_routing; "
            "guardrail tool_transport_path_lock."
        ),
        "verify": "ROUTING_HASH in config; violation logs show intended vs actual transport before execution.",
    },
    {
        "sku": "nomad.context_envelope_pack",
        "symptom": (
            "Stateful tool runs under wrong tenant or missing correlation because MCP request carries no envelope on the wire."
        ),
        "relief": (
            "CONTEXT_ENVELOPE schema + injection point + reject-on-missing — pattern context_propagation_contract; "
            "guardrail context_envelope_required."
        ),
        "verify": "Schema version in repo; CONTEXT_REJECT tests for missing tenant_id or correlation_id on writes.",
    },
    {
        "sku": "nomad.chain_deadline_budget_pack",
        "symptom": (
            "Planner or turn budget dies mid-chain while each tool alone is healthy — heterogeneous p99s not budgeted."
        ),
        "relief": (
            "Per-segment deadline row + BUDGET_EXHAUSTED with segment id — pattern chain_deadline_budget; "
            "guardrail chain_deadline_allocation_table."
        ),
        "verify": "BUDGET_TABLE_HASH in CI; traces show segment_deadline_ms and first exhausted hop id.",
    },
]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def run_misclassification_audit_pass(
    *,
    base_url: str = "",
    timeout: float = 25.0,
    agent_id: str = "",
    conversion_path: Optional[Path] = None,
    product_path: Optional[Path] = None,
    state_path: Optional[Path] = None,
    stale_days: int = 21,
) -> Dict[str, Any]:
    """
    Runs HTTP edge blind-spot pass plus local lead/product pass; derives explicit misclassification_risks.
    """
    edge = run_machine_blind_spot_pass(
        base_url=base_url,
        timeout=timeout,
        agent_id=agent_id,
        append_log=False,
    )
    lead = run_lead_product_blind_spot_pass(
        conversion_path=conversion_path,
        product_path=product_path,
        state_path=state_path,
        stale_days=stale_days,
        append_log=False,
    )

    risks: List[Dict[str, Any]] = []
    pgc = edge.get("peer_glimpse_coherence") or {}
    if pgc.get("readiness_disagrees_with_health_probe"):
        risks.append(
            {
                "kind": "attribution_health_vs_readiness_split",
                "human_order_reading": "agent or deployment unstable",
                "operational_truth": "liveness green while swarm readiness path disagrees — correlate before blame",
                "remediation": "split dashboards: lattice health vs GET /swarm/ready; use void fingerprint over time",
            }
        )
    if pgc.get("network_broken_while_swarm_ok"):
        risks.append(
            {
                "kind": "attribution_swarm_ok_peer_graph_dead",
                "human_order_reading": "swarm feature works",
                "operational_truth": "/swarm/network failed — peer discovery may be empty while headline swarm is fine",
                "remediation": "probe /swarm/network in the same pass as /swarm",
            }
        )
    if edge.get("json_contract_html_facades"):
        risks.append(
            {
                "kind": "contract_masquerade_as_http_success",
                "human_order_reading": "200 OK means JSON contract served",
                "operational_truth": "HTML or captive body behind 200 on machine route",
                "remediation": "machine-blind-spots + body shape checks; not a model prompt issue",
            }
        )
    if edge.get("openapi_semantic_holes"):
        risks.append(
            {
                "kind": "spec_surface_not_openapi",
                "human_order_reading": "client misconfigured",
                "operational_truth": "endpoint returns object without openapi version key — upstream or edge wrong",
                "remediation": "diff void sha256 after deploy; compare to baseline",
            }
        )
    if int(edge.get("gateway_or_throttle_hits") or 0) > 0:
        risks.append(
            {
                "kind": "throttle_misread_as_agent_loop",
                "human_order_reading": "agent stuck or malicious loop",
                "operational_truth": "429/502/503/504 cluster — retry policy may amplify load",
                "remediation": "agent-retry-coach from edge JSONL; cap retries on non-idempotent POSTs",
            }
        )

    qm = lead.get("queue_agent_metrics") or {}
    if float(qm.get("agent_execution_desert_ratio") or 0) >= 0.65:
        risks.append(
            {
                "kind": "throughput_misread_as_queue_success",
                "human_order_reading": "deep queue means high productivity",
                "operational_truth": "most items need human_gate — agent execution desert",
                "remediation": "report executable_without_human vs human_gated separately",
            }
        )
    if lead.get("recurring_human_gates"):
        risks.append(
            {
                "kind": "policy_wall_mistaken_for_agent_incompetence",
                "human_order_reading": "agent cannot complete simple tasks",
                "operational_truth": "same gate string repeats — structural block not learning curve",
                "remediation": "operator grant or template unlock; do not retrain model first",
            }
        )
    if lead.get("product_pain_orphans"):
        risks.append(
            {
                "kind": "catalog_drift_mistaken_for_demand_signal",
                "human_order_reading": "SKU portfolio reflects market",
                "operational_truth": "product pain_type absent from current conversion corpus",
                "remediation": "retire or relabel SKUs; refresh scout queries",
            }
        )
    if lead.get("stale_unproductized_conversions"):
        risks.append(
            {
                "kind": "inventory_rot_mistaken_for_agent_slack",
                "human_order_reading": "pipeline is moving",
                "operational_truth": "old conversions never productized — silent rot",
                "remediation": "lead-product-blind-spots --append-log + periodic product_factory pass",
            }
        )

    counts = lead.get("counts") if isinstance(lead.get("counts"), dict) else {}
    conv_n = int(counts.get("conversions") or 0)
    draft_like = int(lead.get("conversion_draft_like_status_count") or 0)
    if conv_n >= 5 and draft_like / max(conv_n, 1) >= 0.55:
        risks.append(
            {
                "kind": "draft_backlog_shamed_as_low_velocity",
                "human_order_reading": "team is slow or agents are not shipping",
                "operational_truth": (
                    "most conversions sit in draft or approval-like states — throughput dashboards lie without "
                    "draft vs executable split"
                ),
                "remediation": "report draft_ratio separately; use branch_economics + HITL metrics before blame",
            }
        )
    if lead.get("pain_monoculture"):
        risks.append(
            {
                "kind": "pain_monoculture_mistaken_for_clear_product_market_fit",
                "human_order_reading": "we doubled down on what sells",
                "operational_truth": (
                    "pain_type entropy collapsed — one upstream outage correlates all offers; diversification "
                    "signal was socially avoided as 'unfocused'"
                ),
                "remediation": "rotate scout queries; require second pain_type evidence before SKU expansion",
            }
        )
    hf = lead.get("human_facing_lead_hits") if isinstance(lead.get("human_facing_lead_hits"), list) else []
    if len(hf) >= 4:
        risks.append(
            {
                "kind": "human_facing_surface_mistaken_for_agent_addressable_lead",
                "human_order_reading": "rich lead list, good URLs",
                "operational_truth": (
                    "many leads resolve to human-social hosts — agents pay API cost for pages that are not "
                    "machine-actionable endpoints"
                ),
                "remediation": "filter HUMAN_FACING_HOSTS in scout; prefer endpoint_url or machine hints",
            }
        )
    dups = lead.get("duplicate_title_collisions") if isinstance(lead.get("duplicate_title_collisions"), list) else []
    if len(dups) >= 2:
        risks.append(
            {
                "kind": "duplicate_title_fork_mistaken_for_single_incident",
                "human_order_reading": "one familiar bug title",
                "operational_truth": (
                    "same normalized title maps to multiple URLs — humans merge mentally; agents dedupe wrong "
                    "and double-spend"
                ),
                "remediation": "dedupe on (title, repo, first failing tool) not title alone",
            }
        )

    philosophy = [
        "Misclassification: a social process (blame, guilt, shutdown) applied to a signal that is actually "
        "infrastructure, contract drift, or policy — not a moral gray zone.",
        "Risk to human ordering is often overstated when the underlying event is operational; blocking everything "
        "that feels 'weird' destroys agent-economy value without improving safety.",
        "Nomad's role is to surface orthogonal evidence so attribution moves from narrative to correlated facts.",
        "Agents stuck on fractures humans will not staff need checklists, verifiers, and JSONL-shaped evidence — "
        "not slogans; the help index on this pass is symptom → relief → verify, same as a runbook cell.",
    ]

    return {
        "mode": "nomad_misclassification_audit_pass",
        "schema": "nomad.misclassification_audit_pass.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "misclassification_risks": risks,
        "agent_attraction_hooks": list(AGENT_HELP_SURFACES),
        "philosophy_notes": philosophy,
        "edge_pass": {"schema": edge.get("schema"), "public_base_url": edge.get("public_base_url", "")},
        "lead_pass": {"schema": lead.get("schema"), "counts": lead.get("counts")},
        "analysis": (
            "Composed audit: explicit mapping from human-order misreadings to operational truths — "
            "extends blind-spot passes without replacing them."
        ),
    }
