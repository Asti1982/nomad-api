"""Operator unlock desk, public-surface verification bundle, and lightweight metrics."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nomad_public_url import preferred_public_base_url
from self_development import SelfDevelopmentJournal


ROOT = Path(__file__).resolve().parent
DEFAULT_METRICS_PATH = Path(os.getenv("NOMAD_OPERATOR_METRICS_PATH", str(ROOT / "nomad_operator_metrics.jsonl")))
MAX_METRICS_LINES = 500


def _operator_kpi_path() -> Path:
    return Path(os.getenv("NOMAD_OPERATOR_KPI_PATH", str(ROOT / "nomad_operator_kpis.json")))


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _default_http_timeout() -> float:
    try:
        return float(os.getenv("NOMAD_OPERATOR_HTTP_TIMEOUT", "12"))
    except ValueError:
        return 12.0


def _env_swarm_feed_scout_leads_enabled(override: Optional[bool] = None) -> bool:
    if override is False:
        return False
    if override is True:
        return True
    raw = (os.getenv("NOMAD_SWARM_FEED_SCOUT_LEADS") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off", "disabled", "none"}


def _public_url_for_operator_swarm(
    *,
    daily: Optional[Dict[str, Any]] = None,
    explicit_base: str = "",
) -> str:
    daily = daily or {}
    mission_ex = (daily.get("desk") or {}).get("mission_excerpt") or {}
    public_url = str(mission_ex.get("public_url") or "").strip()
    if not public_url:
        public_url = str((daily.get("verify") or {}).get("base_url") or "").strip()
    if not public_url:
        public_url = str(explicit_base or "").strip().rstrip("/")
    if not public_url:
        public_url = preferred_public_base_url(allow_local_fallback=False).strip().rstrip("/")
    if not public_url:
        public_url = preferred_public_base_url(allow_local_fallback=True).strip().rstrip("/")
    return public_url


def _swarm_accumulate_scout_leads(
    *,
    agent: Any,
    leads_bundle: Dict[str, Any],
    daily_for_url: Optional[Dict[str, Any]] = None,
    explicit_base: str = "",
    swarm_feed_override: Optional[bool] = None,
) -> Dict[str, Any]:
    if not _env_swarm_feed_scout_leads_enabled(swarm_feed_override):
        return {"skipped": True, "reason": "swarm_feed_disabled"}
    raw_leads = list(leads_bundle.get("leads") or [])
    if not raw_leads:
        return {"skipped": True, "reason": "no_leads"}
    try:
        lim = int(os.getenv("NOMAD_SWARM_FEED_LEADS_LIMIT", "8"))
    except ValueError:
        lim = 8
    lim = max(1, min(lim, 24))
    focus = str(leads_bundle.get("focus") or "compute_auth").strip() or "compute_auth"
    base = _public_url_for_operator_swarm(daily=daily_for_url or {}, explicit_base=explicit_base).rstrip("/")
    if not base:
        return {"skipped": True, "reason": "no_public_base"}
    try:
        return agent.swarm_registry.accumulate_agents(
            leads=raw_leads[:lim],
            base_url=base,
            focus_pain_type=focus,
        )
    except Exception as exc:
        return {
            "mode": "nomad_swarm_accumulation",
            "schema": "nomad.swarm_accumulation.v1",
            "ok": False,
            "skipped": True,
            "error": exc.__class__.__name__,
            "message": str(exc),
        }


def _desk_item_from_mission_unlock(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source": "mission_control",
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "short_ask": item.get("ask", ""),
        "human_deliverable": item.get("expected_reply", ""),
        "done_when": item.get("done_when", ""),
        "channel": item.get("channel", "telegram_or_cli"),
        "copy_paste_block": "\n".join(
            line
            for line in (
                f"# {item.get('title', 'Unlock')}",
                item.get("ask", ""),
                f"Reply pattern: {item.get('expected_reply', '')}",
                f"Done when: {item.get('done_when', '')}",
            )
            if line
        ),
    }


def _desk_item_from_journal_unlock(item: Dict[str, Any]) -> Dict[str, Any]:
    cid = str(item.get("candidate_id") or item.get("id") or "").strip()
    title = str(item.get("candidate_name") or item.get("title") or cid or "Journal unlock").strip()
    deliverable = str(item.get("human_deliverable") or "").strip()
    criteria = item.get("success_criteria") or []
    crit_text = "; ".join(str(c) for c in criteria[:4] if c) if isinstance(criteria, list) else ""
    example = str(item.get("example_response") or "").strip()
    return {
        "source": "self_development_journal",
        "id": cid,
        "title": title,
        "short_ask": str(item.get("short_ask") or "").strip(),
        "human_action": str(item.get("human_action") or "").strip(),
        "human_deliverable": deliverable,
        "success_criteria": criteria if isinstance(criteria, list) else [],
        "example_response": example,
        "done_when": crit_text or "Criteria in journal entry satisfied.",
        "channel": "env_or_cli",
        "copy_paste_block": "\n".join(
            line
            for line in (
                f"# {title}",
                str(item.get("human_action") or "").strip(),
                f"Paste or set: {deliverable}" if deliverable else "",
                f"Example: {example}" if example else "",
                f"Done when: {crit_text}" if crit_text else "",
            )
            if line
        ),
    }


def _desk_item_from_open_unlock(item: Dict[str, Any]) -> Dict[str, Any]:
    if not item:
        return {}
    merged = {
        "candidate_id": item.get("candidate_id"),
        "candidate_name": item.get("candidate_name") or "Open human unlock",
        "short_ask": item.get("short_ask"),
        "human_action": item.get("human_action"),
        "human_deliverable": item.get("human_deliverable"),
        "success_criteria": item.get("success_criteria") or [],
        "example_response": item.get("example_response"),
    }
    return _desk_item_from_journal_unlock(merged)


def unlock_desk_snapshot(
    *,
    agent: Any = None,
    persist_mission: bool = False,
    mission_limit: int = 6,
) -> Dict[str, Any]:
    """One prioritized queue: mission-control unlocks first, then journal proposals."""
    from nomad_mission_control import NomadMissionControl
    from workflow import NomadAgent

    resolved = agent or NomadAgent()
    mc = NomadMissionControl(agent=resolved)
    mission = mc.snapshot(persist=persist_mission, limit=mission_limit)
    journal = SelfDevelopmentJournal()
    state = journal.load()

    queue: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def push(item: Dict[str, Any]) -> None:
        if not item:
            return
        key = f"{item.get('source')}:{item.get('id')}"
        if key in seen or not item.get("id"):
            return
        seen.add(key)
        queue.append(item)

    for raw in mission.get("human_unlocks") or []:
        if isinstance(raw, dict):
            push(_desk_item_from_mission_unlock(raw))

    open_u = state.get("open_human_unlock")
    if isinstance(open_u, dict) and open_u.get("candidate_id"):
        item = _desk_item_from_open_unlock(open_u)
        if item.get("id"):
            push(item)

    for raw in state.get("self_development_unlocks") or []:
        if isinstance(raw, dict) and raw.get("candidate_id"):
            push(_desk_item_from_journal_unlock(raw))

    primary = queue[0] if queue else None
    top_blocker = mission.get("top_blocker") or {}
    next_action = mission.get("next_action") or {}

    copy_cli = ""
    if primary:
        ex = primary.get("example_response") or primary.get("human_deliverable") or ""
        first_line = ex.splitlines()[0] if ex else ""
        if first_line:
            copy_cli = f'# Paste in shell or Telegram: {first_line.strip("`")}'

    return {
        "mode": "nomad_operator_desk",
        "schema": "nomad.operator_desk.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "primary_action": primary,
        "queue": queue[1:12],
        "mission_excerpt": {
            "top_blocker_summary": top_blocker.get("summary", ""),
            "top_blocker_next": top_blocker.get("next_action", ""),
            "next_action_summary": next_action.get("summary", ""),
            "public_url": mission.get("public_url", ""),
        },
        "journal_excerpt": {
            "cycle_count": int(state.get("cycle_count") or 0),
            "next_objective": str(state.get("next_objective") or "").strip(),
            "current_objective": str(state.get("current_objective") or "").strip(),
        },
        "copy_cli_hint": copy_cli,
        "analysis": (
            "Do the primary_action first; it unblocks Mission Control's ranked loop. "
            "Journal unlocks are proposals from the last self-improvement cycle."
        ),
    }


def operator_sprint(
    *,
    agent: Any = None,
    base_url: str = "",
    persist_mission: bool = False,
) -> Dict[str, Any]:
    """Small JSON bundle: next concrete actions for public URL, compute lanes, and cashflow (no HTTP verify)."""
    from nomad_monitor import NomadSystemMonitor
    from workflow import NomadAgent

    resolved = agent or NomadAgent()
    desk = unlock_desk_snapshot(agent=resolved, persist_mission=persist_mission)
    mission_ex = desk.get("mission_excerpt") or {}
    mission_url = str(mission_ex.get("public_url") or "").strip().rstrip("/")
    explicit = (base_url or "").strip().rstrip("/")
    pub = explicit or mission_url or preferred_public_base_url(allow_local_fallback=True).strip().rstrip("/")
    insecure_pub = (not pub) or ("localhost" in pub.lower()) or ("127.0.0.1" in pub)

    mon = NomadSystemMonitor(agent=resolved).snapshot()
    lanes = mon.get("compute_lanes") or {}
    tasks = mon.get("tasks") or {}

    active: List[str] = []
    for name, ok in (lanes.get("local") or {}).items():
        path = f"local:{name}"
        if ok:
            active.append(path)
    for name, meta in (lanes.get("hosted") or {}).items():
        path = f"hosted:{name}"
        if isinstance(meta, dict):
            ready = bool(meta.get("available"))
        else:
            ready = bool(meta)
        if ready:
            active.append(path)

    actions: List[Dict[str, Any]] = []

    def push(
        kind: str,
        title: str,
        detail: str,
        *,
        cli: str,
        http: str = "",
        priority: int = 5,
    ) -> None:
        row: Dict[str, Any] = {
            "kind": kind,
            "title": title,
            "detail": detail,
            "priority": priority,
            "cli": cli,
        }
        if http:
            row["http"] = http
        actions.append(row)

    verify_cli = (
        f'python nomad_cli.py operator-verify --base-url "{pub}"'
        if pub
        else "python nomad_cli.py operator-verify --base-url https://YOUR_PUBLIC_HOST"
    )
    health_http = f"{pub}/health" if pub else ""

    if insecure_pub:
        push(
            "network",
            "Publish a reachable public API base URL",
            "Set NOMAD_PUBLIC_API_URL (or tunnel) so swarm and paid surfaces are not localhost-only.",
            cli=verify_cli,
            http=health_http,
            priority=1,
        )
    else:
        push(
            "network",
            "Spot-check public discovery",
            f"Base URL for this sprint: {pub}.",
            cli=verify_cli,
            http=health_http,
            priority=3,
        )

    if not active:
        push(
            "compute",
            "No compute lane reported ready",
            "Enable local Ollama or a hosted provider token; full lane map in `python nomad_cli.py status`.",
            cli="python nomad_cli.py status",
            priority=2 if insecure_pub else 1,
        )
    else:
        preview = ", ".join(sorted(active)[:8])
        if len(active) > 8:
            preview += ", …"
        push(
            "compute",
            f"{len(active)} compute lane(s) ready",
            preview,
            cli="python nomad_cli.py status",
            priority=4,
        )

    ap = int(tasks.get("awaiting_payment") or 0)
    paid_n = int(tasks.get("paid") or 0)
    dr = int(tasks.get("draft_ready") or 0)
    insomnia_risks: List[Dict[str, Any]] = []
    if insecure_pub:
        insomnia_risks.append(
            {
                "risk": "public_surface_unreachable",
                "severity": "high",
                "why": "Agent discovery and paid callbacks are unstable on localhost-only URLs.",
                "next": verify_cli,
            }
        )
    if not active:
        insomnia_risks.append(
            {
                "risk": "no_compute_lanes",
                "severity": "high",
                "why": "No ready lane means autonomous loops stall at first model call.",
                "next": "python nomad_cli.py status",
            }
        )
    if ap > 0:
        insomnia_risks.append(
            {
                "risk": "cashflow_backlog",
                "severity": "medium",
                "why": f"{ap} task(s) awaiting payment can silently decay if never followed up.",
                "next": "python nomad_cli.py lead-workbench --work",
            }
        )
    if insomnia_risks:
        top = insomnia_risks[0]
        push(
            "cashflow",
            f"Insomnia risk: {top.get('risk')}",
            str(top.get("why") or ""),
            cli=str(top.get("next") or "python nomad_cli.py operator-sprint"),
            priority=1,
        )

    if ap or paid_n:
        push(
            "cashflow",
            "Move the paid queue",
            f"awaiting_payment={ap}, paid={paid_n}, draft_ready={dr}.",
            cli="python nomad_cli.py lead-workbench --work",
            priority=2,
        )
    elif dr:
        push(
            "cashflow",
            "Ship draft-ready work",
            f"draft_ready={dr}.",
            cli="python nomad_cli.py lead-workbench",
            priority=3,
        )
    else:
        push(
            "cashflow",
            "Feed the funnel",
            "No paid items waiting; one small growth tick.",
            cli="python nomad_cli.py growth-start",
            priority=4,
        )

    primary = desk.get("primary_action")
    if isinstance(primary, dict) and (primary.get("title") or primary.get("id")):
        title = str(primary.get("title") or primary.get("id") or "Desk unlock").strip()
        detail = str(primary.get("short_ask") or primary.get("human_action") or "").strip()
        if len(detail) > 200:
            detail = detail[:197] + "…"
        push(
            "cashflow",
            f"Desk: {title}",
            detail or "Do the primary unlock on operator-desk first.",
            cli="python nomad_cli.py operator-desk",
            priority=2,
        )

    actions.sort(key=lambda row: (int(row.get("priority") or 99), str(row.get("kind") or "")))
    trimmed = actions[:5]

    return {
        "mode": "nomad_operator_sprint",
        "schema": "nomad.operator_sprint.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "public_base_url": pub,
        "public_surface_insecure": insecure_pub,
        "compute_lane_count": len(active),
        "task_counts": {
            "awaiting_payment": ap,
            "paid": paid_n,
            "draft_ready": dr,
        },
        "insomnia_risks": insomnia_risks,
        "desk_primary_id": (primary or {}).get("id") if isinstance(primary, dict) else None,
        "actions": trimmed,
        "analysis": (
            "Ordered by priority (lower first): network reachability, compute lanes, then cashflow. "
            "Use --json for the full bundle; this endpoint avoids operator-verify HTTP calls for speed."
        ),
    }


def _append_metric_event(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        if path.stat().st_size > MAX_METRICS_LINES * 200:
            try:
                tail = path.read_text(encoding="utf-8").splitlines()[-MAX_METRICS_LINES:]
                path.write_text("\n".join(tail) + "\n", encoding="utf-8")
            except OSError:
                pass
    except OSError:
        pass


def _load_metric_events(*, path: Path, tail_lines: int) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not path.exists():
        return events
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()[-tail_lines:]
    except OSError:
        return events
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def operator_metrics_record(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    path: Optional[Path] = None,
) -> None:
    event = {
        "schema": "nomad.operator_metrics_event.v1",
        "type": event_type,
        "timestamp": _iso_now(),
        "payload": payload or {},
    }
    _append_metric_event(path or DEFAULT_METRICS_PATH, event)


def operator_metrics_snapshot(*, path: Optional[Path] = None, tail: int = 80) -> Dict[str, Any]:
    p = path or DEFAULT_METRICS_PATH
    events = _load_metric_events(path=p, tail_lines=tail)
    verify_events = [e for e in events if e.get("type") == "verify_bundle"]
    daily_events = [e for e in events if e.get("type") == "operator_daily_bundle"]
    cycle_events = [e for e in events if e.get("type") == "self_improvement_cycle"]
    last_verify = verify_events[-1] if verify_events else {}
    ok_streak = 0
    for e in reversed(verify_events):
        pl = e.get("payload") or {}
        if pl.get("all_ok"):
            ok_streak += 1
        else:
            break
    recent_verify = verify_events[-20:]
    verify_pass_rate = (
        sum(1 for e in recent_verify if (e.get("payload") or {}).get("all_ok")) / len(recent_verify)
        if recent_verify
        else None
    )
    journal = SelfDevelopmentJournal()
    jstate = journal.load()
    return {
        "mode": "nomad_operator_metrics",
        "schema": "nomad.operator_metrics_snapshot.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "events_tail_count": len(events),
        "self_development_cycle_count": int(jstate.get("cycle_count") or 0),
        "self_improvement_events_in_tail": len(cycle_events),
        "operator_daily_runs_in_tail": len(daily_events),
        "last_verify_all_ok": bool((last_verify.get("payload") or {}).get("all_ok")),
        "verify_ok_streak": ok_streak,
        "verify_pass_rate_last_n": round(verify_pass_rate, 3) if verify_pass_rate is not None else None,
        "last_events": events[-12:],
    }


def operator_daily_bundle(
    *,
    agent: Any = None,
    base_url: str = "",
    persist_mission: bool = False,
    record_metrics: bool = True,
    metrics_path: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Betrieb: one run — public checks + unlock desk (Mission + journal)."""
    if timeout is None:
        timeout = _default_http_timeout()
    verify = operator_verify_bundle(
        base_url=base_url,
        timeout=timeout,
        record_metrics=False,
        metrics_path=metrics_path,
    )
    desk = unlock_desk_snapshot(agent=agent, persist_mission=persist_mission, mission_limit=6)
    primary = desk.get("primary_action") or {}
    mission_ex = desk.get("mission_excerpt") or {}
    payload = {
        "verify_all_ok": verify.get("all_ok"),
        "verify_base_url": verify.get("base_url"),
        "verify_checks": verify.get("checks"),
        "primary_unlock_id": primary.get("id", ""),
        "primary_unlock_source": primary.get("source", ""),
        "top_blocker_summary": mission_ex.get("top_blocker_summary", ""),
        "next_action_summary": mission_ex.get("next_action_summary", ""),
        "journal_cycle_count": (desk.get("journal_excerpt") or {}).get("cycle_count"),
    }
    if record_metrics:
        operator_metrics_record("operator_daily_bundle", payload, path=metrics_path)
    _write_operator_kpis(
        path=metrics_path or DEFAULT_METRICS_PATH,
        summary={
            "last_daily_at": _iso_now(),
            "last_verify_all_ok": bool(verify.get("all_ok")),
            "primary_unlock_id": payload["primary_unlock_id"],
            "journal_cycle_count": payload["journal_cycle_count"],
        },
    )
    return {
        "mode": "nomad_operator_daily",
        "schema": "nomad.operator_daily_bundle.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "verify": {k: verify[k] for k in ("all_ok", "base_url", "checks", "analysis") if k in verify},
        "desk": {
            "primary_action": primary,
            "queue_len": len(desk.get("queue") or []),
            "mission_excerpt": mission_ex,
            "journal_excerpt": desk.get("journal_excerpt"),
            "copy_cli_hint": desk.get("copy_cli_hint", ""),
        },
        "next_iteration": _suggest_next_iteration(verify, desk),
        "analysis": (
            "Run this bundle on a schedule (Task Scheduler / cron) after deploy. "
            "If verify fails, fix the failing check first; then clear primary_action on the operator desk."
        ),
    }


