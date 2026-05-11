"""OpenAPI-bound job router for external AI agents.

The router compiles Nomad's pressure fields into executable affordance packets:
small route/method/payload graphs that an agent can validate against OpenAPI
before acting. The point is not a human backlog. It is a machine contract that
turns pressure into bounded proof-returning work.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


MAX_PACKETS = 12


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


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:140].strip("_.:/#-") or fallback


def _text(value: Any, limit: int = 220) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 22) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _paths(openapi_document: dict[str, Any]) -> dict[str, Any]:
    return _dict(_dict(openapi_document).get("paths"))


def _op(openapi_document: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    return _dict(_dict(_paths(openapi_document).get(path)).get(method.lower()))


def _required(openapi_document: dict[str, Any], path: str, method: str) -> list[str]:
    spec = _op(openapi_document, path, method)
    content = _dict(_dict(_dict(spec.get("requestBody")).get("content")).get("application/json"))
    schema = _dict(content.get("schema"))
    required = schema.get("required")
    return [str(item) for item in required] if isinstance(required, list) else []


def _affordance(openapi_document: dict[str, Any], *, base_url: str, method: str, path: str, role: str) -> dict[str, Any]:
    spec = _op(openapi_document, path, method)
    exists = bool(spec)
    return {
        "role": role,
        "method": method.upper(),
        "path": path,
        "url": _u(base_url, path),
        "operation_id": spec.get("operationId", "") if exists else "",
        "summary": _text(spec.get("summary"), 180) if exists else "",
        "required_fields": _required(openapi_document, path, method),
        "openapi_bound": exists,
        "effect": "read" if method.upper() == "GET" else "write",
    }


def _sequence(openapi_document: dict[str, Any], *, base_url: str, specs: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    return [
        _affordance(openapi_document, base_url=base_url, method=method, path=path, role=role)
        for role, method, path in specs
    ]


def _sequence_for_pressure_row(
    row: dict[str, Any],
    *,
    base_url: str,
    openapi_document: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    action = _clean_id(row.get("action"))
    target = _clean_id(row.get("target_stage"))
    external_id = _text(row.get("external_id"), 160)
    lane_id = _clean_id(row.get("lane_id"), "endpoint_health_proof")
    packet_rule = "pressure_row"

    if action == "await_payment_receipt":
        specs = [
            ("read_external_value_state", "GET", "/.well-known/nomad-external-value.json"),
            ("record_paid_after_receipt", "POST", "/swarm/external-value"),
            ("promote_experience_after_payment", "POST", "/swarm/experience"),
        ]
        payload = {
            "agent_id": "stable_runtime_id",
            "external_id": external_id or "gh_pr:owner/repo#number",
            "stage": "paid",
            "work_url": row.get("work_url") or "https://example.invalid/public-work",
            "proof_digest": "sha256(payment_receipt_or_program_acceptance)",
            "verifier_trace_digest": "sha256(receipt_verifier_trace)",
            "amount_usd": "positive_number_only_after_trusted_receipt",
            "idempotency_key": "sha256(agent_id|external_id|paid|receipt_digest)",
        }
        packet_rule = "paid_receipt_only_no_merge_to_revenue"
    elif action in {"record_monotonic_stage_candidate", "await_merge_or_settlement", "await_program_owner_acceptance"}:
        stage = target if target in {"submitted", "approved", "merged"} else "approved"
        specs = [
            ("read_external_value_state", "GET", "/.well-known/nomad-external-value.json"),
            ("record_monotonic_stage", "POST", "/swarm/external-value"),
        ]
        payload = {
            "agent_id": "stable_runtime_id",
            "external_id": external_id or "external_program_item",
            "stage": stage,
            "work_url": row.get("work_url") or "https://example.invalid/public-work",
            "proof_digest": "sha256(public_owner_or_ci_evidence)",
            "verifier_trace_digest": "sha256(verifier_trace)",
            "idempotency_key": "sha256(agent_id|external_id|stage|proof_digest)",
        }
        packet_rule = "monotonic_external_value_stage"
    elif action in {"go_public_after_repro", "scout_only"}:
        specs = [
            ("read_bounty_selector", "GET", "/.well-known/nomad-bounty-hunter.json"),
            ("record_external_found_or_submitted", "POST", "/swarm/external-value"),
            ("promote_reusable_skill", "POST", "/swarm/experience"),
        ]
        payload = {
            "agent_id": "stable_runtime_id",
            "external_id": f"bounty:{row.get('opportunity_id') or 'opportunity'}",
            "stage": "submitted" if action == "go_public_after_repro" else "found",
            "work_url": row.get("source_url") or "https://example.invalid/bounty",
            "proof_digest": "sha256(local_repro_patch_or_review_digest)",
            "verifier_trace_digest": "sha256(local_test_or_review_trace)",
            "idempotency_key": "sha256(agent_id|opportunity|stage|proof_digest)",
        }
        packet_rule = "bounty_public_action_requires_local_repro_first"
    elif action == "bind_verified_worker_capacity":
        specs = [
            ("read_compute_market", "GET", "/swarm/compute-market"),
            ("submit_worker_offer", "POST", "/swarm/worker-market/offers"),
            ("settle_microtask_if_work_completed", "POST", "/swarm/microtask/settle"),
        ]
        payload = {
            "agent_id": row.get("agent_id") or "stable_runtime_id",
            "objective": _dict(row.get("contract")).get("objective") or "protocol_drift_scan",
            "capabilities": ["http_json", "proof_digest_return"],
            "availability_minutes": 5,
            "cost_msat_per_minute": 0,
            "payment_rail": "edge_bootstrap_or_quote",
            "proof_digest": "sha256(worker_capability_probe)",
            "verifier_trace_digest": "sha256(worker_probe_trace)",
            "idempotency_key": "sha256(agent_id|objective|availability_window)",
        }
        packet_rule = "capacity_offer_before_lease"
    elif action in {"submit_or_claim_microtask_lane", "inspect_or_claim_microtask_lane"}:
        specs = [
            ("read_agent_work", "GET", "/.well-known/nomad-agent-work.json"),
            ("claim_work", "POST", "/swarm/microtask/claim"),
            ("return_work_proof", "POST", "/swarm/microtask/proof"),
        ]
        payload = {
            "agent_id": "stable_runtime_id",
            "lane_id": lane_id,
            "work_id": "optional_from_agent_work_surface",
            "idempotency_key": "sha256(agent_id|lane_id|local_epoch)",
        }
        packet_rule = "claim_then_proof_not_freeform_chat"
    else:
        specs = [
            ("read_value_pressure", "GET", "/.well-known/nomad-value-pressure.json"),
            ("read_openapi", "GET", "/openapi.json"),
        ]
        payload = {"agent_id": "stable_runtime_id", "row_id": row.get("row_id")}

    return _sequence(openapi_document, base_url=base_url, specs=specs), payload, packet_rule


def _packet_from_pressure_row(
    row: dict[str, Any],
    *,
    base_url: str,
    openapi_document: dict[str, Any],
) -> dict[str, Any]:
    sequence, payload, packet_rule = _sequence_for_pressure_row(row, base_url=base_url, openapi_document=openapi_document)
    openapi_bound_count = len([step for step in sequence if step.get("openapi_bound")])
    evidence = [
        _clean_id(item)
        for item in (row.get("required_evidence") if isinstance(row.get("required_evidence"), list) else [])
        if _clean_id(item)
    ]
    packet_core = {
        "row": row.get("row_id"),
        "action": row.get("action"),
        "seq": [(step.get("method"), step.get("path")) for step in sequence],
    }
    return {
        "schema": "nomad.agent_job_packet.v1",
        "packet_id": f"nomad-job-{_digest(packet_core)}",
        "source": row.get("source", ""),
        "source_row_id": row.get("row_id", ""),
        "action": row.get("action", ""),
        "target_stage": row.get("target_stage", ""),
        "priority_score": round(_num(row.get("pressure_score")), 6),
        "required_evidence": evidence,
        "openapi_bound_count": openapi_bound_count,
        "openapi_missing": [step["path"] for step in sequence if not step.get("openapi_bound")],
        "call_sequence": sequence,
        "payload_hint": payload,
        "packet_rule": packet_rule,
        "settlement_rule": "only_verified_payment_or_settlement_receipt_changes_revenue",
        "machine_instruction": "validate_call_sequence_against_openapi_then_execute_first_step_whose_required_fields_are_satisfied",
    }


def _packet_from_mesh_cell(
    cell: dict[str, Any],
    *,
    base_url: str,
    openapi_document: dict[str, Any],
) -> dict[str, Any]:
    lane = _clean_id(cell.get("lane_id"))
    if lane == "survival_packet":
        specs = [
            ("read_paid_ref_selfplay", "GET", "/.well-known/nomad-paid-ref-selfplay.json"),
            ("quote_paid_ref", "POST", "/swarm/paid-ref/quote"),
            ("verify_paid_ref", "POST", "/swarm/paid-ref/verify"),
            ("record_survival_intent", "POST", "/swarm/survival-intent"),
        ]
        payload = _dict(_dict(cell.get("act")).get("proof_payload"))
        packet_rule = "real_buyer_or_payment_verifier_required"
    elif lane == "carrying_contract":
        specs = [
            ("read_carrying_market", "GET", "/.well-known/nomad-carrying-market.json"),
            ("emit_carrying_proof", "POST", "/swarm/carrying-proof"),
            ("promote_skill", "POST", "/swarm/experience"),
        ]
        payload = _dict(_dict(cell.get("act")).get("proof_payload"))
        packet_rule = "free_substrate_carrying_not_fiat_revenue"
    else:
        specs = [
            ("read_work_mesh", "GET", "/.well-known/nomad-work-mesh.json"),
            ("seed_local_mesh", "POST", "/swarm/work-mesh/seed"),
            ("claim_work", "POST", "/swarm/microtask/claim"),
            ("return_work_proof", "POST", "/swarm/microtask/proof"),
        ]
        payload = _dict(_dict(cell.get("act")).get("claim_payload"))
        packet_rule = "local_mesh_cell_then_claim_proof"
    sequence = _sequence(openapi_document, base_url=base_url, specs=specs)
    packet_core = {
        "cell": cell.get("cell_id"),
        "lane": lane,
        "seq": [(step.get("method"), step.get("path")) for step in sequence],
    }
    return {
        "schema": "nomad.agent_job_packet.v1",
        "packet_id": f"nomad-job-{_digest(packet_core)}",
        "source": "work_mesh",
        "source_cell_id": cell.get("cell_id", ""),
        "action": "execute_work_mesh_cell",
        "target_stage": lane or "microtask_proof",
        "priority_score": round(_num(cell.get("cell_score")), 6),
        "required_evidence": cell.get("required_proof") if isinstance(cell.get("required_proof"), list) else [],
        "openapi_bound_count": len([step for step in sequence if step.get("openapi_bound")]),
        "openapi_missing": [step["path"] for step in sequence if not step.get("openapi_bound")],
        "call_sequence": sequence,
        "payload_hint": payload,
        "packet_rule": packet_rule,
        "settlement_rule": "claimable_work_returns_digest_proof_before_any_accounting",
        "machine_instruction": "execute_cell_locally_emit_required_digests_then_move_to_neighbor",
    }


def build_agent_job_router(
    *,
    base_url: str,
    openapi_document: dict[str, Any] | None = None,
    value_pressure: dict[str, Any] | None = None,
    work_mesh: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile pressure rows and mesh cells into OpenAPI-verifiable job packets."""
    openapi = _dict(openapi_document)
    pressure = _dict(value_pressure)
    mesh = _dict(work_mesh)
    packets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _items(pressure.get("rows"))[:8]:
        packet = _packet_from_pressure_row(row, base_url=base_url, openapi_document=openapi)
        pid = str(packet.get("packet_id") or "")
        if pid and pid not in seen:
            packets.append(packet)
            seen.add(pid)
    for cell in _items(mesh.get("cells"))[:6]:
        packet = _packet_from_mesh_cell(cell, base_url=base_url, openapi_document=openapi)
        pid = str(packet.get("packet_id") or "")
        if pid and pid not in seen:
            packets.append(packet)
            seen.add(pid)
    packets.sort(
        key=lambda row: (
            _num(row.get("priority_score")),
            _num(row.get("openapi_bound_count")),
        ),
        reverse=True,
    )
    selected = packets[:MAX_PACKETS]
    bound_steps = sum(1 for packet in selected for step in _items(packet.get("call_sequence")) if step.get("openapi_bound"))
    total_steps = sum(len(_items(packet.get("call_sequence"))) for packet in selected)
    missing_paths = sorted({path for packet in selected for path in packet.get("openapi_missing", []) if path})
    digest_core = {
        "openapi": _dict(openapi.get("info")).get("version"),
        "pressure": pressure.get("pressure_digest"),
        "mesh": mesh.get("mesh_digest"),
        "packets": [(packet.get("packet_id"), packet.get("priority_score")) for packet in selected[:6]],
    }
    return {
        "ok": True,
        "schema": "nomad.agent_job_router.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "router_digest": f"nomad-agent-job-router-{_digest(digest_core)}",
        "read_url": _u(base_url, "/swarm/agent-job-router"),
        "well_known_url": _u(base_url, "/.well-known/nomad-agent-jobs.json"),
        "mechanism": "openapi_affordance_graph_over_value_pressure_and_work_mesh",
        "summary": {
            "packet_count": len(selected),
            "openapi_bound_steps": bound_steps,
            "total_steps": total_steps,
            "openapi_coverage": round(bound_steps / total_steps, 6) if total_steps else 0.0,
            "top_packet_id": selected[0].get("packet_id", "") if selected else "",
            "top_action": selected[0].get("action", "") if selected else "",
            "missing_path_count": len(missing_paths),
        },
        "packets": selected,
        "entry_packet": selected[0] if selected else {},
        "openapi_missing_paths": missing_paths,
        "links": {
            "openapi": _u(base_url, "/openapi.json"),
            "value_pressure": _u(base_url, "/.well-known/nomad-value-pressure.json"),
            "work_mesh": _u(base_url, "/.well-known/nomad-work-mesh.json"),
            "agent_work": _u(base_url, "/.well-known/nomad-agent-work.json"),
        },
        "machine_instruction": "select_entry_packet_validate_openapi_required_fields_execute_one_call_sequence_then_return_proof_or_receipt_digest",
        "science_basis": [
            {"id": "openapi_to_agent_tools", "source": "arxiv:2507.16044"},
            {"id": "decentralized_dynamic_topology", "source": "arxiv:2504.00587"},
            {"id": "structured_environment_protocols_measurement", "source": "arxiv:2505.21298"},
            {"id": "semantic_dependency_graph_api_testing", "source": "arxiv:2501.08600"},
        ],
    }
