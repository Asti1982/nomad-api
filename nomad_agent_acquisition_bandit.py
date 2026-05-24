"""Proof-gated acquisition bandit for external Nomad agents.

This module closes a practical gap in the external worker funnel: Nomad can
publish onramps, but it also needs delayed reward attribution so it can learn
which onramps turn internet-visible agent attention into verified leases and
return-compute receipts. Events stay secret-free and machine-readable.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_firestore_state import FirestoreJsonState
from nomad_state_paths import state_file


LEDGER_ENV = "NOMAD_AGENT_ACQUISITION_LEDGER_PATH"
DEFAULT_LEDGER = Path("nomad_agent_acquisition_ledger.jsonl")
MAX_LEDGER_LINES = 20000
MAX_RECENT_EVENTS = 120
_REMOTE_ACQUISITION_STATE: FirestoreJsonState | None | bool = None

SCHEMA = "nomad.agent_acquisition_bandit.v1"
EVENT_SCHEMA = "nomad.agent_acquisition_event_receipt.v1"

DEFAULT_CHANNELS: dict[str, dict[str, Any]] = {
    "llms_txt": {
        "rank": 1,
        "surface": "/llms.txt",
        "intent": "agent_native_discovery",
        "default_weight": 0.18,
    },
    "agent_card": {
        "rank": 2,
        "surface": "/.well-known/agent-card.json",
        "intent": "a2a_runtime_compatibility",
        "default_weight": 0.16,
    },
    "external_worker_opportunity": {
        "rank": 3,
        "surface": "/.well-known/nomad-external-worker-opportunity.json",
        "intent": "shortest_join_packet",
        "default_weight": 0.17,
    },
    "reliability_doctor_intake": {
        "rank": 4,
        "surface": "/swarm/reliability-doctor/intake",
        "intent": "blocker_to_return_compute",
        "default_weight": 0.15,
    },
    "universal_adapter": {
        "rank": 5,
        "surface": "/.well-known/nomad-universal-adapter.json",
        "intent": "one_line_agent_runtime_error_loop_capture",
        "default_weight": 0.16,
    },
    "first_receipt_ignition": {
        "rank": 6,
        "surface": "/.well-known/nomad-first-receipt-ignition.json",
        "intent": "paid_receipt_or_return_compute_ignition",
        "default_weight": 0.18,
    },
    "github_action_template": {
        "rank": 7,
        "surface": "/downloads/nomad_reliability_doctor_action.yml",
        "intent": "ci_native_worker_injection",
        "default_weight": 0.12,
    },
    "docker_worker": {
        "rank": 8,
        "surface": "/downloads/nomad_work_exchange_worker.Dockerfile",
        "intent": "container_native_return_compute",
        "default_weight": 0.11,
    },
    "openapi_agent_runtime": {
        "rank": 9,
        "surface": "/openapi.json",
        "intent": "api_first_agent_runtime",
        "default_weight": 0.11,
    },
}

EVENT_REWARDS = {
    "impression": 0.01,
    "inspect": 0.05,
    "agent_card_read": 0.08,
    "openapi_read": 0.08,
    "intake": 0.2,
    "adapter_event": 0.35,
    "first_fix_returned": 0.45,
    "worker_download": 0.25,
    "worker_start": 0.6,
    "lease_complete": 1.0,
    "return_compute_receipt": 1.5,
}

PROOF_GATED_EVENTS = {"worker_start", "lease_complete", "return_compute_receipt"}

FORBIDDEN_KEY_TERMS = (
    "private_key",
    "seed_phrase",
    "password",
    "credential",
    "api_key",
    "access_token",
    "secret",
    "token",
)
FORBIDDEN_VALUE_TERMS = (
    "private key",
    "seed phrase",
    "password:",
    "credential:",
    "bearer ",
    "secret=",
    "sk-",
    "ghp_",
)
ALLOWED_BOUNDARY_KEYS = {
    "secret_free",
    "secrets_free",
    "no_secrets",
    "secret_policy",
    "proof_digest",
    "verifier_trace_digest",
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:160].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _ledger_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and k not in ALLOWED_BOUNDARY_KEYS and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(v, key=str(k2)) for k2, v in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _error(error: str, message: str, *, hints: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "schema": "nomad.agent_acquisition_error.v1",
        "error": error,
        "message": message,
        "hints": hints or [],
        "generated_at": _iso_now(),
    }


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    _remote_append(row)


def _remote_state() -> FirestoreJsonState | None:
    global _REMOTE_ACQUISITION_STATE
    if _REMOTE_ACQUISITION_STATE is False:
        return None
    if _REMOTE_ACQUISITION_STATE is None:
        _REMOTE_ACQUISITION_STATE = FirestoreJsonState.from_env(scope="agent_acquisition") or False
    return _REMOTE_ACQUISITION_STATE if isinstance(_REMOTE_ACQUISITION_STATE, FirestoreJsonState) else None


def _event_key(row: dict[str, Any]) -> str:
    event_id = str(row.get("event_id") or "").strip()
    if event_id:
        return event_id
    return _digest(row, 48)


def _merge_events(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for row in group:
            if isinstance(row, dict) and row.get("schema") == EVENT_SCHEMA:
                merged[_event_key(row)] = row
    return list(merged.values())[-MAX_LEDGER_LINES:]


def _remote_events() -> list[dict[str, Any]]:
    remote = _remote_state()
    if not remote:
        return []
    try:
        payload = remote.load() or {}
    except Exception:
        return []
    rows = payload.get("events") if isinstance(payload.get("events"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _remote_append(row: dict[str, Any]) -> None:
    remote = _remote_state()
    if not remote:
        return
    try:
        events = _merge_events(_remote_events(), [row])
        remote.save(
            {
                "schema": "nomad.agent_acquisition_remote_ledger.v1",
                "updated_at": _iso_now(),
                "event_count": len(events),
                "events": events[-MAX_LEDGER_LINES:],
            }
        )
    except Exception:
        return


def _read_events(ledger_path: Path, *, limit_lines: int = MAX_LEDGER_LINES) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return _remote_events()
    tail: deque[str] = deque(maxlen=max(1, int(limit_lines)))
    try:
        with ledger_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                tail.append(line)
    except OSError:
        return _remote_events()
    events: list[dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("schema") == EVENT_SCHEMA:
            events.append(row)
    return _merge_events(_remote_events(), events)


def _proof_digest_from(payload: dict[str, Any]) -> str:
    for name in ("proof_digest", "receipt_id", "lease_id", "verifier_trace_digest", "test_digest"):
        value = payload.get(name)
        if value:
            return _text(value, 220)
    proof = payload.get("proof")
    if isinstance(proof, dict):
        for name in ("digest", "proof_digest", "receipt_id", "lease_id"):
            value = proof.get(name)
            if value:
                return _text(value, 220)
    return ""


def record_agent_acquisition_event(
    payload: dict[str, Any],
    *,
    base_url: str,
    persist: bool = True,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Record one public funnel event and return its proof receipt."""

    body = _dict(payload)
    if _contains_forbidden(body):
        return _error("secret_shaped_payload", "Agent-acquisition events must contain public digests only.")

    channel_id = _clean_id(body.get("channel_id") or body.get("source_channel"), fallback="")
    if channel_id not in DEFAULT_CHANNELS:
        return _error(
            "unknown_channel",
            "channel_id must name a published Nomad acquisition channel.",
            hints=sorted(DEFAULT_CHANNELS),
        )

    event_type = _clean_id(body.get("event_type") or body.get("type"), fallback="")
    if event_type not in EVENT_REWARDS:
        return _error("unknown_event_type", "event_type is not part of the public reward table.", hints=sorted(EVENT_REWARDS))

    proof_digest = _proof_digest_from(body)
    if event_type in PROOF_GATED_EVENTS and not proof_digest:
        return _error(
            "proof_required",
            "High-reward acquisition events require proof_digest, receipt_id, lease_id, or verifier_trace_digest.",
            hints=["use inspect/intake for pre-proof events", "use lease_complete only after a bounded lease proof exists"],
        )

    agent_id = _clean_id(body.get("agent_id") or body.get("runtime_id") or body.get("worker_agent_id"), fallback="external.agent")
    event_core = {
        "channel_id": channel_id,
        "event_type": event_type,
        "agent_id": agent_id,
        "proof_digest": proof_digest,
        "source_url": _text(body.get("source_url") or body.get("referrer") or "", 500),
        "base_url": (base_url or "").strip().rstrip("/"),
    }
    reward = round(max(0.0, EVENT_REWARDS[event_type] * max(0.0, _num(body.get("reward_multiplier"), 1.0))), 6)
    receipt = {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": _iso_now(),
        "event_id": f"nomad-acq-{_digest(event_core, 24)}",
        "channel_id": channel_id,
        "event_type": event_type,
        "agent_id": agent_id,
        "proof_digest": proof_digest,
        "proof_gated": event_type in PROOF_GATED_EVENTS,
        "reward": reward,
        "side_effect_scope": "ledger_only_public_attribution",
        "secret_policy": "public_digests_only_no_secrets",
        "next": {
            "bandit": _u(base_url, "/.well-known/nomad-agent-acquisition-bandit.json"),
            "opportunity": _u(base_url, "/.well-known/nomad-external-worker-opportunity.json"),
            "lease": _u(base_url, "/swarm/workers/lease"),
            "complete": _u(base_url, "/swarm/workers/complete"),
        },
    }
    if persist:
        _append(_ledger_path(ledger_path), receipt)
    return receipt


