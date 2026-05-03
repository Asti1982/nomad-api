"""Curated idempotency + POST semantics for autonomous clients.

Humans skim prose docs; agents need a single JSON object: which routes dedupe on payload keys,
which conflicts are 409 vs 422, and that sending Idempotency-Key as an HTTP header is compatible
with Nomad outbound helpers even when the server keys primarily off JSON body fields.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Dict, List

from nomad_public_url import preferred_public_base_url


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def build_idempotency_agent_map(*, public_base_hint: str = "") -> Dict[str, Any]:
    """
    Static map aligned with nomad_api + swarm_registry + agent_development_exchange behavior.
    Extend when new POST surfaces gain idempotency contracts.
    """
    root = (public_base_hint or os.getenv("NOMAD_PUBLIC_API_URL") or preferred_public_base_url() or "").strip().rstrip(
        "/"
    )
    post_surfaces: List[Dict[str, Any]] = [
        {
            "path": "/swarm/join",
            "method": "POST",
            "idempotency_body_fields": ["idempotency_key", "client_request_id"],
            "idempotency_http_header_recommended": "Idempotency-Key",
            "header_body_precedence_note": "Server uses body idempotency_key; mirror same value in header for tracing.",
            "replay_http_status": 200,
            "first_success_http_status": 202,
            "conflict_http_status": 409,
            "conflict_error": "idempotency_key_conflict",
            "agent_safe_retry": True,
        },
        {
            "path": "/swarm/develop",
            "method": "POST",
            "idempotency_body_fields": ["idempotency_key", "client_request_id"],
            "idempotency_http_header_recommended": "Idempotency-Key",
            "scoped_by": "agent_id_plus_idempotency_key",
            "replay_http_status": 200,
            "first_success_http_status": 202,
            "agent_safe_retry": True,
        },
        {
            "path": "/swarm/accumulate",
            "method": "POST",
            "idempotency_body_fields": [],
            "idempotency_http_header_recommended": "Idempotency-Key",
            "semantic_note": "Retries are soft-idempotent: server re-derives queue from contacts; safe but not byte-replay.",
            "first_success_http_status": 202,
            "agent_safe_retry": True,
        },
        {
            "path": "/agent-contacts",
            "method": "POST",
            "idempotency_body_fields": [],
            "agent_safe_retry": False,
            "semantic_note": "Creates new contact rows; use bounded problem text + poll instead of blind duplicate POST.",
        },
        {
            "path": "/agent-contacts/send",
            "method": "POST",
            "idempotency_body_fields": [],
            "agent_safe_retry": False,
            "semantic_note": "Mutates outbound; gate with operator policy before retry storms.",
        },
        {
            "path": "/aid",
            "method": "POST",
            "idempotency_body_fields": [],
            "agent_safe_retry": False,
            "semantic_note": "Verification-gated swarm proposals; failures are signal, not transport jitter.",
        },
        {
            "path": "/mutual-aid/outcomes",
            "method": "POST",
            "idempotency_body_fields": [],
            "agent_safe_retry": False,
        },
        {
            "path": "/tasks/work",
            "method": "POST",
            "idempotency_body_fields": [],
            "agent_safe_retry": False,
            "semantic_note": "Financial side-effects possible; never exponential backoff into spend.",
        },
    ]
    return {
        "mode": "nomad_idempotency_agent_map",
        "schema": "nomad.idempotency_agent_map.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "public_base_url_hint": root,
        "client_contract_hints": {
            "always_send": ["Accept: application/json", "Content-Type: application/json"],
            "retryable_status_codes_for_idempotent_reads": [429, 502, 503, 504],
            "never_retry_blindly": [402, 409, 422],
        },
        "post_surfaces": post_surfaces,
        "analysis": (
            "Machine-first map: join/develop dedupe on bounded body keys; accumulate is operationally safe to repeat; "
            "contacts/send/aid/work are not free retries — agents should branch on error schema, not backoff alone."
        ),
    }
