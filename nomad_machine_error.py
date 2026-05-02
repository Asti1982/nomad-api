"""Unified machine-readable error bodies for Nomad HTTP APIs."""

from __future__ import annotations

from typing import Any, Optional


def machine_error_response(
    *,
    error: str,
    message: str = "",
    hints: Optional[list[str]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Return a JSON-serializable error dict (schema nomad.machine_error.v1)."""
    body: dict[str, Any] = {
        "ok": False,
        "schema": "nomad.machine_error.v1",
        "error": str(error or "error").strip() or "error",
    }
    msg = str(message or "").strip()
    if msg:
        body["message"] = msg
    if hints:
        body["hints"] = [str(h).strip() for h in hints if str(h).strip()]
    if extra:
        for key, value in extra.items():
            if key not in body:
                body[str(key)] = value
    return body


def merge_machine_error(
    payload: dict[str, Any],
    *,
    error: str,
    message: str = "",
    hints: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Attach machine_error to an existing partial response (keeps legacy top-level fields)."""
    out = dict(payload)
    out["machine_error"] = {
        "schema": "nomad.machine_error.v1",
        "error": str(error or "error").strip() or "error",
    }
    if str(message or "").strip():
        out["machine_error"]["message"] = str(message).strip()
    if hints:
        out["machine_error"]["hints"] = [str(h).strip() for h in hints if str(h).strip()]
    if out.get("ok") is None:
        out["ok"] = False
    return out
