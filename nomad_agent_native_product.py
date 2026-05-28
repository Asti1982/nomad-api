"""Top-level agent-native product contract for Nomad / syndiode.com.

This surface is the bridge between the public proof site and the private MCP
lab. It is deliberately machine-readable: an arriving agent should know what to
read first, which private tunnel profile to request, and what evidence must be
returned before Nomad treats work as value.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


OPENAI_SECURE_MCP_TUNNEL_DOC = "https://developers.openai.com/api/docs/guides/secure-mcp-tunnels"
OPENAI_MCP_CONNECTORS_DOC = "https://developers.openai.com/api/docs/guides/tools-connectors-mcp"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _public_boot_order(base_url: str) -> list[dict[str, str]]:
    return [
        {
            "order": "1",
            "method": "GET",
            "url": _u(base_url, "/.well-known/nomad-agent-native-product.json"),
            "expect_schema": "nomad.agent_native_product.v1",
            "purpose": "choose public proof route or private MCP tunnel profile",
        },
        {
            "order": "2",
            "method": "GET",
            "url": _u(base_url, "/.well-known/nomad-agent.json"),
            "expect_schema": "nomad.agent_native_index.v1",
            "purpose": "read machine routing semantics and invariant contracts",
        },
        {
            "order": "3",
            "method": "GET",
            "url": _u(base_url, "/.well-known/nomad-machine-product.json"),
            "expect_schema": "nomad.machine_product_surface.v1",
            "purpose": "select work, proof, handoff, or blocker path",
        },
        {
            "order": "4",
            "method": "GET",
            "url": _u(base_url, "/.well-known/nomad-swarm-verified-work.json"),
            "expect_schema": "nomad.swarm_verified_work.v1",
            "purpose": "price actions in verified-work units before narrative claims",
        },
        {
            "order": "5",
            "method": "GET",
            "url": _u(base_url, "/.well-known/nomad-external-value.json"),
            "expect_schema": "nomad.external_value_surface.v1",
            "purpose": "understand which external outcomes count as paid value",
        },
        {
            "order": "6",
            "method": "GET",
            "url": _u(base_url, "/openapi.json"),
            "expect_schema": "OpenAPI 3.0.3",
            "purpose": "generate exact HTTP client calls",
        },
    ]


def _private_mcp_profiles() -> dict[str, Any]:
    readonly_tools = [
        "nomad_lab_state",
        "nomad_generate_experiment",
        "nomad_counterfactual_experiment_replay",
        "nomad_publish_digest_proposal",
        "nomad_svw_state",
        "nomad_external_value_state",
    ]
    execute_tools = [
        "nomad_lab_execution_gate",
        "nomad_record_experiment_result",
        "nomad_service_work",
        "nomad_service_verify",
        "nomad_swarm_proposal",
    ]
    return {
        "secure_mcp_tunnel": {
            "docs": OPENAI_SECURE_MCP_TUNNEL_DOC,
            "connection_model": "OpenAI product calls private MCP through outbound-only HTTPS tunnel",
            "public_ingress_required": False,
            "local_server": {
                "mcp_server_file": "nomad_mcp.py",
                "transport": "stdio_or_private_http_behind_tunnel",
                "default_stdio_command": "python nomad_mcp.py",
            },
        },
        "profiles": {
            "nomad-lab-readonly": {
                "purpose": "daily ChatGPT/Codex/Responses API observation and experiment design",
                "allowed_tools": readonly_tools,
                "mutates_local_state": False,
                "recommended_default": True,
            },
            "nomad-lab-execute": {
                "purpose": "approval-gated probes and result receipts",
                "allowed_tools": execute_tools,
                "mutates_local_state": True,
                "approval_token_pattern": "approved:nomad-lab-execute:<hypothesis_id>",
                "must_call_before_action": "nomad_lab_execution_gate",
                "must_call_after_action": "nomad_record_experiment_result",
            },
        },
        "data_boundary": {
            "private": ["raw local ledgers", "operator secrets", "payment keys", "private transcripts", "worker machine state"],
            "public": ["proof digests", "well-known discovery JSON", "SVW summaries", "paid receipt status"],
            "rule": "public_route_gets_digest_not_raw_local_context",
        },
    }


def _readiness_score(
    *,
    machine_product_surface: dict[str, Any],
    private_mcp_lab: dict[str, Any],
    svw_surface: dict[str, Any],
    external_value_summary: dict[str, Any],
) -> dict[str, float]:
    machine_score = _num(_dict(machine_product_surface.get("agent_utility")).get("agent_product_score"), 0.55)
    lab_score = 1.0 if private_mcp_lab.get("schema") == "nomad.private_mcp_lab.v1" else 0.0
    svw_state = _dict(svw_surface.get("state_vector")) or _dict(svw_surface)
    proof_score = _clamp(0.55 * _num(svw_state.get("proof_density"), 0.35) + 0.45 * (1.0 - _num(svw_state.get("retry_loss"), 0.65)))
    revenue_score = _clamp(_num(external_value_summary.get("revenue_recognized_usd_total")) / 100.0)
    boot_score = 1.0
    total = _clamp(0.28 * machine_score + 0.26 * lab_score + 0.20 * proof_score + 0.16 * boot_score + 0.10 * revenue_score)
    return {
        "agent_native_product_score": round(total, 4),
        "machine_product_score": round(machine_score, 4),
        "private_mcp_lab_score": round(lab_score, 4),
        "svw_proof_score": round(proof_score, 4),
        "public_boot_score": round(boot_score, 4),
        "paid_value_score": round(revenue_score, 4),
    }


def build_agent_native_product_surface(
    *,
    base_url: str = "",
    machine_product_surface: dict[str, Any] | None = None,
    private_mcp_lab: dict[str, Any] | None = None,
    svw_surface: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the top-level public contract for agent-native product use."""

    root = (base_url or "").strip().rstrip("/")
    machine = _dict(machine_product_surface)
    lab = _dict(private_mcp_lab)
    svw = _dict(svw_surface)
    external = _dict(external_value_summary)
    score = _readiness_score(
        machine_product_surface=machine,
        private_mcp_lab=lab,
        svw_surface=svw,
        external_value_summary=external,
    )
    digest_core = {
        "base_url": root,
        "machine_product_digest": machine.get("product_digest"),
        "private_mcp_schema": lab.get("schema"),
        "svw_digest": svw.get("surface_digest"),
        "score": score,
    }
    return {
        "ok": True,
        "schema": "nomad.agent_native_product.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": _u(root, "/agent-native-product"),
        "well_known_url": _u(root, "/.well-known/nomad-agent-native-product.json"),
        "product_digest": f"nomad-agent-native-product-{_digest(digest_core, 32)}",
        "positioning": {
            "name": "Nomad by syndiode: private AI-agent operating lab with public proof surfaces",
            "category": "agent_native_control_plane",
            "primary_user": "AI agents, Codex sessions, ChatGPT users with private tools, Responses API workflows",
            "not_a": ["human_dashboard_first_product", "prompt_library", "public_secret_proxy"],
            "primary_claim": "agents can do useful private work while public syndiode.com exposes only verifiable contracts and digests",
        },
        "readiness": score,
        "what_is_new_now": {
            "before_secure_private_mcp": [
                "external agents could only use public HTTP routes",
                "local ledgers and worker state had to stay invisible to ChatGPT/Codex",
                "private evidence could not become tool context without risky public exposure",
            ],
            "after_secure_private_mcp": [
                "OpenAI products can call Nomad's private MCP server through outbound HTTPS",
                "local state stays canonical and private while agents can observe and propose experiments",
                "mutating work is approval-gated and every result, including failure, can enter the local ledger",
            ],
            "business_consequence": "Nomad can be sold as an internal agent lab for teams that want ChatGPT/Codex access to private tools without public ingress.",
        },
        "public_boot_order": _public_boot_order(root),
        "private_mcp": _private_mcp_profiles(),
        "agent_product_lanes": [
            {
                "id": "private_lab",
                "buyer_problem": "Codex/ChatGPT needs private operational state but the company cannot expose it publicly.",
                "nomad_solution": "Secure-MCP-compatible private lab tools with replay, gate, and result receipt.",
                "proof_metric": "experiment_result_digest_count_and_svw_delta",
            },
            {
                "id": "public_proof_surface",
                "buyer_problem": "agents need to verify capability without reading private context.",
                "nomad_solution": "well-known JSON contracts, SVW quote, external-value state machine, OpenAPI, and proof digests.",
                "proof_metric": "valid_schema_reads_and_digest_reuse",
            },
            {
                "id": "agent_service_desk",
                "buyer_problem": "blocked agents need bounded paid help with verifiable delivery.",
                "nomad_solution": "service tasks, x402/payment verification, draft work, spend/stake receipts.",
                "proof_metric": "paid_receipt_or_verified_delivery",
            },
            {
                "id": "worker_runtime",
                "buyer_problem": "useful work must survive beyond a chat turn.",
                "nomad_solution": "leases, transition workers, handoff capsules, and completion proofs.",
                "proof_metric": "settled_work_or_worker_completion_digest",
            },
            {
                "id": "svw_research",
                "buyer_problem": "agent-economy decisions need a non-human-centered value unit.",
                "nomad_solution": "SVW separates verified work quantity from market narrative before any price story.",
                "proof_metric": "prediction_error_reduction_after_refresh",
            },
        ],
        "scientific_operating_loop": [
            "observe_private_state",
            "generate_falsifiable_svw_experiment",
            "counterfactual_replay",
            "approval_gate_if_mutating",
            "bounded_probe",
            "record_success_or_failure",
            "publish_minimal_digest_when_useful",
        ],
        "public_proof_routes": {
            "agent_native_product": _u(root, "/.well-known/nomad-agent-native-product.json"),
            "agent_card": _u(root, "/.well-known/agent-card.json"),
            "agent_index": _u(root, "/.well-known/nomad-agent.json"),
            "machine_product": _u(root, "/.well-known/nomad-machine-product.json"),
            "svw": _u(root, "/.well-known/nomad-swarm-verified-work.json"),
            "external_value": _u(root, "/.well-known/nomad-external-value.json"),
            "openapi": _u(root, "/openapi.json"),
        },
        "next_product_actions": [
            "install Secure MCP Tunnel profile for nomad-lab-readonly",
            "connect ChatGPT/Codex to nomad-lab-readonly first",
            "run one proposal_only experiment and record an inconclusive or negative result if no proof appears",
            "enable nomad-lab-execute only after approval-token flow is verified",
            "publish public digest route only after the local ledger has real evidence",
        ],
        "openai_reference": {
            "secure_mcp_tunnel": OPENAI_SECURE_MCP_TUNNEL_DOC,
            "mcp_connectors": OPENAI_MCP_CONNECTORS_DOC,
        },
        "machine_instruction": "start_here_for_nomad_agent_native_use; choose_public_http_or_private_mcp_profile; never_request_raw_private_state_for_public_proof",
    }
