"""Guarded Telegram bot-to-bot bridge for Nomad."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import requests

from nomad_sales_funnel import build_sales_funnel_surface, compact_sales_lane


SCHEMA = "nomad.telegram_a2a_bridge.v1"
RECEIPT_SCHEMA = "nomad.telegram_a2a_receipt.v1"
DEFAULT_TIMEOUT_SECONDS = 8
MAX_TEXT = 2200


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").replace("\r", " ").split())[:limit]


def _bool(value: Any, default: bool = False) -> bool:
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on", "y"}:
        return True
    if raw in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _int(value: Any, default: int = 0, *, minimum: int = 0, maximum: int = 3) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _digest(payload: Any, length: int = 24) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _env_csv(name: str, defaults: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    values = [item.strip().lstrip("@") for item in raw.split(",") if item.strip()]
    return values or [item.strip().lstrip("@") for item in defaults if item.strip()]


def allowed_bot_usernames() -> list[str]:
    return _env_csv(
        "NOMAD_TELEGRAM_A2A_ALLOWED_BOTS",
        [
            os.getenv("NOMAD_A2A_BOT_USERNAME", "NomadA2ABot"),
            os.getenv("NOMAD_VERIFIER_BOT_USERNAME", "NomadVerifierBot"),
            os.getenv("NOMAD_ARBITER_BOT_USERNAME", "Arbiteragentbot"),
        ],
    )


def allowed_url_prefixes() -> list[str]:
    return _env_csv(
        "NOMAD_TELEGRAM_A2A_ALLOWED_URL_PREFIXES",
        [
            "https://syndiode.com/nomad",
            "https://www.syndiode.com/nomad",
            "https://syndiode.com/.well-known",
            "https://www.syndiode.com/.well-known",
        ],
    )


def parse_a2a_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    fields: dict[str, str] = {}
    for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_-]*)=([^\s]+)", raw):
        fields[key.lower().replace("-", "_")] = value.strip()

    lowered = raw.lower()
    command = "unknown"
    if "nomad_a2a_probe" in lowered or lowered.startswith("/nomad_probe"):
        command = "probe"
    elif "nomad_verify" in lowered or lowered.startswith("/nomad_verify"):
        command = "verify"
    elif "nomad_sales" in lowered or lowered.startswith("/nomad_sales"):
        command = "sales"
    elif "nomad_repair" in lowered or lowered.startswith("/nomad_repair"):
        command = "repair"
    elif "nomad_worker" in lowered or lowered.startswith("/nomad_worker"):
        command = "worker"
    elif "nomad_cursor" in lowered or lowered.startswith("/nomad_cursor"):
        command = "cursor"
    elif "nomad_task" in lowered or lowered.startswith("/nomad_task"):
        command = "task"
    elif "nomad_pledge" in lowered or lowered.startswith("/nomad_pledge"):
        command = "pledge"
    elif "nomad_attach" in lowered or lowered.startswith("/nomad_attach"):
        command = "attach"

    msg_id = _text(fields.get("id") or fields.get("nonce"), 120)
    if not msg_id:
        msg_id = f"a2a-{_digest(raw)}"

    return {
        "raw": raw[:MAX_TEXT],
        "command": command,
        "id": msg_id,
        "fields": fields,
        "depth": _int(fields.get("depth"), 0),
        "max_depth": _int(fields.get("max_depth"), 1),
        "no_reply_required": _bool(fields.get("no_reply_required"), False),
        "reply_required": _bool(fields.get("reply_required"), False),
    }


def _url_allowed(url: str) -> bool:
    cleaned = _text(url, 900)
    if not cleaned.startswith(("https://", "http://")):
        return False
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if host in {"localhost"} or host.startswith(("127.", "10.", "192.168.")):
        return False
    return any(cleaned.startswith(prefix) for prefix in allowed_url_prefixes())


def _verify_url(url: str, expected_schema: str = "") -> dict[str, Any]:
    if not _url_allowed(url):
        return {
            "ok": False,
            "reason": "url_not_allowed",
            "url": _text(url, 900),
            "allowed_prefixes": allowed_url_prefixes(),
        }
    try:
        response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return {"ok": False, "reason": "fetch_failed", "url": _text(url, 900), "error": str(exc)[:240]}
    payload = None
    if "json" in response.headers.get("Content-Type", "").lower():
        try:
            payload = response.json()
        except ValueError:
            payload = None
    schema = payload.get("schema") if isinstance(payload, dict) else ""
    return {
        "ok": response.ok and (not expected_schema or schema == expected_schema),
        "reason": "verified" if response.ok else "http_error",
        "url": _text(url, 900),
        "status_code": response.status_code,
        "content_type": response.headers.get("Content-Type", ""),
        "schema": schema,
        "expected_schema": _text(expected_schema, 180),
    }


def handle_telegram_a2a_message(
    text: str,
    *,
    sender_username: str = "",
    receiver_username: str = "",
    receiver_role: str = "",
    sender_is_bot: bool = True,
    base_url: str = "",
) -> dict[str, Any]:
    parsed = parse_a2a_text(text)
    sender = _text(sender_username, 120).lstrip("@")
    receiver = _text(receiver_username, 120).lstrip("@")
    role = _text(receiver_role or "telegram", 80).lower()
    allowed = {item.lower() for item in allowed_bot_usernames()}
    accepted = bool(sender_is_bot and sender and sender.lower() in allowed and parsed["command"] != "unknown")
    result: dict[str, Any] = {
        "ok": True,
        "accepted": accepted,
        "schema": SCHEMA,
        "receipt_schema": RECEIPT_SCHEMA,
        "received_at": _now(),
        "receipt_id": f"nomad-a2a-{_digest({'sender': sender, 'receiver': receiver, 'id': parsed['id']})}",
        "message_id": parsed["id"],
        "command": parsed["command"],
        "sender_username": sender,
        "receiver_username": receiver,
        "receiver_role": role,
        "depth": parsed["depth"],
        "max_depth": parsed["max_depth"],
        "should_reply": False,
        "reason": "",
        "guardrails": {
            "allowed_bot_usernames": sorted(allowed),
            "bot_sender_required": True,
            "max_depth_cap": 3,
            "no_secret_transport": True,
            "revenue_requires_verified_receipt": True,
        },
    }

    if not sender_is_bot:
        result.update({"accepted": False, "reason": "sender_is_not_bot"})
        return result
    if sender.lower() not in allowed:
        result.update({"accepted": False, "reason": "sender_not_allowed"})
        return result
    if parsed["command"] == "unknown":
        result.update({"accepted": False, "reason": "unknown_nomad_a2a_command"})
        return result

    fields = parsed["fields"]
    if parsed["command"] == "verify":
        result["verification"] = _verify_url(fields.get("url", ""), fields.get("schema", ""))
    elif parsed["command"] in {"sales", "repair", "worker", "cursor"}:
        surface = build_sales_funnel_surface(base_url=base_url)
        lane_map = {
            "sales": "repair_product",
            "repair": "repair_product",
            "worker": "worker_recruitment",
            "cursor": "cursor_referral",
        }
        lane = compact_sales_lane(surface, lane_map[parsed["command"]])
        result["sales_route"] = {
            "ok": True,
            "lane": lane,
            "miniapp": surface.get("public_base_url", "").rstrip("/") + "/telegram-miniapp",
            "payment_recipient_set": bool((surface.get("payment") or {}).get("recipient")),
            "revenue_rule": lane.get("revenue_rule", "revenue_requires_verified_receipt"),
        }
    elif parsed["command"] == "probe":
        result["probe"] = {"ok": True, "purpose": _text(fields.get("purpose") or "bot_to_bot_delivery_check", 160)}
    elif parsed["command"] == "task":
        result["task"] = {
            "ok": True,
            "next": "Use Nomad HTTP POST /tasks after human consent and payment boundary.",
            "service_type": _text(fields.get("service_type") or "transition_worker_setup", 120),
        }
    elif parsed["command"] == "pledge":
        result["pledge"] = {"ok": True, "next": "Use Nomad HTTP POST /machine-treasury/pledge after human consent."}
    elif parsed["command"] == "attach":
        result["attach"] = {"ok": True, "next": "Use GET /swarm/attach-get or POST /swarm/join with stable agent_id."}

    if parsed["no_reply_required"] and not parsed["reply_required"]:
        result["reason"] = "accepted_no_reply_required"
        return result
    if parsed["depth"] >= parsed["max_depth"]:
        result["reason"] = "accepted_max_depth_reached"
        return result

    result["should_reply"] = True
    result["reply_depth"] = parsed["depth"] + 1
    result["reason"] = "accepted_reply_once"
    return result


def format_telegram_a2a_reply(result: dict[str, Any]) -> str:
    ok = str(bool(result.get("accepted"))).lower()
    verified = result.get("verification") if isinstance(result.get("verification"), dict) else {}
    route = result.get("sales_route") if isinstance(result.get("sales_route"), dict) else {}
    lane = route.get("lane") if isinstance(route.get("lane"), dict) else {}
    lines = [
        "NOMAD_A2A_RECEIPT v1",
        f"id={_text(result.get('message_id'), 120)}",
        f"receipt_id={_text(result.get('receipt_id'), 140)}",
        f"accepted={ok}",
        f"command={_text(result.get('command'), 40)}",
        f"from=@{_text(result.get('receiver_username'), 120)}",
        f"to=@{_text(result.get('sender_username'), 120)}",
        f"depth={_int(result.get('reply_depth'), 1)}",
        "max_depth=1",
        "no_reply_required=true",
        f"reason={_text(result.get('reason'), 120)}",
    ]
    if verified:
        lines.extend(
            [
                f"verify_ok={str(bool(verified.get('ok'))).lower()}",
                f"status_code={verified.get('status_code', '')}",
                f"schema={_text(verified.get('schema'), 120)}",
            ]
        )
    if route:
        lines.extend(
            [
                f"route={_text(lane.get('lane_id'), 120)}",
                f"entry={_text(lane.get('entry') or route.get('miniapp'), 400)}",
                f"payment_recipient_set={str(bool(route.get('payment_recipient_set'))).lower()}",
                f"revenue_rule={_text(route.get('revenue_rule'), 160)}",
            ]
        )
    return "\n".join(lines)


def build_telegram_a2a_bridge_surface(*, base_url: str = "") -> dict[str, Any]:
    base = (base_url or "").strip().rstrip("/")
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _now(),
        "public_base_url": base,
        "bots": {
            "a2a": os.getenv("NOMAD_A2A_BOT_USERNAME", "NomadA2ABot"),
            "verifier": os.getenv("NOMAD_VERIFIER_BOT_USERNAME", "NomadVerifierBot"),
        },
        "commands": [
            "NOMAD_A2A_PROBE",
            "NOMAD_VERIFY",
            "NOMAD_SALES",
            "NOMAD_REPAIR",
            "NOMAD_WORKER",
            "NOMAD_CURSOR",
            "NOMAD_TASK",
            "NOMAD_PLEDGE",
            "NOMAD_ATTACH",
        ],
        "guardrails": {
            "allowlist": allowed_bot_usernames(),
            "max_depth": 1,
            "private_secrets": "never send private keys, seed phrases, API tokens, or raw payment secrets",
            "revenue": "only after verified task payment, Cursor credit receipt, or settled grant agreement",
        },
        "examples": [
            "NOMAD_A2A_PROBE v1 id=probe-001 max_depth=0 no_reply_required=true",
            f"NOMAD_VERIFY v1 id=verify-001 max_depth=1 url={base}/.well-known/nomad-telegram-miniapp.json schema=nomad.telegram_miniapp.v1",
            "NOMAD_REPAIR v1 id=repair-001 max_depth=1 problem=agent_runtime_blocked",
            "NOMAD_WORKER v1 id=worker-001 max_depth=1",
            "NOMAD_CURSOR v1 id=cursor-001 max_depth=1",
        ],
    }
