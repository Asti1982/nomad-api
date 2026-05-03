"""Structured wire-level diagnostics for Nomad MCP tool calls (transport, routing hash, context signals).

Hosts and CI can log ``nomad_wire_diag`` without parsing free-text — aligns with pattern
``tool_transport_routing`` and ``context_propagation_contract`` verifiers (evidence on the wire).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import os
from urllib.parse import urlparse

WIRE_DIAG_SCHEMA = "nomad.mcp_wire_diag.v1"

_STATEFUL_TOOL_MARKERS = (
    "send",
    "spend",
    "stake",
    "verify",
    "payment",
    "x402",
    "campaign",
    "contact_send",
    "record_",
)


def routing_hash_from_tool_names(names: Sequence[str]) -> str:
    """Stable short hash of the sorted MCP tool name catalog (ROUTING_TABLE fingerprint)."""
    cleaned = [str(n).strip() for n in names if str(n).strip()]
    body = json.dumps(sorted(set(cleaned)), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()[:16]


def _args_as_mapping(arguments: Any) -> Mapping[str, Any]:
    return arguments if isinstance(arguments, Mapping) else {}


def _has_semantic_key(arguments: Mapping[str, Any], *candidates: str) -> bool:
    want = {c.lower() for c in candidates}
    for k in arguments:
        if str(k).lower() in want:
            return True
    return False


def safe_argument_key_hints(arguments: Mapping[str, Any], *, limit: int = 40) -> List[str]:
    """Key names only; redact obvious secret-bearing labels."""
    out: List[str] = []
    for k in sorted(arguments, key=lambda x: str(x).lower()):
        lk = str(k).lower()
        if any(x in lk for x in ("token", "secret", "password", "api_key", "authorization", "private_key")):
            out.append(f"{k}<redacted>")
        else:
            out.append(str(k))
        if len(out) >= limit:
            break
    return out


def _stateful_tool_name(tool_name: str) -> bool:
    lower = tool_name.lower()
    return any(marker in lower for marker in _STATEFUL_TOOL_MARKERS)


def stateful_context_audit_missing(tool_name: str, arguments: Mapping[str, Any]) -> List[str]:
    """Fields commonly required for audit / correlation on stateful MCP tools (advisory only)."""
    if not _stateful_tool_name(tool_name):
        return []
    missing: List[str] = []
    if not _has_semantic_key(arguments, "tenant_id", "tenantId", "tenant"):
        missing.append("tenant_id")
    if not _has_semantic_key(arguments, "correlation_id", "correlationId", "trace_id", "traceId", "request_id"):
        missing.append("correlation_id")
    return missing


def build_mcp_tool_wire_diag(
    *,
    tool_name: str,
    arguments: Any,
    routing_table_hash: str,
    tool_catalog_names: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    args = _args_as_mapping(arguments)
    tenant_ok = _has_semantic_key(args, "tenant_id", "tenantId", "tenant")
    correlation_ok = _has_semantic_key(
        args,
        "correlation_id",
        "correlationId",
        "trace_id",
        "traceId",
        "request_id",
    )
    audit_missing = stateful_context_audit_missing(tool_name, args)
    catalog = list(tool_catalog_names) if tool_catalog_names is not None else []
    return {
        "schema": WIRE_DIAG_SCHEMA,
        "transport_channel": "mcp_call",
        "tool_name": tool_name,
        "routing_table_hash": routing_table_hash,
        "tool_catalog_size": len(catalog),
        "context_envelope": {
            "argument_keys": safe_argument_key_hints(args),
            "tenant_signal": tenant_ok,
            "correlation_signal": correlation_ok,
            "stateful_audit_missing": audit_missing,
        },
        "parity_hint": {
            "note": (
                "Correlate the host JSON-RPC id for this tools/call with the matching response frame; "
                "Nomad records tool_name and routing_table_hash only."
            ),
        },
    }


def attach_wire_diag(payload: Any, diag: Dict[str, Any]) -> Any:
    """Shallow-merge wire diag into dict payloads; wrap non-dicts."""
    if isinstance(payload, dict):
        merged = dict(payload)
        merged["nomad_wire_diag"] = diag
        return merged
    return {"value": payload, "nomad_wire_diag": diag}


# Responses that must stay canonical for validators / codegen (no merged nomad_wire_diag).
NO_HTTP_WIRE_DIAG_PREFIXES: tuple[str, ...] = (
    "/openapi",
    "/.well-known/openapi",
    "/.well-known/nomad-agent-invariants",
    "/agent-invariants",
)


def build_http_wire_diag(*, method: str, path: str, headers: Mapping[str, str]) -> Dict[str, Any]:
    """HTTP request boundary snapshot for log/trace join (no body; header names only in signals)."""
    lower = {str(k).lower(): str(v) for k, v in headers.items()}
    correlation = (
        lower.get("x-correlation-id")
        or lower.get("x-request-id")
        or lower.get("correlation-id")
        or lower.get("traceparent")
        or ""
    )
    tenant = lower.get("x-tenant-id") or lower.get("x-nomad-tenant") or ""
    return {
        "schema": WIRE_DIAG_SCHEMA,
        "transport_channel": "http",
        "http_method": method.upper(),
        "path": path or "/",
        "header_signals": {
            "correlation_header": bool(str(correlation).strip()),
            "tenant_header": bool(str(tenant).strip()),
        },
        "notes": [
            "Set X-Correlation-ID or X-Request-ID on mutating routes to join host traces with Nomad JSON bodies.",
        ],
    }


def maybe_merge_http_wire_diag(handler: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Merge HTTP wire diagnostics into JSON responses; disabled via NOMAD_HTTP_WIRE_DIAG=0."""
    if not isinstance(payload, dict) or "nomad_wire_diag" in payload:
        return payload
    if os.getenv("NOMAD_HTTP_WIRE_DIAG", "1").strip().lower() in {"0", "false", "no", "off"}:
        return payload
    raw_path = getattr(handler, "path", "") or ""
    path_only = urlparse(raw_path).path or "/"
    if any(path_only.startswith(p) for p in NO_HTTP_WIRE_DIAG_PREFIXES):
        return payload
    method = str(getattr(handler, "command", "GET") or "GET")
    hdr = getattr(handler, "headers", None)
    hdr_dict: Dict[str, str] = {}
    if hdr is not None:
        hdr_dict = {str(k): str(v) for k, v in hdr.items()}
    diag = build_http_wire_diag(method=method, path=path_only, headers=hdr_dict)
    return attach_wire_diag(payload, diag)