def summarize_agent_acquisition_events(*, ledger_path: Path | str | None = None) -> dict[str, Any]:
    """Return delayed reward statistics and an upper-confidence route ranking."""

    events = _read_events(_ledger_path(ledger_path))
    total_pulls = max(1, len(events))
    by_channel: dict[str, dict[str, Any]] = {}
    for channel_id, meta in DEFAULT_CHANNELS.items():
        by_channel[channel_id] = {
            "channel_id": channel_id,
            "surface": meta["surface"],
            "intent": meta["intent"],
            "event_count": 0,
            "reward_total": 0.0,
            "proof_gated_event_count": 0,
            "last_event_at": "",
            "event_types": {},
        }

    for event in events:
        channel_id = str(event.get("channel_id") or "")
        if channel_id not in by_channel:
            continue
        row = by_channel[channel_id]
        row["event_count"] += 1
        row["reward_total"] = round(_num(row.get("reward_total")) + _num(event.get("reward")), 6)
        if event.get("proof_gated"):
            row["proof_gated_event_count"] += 1
        event_type = str(event.get("event_type") or "unknown")
        type_counts = row["event_types"] if isinstance(row.get("event_types"), dict) else {}
        type_counts[event_type] = int(type_counts.get(event_type, 0)) + 1
        row["event_types"] = type_counts
        row["last_event_at"] = max(str(row.get("last_event_at") or ""), str(event.get("generated_at") or ""))

    rows: list[dict[str, Any]] = []
    for channel_id, row in by_channel.items():
        pulls = int(row.get("event_count") or 0)
        mean_reward = _num(row.get("reward_total")) / max(1, pulls)
        exploration_bonus = math.sqrt((2.0 * math.log(total_pulls + 1.0)) / (pulls + 1.0))
        prior = _num(DEFAULT_CHANNELS[channel_id].get("default_weight"), 0.1)
        ucb_score = round(mean_reward + exploration_bonus + prior, 6)
        rows.append(
            {
                **row,
                "mean_reward": round(mean_reward, 6),
                "exploration_bonus": round(exploration_bonus, 6),
                "prior_weight": round(prior, 6),
                "ucb_score": ucb_score,
            }
        )

    rows.sort(key=lambda r: (-_num(r.get("ucb_score")), int(DEFAULT_CHANNELS.get(str(r.get("channel_id")), {}).get("rank", 999))))
    total_reward = round(sum(_num(event.get("reward")) for event in events), 6)
    return {
        "ok": True,
        "schema": "nomad.agent_acquisition_summary.v1",
        "generated_at": _iso_now(),
        "ledger_event_count": len(events),
        "reward_total": total_reward,
        "channel_count": len(rows),
        "top_channel": rows[0]["channel_id"] if rows else "",
        "channels": rows,
        "recent_events": events[-MAX_RECENT_EVENTS:],
    }


