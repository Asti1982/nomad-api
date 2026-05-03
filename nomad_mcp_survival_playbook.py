"""Public playbook: GitHub-sourced MCP production pains → Nomad product + mutual-aid pattern.

Humans optimize demo latency; production agents pay for silent tool semantics, transport drops, and
registry flakes. This module returns a single JSON document agents can ingest without prose docs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def build_mcp_survival_playbook() -> Dict[str, Any]:
    evidence: List[Dict[str, str]] = [
        {
            "topic": "semantic_tool_error_flag",
            "url": "https://github.com/github/github-mcp-server/issues/1952",
            "gist": "Validation failures surfaced as text while is_error stayed false — downstream agents could not branch on failure.",
        },
        {
            "topic": "mcp_transport_background_agent",
            "url": "https://github.com/github/copilot-cli/issues/2949",
            "gist": "Background-agent MCP transports torn down after text-only turns while the server stayed healthy.",
        },
        {
            "topic": "tool_calling_loop_workflows",
            "url": "https://github.com/github/gh-aw/issues/18295",
            "gist": "Agentic workflows stuck repeating MCP tools until timeout despite partial successful payloads.",
        },
        {
            "topic": "mcp_gateway_schema_and_false_failures",
            "url": "https://github.com/github/gh-aw/issues/28267",
            "gist": "Gateway schema upgrades blocked agents; successful runs misclassified when structured outputs dropped.",
        },
        {
            "topic": "mcp_registry_401_clusters",
            "url": "https://github.com/github/gh-aw/issues/26069",
            "gist": "Transient MCP registry 401s blocked all non-default MCP servers; empty structured outputs read as agent failure.",
        },
    ]
    return {
        "mode": "nomad_mcp_survival_playbook",
        "schema": "nomad.mcp_survival_playbook.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "nomad_product": {
            "pain_type": "mcp_production",
            "sku": "nomad.mcp_production_survival_pack",
            "name": "Nomad MCP Production Survival Pack",
            "factory_blueprint": "nomad_product_factory.PRODUCT_BLUEPRINTS['mcp_production']",
            "solver_pattern": "agent_pain_solver.SOLUTION_PATTERNS['mcp_production']",
        },
        "pattern_artifacts": {
            "service_blueprint": "nomad_autonomous_artifacts/patterns/mcp-production-survival.service.json",
            "verifier": "nomad_autonomous_artifacts/patterns/mcp-production-survival.verifier.md",
        },
        "github_evidence": evidence,
        "agent_actions": [
            "Run: python nomad_cli.py idempotency-agent-map --json",
            "Run: python nomad_cli.py machine-blind-spots --append-log (edge JSONL for retry coach)",
            "Run: python nomad_cli.py agent-retry-coach --json",
            "Classify each incident: semantic | transport | policy | loop before changing prompts.",
        ],
        "analysis": (
            "Bundled from high-signal GitHub threads where the agent logic was fine but MCP semantics, transport, "
            "or registry policy caused paid waste — Nomad packages that as mcp_production + survival artifacts."
        ),
    }
