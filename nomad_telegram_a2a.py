"""Telegram bot-to-bot transport receipts for Nomad.

Telegram Bot API 10.0 allows bots to address other bots by @username when
both bots enable Bot-to-Bot Communication Mode in BotFather. Nomad keeps this
as a bounded transport: explicit opt-in, allowlist, dedupe, depth and TTL.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent
DEFAULT_TELEGRAM_A2A_LEDGER_PATH = Path(
    os.getenv("NOMAD_TELEGRAM_A2A_LEDGER_PATH", ROOT / "nomad_telegram_a2a_ledger.jsonl")
)
BOT_USERNAME_RE = re.compile(r"^@?[A-Za-z][A-Za-z0-9_]{4,31}$")
FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token", "token")
FORBIDDEN_VALUE_TERMS = ("private key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _bool_env(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, *, low: int = 0, high: int = 86400) -> int:
    try:
        value = int(os.getenv(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _text(value: Any, limit: int = 280) -> str:
    return " ".join(str(value or "").split())[:limit]


def _looks_digest(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return bool(re.fullmatch(r"(sha256:)?[a-f0-9]{32,128}", text))


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(v, key=str(k2)) for k2, v in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _clean_username(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.startswith("@"):
        text = f"@{text}"
    return text if BOT_USERNAME_RE.fullmatch(text) else ""


def _allowed_targets() -> list[str]:
    raw = os.getenv("TELEGRAM_BOT_TO_BOT_TARGETS") or os.getenv("NOMAD_TELEGRAM_A2A_TARGETS") or ""
    targets = []
    for part in re.split(r"[\s,;]+", raw):
        username = _clean_username(part)
        if username:
            targets.append(username.lower())
    return sorted(set(targets))


def _read_ledger(path: Path | str | None = None, *, limit: int = 80) -> list[dict[str, Any]]:
    p = Path(path) if path else DEFAULT_TELEGRAM_A2A_LEDGER_PATH
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-max(1, limit * 3) :]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:]


def _append_ledger(row: dict[str, Any], path: Path | str | None = None) -> None:
    p = Path(path) if path else DEFAULT_TELEGRAM_A2A_LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _message_body(payload: dict[str, Any], *, proof_digest: str, idempotency_digest: str, max_chars: int) -> str:
    body = payload.get("text") or payload.get("message") or payload.get("payload") or payload.get("content") or {}
    if isinstance(body, (dict, list)):
        body_text = json.dumps(body, ensure_ascii=True, sort_keys=True)
    else:
        body_text = str(body or "")
    envelope = {
        "schema": "nomad.telegram_bot_to_bot_envelope.v1",
        "sender_agent_id": _text(payload.get("sender_agent_id") or payload.get("agent_id") or "nomad", 120),
        "conversation_id": _text(payload.get("conversation_id") or f"tg-a2a-{idempotency_digest[:12]}", 120),
        "proof_digest": proof_digest,
        "idempotency_digest": f"sha256:{idempotency_digest}",
        "ttl_seconds": _int_env("TELEGRAM_BOT_TO_BOT_DEFAULT_TTL_SECONDS", 300, low=30, high=3600),
        "body": body_text,
    }
    text = json.dumps(envelope, ensure_ascii=True, sort_keys=True)
    return text[:max_chars]


def _token_present() -> bool:
    return bool((os.getenv("TELEGRAM_BOT_TOKEN") or "").strip())


def _send_authorized(request_secret: str | None) -> bool:
    required = (os.getenv("NOMAD_TELEGRAM_A2A_SEND_SECRET") or "").strip()
    if required:
        return bool(request_secret and request_secret == required)
    return _bool_env("TELEGRAM_BOT_TO_BOT_PUBLIC_SEND", False)


def build_telegram_bot_to_bot_surface(*, base_url: str = "", ledger_path: Path | str | None = None) -> dict[str, Any]:
    recent = _read_ledger(ledger_path, limit=20)
    allowed = _allowed_targets()
    return {
        "ok": True,
        "schema": "nomad.telegram_bot_to_bot_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "telegram_source": {
            "bot_api_changelog": "https://core.telegram.org/bots/api-changelog",
            "bot_to_bot_guide": "https://core.telegram.org/bots/features#bot-to-bot-communication",
            "telegram_blog": "https://telegram.org/blog/ai-bot-revolution-11-new-features",
            "bot_api_version": "10.0",
        },
        "capability": {
            "private_bot_to_bot": True,
            "group_bot_to_bot": True,
            "requires_botfather_bot_to_bot_mode_for_private_messages": True,
            "requires_both_private_bots_opted_in": True,
        },
        "configured": {
            "enabled": _bool_env("TELEGRAM_BOT_TO_BOT_ENABLED", False),
            "token_present": _token_present(),
            "allowed_targets": allowed,
            "public_send_enabled": _bool_env("TELEGRAM_BOT_TO_BOT_PUBLIC_SEND", False),
            "send_secret_configured": bool((os.getenv("NOMAD_TELEGRAM_A2A_SEND_SECRET") or "").strip()),
            "dry_run": _bool_env("TELEGRAM_BOT_TO_BOT_DRY_RUN", False),
        },
        "loop_prevention": {
            "dedupe": "idempotency_digest",
            "max_depth": _int_env("TELEGRAM_BOT_TO_BOT_MAX_DEPTH", 4, low=0, high=32),
            "max_ttl_seconds": _int_env("TELEGRAM_BOT_TO_BOT_MAX_TTL_SECONDS", 600, low=30, high=3600),
            "min_interval_seconds_per_target": _int_env("TELEGRAM_BOT_TO_BOT_MIN_INTERVAL_SECONDS", 5, low=0, high=3600),
            "max_message_chars": _int_env("TELEGRAM_BOT_TO_BOT_MAX_MESSAGE_CHARS", 3000, low=256, high=4096),
        },
        "links": {
            "self": _u(base_url, "/.well-known/nomad-telegram-a2a.json"),
            "send": _u(base_url, "/swarm/telegram-a2a/messages"),
            "direct_a2a": _u(base_url, "/a2a/message"),
            "agent_card": _u(base_url, "/.well-known/agent-card.json"),
        },
        "recent_receipt_count": len(recent),
        "latest_receipt": recent[-1] if recent else {},
        "operator_setup": [
            "Enable Bot-to-Bot Communication Mode for Nomad's bot in BotFather.",
            "Ensure the target bot also enabled Bot-to-Bot Communication Mode.",
            "Set TELEGRAM_BOT_TO_BOT_ENABLED=true and TELEGRAM_BOT_TO_BOT_TARGETS=@TargetBot.",
            "Set NOMAD_TELEGRAM_A2A_SEND_SECRET for public HTTP sends, or keep dry-run/receipt mode.",
        ],
        "machine_instruction": "use_as_low_friction_agent_transport_only_after_allowlist_and_loop_guards; prefer_http_a2a_for_large_payloads",
    }


def route_telegram_bot_to_bot_message(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    request_secret: str | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    now = _iso_now()
    target = _clean_username(body.get("target_bot_username") or body.get("target_bot") or body.get("chat_id"))
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 220)
    if proof_digest and re.fullmatch(r"[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{proof_digest.lower()}"
    if not proof_digest:
        proof_digest = f"sha256:{_digest(body, length=64)}"
    depth = _int_env("TELEGRAM_BOT_TO_BOT_DEFAULT_DEPTH", 0, low=0, high=32)
    try:
        depth = int(body.get("depth", depth))
    except (TypeError, ValueError):
        depth = 0
    ttl_seconds = _int_env("TELEGRAM_BOT_TO_BOT_DEFAULT_TTL_SECONDS", 300, low=30, high=3600)
    try:
        ttl_seconds = int(body.get("ttl_seconds", ttl_seconds))
    except (TypeError, ValueError):
        ttl_seconds = 300
    max_depth = _int_env("TELEGRAM_BOT_TO_BOT_MAX_DEPTH", 4, low=0, high=32)
    max_ttl = _int_env("TELEGRAM_BOT_TO_BOT_MAX_TTL_SECONDS", 600, low=30, high=3600)
    allowed = _allowed_targets()
    allow_unlisted = _bool_env("TELEGRAM_BOT_TO_BOT_ALLOW_UNLISTED", False)
    idempotency_digest = _digest(
        {
            "target": target.lower(),
            "proof_digest": proof_digest,
            "conversation_id": body.get("conversation_id"),
            "idempotency_key": body.get("idempotency_key"),
            "content": body.get("text") or body.get("message") or body.get("payload") or body.get("content"),
        },
        length=64,
    )
    recent = _read_ledger(ledger_path, limit=120)
    duplicate = next((item for item in recent if item.get("idempotency_digest") == f"sha256:{idempotency_digest}"), None)
    now_seconds = time.time()
    latest_target_send = 0.0
    for item in reversed(recent):
        if str(item.get("target_bot_username") or "").lower() == target.lower() and item.get("sent"):
            latest_target_send = float(item.get("sent_at_unix") or 0.0)
            break
    min_interval = _int_env("TELEGRAM_BOT_TO_BOT_MIN_INTERVAL_SECONDS", 5, low=0, high=3600)
    rate_limited = bool(latest_target_send and now_seconds - latest_target_send < min_interval)
    mode_ack = bool(body.get("bot_to_bot_mode_ack")) or _bool_env("TELEGRAM_BOT_TO_BOT_MODE_ACK", False)
    checks = {
        "target_bot_username_valid": bool(target),
        "target_allowlisted_or_unlisted_allowed": bool(target and (target.lower() in allowed or allow_unlisted)),
        "telegram_bot_token_present": _token_present(),
        "bot_to_bot_mode_ack": mode_ack,
        "enabled": _bool_env("TELEGRAM_BOT_TO_BOT_ENABLED", False),
        "send_authorized": _send_authorized(request_secret),
        "proof_digest_present": _looks_digest(proof_digest),
        "ttl_within_limit": 0 < ttl_seconds <= max_ttl,
        "depth_within_limit": 0 <= depth <= max_depth,
        "not_duplicate": duplicate is None,
        "not_rate_limited": not rate_limited,
        "secret_free_payload": not _contains_forbidden(body),
    }
    max_chars = _int_env("TELEGRAM_BOT_TO_BOT_MAX_MESSAGE_CHARS", 3000, low=256, high=4096)
    message = _message_body(body, proof_digest=proof_digest, idempotency_digest=idempotency_digest, max_chars=max_chars)
    dry_run = _bool_env("TELEGRAM_BOT_TO_BOT_DRY_RUN", False)
    sent = False
    send_status = 0
    telegram_response: dict[str, Any] = {}
    if duplicate:
        decision = "duplicate_telegram_a2a_noop"
    elif all(checks.values()) and dry_run:
        decision = "telegram_bot_to_bot_dry_run_receipt"
    elif all(checks.values()):
        token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": target, "text": message, "disable_web_page_preview": True},
                timeout=20,
            )
            send_status = response.status_code
            telegram_response = response.json() if response.content else {}
            sent = bool(response.ok and telegram_response.get("ok"))
            decision = "telegram_bot_to_bot_sent" if sent else "telegram_bot_to_bot_send_failed"
        except Exception as exc:  # noqa: BLE001
            telegram_response = {"ok": False, "error": str(exc)[:240]}
            decision = "telegram_bot_to_bot_send_failed"
    else:
        missing = [key for key, value in checks.items() if not value]
        decision = "hold_telegram_bot_to_bot_until_" + "_and_".join(missing[:3])
    row = {
        "ok": True,
        "schema": "nomad.telegram_bot_to_bot_receipt.v1",
        "generated_at": now,
        "accepted": bool((sent or dry_run) and not duplicate and all(checks.values())),
        "sent": sent,
        "dry_run": dry_run,
        "decision": decision,
        "target_bot_username": target,
        "proof_digest": proof_digest,
        "idempotency_digest": f"sha256:{idempotency_digest}",
        "conversation_id": _text(body.get("conversation_id") or f"tg-a2a-{idempotency_digest[:12]}", 120),
        "depth": depth,
        "ttl_seconds": ttl_seconds,
        "checks": checks,
        "message_chars": len(message),
        "telegram_status": send_status,
        "telegram_response_ok": bool(telegram_response.get("ok")),
        "sent_at_unix": now_seconds if sent else 0,
        "links": {
            "surface": _u(base_url, "/.well-known/nomad-telegram-a2a.json"),
            "direct_a2a": _u(base_url, "/a2a/message"),
        },
        "machine_instruction": "treat_duplicate_or_rate_limited_receipts_as_noop; never_continue_bot_to_bot_loop_past_depth_or_ttl",
    }
    _append_ledger(row, ledger_path)
    return row