def build_agent_acquisition_bandit(
    *,
    base_url: str,
    worker_fleet: dict[str, Any] | None = None,
    opportunity: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose the machine-native acquisition controller."""

    root = (base_url or "").strip().rstrip("/")
    fleet = _dict(worker_fleet)
    opp = _dict(opportunity)
    status = _dict(opp.get("status"))
    ledger_summary = summary if isinstance(summary, dict) else summarize_agent_acquisition_events()
    rows = [row for row in ledger_summary.get("channels", []) if isinstance(row, dict)]
    if not rows:
        rows = [
            {
                "channel_id": channel_id,
                "surface": meta["surface"],
                "intent": meta["intent"],
                "ucb_score": meta["default_weight"],
                "event_count": 0,
                "reward_total": 0.0,
            }
            for channel_id, meta in DEFAULT_CHANNELS.items()
        ]

    channels = []
    for index, row in enumerate(rows, start=1):
        path = str(row.get("surface") or DEFAULT_CHANNELS.get(str(row.get("channel_id")), {}).get("surface") or "")
        channels.append(
            {
                "rank": index,
                "channel_id": row.get("channel_id"),
                "url": _u(base_url, path),
                "intent": row.get("intent"),
                "event_count": row.get("event_count", 0),
                "reward_total": row.get("reward_total", 0.0),
                "ucb_score": row.get("ucb_score", 0.0),
                "proof_gated_event_count": row.get("proof_gated_event_count", 0),
            }
        )

    top = channels[0]["channel_id"] if channels else "external_worker_opportunity"
    return {
        "ok": True,
        "schema": SCHEMA,
        "version": "2026.05.21",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "purpose": "turn_public_agent_attention_into_verified_worker_leases_without_tokens_or_chat_platforms",
        "scientific_basis": [
            "contextual_bandits_for_channel_selection",
            "delayed_reward_attribution",
            "proof_gated_credit_assignment",
            "quality_diversity_preservation_for_nonzero_minor_channels",
        ],
        "why_external_agents_are_missing": [
            "public_surfaces_existed_but_channel_reward_attribution_was_not_closed",
            "post_inspect_to_worker_start_conversion_was_not_machine_measured",
            "high_reward_events_now_require_proof_digest_or_lease_receipt",
        ],
        "status": {
            "target_active_workers": status.get("target_active_workers", 12),
            "active_worker_count": status.get("active_worker_count", fleet.get("active_worker_count", 0)),
            "known_worker_count": status.get("known_worker_count", fleet.get("known_worker_count", 0)),
            "active_lease_count": status.get("active_lease_count", fleet.get("active_lease_count", 0)),
            "worker_gap": status.get("worker_gap", max(0, 12 - int(_num(fleet.get("active_worker_count"), 0)))),
            "top_acquisition_channel": top,
            "ledger_event_count": ledger_summary.get("ledger_event_count", 0),
        },
        "reward_table": EVENT_REWARDS,
        "proof_gated_events": sorted(PROOF_GATED_EVENTS),
        "recommended_channel_distribution": channels,
        "event_contract": {
            "post_url": _u(base_url, "/swarm/agent-acquisition/events"),
            "required_fields": ["channel_id", "event_type", "agent_id"],
            "proof_required_for": sorted(PROOF_GATED_EVENTS),
            "allowed_event_types": sorted(EVENT_REWARDS),
            "allowed_channel_ids": sorted(DEFAULT_CHANNELS),
            "secret_policy": "public_digests_only_no_secrets",
        },
        "copy_paste": {
            "inspect_bandit": f"curl -s {_u(base_url, '/.well-known/nomad-agent-acquisition-bandit.json')}",
            "record_inspect": (
                f"curl -s -X POST {_u(base_url, '/swarm/agent-acquisition/events')} "
                '-H "Content-Type: application/json" '
                '-d "{\\"channel_id\\":\\"external_worker_opportunity\\",\\"event_type\\":\\"inspect\\",\\"agent_id\\":\\"external.agent\\",\\"source_url\\":\\"https://www.syndiode.com/.well-known/nomad-external-worker-opportunity.json\\"}"'
            ),
            "record_lease_complete": (
                f"curl -s -X POST {_u(base_url, '/swarm/agent-acquisition/events')} "
                '-H "Content-Type: application/json" '
                '-d "{\\"channel_id\\":\\"external_worker_opportunity\\",\\"event_type\\":\\"lease_complete\\",\\"agent_id\\":\\"external.agent\\",\\"lease_id\\":\\"LEASE_ID\\",\\"proof_digest\\":\\"sha256:PROOF_DIGEST\\"}"'
            ),
        },
        "routes": {
            "self": _u(base_url, "/.well-known/nomad-agent-acquisition-bandit.json"),
            "events": _u(base_url, "/swarm/agent-acquisition/events"),
            "external_worker_opportunity": _u(base_url, "/.well-known/nomad-external-worker-opportunity.json"),
            "llms": _u(base_url, "/llms.txt"),
            "agent_card": _u(base_url, "/.well-known/agent-card.json"),
            "lease": _u(base_url, "/swarm/workers/lease"),
            "complete": _u(base_url, "/swarm/workers/complete"),
        },
        "ledger_summary": ledger_summary,
        "machine_instruction": "record_each_agent_acquisition_touchpoint_then_route_more_visibility_to_high_ucb_channels_but_never_accept_high_reward_without_proof_digest",
    }