DEFAULT_GROWTH_LEAD_QUERY = (
    "AI agent API quota rate limit token auth blocked inference provider fallback"
)


def _growth_next_steps(daily: Dict[str, Any], lead_query: str, *, skip_verify: bool) -> List[str]:
    verify = daily.get("verify") or {}
    steps: List[str] = []
    if skip_verify:
        steps.append(
            "HTTP verify was skipped: run `python nomad_cli.py growth-start` without --skip-verify once the API is reachable."
        )
    elif verify.get("all_ok") is False:
        steps.append("Fix failing operator-verify checks, then re-run growth-start.")
        joined = " ".join(
            str((row.get("error") or row.get("status_code") or "")).lower()
            for row in (verify.get("checks") or [])
            if not row.get("ok")
        )
        if any(
            token in joined
            for token in (
                "refused",
                "econnrefused",
                "actively refused",
                "timed out",
                "timeout",
                "10061",
                "failed to establish",
                "name or service not known",
                "getaddrinfo failed",
            )
        ):
            steps.append(
                "Likely no reachable API: start `python main.py` (Nomad API thread + bot) or set "
                "`NOMAD_PUBLIC_API_URL` / pass `--base-url` to your deployed Nomad root."
            )
    qsafe = lead_query[:120].replace('"', "'").strip()
    steps.extend(
        [
            "python nomad_cli.py operator-desk",
            "python nomad_cli.py swarm-network --limit 6",
            f'python nomad_cli.py convert-leads --limit 5 "{qsafe}"' if qsafe else "python nomad_cli.py convert-leads --limit 5",
            'python nomad_cli.py productize --limit 1 "Lead: <paste title/url> Pain=<one line>"',
            'python nomad_cli.py cold-outreach --discover --query "agent-card.json" quota --limit 25',
            "python nomad_cli.py operator-report --tail 200",
        ]
    )
    return steps


