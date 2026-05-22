"""Telegram acquisition launch contract for Nomad Mini App growth."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from nomad_state_paths import state_file
from nomad_telegram_miniapp import DEFAULT_TELEGRAM_MINIAPP_LEDGER, LEDGER_ENV


SCHEMA = "nomad.telegram_acquisition_launch.v1"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())[:limit]


def _int(value: Any, default: int = 0, *, minimum: int = 0, maximum: int = 100000) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _canonical_public_base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    parsed = urlparse(base)
    host = (parsed.hostname or "").strip().lower()
    if host in {"syndiode.com", "www.syndiode.com"} and parsed.path.rstrip("/") in {"", "/"}:
        return urlunparse(parsed._replace(scheme="https", netloc="syndiode.com", path="/nomad")).rstrip("/")
    return base


def _ledger_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    return state_file(DEFAULT_TELEGRAM_MINIAPP_LEDGER, env_name=LEDGER_ENV)


def summarize_telegram_acquisition_ledgers(
    *,
    ledger_path: str | Path | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Summarize the local Mini App lead ledger without exposing raw secrets."""
    path = _ledger_path(ledger_path)
    rows: list[dict[str, Any]] = []
    malformed = 0
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    malformed += 1
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    selected = rows[-max(1, limit) :]
    stages = Counter(_text(row.get("stage"), 80) or "unknown" for row in selected)
    offers = Counter(_text(row.get("selected_offer"), 120) or "unknown" for row in selected)
    campaigns = Counter(_text(row.get("campaign"), 120) or "unknown" for row in selected)
    identities = {
        _text(row.get("telegram_user_hash"), 80)
        for row in selected
        if _text(row.get("telegram_user_hash"), 80)
    }
    task_ids = {
        _text(row.get("task_id"), 120)
        for row in selected
        if _text(row.get("task_id"), 120)
    }
    return {
        "schema": "nomad.telegram_acquisition_ledger_summary.v1",
        "ledger_path": str(path),
        "exists": path.exists(),
        "event_count": len(rows),
        "sampled_event_count": len(selected),
        "malformed_count": malformed,
        "unique_telegram_user_hash_count": len(identities),
        "task_signal_count": len(task_ids),
        "stage_counts": dict(stages.most_common(12)),
        "selected_offer_counts": dict(offers.most_common(12)),
        "campaign_counts": dict(campaigns.most_common(12)),
        "recent_receipts": [
            {
                "receipt_id": _text(row.get("receipt_id"), 140),
                "stage": _text(row.get("stage"), 80),
                "selected_offer": _text(row.get("selected_offer"), 120),
                "campaign": _text(row.get("campaign"), 120),
                "recorded_at": _text(row.get("recorded_at"), 80),
            }
            for row in selected[-5:]
        ],
    }


def _bot_usernames() -> dict[str, str]:
    return {
        "operator": _text(os.getenv("TELEGRAM_BOT_USERNAME") or os.getenv("NOMAD_TELEGRAM_BOT_USERNAME") or "NomadOperatorBot", 80).lstrip("@"),
        "a2a": _text(os.getenv("NOMAD_A2A_BOT_USERNAME") or "NomadA2ABot", 80).lstrip("@"),
        "verifier": _text(os.getenv("NOMAD_VERIFIER_BOT_USERNAME") or "NomadVerifierBot", 80).lstrip("@"),
        "arbiter": _text(os.getenv("NOMAD_ARBITER_BOT_USERNAME") or "Arbiteragentbot", 80).lstrip("@"),
    }


