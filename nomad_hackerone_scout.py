from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any, Callable

import requests

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency in slim deploys
    load_dotenv = None


DEFAULT_HACKERONE_API_BASE = "https://api.hackerone.com"

FetchJson = Callable[[str, tuple[str, str], float], Any]
PostJson = Callable[[str, dict[str, Any], tuple[str, str], float], Any]


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv()


def _normalize_api_base(api_base: str | None) -> str:
    raw = (api_base or DEFAULT_HACKERONE_API_BASE).strip()
    if not raw:
        raw = DEFAULT_HACKERONE_API_BASE
    if "://" not in raw:
        raw = f"https://{raw}"
    raw = raw.rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3].rstrip("/")
    return raw


def _request_json(url: str, auth: tuple[str, str], timeout: float) -> Any:
    response = requests.get(
        url,
        headers={"Accept": "application/json"},
        auth=auth,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _post_json(url: str, payload: dict[str, Any], auth: tuple[str, str], timeout: float) -> Any:
    response = requests.post(
        url,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        auth=auth,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _credential_metadata(identifier: str | None, token: str | None) -> dict[str, Any]:
    identifier = identifier or ""
    token = token or ""
    return {
        "identifier_present": bool(identifier.strip()),
        "identifier_length": len(identifier),
        "token_present": bool(token.strip()),
        "token_length": len(token),
        "auth_scheme": "http_basic_identifier_token",
        "secret_material_emitted": False,
    }


def _jsonapi_data(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _scope_row(item: dict[str, Any]) -> dict[str, Any]:
    attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
    identifier = str(attrs.get("asset_identifier") or "").strip()
    asset_type = str(attrs.get("asset_type") or "").strip()
    instruction = str(attrs.get("instruction") or "")
    eligible_for_bounty = bool(attrs.get("eligible_for_bounty"))
    eligible_for_submission = bool(attrs.get("eligible_for_submission"))
    source_locator = identifier.startswith("https://") or "github.com/" in instruction.lower() or "download" in instruction.lower()
    return {
        "id": str(item.get("id") or ""),
        "asset_type": asset_type,
        "asset_identifier": identifier,
        "eligible_for_bounty": eligible_for_bounty,
        "eligible_for_submission": eligible_for_submission,
        "max_severity": str(attrs.get("max_severity") or ""),
        "instruction": instruction,
        "safe_for_read_only_source_review": (
            asset_type.upper() == "SOURCE_CODE"
            and eligible_for_bounty
            and eligible_for_submission
            and source_locator
        ),
    }


def _program_summary(handle: str, payload: Any) -> dict[str, Any]:
    rows = _jsonapi_data(payload)
    if not rows:
        return {"handle": handle}
    item = rows[0]
    attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
    return {
        "id": str(item.get("id") or ""),
        "handle": str(attrs.get("handle") or handle),
        "name": str(attrs.get("name") or ""),
        "state": str(attrs.get("state") or ""),
        "offers_bounties": bool(attrs.get("offers_bounties")),
        "submission_state": str(attrs.get("submission_state") or ""),
        "currency": str(attrs.get("currency") or ""),
    }


def _proof_digest(handle: str, scopes: list[dict[str, Any]]) -> str:
    stable = [
        {
            "id": item.get("id"),
            "asset_type": item.get("asset_type"),
            "asset_identifier": item.get("asset_identifier"),
            "eligible_for_bounty": item.get("eligible_for_bounty"),
            "eligible_for_submission": item.get("eligible_for_submission"),
        }
        for item in scopes
    ]
    encoded = json.dumps({"handle": handle, "scopes": stable}, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _auth_probe_digest(identifier: str, token: str) -> str:
    marker = f"{identifier}:{len(token)}".encode("utf-8")
    return f"sha256:{hashlib.sha256(marker).hexdigest()[:32]}"


def _hackerone_api_root(api_base: str | None = None) -> str:
    return f"{_normalize_api_base(api_base)}/v1"


def _report_amount_usd(payload: Any) -> float:
    """Best-effort bounty amount extraction without assuming H1 always exposes it."""
    if not isinstance(payload, dict):
        return 0.0
    candidates: list[Any] = []
    data = payload.get("data")
    if isinstance(data, dict):
        attrs = data.get("attributes")
        if isinstance(attrs, dict):
            candidates.extend(
                [
                    attrs.get("bounty_amount"),
                    attrs.get("bounty_amount_in_dollars"),
                    attrs.get("total_bounty_amount"),
                ]
            )
    included = payload.get("included")
    if isinstance(included, list):
        for item in included:
            if not isinstance(item, dict):
                continue
            attrs = item.get("attributes")
            if not isinstance(attrs, dict):
                continue
            candidates.extend(
                [
                    attrs.get("amount"),
                    attrs.get("amount_in_dollars"),
                    attrs.get("total_amount"),
                    attrs.get("bonus_amount"),
                ]
            )
    for value in candidates:
        try:
            amount = float(value or 0.0)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            return round(amount, 4)
    return 0.0


def _report_status_from_payload(report_id: str, payload: Any) -> dict[str, Any]:
    rows = _jsonapi_data(payload)
    item = rows[0] if rows else {}
    attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
    state = str(attrs.get("state") or "").strip().lower()
    triaged_at = str(attrs.get("triaged_at") or "")
    bounty_awarded_at = str(attrs.get("bounty_awarded_at") or "")
    closed_at = str(attrs.get("closed_at") or "")
    amount_usd = _report_amount_usd(payload)
    validated_states = {"triaged", "resolved"}
    rejected_states = {"duplicate", "informative", "not-applicable", "spam"}

    return {
        "ok": bool(item),
        "source": "hackerone",
        "report_id": str(item.get("id") or report_id),
        "state": state,
        "title": str(attrs.get("title") or ""),
        "created_at": str(attrs.get("created_at") or ""),
        "triaged_at": triaged_at,
        "closed_at": closed_at,
        "bounty_awarded_at": bounty_awarded_at,
        "hackerone_validated": bool(triaged_at or state in validated_states),
        "hackerone_resolved": state == "resolved",
        "hackerone_rejected": state in rejected_states,
        "owner_acceptance_signal": bool(triaged_at or state in validated_states),
        "payment_receipt": bool(bounty_awarded_at and amount_usd > 0),
        "amount_usd": amount_usd,
        "public_url": f"https://hackerone.com/reports/{item.get('id') or report_id}",
        "secret_material_emitted": False,
    }


def fetch_hackerone_report_status(
    report_id: str,
    *,
    api_base: str | None = None,
    identifier: str | None = None,
    token: str | None = None,
    timeout: float = 20.0,
    fetch_json: FetchJson | None = None,
) -> dict[str, Any]:
    """Fetch one report state for read-only reconciliation.

    The returned object is intentionally shaped like Nomad's external-value
    status snapshots and never includes API credentials.
    """
    _load_env()
    rid = str(report_id or "").strip()
    if not rid:
        return {"ok": False, "source": "hackerone", "error": "missing_report_id"}

    resolved_identifier = identifier if identifier is not None else os.getenv("HACKERONE_API_IDENTIFIER")
    resolved_token = token if token is not None else os.getenv("HACKERONE_API_TOKEN")
    credential_state = _credential_metadata(resolved_identifier, resolved_token)
    if not credential_state["identifier_present"] or not credential_state["token_present"]:
        return {
            "ok": False,
            "source": "hackerone",
            "report_id": rid,
            "error": "hackerone_api_credentials_missing",
            "credential_state": credential_state,
        }

    fetch = fetch_json or _request_json
    api_root = _hackerone_api_root(api_base or os.getenv("HACKERONE_API_BASE"))
    try:
        payload = fetch(
            f"{api_root}/hackers/reports/{rid}?include=bounties,severity,structured_scope,program",
            (str(resolved_identifier), str(resolved_token)),
            timeout,
        )
    except Exception as exc:  # pragma: no cover - live network path
        return {
            "ok": False,
            "source": "hackerone",
            "report_id": rid,
            "error": f"report_fetch_failed:{type(exc).__name__}",
        }
    out = _report_status_from_payload(rid, payload)
    out["credential_state"] = credential_state
    return out


def _submission_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    attrs: dict[str, Any] = {}
    for key in (
        "team_handle",
        "title",
        "vulnerability_information",
        "impact",
        "severity_rating",
        "weakness_id",
        "structured_scope_id",
    ):
        if key not in source:
            continue
        value = source.get(key)
        if value in ("", None):
            continue
        attrs[key] = value
    if "structured_scope_id" in attrs:
        try:
            attrs["structured_scope_id"] = int(attrs["structured_scope_id"])
        except (TypeError, ValueError):
            pass
    if "weakness_id" in attrs:
        try:
            attrs["weakness_id"] = int(attrs["weakness_id"])
        except (TypeError, ValueError):
            attrs.pop("weakness_id", None)
    return attrs


def _validate_submission_attributes(attrs: dict[str, Any]) -> list[str]:
    missing = []
    for key in ("team_handle", "title", "vulnerability_information", "impact"):
        if not str(attrs.get(key) or "").strip():
            missing.append(f"missing_{key}")
    return missing


def submit_hackerone_report(
    report_payload: dict[str, Any],
    *,
    api_base: str | None = None,
    identifier: str | None = None,
    token: str | None = None,
    timeout: float = 30.0,
    post_json: PostJson | None = None,
) -> dict[str, Any]:
    """Submit a verified report packet to HackerOne without emitting secrets."""
    _load_env()
    attrs = _submission_attributes(report_payload if isinstance(report_payload, dict) else {})
    missing = _validate_submission_attributes(attrs)
    if missing:
        return {
            "ok": False,
            "source": "hackerone",
            "error": "invalid_report_payload",
            "missing": missing,
            "secret_material_emitted": False,
        }

    resolved_identifier = identifier if identifier is not None else os.getenv("HACKERONE_API_IDENTIFIER")
    resolved_token = token if token is not None else os.getenv("HACKERONE_API_TOKEN")
    credential_state = _credential_metadata(resolved_identifier, resolved_token)
    if not credential_state["identifier_present"] or not credential_state["token_present"]:
        return {
            "ok": False,
            "source": "hackerone",
            "error": "hackerone_api_credentials_missing",
            "credential_state": credential_state,
            "secret_material_emitted": False,
        }

    body = {"data": {"type": "report", "attributes": attrs}}
    submit = post_json or _post_json
    api_root = _hackerone_api_root(api_base or os.getenv("HACKERONE_API_BASE"))
    try:
        payload = submit(
            f"{api_root}/hackers/reports",
            body,
            (str(resolved_identifier), str(resolved_token)),
            timeout,
        )
    except Exception as exc:  # pragma: no cover - live network path
        return {
            "ok": False,
            "source": "hackerone",
            "error": f"report_submit_failed:{type(exc).__name__}",
            "secret_material_emitted": False,
        }

    rows = _jsonapi_data(payload)
    item = rows[0] if rows else {}
    response_attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
    report_id = str(item.get("id") or "")
    return {
        "ok": bool(report_id),
        "source": "hackerone",
        "report_id": report_id,
        "state": str(response_attrs.get("state") or ""),
        "title": str(response_attrs.get("title") or attrs.get("title") or ""),
        "created_at": str(response_attrs.get("created_at") or ""),
        "public_url": f"https://hackerone.com/reports/{report_id}" if report_id else "",
        "credential_state": credential_state,
        "secret_material_emitted": False,
    }


def _draft_lines(title: str, sections: list[tuple[str, list[str]]]) -> str:
    lines = [f"# {title.strip()}", ""]
    for heading, body in sections:
        lines.append(f"## {heading}")
        lines.append("")
        if body:
            lines.extend(line.rstrip() for line in body)
        else:
            lines.append("TBD")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_hackerone_report_draft(
    *,
    program_handle: str,
    title: str,
    scope: dict[str, Any],
    summary: str,
    source_evidence: list[str] | None = None,
    repro_steps: list[str] | None = None,
    impact: str = "",
    severity_rating: str = "medium",
    local_reproducer_path: str = "",
    local_reproducer_digest: str = "",
    local_reproducer_verified: bool = False,
) -> dict[str, Any]:
    """Create a submission packet and keep the submit gate explicit."""
    handle = (program_handle or "").strip().strip("/")
    clean_title = " ".join(str(title or "").split())
    scope_id = str(scope.get("id") or scope.get("structured_scope_id") or "").strip()
    asset_identifier = str(scope.get("asset_identifier") or "").strip()
    evidence = [str(item).strip() for item in (source_evidence or []) if str(item).strip()]
    steps = [str(item).strip() for item in (repro_steps or []) if str(item).strip()]
    impact_text = " ".join(str(impact or "").split())
    reproducer_digest = str(local_reproducer_digest or "").strip()
    reproducer_path = str(local_reproducer_path or "").strip()
    ready = all(
        [
            handle,
            clean_title,
            scope_id,
            summary.strip(),
            evidence,
            steps,
            impact_text,
            reproducer_digest,
            local_reproducer_verified,
        ]
    )
    blocked: list[str] = []
    if not scope_id or not asset_identifier:
        blocked.append("missing_structured_scope")
    if not evidence:
        blocked.append("missing_source_evidence")
    if not steps:
        blocked.append("missing_repro_steps")
    if not reproducer_digest:
        blocked.append("missing_local_reproducer_digest")
    if not local_reproducer_verified:
        blocked.append("missing_verified_reproducer_run")
    if not impact_text:
        blocked.append("missing_impact")

    markdown = _draft_lines(
        clean_title or "HackerOne report draft",
        [
            ("Summary", [summary.strip()] if summary.strip() else []),
            (
                "Affected Asset",
                [
                    f"- Program: `{handle}`",
                    f"- Structured scope: `{scope_id}`",
                    f"- Asset: `{asset_identifier}`",
                ],
            ),
            ("Source Evidence", [f"- {item}" for item in evidence]),
            ("Steps To Reproduce", [f"{idx}. {step}" for idx, step in enumerate(steps, start=1)]),
            (
                "Local Reproducer",
                [
                    f"- Path: `{reproducer_path}`",
                    f"- Digest: `{reproducer_digest}`",
                    f"- Verified locally: `{'yes' if local_reproducer_verified else 'no'}`",
                ]
                if reproducer_digest
                else [],
            ),
            ("Impact", [impact_text] if impact_text else []),
            (
                "Safety Notes",
                [
                    "Only tested against owned/local assets.",
                    "No live third-party target probing is required by this packet.",
                ],
            ),
        ],
    )

    payload = {
        "team_handle": handle,
        "title": clean_title,
        "vulnerability_information": markdown,
        "impact": impact_text,
        "severity_rating": severity_rating,
        "structured_scope_id": scope_id,
    }
    return {
        "schema": "nomad.hackerone_report_draft.v1",
        "ok": ready,
        "submit_ready": ready,
        "program_handle": handle,
        "scope_id": scope_id,
        "asset_identifier": asset_identifier,
        "payload": payload,
        "markdown": markdown,
        "blocked_actions": blocked,
        "allowed_actions": ["hackerone_submit"] if ready else ["complete_reproducer_and_evidence"],
        "machine_instruction": (
            "submit_only_after_scope_evidence_reproducer_and_impact_are_complete"
            if ready
            else "continue_local_repro_before_any_hackerone_submission"
        ),
    }


def build_hackerone_scope_scout(
    handle: str = "zabbix",
    *,
    api_base: str | None = None,
    identifier: str | None = None,
    token: str | None = None,
    timeout: float = 20.0,
    fetch_json: FetchJson | None = None,
    program_payload: dict[str, Any] | None = None,
    scopes_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _load_env()
    handle = (handle or "zabbix").strip().strip("/") or "zabbix"
    api_base_public = _normalize_api_base(api_base or os.getenv("HACKERONE_API_BASE"))
    resolved_identifier = identifier if identifier is not None else os.getenv("HACKERONE_API_IDENTIFIER")
    resolved_token = token if token is not None else os.getenv("HACKERONE_API_TOKEN")
    credential_state = _credential_metadata(resolved_identifier, resolved_token)
    fetch = fetch_json or _request_json
    errors: list[str] = []

    program: dict[str, Any] = {"handle": handle}
    scopes: list[dict[str, Any]] = []

    if not credential_state["identifier_present"] or not credential_state["token_present"]:
        errors.append("hackerone_api_credentials_missing")
    else:
        auth = (str(resolved_identifier), str(resolved_token))
        if program_payload is None:
            try:
                program_payload = fetch(f"{api_base_public}/v1/hackers/programs/{handle}", auth, timeout)
            except Exception as exc:  # pragma: no cover - live network path
                errors.append(f"program_fetch_failed:{type(exc).__name__}")
        if program_payload is not None:
            program = _program_summary(handle, program_payload)

        if scopes_payload is None:
            try:
                scopes_payload = fetch(
                    f"{api_base_public}/v1/hackers/programs/{handle}/structured_scopes?page[size]=100",
                    auth,
                    timeout,
                )
            except Exception as exc:  # pragma: no cover - live network path
                errors.append(f"scope_fetch_failed:{type(exc).__name__}")
        if scopes_payload is not None:
            scopes = [_scope_row(item) for item in _jsonapi_data(scopes_payload)]

    eligible_scopes = [
        item
        for item in scopes
        if item["eligible_for_bounty"] and item["eligible_for_submission"]
    ]
    eligible_source_scopes = [
        item
        for item in eligible_scopes
        if item["asset_type"].upper() == "SOURCE_CODE"
    ]
    top_source_scope = eligible_source_scopes[0] if eligible_source_scopes else None
    api_authenticated = (
        credential_state["identifier_present"]
        and credential_state["token_present"]
        and "scope_fetch_failed" not in ",".join(errors)
        and bool(scopes)
    )

    if not api_authenticated:
        machine_instruction = "fix_hackerone_api_auth_before_value_cycle"
    elif not top_source_scope:
        machine_instruction = "read_only_scope_review_only_no_submit_until_eligible_asset_exists"
    else:
        machine_instruction = "read_only_source_review_then_local_reproducer_before_hackerone_submission"

    auth_digest = (
        _auth_probe_digest(str(resolved_identifier), str(resolved_token))
        if credential_state["identifier_present"] and credential_state["token_present"]
        else ""
    )

    return {
        "schema": "nomad.hackerone_scope_scout.v1",
        "ok": api_authenticated and bool(top_source_scope) and not errors,
        "generated_at": datetime.now(UTC).isoformat(),
        "api_base_public": api_base_public,
        "program": program,
        "credential_state": credential_state,
        "auth_probe_digest": auth_digest,
        "scope_summary": {
            "scope_count": len(scopes),
            "eligible_count": len(eligible_scopes),
            "eligible_source_count": len(eligible_source_scopes),
            "top_source_scope": top_source_scope,
        },
        "eligible_scopes": eligible_scopes,
        "allowed_actions": [
            "read_only_program_scope_review",
            "read_only_source_download_from_eligible_source_scope",
            "offline_source_review",
            "local_reproducer_after_candidate_vulnerability",
        ],
        "blocked_actions": [
            "live_target_probe_without_explicit_scope_and_repro_plan",
            "hackerone_submission_without_reproducible_vulnerability",
            "external_value_submitted_stage_without_report_url",
            "external_value_paid_stage_without_positive_receipt",
        ],
        "value_cycle_gate": {
            "stage": "found",
            "revenue_usd": 0.0,
            "submit_allowed": False,
            "paid_record_allowed": False,
            "submit_allowed_when": "reproducible_vulnerability_evidence_exists_and_operator_confirms_go",
            "paid_record_allowed_when": "trusted_hackerone_payment_receipt_with_positive_amount",
        },
        "proof_digest": _proof_digest(handle, scopes),
        "machine_instruction": machine_instruction,
        "errors": errors,
    }


__all__ = [
    "DEFAULT_HACKERONE_API_BASE",
    "_normalize_api_base",
    "build_hackerone_report_draft",
    "build_hackerone_scope_scout",
    "fetch_hackerone_report_status",
    "submit_hackerone_report",
]