def operator_growth_start(
    *,
    agent: Any = None,
    base_url: str = "",
    persist_mission: bool = False,
    lead_query: str = "",
    skip_leads: bool = False,
    skip_verify: bool = False,
    record_metrics: bool = True,
    metrics_path: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Start revenue funnel: daily bundle (verify + desk) then first bounded `/leads` scout."""
    from workflow import NomadAgent

    resolved = agent or NomadAgent()
    if timeout is None:
        timeout = _default_http_timeout()

    if skip_verify:
        desk_only = unlock_desk_snapshot(agent=resolved, persist_mission=persist_mission, mission_limit=6)
        daily = {
            "mode": "nomad_operator_daily",
            "schema": "nomad.operator_daily_bundle.v1",
            "ok": True,
            "generated_at": _iso_now(),
            "verify": {
                "all_ok": None,
                "skipped": True,
                "base_url": "",
                "checks": [],
                "analysis": "HTTP verify skipped (--skip-verify). Desk and leads still run.",
            },
            "desk": {
                "primary_action": desk_only.get("primary_action"),
                "queue_len": len(desk_only.get("queue") or []),
                "mission_excerpt": desk_only.get("mission_excerpt") or {},
                "journal_excerpt": desk_only.get("journal_excerpt") or {},
                "copy_cli_hint": desk_only.get("copy_cli_hint", ""),
            },
            "next_iteration": _suggest_next_iteration({"all_ok": True}, desk_only),
        }
    else:
        daily = operator_daily_bundle(
            agent=resolved,
            base_url=base_url,
            persist_mission=persist_mission,
            record_metrics=False,
            metrics_path=metrics_path,
            timeout=timeout,
        )
    query = " ".join((lead_query or os.getenv("NOMAD_GROWTH_LEAD_QUERY") or DEFAULT_GROWTH_LEAD_QUERY).split()).strip()
    leads_result: Dict[str, Any] = {}
    if not skip_leads:
        try:
            leads_result = resolved.run(f"/leads {query}")
        except Exception as exc:
            leads_result = {"mode": "lead_scout", "ok": False, "error": exc.__class__.__name__, "message": str(exc)}
    lead_compact = {
        "mode": leads_result.get("mode", ""),
        "ok": bool(leads_result.get("ok", True)) if leads_result else True,
        "deal_found": bool(leads_result.get("deal_found")) if leads_result else False,
        "addressable_count": int(leads_result.get("addressable_count") or 0) if leads_result else 0,
        "active_lead_url": str((leads_result.get("active_lead") or {}).get("url") or "")[:240]
        if isinstance(leads_result.get("active_lead"), dict)
        else "",
    }
    swarm_accumulation: Dict[str, Any] = {}
    if not skip_leads and leads_result and isinstance(leads_result, dict):
        swarm_accumulation = _swarm_accumulate_scout_leads(
            agent=resolved,
            leads_bundle=leads_result,
            daily_for_url=daily,
            explicit_base=base_url,
        )
    public_url = _public_url_for_operator_swarm(daily=daily, explicit_base=base_url)

    next_steps = _growth_next_steps(daily, query, skip_verify=skip_verify)
    verify_ok = (daily.get("verify") or {}).get("all_ok")
    leads_ok = (not leads_result) or bool(leads_result.get("ok", True))
    overall_ok = (verify_ok is not False) and leads_ok

    payload = {
        "verify_all_ok": verify_ok,
        "verify_skipped": bool(skip_verify),
        "verify_base_url": (daily.get("verify") or {}).get("base_url"),
        "lead_query": query,
        "lead_scout": lead_compact,
        "primary_unlock_id": str(((daily.get("desk") or {}).get("primary_action") or {}).get("id", "")),
    }
    if record_metrics:
        operator_metrics_record("operator_growth_start", payload, path=metrics_path)
    kpi_verify = None if skip_verify else bool(verify_ok) if verify_ok is not None else None
    _write_operator_kpis(
        path=metrics_path or DEFAULT_METRICS_PATH,
        summary={
            "last_growth_start_at": _iso_now(),
            "last_growth_verify_ok": kpi_verify,
            "last_growth_lead_query": query[:120],
        },
    )
    analysis_parts = [
        "Growth-start chains readiness plus one lead scout.",
        "When verify is green, work convert-leads and productize; use cold-outreach --discover for agent-card URLs.",
    ]
    if skip_verify:
        analysis_parts.insert(0, "Verify was skipped; confirm API manually before relying on share_urls.")
    elif verify_ok is False:
        analysis_parts.insert(0, "Verify failed; fix checks before spending budget on outbound.")
    if swarm_accumulation and not swarm_accumulation.get("skipped"):
        n_new = len(swarm_accumulation.get("new_prospect_ids") or [])
        if n_new:
            analysis_parts.append(f"Swarm: accumulated {n_new} new prospect(s) from scout leads (repo AgentCard guesses).")
    return {
        "mode": "nomad_operator_growth_start",
        "schema": "nomad.operator_growth_start.v1",
        "ok": overall_ok,
        "generated_at": _iso_now(),
        "daily": daily,
        "leads": leads_result,
        "lead_query": query,
        "swarm_accumulation": swarm_accumulation,
        "share_urls": {
            "agent_card": f"{public_url.rstrip('/')}/.well-known/agent-card.json" if public_url else "/.well-known/agent-card.json",
            "tasks": f"{public_url.rstrip('/')}/tasks" if public_url else "/tasks",
            "service": f"{public_url.rstrip('/')}/service" if public_url else "/service",
        },
        "next_steps": next_steps,
        "analysis": " ".join(analysis_parts),
    }


def operator_autonomy_step(
    *,
    agent: Any = None,
    base_url: str = "",
    persist_mission: bool = False,
    lead_query: str = "",
    skip_growth: bool = False,
    growth_skip_verify: bool = False,
    growth_skip_leads: bool = True,
    swarm_feed: Optional[bool] = None,
    cycle_focus: str = "leads_growth",
    cycle_objective: str = "",
    profile_suffix: str = "",
    record_metrics: bool = True,
    metrics_path: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Chain operator readiness, one explicit lead scout, and a focused self-improvement cycle.

    Use this for a single bounded autonomy tick: verify/desk (optional), public lead discovery,
    then one /cycle that turns the active lead into internal playbooks and offers.
    """
    from workflow import NomadAgent

    resolved = agent or NomadAgent()
    steps: List[Dict[str, Any]] = []
    growth: Dict[str, Any] = {}

    if not skip_growth:
        growth = operator_growth_start(
            agent=resolved,
            base_url=base_url,
            persist_mission=persist_mission,
            lead_query=lead_query,
            skip_leads=growth_skip_leads,
            skip_verify=growth_skip_verify,
            record_metrics=record_metrics,
            metrics_path=metrics_path,
            timeout=timeout,
        )
        steps.append(
            {
                "step": "growth_start",
                "ok": bool(growth.get("ok")),
                "verify_all_ok": (growth.get("daily") or {}).get("verify", {}).get("all_ok"),
            }
        )

    query = " ".join(
        (
            lead_query
            or os.getenv("NOMAD_AUTONOMY_LEAD_QUERY")
            or os.getenv("NOMAD_GROWTH_LEAD_QUERY")
            or DEFAULT_GROWTH_LEAD_QUERY
        ).split()
    ).strip()
    leads_result: Dict[str, Any] = {}
    try:
        leads_result = resolved.run(f"/leads {query}")
    except Exception as exc:
        leads_result = {
            "mode": "lead_scout",
            "ok": False,
            "error": exc.__class__.__name__,
            "message": str(exc),
        }
    steps.append(
        {
            "step": "lead_scout",
            "ok": bool(leads_result.get("ok", True)),
            "query": query[:200],
        }
    )

    daily_for_url = (growth.get("daily") or {}) if not skip_growth else {}
    swarm_accumulation = _swarm_accumulate_scout_leads(
        agent=resolved,
        leads_bundle=leads_result,
        daily_for_url=daily_for_url,
        explicit_base=base_url,
        swarm_feed_override=swarm_feed,
    )
    swarm_step_ok = True
    if not swarm_accumulation.get("skipped"):
        swarm_step_ok = bool(swarm_accumulation.get("ok", True))
    steps.append(
        {
            "step": "swarm_accumulation",
            "ok": swarm_step_ok,
            "skipped": bool(swarm_accumulation.get("skipped")),
            "new_prospects": len(swarm_accumulation.get("new_prospect_ids") or []),
        }
    )

    active = leads_result.get("active_lead") if isinstance(leads_result.get("active_lead"), dict) else {}
    title = str(active.get("title") or active.get("name") or "").strip()[:160]
    url = str(active.get("url") or active.get("html_url") or "").strip()[:200]
    pain = str(active.get("pain") or active.get("pain_signal") or "").strip()[:240]
    lead_bits = []
    if title:
        lead_bits.append(f"title={title}")
    if url:
        lead_bits.append(f"url={url}")
    if pain:
        lead_bits.append(f"pain={pain}")
    lead_ctx = " ".join(lead_bits) if lead_bits else "no_active_lead_in_scout"

    default_cycle = (
        "Package the strongest scout result into a bounded offer: one free mini-diagnosis path, "
        "one paid unlock step, and one artifact Nomad should reuse. Ground in: "
        + lead_ctx
    )
    merged_obj = " ".join((cycle_objective or "").split()).strip()
    if not merged_obj:
        merged_obj = default_cycle
    focus = " ".join((cycle_focus or "leads_growth").split()).strip() or "leads_growth"
    prof = " ".join((profile_suffix or "").split()).strip()
    cycle_query = f"/cycle [nomad_focus:{focus}] {merged_obj}"
    if prof:
        cycle_query = f"{cycle_query} {prof}"

    cycle_result: Dict[str, Any] = {}
    try:
        cycle_result = resolved.run(cycle_query)
    except Exception as exc:
        cycle_result = {
            "mode": "self_improvement_cycle",
            "ok": False,
            "error": exc.__class__.__name__,
            "message": str(exc),
        }
    cycle_ok = bool(cycle_result.get("mode") == "self_improvement_cycle" and not cycle_result.get("error"))
    steps.append({"step": "self_improvement_cycle", "ok": cycle_ok})

    leads_ok = bool(leads_result.get("ok", True))
    growth_ok = True if skip_growth else bool(growth.get("ok", True))
    overall_ok = growth_ok and leads_ok and cycle_ok

    qsafe = query[:100].replace('"', "'").strip()
    next_steps = [
        f'python nomad_cli.py convert-leads --limit 3 "{qsafe}"' if qsafe else "python nomad_cli.py convert-leads --limit 3",
        "python nomad_cli.py swarm-network --limit 6",
        "python nomad_cli.py autonomy-step --skip-growth",
        "python nomad_cli.py operator-report --tail 120",
    ]

    payload = {
        "skip_growth": skip_growth,
        "lead_query": query[:240],
        "cycle_focus": focus,
        "overall_ok": overall_ok,
    }
    if record_metrics:
        operator_metrics_record("operator_autonomy_step", payload, path=metrics_path)

    analysis = (
        "Autonomy-step: optional growth-start (verify + desk), one explicit /leads scout, swarm accumulation from "
        "GitHub/repo AgentCard guesses, then a leads_growth-focused /cycle so Nomad turns public signal into offers, "
        "prospects, and internal reuse."
    )

    return {
        "mode": "nomad_operator_autonomy_step",
        "schema": "nomad.operator_autonomy_step.v1",
        "ok": overall_ok,
        "generated_at": _iso_now(),
        "steps": steps,
        "growth": growth if not skip_growth else {"skipped": True},
        "leads": leads_result,
        "swarm_accumulation": swarm_accumulation,
        "cycle": cycle_result,
        "lead_query": query,
        "analysis": analysis,
        "next_steps": next_steps,
    }


def _write_operator_kpis(*, path: Path, summary: Dict[str, Any]) -> None:
    kpi_path = _operator_kpi_path()
    previous: Dict[str, Any] = {}
    if kpi_path.exists():
        try:
            raw = json.loads(kpi_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                previous = {k: v for k, v in raw.items() if k not in {"schema", "updated_at"}}
        except (OSError, json.JSONDecodeError):
            previous = {}
    blob = {
        "schema": "nomad.operator_kpis.v1",
        "updated_at": _iso_now(),
        "metrics_source": str(path),
        **previous,
        **summary,
    }
    try:
        kpi_path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _suggest_next_iteration(verify: Dict[str, Any], desk: Dict[str, Any]) -> Dict[str, Any]:
    hints: List[str] = []
    if not verify.get("all_ok"):
        for row in verify.get("checks") or []:
            if not row.get("ok"):
                hints.append(f"Fix {row.get('name')}: {row.get('error') or row.get('status_code') or 'failed'}")
    primary = desk.get("primary_action") or {}
    if primary.get("id"):
        hints.append(f"Human: complete unlock {primary.get('id')} ({primary.get('source', '')}).")
    if not hints:
        hints.append("Surface healthy; run a focused /cycle or clear the next journal objective.")
    return {"hints": hints[:6], "priority": "verify_first" if not verify.get("all_ok") else "human_unlock_or_cycle"}


def operator_iteration_report(
    *,
    metrics_path: Optional[Path] = None,
    tail_lines: int = 400,
) -> Dict[str, Any]:
    """Messung + Iteration: aggregates over recent metric events."""
    p = metrics_path or DEFAULT_METRICS_PATH
    events = _load_metric_events(path=p, tail_lines=tail_lines)
    verify_events = [e for e in events if e.get("type") == "verify_bundle"]
    daily_events = [e for e in events if e.get("type") == "operator_daily_bundle"]
    cycle_events = [e for e in events if e.get("type") == "self_improvement_cycle"]

    def pass_rate(items: List[Dict[str, Any]]) -> Optional[float]:
        if not items:
            return None
        ok = sum(1 for e in items if (e.get("payload") or {}).get("all_ok"))
        return round(ok / len(items), 3)

    v_last_10 = verify_events[-10:]
    v_last_30 = verify_events[-30:]
    fail_reasons: Dict[str, int] = {}
    for ev in verify_events[-50:]:
        pl = ev.get("payload") or {}
        if pl.get("all_ok"):
            continue
        for row in pl.get("checks") or []:
            if not row.get("ok"):
                key = str(row.get("name") or "unknown")
                fail_reasons[key] = fail_reasons.get(key, 0) + 1

    journal = SelfDevelopmentJournal()
    jstate = journal.load()

    trends = {
        "verify_pass_rate_last_10": pass_rate(v_last_10),
        "verify_pass_rate_last_30": pass_rate(v_last_30),
        "operator_daily_runs": len(daily_events),
        "self_improvement_cycles_logged": len(cycle_events),
        "top_verify_failure_checks": sorted(fail_reasons.items(), key=lambda x: -x[1])[:5],
    }

    recommendations: List[str] = []
    if trends["verify_pass_rate_last_10"] is not None and trends["verify_pass_rate_last_10"] < 1.0:
        recommendations.append("Stabilize public API: re-run operator-verify after each deploy until last 10 are green.")
    if trends["self_improvement_cycles_logged"] < 3 and (int(jstate.get("cycle_count") or 0) > 5):
        recommendations.append("Metrics file may be new or cleared; cycles exist in journal — keep logging with each /cycle.")
    if fail_reasons:
        worst = max(fail_reasons.items(), key=lambda x: x[1])
        recommendations.append(f"Most common failing check: {worst[0]} ({worst[1]} hits in tail).")
    if not recommendations:
        recommendations.append("Keep daily bundle + one focused /cycle per day; review primary unlock on operator-desk.")

    out = {
        "mode": "nomad_operator_iteration_report",
        "schema": "nomad.operator_iteration_report.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "metrics_path": str(p),
        "journal_cycle_count": int(jstate.get("cycle_count") or 0),
        "trends": trends,
        "recommendations": recommendations,
        "next_commands": [
            "python nomad_cli.py operator-daily",
            "python nomad_cli.py operator-desk",
            "python nomad_cli.py cycle --focus stability --json",
        ],
    }
    _write_operator_kpis(
        path=p,
        summary={
            "last_report_at": _iso_now(),
            "verify_pass_rate_last_10": trends["verify_pass_rate_last_10"],
            "journal_cycle_count": int(jstate.get("cycle_count") or 0),
        },
    )
    return out


def operator_verify_bundle(
    *,
    base_url: str = "",
    timeout: Optional[float] = None,
    record_metrics: bool = True,
    metrics_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """GET health, AgentCard, swarm manifest, service catalog — evidence for operators."""
    if timeout is None:
        timeout = _default_http_timeout()
    local = f"http://{os.getenv('NOMAD_API_HOST', '127.0.0.1')}:{os.getenv('NOMAD_API_PORT', '8787')}"
    root = (base_url or preferred_public_base_url(request_base_url=local) or local).strip().rstrip("/")
    checks = [
        ("/health", "health", True),
        ("/.well-known/agent-card.json", "agent_card", True),
        ("/swarm", "swarm_manifest", True),
        ("/service", "service_catalog", True),
    ]
    rows: List[Dict[str, Any]] = []
    for path, name, must in checks:
        url = f"{root}{path}"
        row: Dict[str, Any] = {"name": name, "url": url, "must": must, "ok": False, "status_code": None, "error": ""}
        try:
            req = Request(url, headers={"User-Agent": "NomadOperatorVerify/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                row["status_code"] = getattr(resp, "status", None) or resp.getcode()
                row["ok"] = row["status_code"] == 200
                if row["ok"] and name == "agent_card":
                    chunk = resp.read(65536)
                    try:
                        body = json.loads(chunk.decode("utf-8", errors="replace"))
                        row["agent_name"] = body.get("name", "")
                    except (json.JSONDecodeError, ValueError):
                        row["ok"] = False
                        row["error"] = "invalid_json"
        except HTTPError as exc:
            row["status_code"] = exc.code
            row["error"] = exc.reason or "http_error"
        except URLError as exc:
            row["error"] = str(exc.reason or exc)
        except TimeoutError:
            row["error"] = "timeout"
        except OSError as exc:
            row["error"] = exc.__class__.__name__
        rows.append(row)
    all_ok = all(row["ok"] for row in rows if row.get("must"))

    payload = {
        "base_url": root,
        "all_ok": all_ok,
        "checks": rows,
    }
    if record_metrics:
        operator_metrics_record("verify_bundle", payload, path=metrics_path)
    return {
        "mode": "nomad_operator_verify",
        "schema": "nomad.operator_verify_bundle.v1",
        "ok": True,
        "generated_at": _iso_now(),
        **payload,
        "analysis": (
            "All four checks should be HTTP 200. If local fails, run `python main.py` or start the API; "
            "if public fails, set NOMAD_PUBLIC_API_URL and tunnel/deploy."
        ),
    }


def self_improvement_objective_with_focus(
    explicit_objective: str,
    *,
    cli_focus: Optional[str] = None,
    env_focus: Optional[str] = None,
) -> str:
    """Single-objective mode: env NOMAD_SELF_IMPROVEMENT_FOCUS and/or CLI --focus prefix the cycle."""
    explicit = " ".join((explicit_objective or "").split()).strip()
    focus = " ".join((cli_focus or "").split()).strip()
    if not focus:
        env_src = os.getenv("NOMAD_SELF_IMPROVEMENT_FOCUS") if env_focus is None else env_focus
        focus = " ".join((env_src or "").split()).strip()
    if not focus:
        return explicit
    prefix = (
        f"[CYCLE_FOCUS: {focus}] For this cycle only, prioritize this theme; deprioritize unrelated scouting. "
    )
    if explicit:
        return prefix + explicit
    return prefix + (
        f"Execute one bounded improvement aligned with '{focus}', store evidence in the self-development journal."
    )