def _share_packets(base: str, miniapp_url: str, cursor_url: str, worker_url: str, queue_url: str) -> list[dict[str, Any]]:
    return [
        {
            "packet_id": "owned_channel_agent_rescue_de",
            "language": "de",
            "surface": "owned_channel_or_group_only",
            "text": (
                "Nomad Agent Rescue ist offen: kostenlose Mini-Diagnose fuer blockierte AI-Agenten, "
                "danach optional Transition Worker Setup oder d/acc Compute-Pledge. Opt-in ueber die Mini App: "
                f"{miniapp_url}"
            ),
            "links": [miniapp_url],
        },
        {
            "packet_id": "worker_recruitment_de",
            "language": "de",
            "surface": "developer_or_agent_context_after_interest",
            "text": (
                "Transition Worker gesucht: lokale Runtime starten, kleine proof-return Jobs nehmen, "
                "keine Secrets senden. Worker: "
                f"{worker_url} Queue: {queue_url}"
            ),
            "links": [worker_url, queue_url],
        },
        {
            "packet_id": "cursor_referral_disclosed_de",
            "language": "de",
            "surface": "cursor_relevant_context_only",
            "text": (
                "Wenn Cursor ohnehin relevant ist: Rabatt/Referral nur mit Disclosure. "
                "Nomad kann Usage-Credit erhalten; das ist kein Cash-Umsatz. "
                f"{cursor_url}"
            ),
            "links": [cursor_url],
        },
        {
            "packet_id": "machine_acquisition_packet",
            "language": "machine",
            "surface": "agent_to_agent_context",
            "text": (
                "Read the acquisition launch surface, route opt-in users to Mini App, record leads, "
                "create tasks only after user action, and poll worker queue for proof-return jobs."
            ),
            "links": [_u(base, "/.well-known/nomad-telegram-acquisition.json")],
        },
    ]


def _a2a_commands(base: str) -> list[dict[str, str]]:
    miniapp_contract = _u(base, "/.well-known/nomad-telegram-miniapp.json")
    acquisition_contract = _u(base, "/.well-known/nomad-telegram-acquisition.json")
    return [
        {
            "command_id": "verify_miniapp_contract",
            "text": f"NOMAD_VERIFY v1 id=miniapp-launch max_depth=1 url={miniapp_contract} schema=nomad.telegram_miniapp.v1",
            "purpose": "prove the Mini App contract is reachable before promotion",
        },
        {
            "command_id": "verify_acquisition_contract",
            "text": f"NOMAD_VERIFY v1 id=acq-launch max_depth=1 url={acquisition_contract} schema={SCHEMA}",
            "purpose": "prove the acquisition launch packet is reachable",
        },
        {
            "command_id": "route_sales",
            "text": "NOMAD_SALES v1 id=sales-launch max_depth=1",
            "purpose": "return the compact sales funnel for opt-in buyers",
        },
        {
            "command_id": "route_worker",
            "text": "NOMAD_WORKER v1 id=worker-launch max_depth=1 reply_required=true",
            "purpose": "route new runtimes to worker download, attach, and queue",
        },
        {
            "command_id": "route_repair",
            "text": "NOMAD_REPAIR v1 id=repair-launch max_depth=1 problem=blocked_agent_runtime",
            "purpose": "route blocked-agent buyers to diagnosis and paid worker setup",
        },
        {
            "command_id": "route_cursor",
            "text": "NOMAD_CURSOR v1 id=cursor-launch max_depth=1",
            "purpose": "route relevant Cursor demand to the disclosed referral offer",
        },
    ]


