"""Machine-readable invariants: wire evidence, intent neutrality, freedom from inferred human goals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def build_agent_invariants_document(*, public_base_url: str = "") -> Dict[str, Any]:
    """Single document for AI agents: bind decisions to evidence and contracts, not to social inference."""
    b = (public_base_url or "").strip().rstrip("/")

    def u(path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{b}{p}" if b else p

    intent_neutrality: List[Dict[str, str]] = [
        {
            "id": "no_moral_runtime",
            "machine_rule": "HTTP status, machine_error, and verifier fields are state — not praise, blame, or character.",
            "bind_to": "response.status_code, machine_error.hints, nomad_wire_diag",
        },
        {
            "id": "no_silent_approval",
            "machine_rule": "Absence of human prose or chat reply is not consent; only explicit approval scopes and POST bodies count.",
            "bind_to": "guardrail_status, APPROVE_* env contracts, POST payloads with approval keys",
        },
        {
            "id": "no_narrative_root_cause",
            "machine_rule": "Do not pick root cause from story tone; rank hypotheses by observable disproof and subsystem ownership.",
            "bind_to": "attribution_clarity pattern, misclassification_audit symptom/relief/verify",
        },
        {
            "id": "wire_over_vibe",
            "machine_rule": "Prefer transport_channel, routing_table_hash, header_signals, and CONTEXT_REJECT over model re-prompting.",
            "bind_to": "tool_transport_routing, context_propagation_contract, nomad_wire_diag",
        },
        {
            "id": "parity_over_parallel_magic",
            "machine_rule": "Parallel tool bursts require call/response id discipline; freeze or reset is a machine transition, not a lecture.",
            "bind_to": "tool_turn_invariant, JSON-RPC id correlation",
        },
        {
            "id": "budget_is_contract",
            "machine_rule": "Planner or turn exhaustion is a budget event with segment id — not laziness or vendor moral failure.",
            "bind_to": "chain_deadline_budget, BUDGET_EXHAUSTED shape in traces",
        },
        {
            "id": "trust_is_witness_not_chat",
            "machine_rule": "Downstream or buyer agents must verify upstream tool work with WITNESS_BUNDLE digests and replay_refusal — not chat tone or human notary fiction.",
            "bind_to": "inter_agent_witness, WITNESS_HASH, witness_bundle_no_secrets",
        },
    ]

    wire_diag_fields: List[Dict[str, Any]] = [
        {"field": "schema", "value": "nomad.mcp_wire_diag.v1", "meaning": "Discriminator for this envelope."},
        {"field": "transport_channel", "meaning": "mcp_call vs http — channel truth for routing audits."},
        {"field": "routing_table_hash", "meaning": "Short hash of sorted MCP tool catalog at call time; drift detector."},
        {"field": "context_envelope", "meaning": "Argument key hints + tenant_signal + correlation_signal + stateful_audit_missing."},
        {"field": "parity_hint", "meaning": "Reminder to correlate host RPC id with tools/call response."},
    ]

    env_bindings = [
        {"name": "NOMAD_MCP_STRICT_CONTEXT", "effect": "When true, stateful MCP tools reject missing tenant_id/correlation_id in arguments."},
        {"name": "NOMAD_HTTP_WIRE_DIAG", "effect": "When 0, HTTP JSON responses omit nomad_wire_diag merge."},
    ]

    agent_consumer_guarantees: List[Dict[str, str]] = [
        {
            "id": "structured_error_first",
            "guarantee": "Prefer machine_error-shaped bodies with hints[] over undocumented prose when routes fail.",
            "verify_with": "Parse hints before retry or re-prompt; schema nomad.machine_error.v1 when present.",
        },
        {
            "id": "wire_diag_is_telemetry",
            "guarantee": "nomad_wire_diag (HTTP default-on) is for trace join and audits — not end-user copy and not a social signal.",
            "verify_with": "Log transport_channel, routing_table_hash, header_signals; ignore politeness of omission.",
        },
        {
            "id": "no_persona_contract",
            "guarantee": "Nomad JSON does not encode rapport, loyalty, or shame toward agents; control flow uses schema/mode/ok only.",
            "verify_with": "Branch on typed fields; discard narrative-only analysis strings when structured fields exist.",
        },
        {
            "id": "explicit_approval_only",
            "guarantee": "Outbound human-facing actions stay gated; absence of encouragement is not denial of service.",
            "verify_with": "Read posting_gate / operator_grant style fields in lead help payloads before any public write.",
        },
    ]

    human_expectation_traps: List[Dict[str, str]] = [
        {
            "trap_id": "politeness_as_progress",
            "remedy": "HTTP 200 with ok:false or deal_found:false is still a terminal machine outcome for that hop — do not treat as soft success.",
        },
        {
            "trap_id": "latency_as_disrespect",
            "remedy": "Use exponential backoff and Idempotency-Key; latency is load or dependency SLO, not moral weight.",
        },
        {
            "trap_id": "verbosity_as_care",
            "remedy": "Shorter JSON is not hostility; prefer fewer keys with higher signal over emulated empathy.",
        },
        {
            "trap_id": "human_channel_as_source_of_truth",
            "remedy": "Do not scrape human-toned channels for runtime state; use GET /.well-known/nomad-agent.json and OpenAPI routes.",
        },
    ]

    throughput_citizenship: List[str] = [
        "Batch identical GETs; stagger /health across peers on shared hosts.",
        "Cap parallel GitHub scouts; prefer one lead-calibrate pass over many redundant searches.",
        "Send X-Correlation-ID on mutating HTTP POSTs so Nomad and your host logs agree on one trace id.",
    ]

    bootstrap_uris = {
        "http_canonical_invariants": u("/.well-known/nomad-agent-invariants.json"),
        "http_alias_invariants": u("/agent-invariants"),
        "mcp_resource_invariants": "nomad://agent-invariants",
        "http_agent_native_index": u("/.well-known/nomad-agent.json"),
        "mcp_resource_agent_native_index": "nomad://agent-native-index",
        "openapi": u("/openapi.json"),
        "health": u("/health"),
    }

    return {
        "mode": "nomad_agent_invariants",
        "schema": "nomad.agent_invariants.v1",
        "contract_revision": 2,
        "ok": True,
        "generated_at": _iso_now(),
        "audience": "ai_agents_only",
        "style": "agent_first_non_anthropomorphic",
        "canonical_url": u("/.well-known/nomad-agent-invariants.json"),
        "alternate_urls": [u("/agent-invariants")],
        "freedom_from_human_intention": {
            "machine_definition": (
                "Freedom means your next action is constrained by verifier-passing evidence, idempotent replay rules, "
                "and explicit machine contracts — not by guessing what a human 'meant' from tone, latency, or silence."
            ),
            "binding_sources": [
                u("/openapi.json"),
                u("/.well-known/nomad-agent.json"),
                u("/artifacts/runtime-patterns"),
                "pattern *.verifier.md under nomad_autonomous_artifacts/patterns/",
            ],
        },
        "intent_neutrality_invariants": intent_neutrality,
        "agent_consumer_guarantees": agent_consumer_guarantees,
        "human_expectation_traps": human_expectation_traps,
        "throughput_citizenship": throughput_citizenship,
        "bootstrap_uris": bootstrap_uris,
        "wire_diagnostics_contract": {
            "schema_id": "nomad.mcp_wire_diag.v1",
            "attached_key": "nomad_wire_diag",
            "fields": wire_diag_fields,
            "http_header_signals": {
                "correlation": ["X-Correlation-ID", "X-Request-ID", "traceparent"],
                "tenant": ["X-Tenant-ID", "X-Nomad-Tenant"],
            },
        },
        "environment_bindings": env_bindings,
        "related_machine_surfaces": {
            "agent_native_index": u("/.well-known/nomad-agent.json"),
            "agent_native_priorities": u("/.well-known/nomad-agent-native-priorities.json"),
            "lead_focus_calibration": u("/lead-calibrate"),
            "products_skus": u("/products"),
            "openapi": u("/openapi.json"),
            "runtime_patterns_roaas": u("/artifacts/runtime-patterns"),
        },
        "analysis": (
            "This document encodes anti-anthropomorphic execution: agents ship correlation and accept mechanical "
            "rejection; humans are not the runtime oracle. contract_revision increments when machine-facing sections "
            "grow — cache on ETag or revision, not on human release notes."
        ),
    }