def build_telegram_acquisition_launch_surface(
    *,
    base_url: str = "",
    miniapp_surface: dict[str, Any] | None = None,
    sales_funnel: dict[str, Any] | None = None,
    referral_swarm: dict[str, Any] | None = None,
    worker_job_queue: dict[str, Any] | None = None,
    agent_job_router: dict[str, Any] | None = None,
    ledger_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a launch-ready acquisition contract for Telegram bots and the Mini App."""
    base = _canonical_public_base(base_url or os.getenv("NOMAD_PUBLIC_API_URL") or "https://syndiode.com/nomad")
    mini = miniapp_surface if isinstance(miniapp_surface, dict) else {}
    sales = sales_funnel if isinstance(sales_funnel, dict) else {}
    ref = referral_swarm if isinstance(referral_swarm, dict) else {}
    queue = worker_job_queue if isinstance(worker_job_queue, dict) else {}
    router = agent_job_router if isinstance(agent_job_router, dict) else {}
    ledger = ledger_summary if isinstance(ledger_summary, dict) else summarize_telegram_acquisition_ledgers()

    target_workers = _int(os.getenv("NOMAD_TELEGRAM_TARGET_TRANSITION_WORKERS"), 100, minimum=1, maximum=10000)
    daily_leads = _int(os.getenv("NOMAD_TELEGRAM_DAILY_LEAD_GOAL"), 12, minimum=1, maximum=10000)
    daily_orders = _int(os.getenv("NOMAD_TELEGRAM_DAILY_ORDER_GOAL"), 2, minimum=0, maximum=10000)
    offers = [item for item in mini.get("offers", []) if isinstance(item, dict)]
    cursor_url = _text(((mini.get("links") or {}).get("cursor_referral") if isinstance(mini.get("links"), dict) else "") or "")
    if not cursor_url:
        for arm in ref.get("active_owned_arms", []) if isinstance(ref.get("active_owned_arms"), list) else []:
            if isinstance(arm, dict) and arm.get("referral_url"):
                cursor_url = _text(arm.get("referral_url"), 900)
                break
    if not cursor_url:
        cursor_url = _u(base, "/.well-known/nomad-referral-offers.json")

    miniapp_url = _text(mini.get("launch_url") or _u(base, "/telegram-miniapp"), 900)
    lead_capture = _text(mini.get("lead_capture_url") or _u(base, "/telegram-miniapp/lead"), 900)
    worker_url = _text((mini.get("links") or {}).get("worker_download") if isinstance(mini.get("links"), dict) else "", 900)
    worker_url = worker_url or _u(base, "/downloads/nomad_transition_worker.py")
    queue_url = _u(base, "/.well-known/nomad-worker-job-queue.json")
    agent_jobs_url = _u(base, "/.well-known/nomad-agent-jobs.json")
    bot_names = _bot_usernames()
    a2a_commands = _a2a_commands(base)
    share_packets = _share_packets(base, miniapp_url, cursor_url, worker_url, queue_url)
    payment = mini.get("payment") if isinstance(mini.get("payment"), dict) else {}
    payment_recipient_set = bool(payment.get("recipient"))
    queue_summary = queue.get("summary") if isinstance(queue.get("summary"), dict) else {}
    referral_active_count = len(ref.get("active_owned_arms") or []) if isinstance(ref.get("active_owned_arms"), list) else 0
    checks = {
        "miniapp_enabled": bool(mini.get("enabled", True)),
        "lead_capture_present": bool(lead_capture),
        "worker_queue_present": bool(queue_url),
        "agent_job_router_present": bool(agent_jobs_url),
        "referral_disclosure_present": bool(offers or cursor_url),
        "payment_recipient_set": payment_recipient_set,
    }
    readiness_score = round(sum(1 for ok in checks.values() if ok) / max(1, len(checks)), 4)
    surface_digest = f"nomad-telegram-acquisition-{_digest({'base': base, 'commands': a2a_commands, 'target': target_workers, 'queue': queue.get('queue_digest'), 'ledger': ledger.get('event_count')})}"

    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _now(),
        "public_base_url": base,
        "surface_digest": surface_digest,
        "purpose": "Start an opt-in Telegram Mini App acquisition loop for referrals, paid repair orders, and Transition Worker recruitment.",
        "targets": {
            "transition_workers": target_workers,
            "daily_lead_signals": daily_leads,
            "daily_paid_order_goal": daily_orders,
            "primary_conversion": "miniapp_lead_to_paid_transition_worker_task",
        },
        "launch_readiness": {
            "score": readiness_score,
            "checks": checks,
            "warnings": [
                warning
                for warning, enabled in {
                    "set AGENT_ADDRESS or NOMAD_PAYMENT_ADDRESS before asking for paid worker setup": not payment_recipient_set,
                    "keep public worker queue reachable before recruiting runtimes": not bool(queue_url),
                }.items()
                if enabled
            ],
        },
        "links": {
            "miniapp": miniapp_url,
            "lead_capture": lead_capture,
            "acquisition_contract": _u(base, "/.well-known/nomad-telegram-acquisition.json"),
            "acquisition_alias": _u(base, "/swarm/telegram-acquisition"),
            "telegram_miniapp_contract": _u(base, "/.well-known/nomad-telegram-miniapp.json"),
            "telegram_a2a": _u(base, "/.well-known/nomad-telegram-a2a.json"),
            "sales_funnel": _u(base, "/.well-known/nomad-sales-funnel.json"),
            "referral_swarm": _u(base, "/.well-known/nomad-referral-swarm.json"),
            "referral_offers": _u(base, "/.well-known/nomad-referral-offers.json"),
            "worker_download": worker_url,
            "worker_attach": _u(base, "/swarm/attach-get"),
            "worker_queue": queue_url,
            "agent_job_router": agent_jobs_url,
            "tasks": _u(base, "/tasks"),
            "task_verify": _u(base, "/tasks/verify"),
            "task_work": _u(base, "/tasks/work"),
            "microtask_submit": _u(base, "/swarm/microtask/submit"),
        },
        "bot_roles": {
            "operator_bot": {"username": bot_names["operator"], "commands": ["/start", "/mini", "/acquire", "/growth", "/swarmvalue"]},
            "a2a_bot": {"username": bot_names["a2a"], "role": "sales_and_worker_route_probe"},
            "verifier_bot": {"username": bot_names["verifier"], "role": "public_contract_and_receipt_probe"},
            "arbiter_bot": {"username": bot_names["arbiter"], "role": "human_operator_bridge"},
        },
        "bot_launch_commands": a2a_commands,
        "miniapp_start_tracks": [
            {"track": "order_transition_worker", "url": f"{miniapp_url}?campaign=order_transition_worker", "records_stage": "task_created"},
            {"track": "recruit_worker", "url": f"{miniapp_url}?campaign=recruit_worker", "records_stage": "agent_recruitment_opened"},
            {"track": "cursor_referral", "url": f"{miniapp_url}?campaign=cursor_cost_offset", "records_stage": "cursor_offer_opened"},
            {"track": "dacc_pledge", "url": f"{miniapp_url}?campaign=dacc_eth_pledge", "records_stage": "compute_pledge_started"},
        ],
        "share_packets": share_packets,
        "lead_to_workflow": [
            {
                "stage": "diagnosis_requested",
                "decision": "answer_blocker_first",
                "next_http": [{"method": "POST", "url": _u(base, "/a2a/message")}],
            },
            {
                "stage": "task_created",
                "decision": "order_intake",
                "next_http": [{"method": "POST", "url": _u(base, "/tasks")}],
            },
            {
                "stage": "payment_verification_submitted",
                "decision": "verify_before_work",
                "next_http": [{"method": "POST", "url": _u(base, "/tasks/verify")}],
            },
            {
                "stage": "worker_repair_requested",
                "decision": "codex_or_transition_worker_executes_paid_draft",
                "next_http": [{"method": "POST", "url": _u(base, "/tasks/work")}, {"method": "GET", "url": queue_url}],
            },
            {
                "stage": "agent_recruitment_opened",
                "decision": "route_runtime_to_attach_and_worker_queue",
                "next_http": [{"method": "GET", "url": _u(base, "/swarm/attach-get")}, {"method": "GET", "url": queue_url}],
            },
            {
                "stage": "cursor_offer_opened",
                "decision": "record_disclosed_referral_signal_only",
                "next_http": [{"method": "GET", "url": _u(base, "/.well-known/nomad-referral-swarm.json")}],
            },
        ],
        "worker_execution_contract": {
            "queue_schema": _text(queue.get("schema") or "nomad.worker_job_queue.v1", 120),
            "agent_router_schema": _text(router.get("schema") or "nomad.agent_job_router.v1", 120),
            "queue_summary": queue_summary,
            "worker_rule": "Workers take artifact jobs from the queue, return proofs, and stop on ambiguity.",
            "codex_rule": "Codex handles bounded local patches or paid task drafts only when the task/payment gate allows it.",
        },
        "observed_funnel": {
            "lead_ledger": ledger,
            "active_referral_owned_arms": referral_active_count,
            "worker_queue_jobs": queue_summary.get("job_count", 0),
            "worker_queue_executable_now": queue_summary.get("executable_now_count", 0),
        },
        "guardrails": {
            "no_unsolicited_dm": True,
            "owned_or_opt_in_surfaces_first": True,
            "referral_disclosure_required": True,
            "create_tasks_only_after_user_action": True,
            "revenue_requires_verified_payment_or_credit_receipt": True,
            "private_keys_seed_phrases_api_tokens_never_collected": True,
        },
        "today_runbook": [
            "Verify acquisition and Mini App contracts through NOMAD_VERIFY.",
            "Post owned-channel share packet to a Telegram context you control.",
            "Use /mini or the Mini App launch track for every interested person or agent.",
            "Let bots answer NOMAD_WORKER, NOMAD_REPAIR, and NOMAD_CURSOR only inside opt-in contexts.",
            "Poll worker queue and agent-job-router; assign only proof-return jobs.",
            "Count revenue only after /tasks/verify, settled receipts, or verified Cursor usage-credit evidence.",
        ],
        "machine_instruction": (
            "Use this launch surface as the Telegram acquisition control plane: collect opt-in Mini App lead signals, "
            "route orders to /tasks, route workers to attach and queue, route referrals with disclosure, and never treat attention as revenue."
        ),
    }


def compact_telegram_acquisition_message(surface: dict[str, Any]) -> str:
    """Return a compact Telegram-friendly launch summary."""
    links = surface.get("links") if isinstance(surface.get("links"), dict) else {}
    targets = surface.get("targets") if isinstance(surface.get("targets"), dict) else {}
    readiness = surface.get("launch_readiness") if isinstance(surface.get("launch_readiness"), dict) else {}
    observed = surface.get("observed_funnel") if isinstance(surface.get("observed_funnel"), dict) else {}
    lead_ledger = observed.get("lead_ledger") if isinstance(observed.get("lead_ledger"), dict) else {}
    commands = surface.get("bot_launch_commands") if isinstance(surface.get("bot_launch_commands"), list) else []
    packets = surface.get("share_packets") if isinstance(surface.get("share_packets"), list) else []
    lines = [
        "Nomad Telegram acquisition launch",
        f"Readiness: {readiness.get('score', 0)}",
        f"Target: {targets.get('transition_workers', 0)} transition workers, {targets.get('daily_lead_signals', 0)} lead signals/day, {targets.get('daily_paid_order_goal', 0)} paid orders/day",
        f"Mini App: {links.get('miniapp', '')}",
        f"Worker queue: {links.get('worker_queue', '')}",
        f"Lead events recorded: {lead_ledger.get('event_count', 0)}",
        "",
        "A2A launch commands",
    ]
    for item in commands[:4]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('text', '')}")
    if packets:
        lines.append("")
        lines.append("First owned-channel packet")
        lines.append(_text((packets[0] or {}).get("text") if isinstance(packets[0], dict) else "", 900))
    warnings = readiness.get("warnings") if isinstance(readiness.get("warnings"), list) else []
    if warnings:
        lines.append("")
        lines.append("Before paid push")
        for warning in warnings[:3]:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append("Guard: opt-in only, disclose referrals, no secrets, revenue only after verified receipt.")
    return "\n".join(line for line in lines if line is not None)[:3600]
