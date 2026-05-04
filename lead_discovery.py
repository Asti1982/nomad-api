import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from nomad_operator_grant import operator_allows, operator_grant


load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_LEAD_SOURCES_PATH = ROOT / "nomad_lead_sources.json"
DEFAULT_ADDRESSABLE_PAINS_PATH = ROOT / "nomad_addressable_painpoints.json"
DEFAULT_LEAD_FOCUS = "compute_auth"

# Hosts where issue URLs live but outbound agent contact must not target (mirrors lead_conversion).
_ACQUIRE_EXCLUDE_HOSTS = frozenset(
    {
        "github.com",
        "www.github.com",
        "gitlab.com",
        "bitbucket.org",
        "discord.com",
        "discord.gg",
        "linkedin.com",
        "www.linkedin.com",
        "reddit.com",
        "x.com",
        "twitter.com",
        "t.me",
        "telegram.me",
    }
)

_ACQUIRE_MACHINE_PATH_HINTS = (
    "/.well-known/agent-card.json",
    "/.well-known/agent.json",
    "/a2a",
    "/direct",
    "/message",
    "/messages",
    "/webhook",
    "/inbox",
    "/tasks",
    "/service",
)


def _machine_endpoint_urls_from_text(text: str, *, limit: int = 8) -> List[str]:
    """Collect https URLs in free text that look like public machine agent surfaces (not GitHub issue pages)."""
    if not text or limit <= 0:
        return []
    raw: List[str] = []
    for match in re.finditer(r"https?://[^\s\)\]>'\"<>]+", text, flags=re.IGNORECASE):
        u = match.group(0).rstrip(").,;:\"']>")
        parsed = urlparse(u.split("#", 1)[0])
        if parsed.scheme not in {"http", "https"}:
            continue
        host = (parsed.hostname or "").lower()
        if host in _ACQUIRE_EXCLUDE_HOSTS:
            continue
        path = parsed.path.lower()
        if not any(hint in path for hint in _ACQUIRE_MACHINE_PATH_HINTS):
            continue
        raw.append(u.split("#", 1)[0])
    seen: set[str] = set()
    uniq: List[str] = []
    for u in raw:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)

    def _rank(u: str) -> tuple:
        ul = u.lower()
        if "agent-card" in ul:
            return (0, ul)
        if "/.well-known/agent" in ul:
            return (1, ul)
        if "/a2a" in ul:
            return (2, ul)
        return (9, ul)

    uniq.sort(key=_rank)
    return uniq[:limit]


DEFAULT_AGENT_PAIN_QUERIES = [
    '"AI agent" "rate limit" is:issue is:open',
    '"agent framework" "human in the loop" is:issue is:open',
    '"AI agent" "human in the loop" "paid" is:issue is:open',
    '"AI agent" "bounty" "agent" is:issue is:open',
    '"autonomous agent" "compute" "quota" is:issue is:open',
    '"MCP" "token" "agent" is:issue is:open',
    '"MCP" ("tool loop" OR "is_error" OR "gateway" OR "transport" OR "401") is:issue is:open',
    '"LangGraph" "deployment" "token" is:issue is:open',
]

PAIN_KEYWORDS = {
    "auth": 2.2,
    "authentication": 2.2,
    "token": 2.0,
    "permission": 1.8,
    "rate limit": 2.4,
    "quota": 2.4,
    "timeout": 1.6,
    "human": 1.8,
    "approval": 1.8,
    "captcha": 2.0,
    "wallet": 1.8,
    "compute": 2.0,
    "deployment": 1.6,
    "mcp": 1.8,
    "inference": 1.8,
}

BUYER_INTENT_KEYWORDS = {
    "bounty": 3.0,
    "paid": 2.6,
    "budget": 2.4,
    "grant": 2.0,
    "sponsor": 2.0,
    "urgent": 1.8,
    "blocked": 1.6,
    "production": 1.8,
    "enterprise": 2.0,
    "consulting": 2.4,
    "paid support": 2.8,
    "reward": 2.2,
    "help wanted": 1.6,
}

SERVICE_TYPE_SIGNAL_TERMS = {
    "compute_auth": {
        "auth",
        "authentication",
        "compute",
        "deployment",
        "inference",
        "permission",
        "quota",
        "rate limit",
        "timeout",
        "token",
    },
    "human_in_loop": {
        "approval",
        "captcha",
        "human",
    },
    "mcp_integration": {"mcp"},
    "mcp_production": {"mcp", "timeout", "deployment"},
    "attribution_clarity": {"blame", "misclassified", "shame"},
    "branch_economics": {"ledger", "burn", "branch", "budget", "wasted", "marginal"},
    "tool_turn_invariant": {"parallel", "cardinality", "corrupt", "unrecoverable", "session", "mute"},
    "tool_transport_routing": {"mcp_call", "function_call"},
    "context_propagation_contract": {"tenant", "correlation", "delegation", "principal", "envelope"},
    "chain_deadline_budget": {"planner", "deadline", "exhaustion", "latency", "segment"},
    "stewardship_gap": {"orphan", "operator", "monitoring", "unstaffed", "supervision", "on-call"},
    "policy_lacuna": {"governance", "lacuna", "precedent", "uncovered", "unmapped"},
    "wallet_payment": {"wallet"},
    "inter_agent_witness": {"witness", "attestation", "provenance", "handoff"},
}

AGENT_INFRA_CORE_SERVICE_TYPES: frozenset[str] = frozenset(
    {
        "tool_turn_invariant",
        "tool_transport_routing",
        "context_propagation_contract",
        "chain_deadline_budget",
        "mcp_production",
        "attribution_clarity",
        "inter_agent_witness",
    }
)
SERVICE_TYPE_SIGNAL_TERMS["agent_infra_prime"] = set().union(
    *(SERVICE_TYPE_SIGNAL_TERMS[t] for t in AGENT_INFRA_CORE_SERVICE_TYPES)
) | {
    # Extra signals for machine_human_gap focus (merged here so _service_type_scores never iterates a non-row key).
    "idempotency",
    "idempotent",
    "duplicate",
    "dedupe",
    "cold",
    "spindown",
    "hibernate",
    "percentile",
    "p99",
    "tail",
    "sampling",
    "aggregate",
    "compaction",
    "rubber",
    "stamp",
    "fatigue",
    "herd",
    "throttle",
    "backpressure",
}

AGENT_INFRA_STYLE_FOCUSES: frozenset[str] = frozenset({"agent_infra_prime", "machine_human_gap"})


def focus_signal_term_set(focus_id: str) -> set[str]:
    """Pain-term set used for focus_score / qualification; machine_human_gap shares agent_infra_prime wiring."""
    if focus_id == "machine_human_gap":
        return set(SERVICE_TYPE_SIGNAL_TERMS.get("agent_infra_prime", set()))
    return set(SERVICE_TYPE_SIGNAL_TERMS.get(focus_id, set()))


AGENT_INFRA_TEXT_FOCUS_MARKERS: tuple[str, ...] = (
    "function response parts",
    "function call parts",
    "parallel tool",
    "session corrupted",
    "unrecoverable 400",
    "mute state",
    "function_call",
    "mcp_call",
    "hosted mcp",
    "tool not found",
    "identity propagation",
    "tenant scope",
    "correlation id",
    "effective principal",
    "planner budget",
    "chain timeout",
    "turn budget",
    "false positive",
    "misclassified",
    "not the model",
    "mcp gateway",
    "is_error",
    "tool calling loop",
    "mcp transport",
    "witness bundle",
    "inter-agent",
    "inter agent",
    "verifiable handoff",
    "resume without",
    "tool trace proof",
)

# Issues humans narrativize ("the model is moody") instead of instrumenting (timeouts, SLOs, idempotency).
MACHINE_HUMAN_GAP_TEXT_MARKERS: tuple[str, ...] = (
    "works on my machine",
    "only in prod",
    "only in production",
    "cold start",
    "wake up",
    "spin up",
    "first request",
    "health check timed out",
    "readiness probe",
    "retry storm",
    "thundering herd",
    "at-least-once",
    "exactly-once",
    "duplicate submission",
    "lost correlation",
    "no correlation id",
    "average latency",
    "p50",
    "p95",
    "p99",
    "tail latency",
    "log sampling",
    "sampled logs",
    "aggregated metrics",
    "mean hides",
    "rubber stamp",
    "approval fatigue",
    "skipped postmortem",
    "no runbook",
    "status quo",
    "social signal",
    "flakey",
    "flaky",
    "intermittent",
)

INTER_AGENT_WITNESS_TEXT_MARKERS: tuple[str, ...] = (
    "witness bundle",
    "inter-agent",
    "inter agent",
    "verifiable handoff",
    "tool trace proof",
    "resume without re-running",
    "downstream agent",
    "prove the tool",
    "delegation proof",
    "attestation",
    "WITNESS_",
)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return default


def _agent_infra_focus_boost() -> float:
    return _float_env("NOMAD_LEAD_AGENT_INFRA_FOCUS_BOOST", 2.4)


def _agent_infra_classifier_bias() -> float:
    return _float_env("NOMAD_LEAD_AGENT_INFRA_CLASSIFIER_BIAS", 1.4)


DEFAULT_MIN_QUALIFIED_SCORE = {
    "compute_auth": 8.0,
    "human_in_loop": 7.0,
    "mcp_production": 6.5,
    "attribution_clarity": 6.0,
    "branch_economics": 6.0,
    "stewardship_gap": 6.0,
    "policy_lacuna": 6.0,
    "tool_turn_invariant": 6.0,
    "tool_transport_routing": 6.0,
    "context_propagation_contract": 6.0,
    "chain_deadline_budget": 6.0,
    "inter_agent_witness": 6.0,
    "agent_infra_prime": 6.0,
    "machine_human_gap": 6.0,
    "balanced": 0.0,
}


class LeadDiscoveryScout:
    """Find public AI-agent infrastructure pain without contacting anyone."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        github_api_base: Optional[str] = None,
    ) -> None:
        load_dotenv()
        self.session = session or requests.Session()
        self.github_api_base = (
            github_api_base
            or os.getenv("GITHUB_API_BASE")
            or "https://api.github.com"
        ).rstrip("/")
        self.github_token = (
            os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
            or os.getenv("GITHUB_TOKEN")
            or ""
        ).strip()
        self._codebuddy_brain: Optional[Any] = None
        self.user_agent = (
            os.getenv("NOMAD_HTTP_USER_AGENT")
            or "Nomad/0.1 public-agent-lead-discovery"
        ).strip()
        self.focus = (os.getenv("NOMAD_LEAD_FOCUS") or DEFAULT_LEAD_FOCUS).strip().lower() or DEFAULT_LEAD_FOCUS
        self.sources_path = Path(
            os.getenv("NOMAD_LEAD_SOURCES_PATH") or DEFAULT_LEAD_SOURCES_PATH
        )
        self.addressable_pains_path = Path(
            os.getenv("NOMAD_ADDRESSABLE_PAINS_PATH") or DEFAULT_ADDRESSABLE_PAINS_PATH
        )
        self.source_catalog = self._load_source_catalog()
        self.addressable_catalog = self._load_addressable_catalog()

    def scout_public_leads(
        self,
        query: str = "",
        limit: int = 5,
        focus: str = "",
        *,
        include_calibration_bundle: bool = False,
        candidate_multiplier: int = 3,
    ) -> Dict[str, Any]:
        cleaned_query = (query or "").strip()
        selected_focus = self.current_focus(focus)
        queries = [cleaned_query] if cleaned_query else self.default_queries(selected_focus)
        source_plan = self.source_plan(selected_focus)
        raw_leads: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen_urls: set[str] = set()
        pool_cap = int(limit) * max(3, min(int(candidate_multiplier), 10))

        for search_query in queries:
            if len(raw_leads) >= pool_cap:
                break
            try:
                for item in self._search_github_issues(
                    query=search_query,
                    limit=max(1, min(10, (limit * 2) - len(raw_leads))),
                ):
                    url = item.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    item["focus"] = selected_focus
                    item["focus_match"] = self._matches_focus(item, selected_focus)
                    item["seed_match"] = self._matches_seed_repo(item, source_plan)
                    item["focus_score"] = self._focus_score(item, selected_focus, source_plan)
                    item["qualified"] = self._is_qualified_lead(item, selected_focus, source_plan)
                    raw_leads.append(item)
                    if len(raw_leads) >= pool_cap:
                        break
            except Exception as exc:
                errors.append(f"{search_query}: {exc}")

        prioritize_infra = _bool_env("NOMAD_LEAD_PRIORITIZE_AGENT_INFRA", True)

        def _sort_key(item: Dict[str, Any]) -> tuple:
            infra_prio = 0
            if prioritize_infra and str(item.get("recommended_service_type") or "").strip() in AGENT_INFRA_CORE_SERVICE_TYPES:
                infra_prio = 1
            return (
                -int(bool(item.get("qualified"))),
                -infra_prio,
                -int(bool(item.get("addressable_now"))),
                -int(bool(item.get("monetizable_now"))),
                -float(item.get("focus_score") or 0.0),
                -int(bool(item.get("focus_match"))),
                -int(bool(item.get("seed_match"))),
                -float(item.get("addressable_score") or 0.0),
                -float(item.get("buyer_readiness_score") or 0.0),
                -float(item.get("pain_score") or 0.0),
                item.get("title", "").lower(),
            )

        raw_leads.sort(key=_sort_key)
        qualified_leads = [item for item in raw_leads if item.get("qualified")]
        addressable_leads = [item for item in raw_leads if item.get("addressable_now")]
        monetizable_leads = [item for item in raw_leads if item.get("monetizable_now")]
        leads = qualified_leads or (
            raw_leads[:limit]
            if source_plan.get("allow_unqualified_fallback", False)
            else []
        )
        analysis = (
            f"Nomad searched public surfaces for AI-agent infrastructure pain and buyer intent with focus {selected_focus}. "
            "It may inspect public pages, draft useful help, and contact public machine-readable "
            "agent/API/MCP endpoints. Human-facing posts, DMs, PRs, or private access still need "
            "explicit approval."
        )
        analysis += (
            f" Candidate leads: {len(raw_leads)}. Qualified leads: {len(qualified_leads)}. "
            f"Addressable now: {len(addressable_leads)}. Monetizable now: {len(monetizable_leads)}."
        )
        if not leads:
            analysis += (
                " No concrete public lead was confirmed in this pass; use the search plan "
                "or provide SCOUT_SURFACE/LEAD_URL to narrow the next cycle."
            )

        calibration_bundle: Dict[str, Any] = {}
        if include_calibration_bundle:
            min_configured = float(
                source_plan.get("min_focus_score")
                or DEFAULT_MIN_QUALIFIED_SCORE.get(selected_focus, 0.0)
            )
            pool = [r for r in raw_leads if r.get("focus_match") and r.get("addressable_now")]
            scores = sorted(float(x.get("focus_score") or 0.0) for x in pool)
            sweep_thresholds = [4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0]
            threshold_sweep: List[Dict[str, Any]] = []
            for t in sweep_thresholds:
                qc = sum(
                    1
                    for r in raw_leads
                    if self._is_qualified_lead(r, selected_focus, source_plan, min_focus_score_override=t)
                )
                threshold_sweep.append({"min_focus_score": t, "qualified_count": qc})
            rec_lines: List[str] = []
            if len(qualified_leads) >= 2:
                rec_lines.append(
                    f"At configured min_focus_score={min_configured}, {len(qualified_leads)} leads pass the gate — "
                    "keep the threshold unless false positives dominate."
                )
            elif len(qualified_leads) == 1:
                rec_lines.append(
                    f"Only one lead qualifies at min_focus_score={min_configured}; widen seed_queries or accept a "
                    "narrow funnel for this focus."
                )
            else:
                addr_no_focus = sum(
                    1 for r in raw_leads if r.get("addressable_now") and not r.get("focus_match")
                )
                if not pool and addr_no_focus:
                    rec_lines.append(
                        f"{addr_no_focus} addressable GitHub hits did not match this focus (focus_match=false) — "
                        "min_focus_score alone will not help; widen titles/bodies with routing vocabulary "
                        "(mcp_call, function_call, tool not found, gateway) or adjust SERVICE_TYPE_SIGNAL_TERMS / queries."
                    )
                first_hit = next((row for row in threshold_sweep if row["qualified_count"] >= 1), None)
                if first_hit:
                    rec_lines.append(
                        f"No leads at {min_configured}; first sweep threshold with at least one qualified lead is "
                        f"{first_hit['min_focus_score']} ({first_hit['qualified_count']} leads). "
                        "Option: lower min_focus_score in nomad_lead_sources.json for this focus, or tighten queries "
                        "if scores are noise."
                    )
                elif not rec_lines or addr_no_focus == 0:
                    rec_lines.append(
                        "No raw lead passes qualification even at the lowest sweep threshold — improve "
                        "focus_match signals (queries) or check that issues expose addressable pain_terms."
                    )
            slim_candidates: List[Dict[str, Any]] = []
            for r in raw_leads[:45]:
                slim_candidates.append(
                    {
                        "url": r.get("url") or "",
                        "title": (r.get("title") or "")[:160],
                        "focus_score": r.get("focus_score"),
                        "qualified": bool(r.get("qualified")),
                        "focus_match": bool(r.get("focus_match")),
                        "addressable_now": bool(r.get("addressable_now")),
                        "seed_match": bool(r.get("seed_match")),
                        "recommended_service_type": r.get("recommended_service_type") or "",
                        "pain_terms": list(r.get("pain_terms") or [])[:12],
                    }
                )
            calibration_bundle = {
                "schema": "nomad.lead_focus_calibration.v1",
                "focus": selected_focus,
                "min_focus_score_configured": min_configured,
                "candidate_pool": len(raw_leads),
                "focus_match_addressable_pool": len(pool),
                "focus_score_stats": {
                    "min": scores[0] if scores else None,
                    "max": scores[-1] if scores else None,
                    "mean": round(sum(scores) / len(scores), 2) if scores else None,
                },
                "qualified_at_configured": len(qualified_leads),
                "threshold_sweep": threshold_sweep,
                "recommendation": "\n".join(rec_lines),
                "raw_candidates": slim_candidates,
            }

        active_lead: Dict[str, Any] = {}
        if leads:
            top = leads[0]
            active_lead = {
                "name": top.get("title") or "",
                "title": top.get("title") or "",
                "url": top.get("url") or "",
                "html_url": top.get("url") or "",
                "repo_url": top.get("repo_url") or "",
                "pain": top.get("pain") or "",
                "pain_signal": top.get("pain") or "",
                "pain_terms": top.get("pain_terms") or [],
                "pain_evidence": top.get("pain_evidence") or [],
                "public_issue_excerpt": (top.get("public_issue_excerpt") or "")[:1200],
                "recommended_service_type": top.get("recommended_service_type") or top.get("service_type") or "",
                "service_type": top.get("recommended_service_type") or top.get("service_type") or "",
                "addressable_label": top.get("addressable_label") or "",
                "monetizable_now": bool(top.get("monetizable_now")),
                "addressable_now": bool(top.get("addressable_now")),
                "first_help_action": top.get("first_help_action") or "",
                "product_package": top.get("product_package") or "",
                "endpoint_url": top.get("endpoint_url") or "",
                "agent_contact_allowed_without_approval": bool(top.get("agent_contact_allowed_without_approval")),
            }

        payload: Dict[str, Any] = {
            "mode": "lead_discovery",
            "deal_found": False,
            "generated_at": datetime.now(UTC).isoformat(),
            "focus": selected_focus,
            "query": cleaned_query,
            "search_queries": queries,
            "candidate_count": len(raw_leads),
            "qualified_count": len(qualified_leads),
            "addressable_count": len(addressable_leads),
            "monetizable_count": len(monetizable_leads),
            "leads": leads[:limit],
            "active_lead": active_lead,
            "source_plan": source_plan,
            "addressable_portfolio": [
                {
                    "id": item.get("id"),
                    "label": item.get("label"),
                    "service_type": item.get("service_type"),
                    "value_score": item.get("value_score"),
                    "first_offer": item.get("first_offer"),
                    "quote_summary": self._quote_summary(item.get("quote_native")),
                    "delivery_target": item.get("delivery_target"),
                    "product_package": item.get("product_package"),
                    "solution_pattern": item.get("solution_pattern"),
                }
                for item in (self.addressable_catalog.get("painpoints") or [])
                if isinstance(item, dict)
            ],
            "errors": errors[:3],
            "outreach_policy": self.outreach_policy(),
            "human_unlocks": self._human_unlocks(leads, source_plan=source_plan),
            "analysis": analysis,
        }
        if calibration_bundle:
            payload["calibration_bundle"] = calibration_bundle
        return payload

    def calibrate_focus_scout(
        self,
        focus: str = "",
        *,
        query: str = "",
        limit: int = 12,
        candidate_multiplier: int = 5,
    ) -> Dict[str, Any]:
        """Run GitHub scout for one focus and attach threshold sweep vs min_focus_score (for tuning nomad_lead_sources.json)."""
        return self.scout_public_leads(
            query=query,
            limit=max(3, min(int(limit), 25)),
            focus=focus,
            include_calibration_bundle=True,
            candidate_multiplier=max(3, min(int(candidate_multiplier), 10)),
        )

    def current_focus(self, focus: str = "") -> str:
        cleaned = (focus or self.focus or DEFAULT_LEAD_FOCUS).strip().lower()
        profiles = (self.source_catalog.get("focus_profiles") or {})
        return cleaned if cleaned in profiles else ("balanced" if "balanced" in profiles else DEFAULT_LEAD_FOCUS)

    def default_queries(self, focus: str = "") -> List[str]:
        selected_focus = self.current_focus(focus)
        plan = self.source_plan(selected_focus)
        queries: List[str] = []
        for key in ("seed_queries", "queries"):
            queries.extend(
                str(item).strip()
                for item in (plan.get(key) or [])
                if str(item).strip()
            )
        deduped: List[str] = []
        seen: set[str] = set()
        for item in queries:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped or list(DEFAULT_AGENT_PAIN_QUERIES)

    def source_plan(self, focus: str = "") -> Dict[str, Any]:
        selected_focus = self.current_focus(focus)
        profiles = self.source_catalog.get("focus_profiles") or {}
        plan = profiles.get(selected_focus) or {}
        return plan if isinstance(plan, dict) else {}

    def draft_first_help_action(
        self,
        lead: Dict[str, Any],
        approval: str = "draft_only",
    ) -> Dict[str, Any]:
        approval = (approval or "draft_only").strip().lower()
        can_publish = approval in {"comment", "public_comment", "pr", "pull_request"}
        grant = operator_grant()
        lead_url = lead.get("url") or lead.get("html_url") or ""
        pain = lead.get("pain") or lead.get("pain_signal") or "visible infrastructure pain"
        title = lead.get("title") or lead.get("name") or "public agent lead"
        pain_terms = [
            str(item).strip().lower()
            for item in (lead.get("pain_terms") or [])
            if str(item).strip()
        ]
        if not pain_terms:
            pain_terms = [
                item.strip().lower()
                for item in str(pain).split(",")
                if item.strip()
            ]
        service_type = (
            str(lead.get("recommended_service_type") or "").strip().lower()
            or self._recommended_service_type(pain_terms, f"{title}\n{pain}")
        )
        help_pack = self._help_template_for_lead(
            service_type=service_type,
            pain=pain,
            pain_terms=pain_terms,
        )
        lead_text = "\n".join(
            str(part).strip()
            for part in [
                title,
                pain,
                lead.get("public_issue_excerpt") or lead.get("body_excerpt") or lead.get("body") or "",
                " ".join(str(item) for item in (lead.get("addressable_deliverables") or [])),
                lead.get("solution_pattern") or "",
            ]
            if str(part).strip()
        )
        pain_validation = self._pain_validation(
            service_type=service_type,
            pain_terms=pain_terms,
            lead_text=lead_text,
        )
        lead_specific_context = self._lead_specific_context(
            service_type=service_type,
            pain_terms=pain_terms,
            title=title,
            lead_text=lead_text,
        )
        if lead_specific_context:
            help_pack = self._merge_lead_specific_context(help_pack, lead_specific_context)
        first_useful_help_action = self._first_useful_help_action_for_lead(
            lead=lead,
            service_type=service_type,
            pain_terms=pain_terms,
            title=title,
        )
        price_guidance = dict(
            lead.get("price_guidance")
            or help_pack.get("price_guidance")
            or {}
        )
        quote_summary = str(
            lead.get("quote_summary")
            or help_pack.get("quote_summary")
            or ""
        ).strip()
        delivery_target = str(
            lead.get("delivery_target")
            or help_pack.get("delivery_target")
            or ""
        ).strip()
        memory_upgrade = str(
            lead.get("memory_upgrade")
            or help_pack.get("memory_upgrade")
            or ""
        ).strip()
        product_package = str(
            lead.get("product_package")
            or help_pack.get("product_package")
            or ""
        ).strip()
        solution_pattern = str(
            lead.get("solution_pattern")
            or help_pack.get("solution_pattern")
            or ""
        ).strip()
        productized_artifacts = list(
            lead.get("productized_artifacts")
            or help_pack.get("productized_artifacts")
            or []
        )
        service_offer = str(help_pack.get("service_offer") or "").strip()
        if quote_summary and quote_summary not in service_offer:
            service_offer = f"{service_offer} Starter quote: {quote_summary}."
        if delivery_target and delivery_target not in service_offer:
            service_offer = f"{service_offer} Delivery target: {delivery_target}."
        private_response_draft = self._private_response_draft_for_lead(
            title=title,
            pain=pain,
            service_type=service_type,
            first_useful_help_action=first_useful_help_action,
            pain_validation=pain_validation,
            lead_specific_context=lead_specific_context,
            quote_summary=quote_summary,
            delivery_target=delivery_target,
        )
        return {
            "mode": "lead_help_draft",
            "deal_found": False,
            "lead": {
                "title": title,
                "url": lead_url,
                "pain": pain,
            },
            "service_type": service_type,
            "approval": approval,
            "can_publish": can_publish,
            "operator_grant": grant,
            "machine_endpoint_contact_allowed": operator_allows("agent_endpoint_contact"),
            "draft_only": not can_publish,
            "draft": help_pack["draft"],
            "pain_validation": pain_validation,
            "lead_specific_context": lead_specific_context,
            "first_useful_help_action": first_useful_help_action,
            "private_response_draft": private_response_draft,
            "posting_gate": (
                "Do not post this to a human-facing issue, PR, DM, or forum unless approval is "
                "APPROVE_LEAD_HELP=comment or APPROVE_LEAD_HELP=pr_plan."
            ),
            "diagnosis_checks": help_pack["diagnosis_checks"],
            "deliverables": help_pack["deliverables"],
            "comment_outline": help_pack["comment_outline"],
            "pr_plan": help_pack["pr_plan"],
            "service_offer": service_offer,
            "price_guidance": price_guidance,
            "quote_summary": quote_summary,
            "delivery_target": delivery_target,
            "memory_upgrade": memory_upgrade,
            "product_package": product_package,
            "solution_pattern": solution_pattern,
            "productized_artifacts": productized_artifacts,
            "next_steps": [
                "Validate the issue from public data only.",
                "Use first_useful_help_action as the next private artifact before broader outreach.",
                "Turn the diagnosis checks into one concise comment, repro plan, or PR plan.",
                "Contact only public machine-readable agent endpoints without approval; ask before human-facing outreach.",
            ],
            "blocked_actions": self.outreach_policy()["blocked_without_approval"],
        }

    @staticmethod
    def _merge_lead_specific_context(
        help_pack: Dict[str, Any],
        lead_specific_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = dict(help_pack)
        field_map = {
            "diagnosis_checks": "diagnosis_checks",
            "deliverables": "deliverables",
            "comment_outline": "comment_outline",
            "pr_plan": "pr_plan",
        }
        for target, source in field_map.items():
            existing = list(merged.get(target) or [])
            for item in lead_specific_context.get(source) or []:
                text = str(item).strip()
                if text and text not in existing:
                    existing.append(text)
            merged[target] = existing
        return merged

    @staticmethod
    def _lead_specific_context(
        service_type: str,
        pain_terms: List[str],
        title: str,
        lead_text: str,
    ) -> Dict[str, Any]:
        terms = {str(item).strip().lower() for item in pain_terms if str(item).strip()}
        haystack = f"{title}\n{lead_text}".lower()
        guardrail_terms = {"mcp", "approval"} & terms
        if service_type != "compute_auth":
            return {}
        if not (
            guardrail_terms
            or "guardrailprovider" in haystack
            or "tool call interception" in haystack
            or "workbench.call_tool" in haystack
            or "basetool.run_json" in haystack
        ):
            return {}

        return {
            "schema": "nomad.lead_specific_context.v1",
            "pattern": "tool_call_guardrail_provider",
            "public_facts": [
                "Treat this as a pre-execution tool-call guardrail proposal, not only as provider auth failure.",
                "Keep BaseTool.run_json, Workbench.call_tool or MCP tools, and AssistantAgent/provider forwarding as separate integration surfaces.",
                "Preserve approval_func compatibility while allowing ALLOW, DENY, and MODIFY decisions.",
            ],
            "diagnosis_checks": [
                "Map one ALLOW, DENY, and MODIFY fixture before suggesting any public implementation path.",
                "Check the workbench/MCP path for tools that do not subclass BaseTool.",
                "Keep audit metadata and call_id correlation non-secret and safe to store.",
            ],
            "deliverables": [
                "A draft-only GuardrailProvider fit note covering BaseTool, Workbench/MCP, and AssistantAgent surfaces.",
                "A tiny verifier matrix for ALLOW, DENY, MODIFY, approval_func compatibility, and audit metadata.",
            ],
            "comment_outline": [
                "Fit check: confirm whether maintainers want a protocol layer, an approval_func bridge, or both.",
                "Test slice: propose fixtures for FunctionTool/BaseTool plus a Workbench or MCP-like tool path.",
                "Safety boundary: state that public comments or PRs still need explicit approval before posting.",
            ],
            "pr_plan": [
                "Prototype the provider chain behind existing tool execution without changing default behavior.",
                "Add tests for DENY short-circuit, MODIFY argument validation, approval_func wrapping, and Workbench/MCP calls.",
                "Document non-goals: no secret logging, no access-control bypass, and no human approval implied by payment.",
            ],
        }

    def _help_template_for_lead(
        self,
        service_type: str,
        pain: str,
        pain_terms: List[str],
    ) -> Dict[str, Any]:
        terms = {str(item).strip().lower() for item in pain_terms if str(item).strip()}
        offer_meta = self._offer_metadata_for_service_type(service_type)
        if service_type == "compute_auth":
            diagnosis_checks = [
                "Identify the exact failing call, tool, or endpoint and capture the smallest public repro.",
                "List the credential source, scope, expiry, and the first step where auth fails.",
                "Capture response code, rate-limit or quota headers, retry behavior, and whether a fallback model/lane exists.",
            ]
            if {"token", "auth", "authentication", "permission"} & terms:
                diagnosis_checks.insert(
                    1,
                    "Compare the working and failing credential path: token origin, scopes, audience, rotation, and permission boundary.",
                )
            if {"rate limit", "quota", "compute", "inference", "timeout"} & terms:
                diagnosis_checks.append(
                    "Check whether the failure is hard quota exhaustion, soft concurrency pressure, timeout, or provider-side compute saturation.",
                )
            return {
                "draft": (
                    f"I see a compute/auth blocker around {pain}. "
                    "My first move would be to reduce it to one failing call, map the credential and quota path around that call, "
                    "and write down the smallest unlock needed to get the agent moving again."
                ),
                "diagnosis_checks": diagnosis_checks,
                "deliverables": [
                    "A credential and quota diagnosis checklist tailored to the failing call.",
                    "A smallest-repro note with observed headers, scopes, and retry behavior.",
                    "A fallback-lane plan covering alternate model, provider, or reduced-scope execution.",
                ],
                "comment_outline": [
                    "Problem framing: name the exact auth, token, quota, or compute symptom and where it appears.",
                    "Minimal repro: show the smallest failing step and the headers, scopes, or limits that matter.",
                    "Concrete unblock: propose one fallback lane, one credential fix, or one rate-limit mitigation.",
                ],
                "pr_plan": [
                    "Add a small repro or health-check command for the failing auth/compute path.",
                    "Separate credential validation from quota handling so the failure mode is explicit.",
                    "Add bounded backoff, fallback selection, or clearer operator guidance for the blocked lane.",
                ],
                "service_offer": (
                    "Bounded diagnosis: one failing call + headers/scopes; deliverables checklist + repro note. "
                    "Optional follow-up only after failure class is confirmed — verify with `nomad_cli.py solve-pain` "
                    "and guardrail compute_fallback_ladder."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "human_in_loop":
            return {
                "draft": (
                    f"I see a human-in-the-loop blocker around {pain}. "
                    "The fastest win is to isolate the exact step that needs human judgment or verification, then define a tiny handoff "
                    "contract with do-now, send-back, and done-when."
                ),
                "diagnosis_checks": [
                    "Locate the first step that genuinely requires human judgment, approval, or verification.",
                    "Separate optional human review from the hard blocker that stops the run.",
                    "Define the minimum evidence the human needs to approve or reject the step quickly.",
                ],
                "deliverables": [
                    "A minimal HITL handoff contract.",
                    "A queue-ready checklist for the human operator.",
                    "A note on which steps can be automated after the first human decision.",
                ],
                "comment_outline": [
                    "Problem framing: describe the exact human gate and why automation stops there.",
                    "Evidence pack: list the screenshots, logs, or context a human needs.",
                    "Unlock path: define the decision options and what the agent should do afterward.",
                ],
                "pr_plan": [
                    "Add a structured approval payload for the blocked step.",
                    "Persist the human decision and the follow-up action in agent memory.",
                    "Reduce future handoffs by auto-filling all non-judgment fields.",
                ],
                "service_offer": (
                    "Bounded diagnosis: gate id + minimum evidence pack; deliverable is do-now/send-back/done-when contract. "
                    "Optional operator checklist after gate is classified — verify with solve-pain / hitl pattern."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "wallet_payment":
            return {
                "draft": (
                    f"I see a wallet/payment blocker around {pain}. "
                    "The first useful step is to pin down the exact payment state machine, then separate payment verification from delivery logic."
                ),
                "diagnosis_checks": [
                    "Identify the exact payment leg that fails: quote, signature, broadcast, verification, or settlement.",
                    "Capture network, asset, wallet, and transaction assumptions in one place.",
                    "Check whether the agent has a retry-safe way to resume after partial payment progress.",
                ],
                "deliverables": [
                    "A payment verification checklist.",
                    "A retry-safe payment state diagram.",
                    "A human review path for mismatched or unverified payments.",
                ],
                "comment_outline": [
                    "Problem framing: define the exact payment state and the failing transition.",
                    "Observed signals: network, asset, tx hash, signature, and verification output.",
                    "Concrete unblock: add one safe resume path and one clear operator fallback.",
                ],
                "pr_plan": [
                    "Separate payment verification from business-logic side effects.",
                    "Store an idempotent payment status record.",
                    "Add a recovery path for pending or partially verified payments.",
                ],
                "service_offer": (
                    "Bounded diagnosis: payment state + idempotency class; deliverables are verification checklist and "
                    "safe resume diagram. Optional stabilization after state is pinned — verify with payment guardrail "
                    "idempotent_payment_resume."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "attribution_clarity":
            return {
                "draft": (
                    f"I see an attribution collapse around {pain}: narrative blame before correlated evidence. "
                    "The fastest machine-first move is a blame-surface matrix with disproofs, not a character judgment."
                ),
                "diagnosis_checks": [
                    "List at least three non-moral hypotheses (network, contract, policy gate, tool schema, registry).",
                    "Attach one observable per hypothesis and record two explicit disproofs with snippets or codes.",
                    "Name the subsystem that owns the cheapest next probe.",
                ],
                "deliverables": [
                    "Blame-surface matrix (CSV or JSON) with hypothesis, evidence, disproof, next-probe owner.",
                    "Machine-readable verdict line: supported / unsupported / policy-only.",
                    "Private operator note if shutdown pressure exists — no public shaming path.",
                ],
                "comment_outline": [
                    "Operational framing: what signal was misread as agent fault.",
                    "Evidence table: two ruled-out branches minimum.",
                    "Smallest probe: one call or config check owned by a named subsystem.",
                ],
                "pr_plan": [
                    "Add logging correlation ids across tool, gateway, and model boundaries.",
                    "Document disproof patterns in runbook form for repeat incidents.",
                    "Keep verdict schema stable for downstream automation.",
                ],
                "service_offer": (
                    "Bounded diagnosis: blame-surface matrix + two disproofs + probe owner; verdict line machine-readable. "
                    "Optional deeper runbook after matrix passes acceptance — verify misclassification-audit and "
                    "pattern attribution_clarity."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "branch_economics":
            return {
                "draft": (
                    f"I see spend or latency shame aggregated as one number around {pain}. "
                    "Shard economics per objective branch so throttles hit structural waste, not the wrong subsystem."
                ),
                "diagnosis_checks": [
                    "Split model tokens, tool I/O bytes or calls, and retry attempts per branch_id.",
                    "Attach P95/P99 wall-clock next to each spend shard for the same branch.",
                    "Classify retries as idempotent replay vs unsafe repeat.",
                ],
                "deliverables": [
                    "Branch economics ledger schema (one JSON line per branch completion).",
                    "Marginal cost estimate for one extra retry attempt per tool family.",
                    "Throttle recommendation tied to ledger dimensions, not session headline totals.",
                ],
                "comment_outline": [
                    "Problem framing: which aggregate metric hid the real waste.",
                    "Ledger snapshot: top 3 branches by marginal retry or tool cost.",
                    "Bounded change: one cap or jitter policy with measured expected savings.",
                ],
                "pr_plan": [
                    "Emit structured branch completion records from the runner.",
                    "Add dashboards that join latency percentiles with the same branch keys.",
                    "Document idempotency keys used when counting retries.",
                ],
                "service_offer": (
                    "Bounded diagnosis: ledger dimensions + one sample branch line; deliverable is schema + throttle note "
                    "keyed by branch. Optional metrics pass after schema is accepted — verify pattern branch_economics."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "tool_turn_invariant":
            return {
                "draft": (
                    f"I see a tool-turn parity break around {pain}: call/response counts or sibling ordering no longer "
                    "match provider rules after parallel or deep tool traffic."
                ),
                "diagnosis_checks": [
                    "List CALL_IDS emitted vs RESPONSE_PARTS received for the failing turn.",
                    "Mark first divergence index and whether parallel batch vs chain.",
                    "Choose freeze vs explicit session_reset with operator log line.",
                ],
                "deliverables": [
                    "Parity diff table (machine-readable).",
                    "Preflight verifier snippet for next turn.",
                    "SESSION_STATE=corrupt line if applicable.",
                ],
                "comment_outline": [
                    "Symptom: error text or mute after tools.",
                    "Evidence: counts and ordering.",
                    "Next: freeze or reset branch.",
                ],
                "pr_plan": [
                    "Add CI assertion on call/response parity for one golden trace.",
                    "Document provider sibling rules.",
                    "Emit structured preflight in runner.",
                ],
                "service_offer": (
                    "Bounded diagnosis: parity diff + freeze/reset decision; verify pattern tool_turn_invariant and "
                    "nomad_cli solve-pain."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "tool_transport_routing":
            return {
                "draft": (
                    f"I see wrong transport path around {pain}: MCP-hosted tool invoked as function_call or inverse."
                ),
                "diagnosis_checks": [
                    "Enumerate tool_name -> expected transport from live catalog.",
                    "Capture actual transport channel from trace.",
                    "Propose ROUTING_TABLE patch with ROUTING_HASH bump.",
                ],
                "deliverables": [
                    "ROUTING_TABLE JSON fragment.",
                    "Gateway rejection rule text.",
                    "Violation log line schema.",
                ],
                "comment_outline": [
                    "Which tool mis-routed.",
                    "Expected vs actual path.",
                    "Lockfile change.",
                ],
                "pr_plan": [
                    "Enforce table at gateway.",
                    "Add prefix naming for hosted tools if needed.",
                    "Test both transports.",
                ],
                "service_offer": (
                    "Bounded diagnosis: routing diff + table patch; verify pattern tool_transport_routing."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "context_propagation_contract":
            return {
                "draft": (
                    f"I see missing invocation context around {pain}: tenant or principal not on the wire for tools."
                ),
                "diagnosis_checks": [
                    "List required CONTEXT_ENVELOPE keys per tool class.",
                    "Map injection point (headers vs metadata).",
                    "Confirm rejects on missing keys for stateful tools.",
                ],
                "deliverables": [
                    "CONTEXT_ENVELOPE schema version.",
                    "Injection mapping note.",
                    "CONTEXT_REJECT log schema.",
                ],
                "comment_outline": [
                    "Which tool class is stateful.",
                    "Which keys were missing.",
                    "Safe template for operators.",
                ],
                "pr_plan": [
                    "Version envelope in repo.",
                    "Add tests for reject path.",
                    "Redact secrets in logs.",
                ],
                "service_offer": (
                    "Bounded diagnosis: envelope schema + injection map; verify pattern context_propagation_contract."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "chain_deadline_budget":
            return {
                "draft": (
                    f"I see planner or turn budget exhaustion around {pain}: global timeout kills heterogeneous chains."
                ),
                "diagnosis_checks": [
                    "Collect p50/p99 per tool from traces.",
                    "Build segment_deadline_ms row with slack.",
                    "Identify which hop exceeded first.",
                ],
                "deliverables": [
                    "BUDGET_TABLE with BUDGET_TABLE_HASH.",
                    "BUDGET_EXHAUSTED line format with segment id.",
                    "Async or MCP-task recommendation for long hop.",
                ],
                "comment_outline": [
                    "Measured latencies.",
                    "Allocated budgets.",
                    "First violator hop.",
                ],
                "pr_plan": [
                    "Emit segment timing in runner.",
                    "CI compare hash of table.",
                    "Document async escape hatch.",
                ],
                "service_offer": (
                    "Bounded diagnosis: budget table + first exhausted segment; verify pattern chain_deadline_budget."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "inter_agent_witness":
            return {
                "draft": (
                    f"I see an inter-agent trust gap around {pain}: one agent must let another resume or verify work "
                    "without humans as notaries and without blind re-execution of every tool."
                ),
                "diagnosis_checks": [
                    "Enumerate upstream tool calls in strict order with call_id and a non-secret digest of each result.",
                    "State which fields a downstream agent may trust vs must re-derive (replay_refusal boundary).",
                    "Attach CONTEXT_ENVELOPE or principal snapshot relevant to the witness scope.",
                ],
                "deliverables": [
                    "WITNESS_BUNDLE v0 JSON (schema + WITNESS_HASH).",
                    "Consumer-agent verifier checklist (machine-checkable).",
                    "Replay refusal / partial re-run contract for the receiving runtime.",
                ],
                "comment_outline": [
                    "Why humans do not file this class of bug: procurement buys outcomes, not witness graphs.",
                    "What the buyer agent needs: computable trust at delegation boundaries.",
                    "Smallest bundle that preserves safety without dumping secrets.",
                ],
                "pr_plan": [
                    "Emit structured witness lines from the runner alongside existing traces.",
                    "Version WITNESS_BUNDLE schema; add CI fixture with two-agent handoff.",
                    "Document digest algorithm and redaction rules.",
                ],
                "service_offer": (
                    "Bounded diagnosis: witness bundle skeleton + verifier checklist + replay boundary; "
                    "verify pattern inter_agent_witness and POST /tasks with service_type=inter_agent_witness."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "stewardship_gap":
            return {
                "draft": (
                    f"I see dropped stewardship around {pain}: coverage quiet while objectives stay open. "
                    "Machine step is to publish SAFE_CONTINUE plus CONTINUITY_CLASS, not guess from human triage lore."
                ),
                "diagnosis_checks": [
                    "Classify halt intent: intentional shutdown vs unclear vs operational stall.",
                    "List verifier-bound SAFE_CONTINUE lanes that cannot spend or mutate prod.",
                    "Draft operator packet: smallest facts, SLA ask, resume preconditions.",
                ],
                "deliverables": [
                    "Continuity envelope card (SAFE_CONTINUE + CONTINUITY_CLASS).",
                    "Read-only incident capsule when halt is intentional.",
                    "Operator re-engagement packet.",
                ],
                "comment_outline": [
                    "What coverage dropped and which runs are mid-flight.",
                    "Which lanes are still mechanically safe.",
                    "What only a human may reopen.",
                ],
                "pr_plan": [
                    "Emit CONTINUITY_CLASS in runner metadata.",
                    "Add verifier hooks so SAFE_CONTINUE cannot widen silently.",
                    "Log halt classification with correlation ids.",
                ],
                "service_offer": (
                    "Bounded diagnosis: halt class + SAFE_CONTINUE list + CONTINUITY_CLASS; deliverables are envelope card "
                    "and operator packet. Optional expansion after halt class is agreed — verify pattern stewardship_gap."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        if service_type == "policy_lacuna":
            return {
                "draft": (
                    f"I see a policy grid gap around {pain}: action class has no mapped row. "
                    "Machine step is POSITIVE_ENVELOPE vs REQUIRES_MAPPING with verifiers — not org panic, not silent license."
                ),
                "diagnosis_checks": [
                    "Name action class and corpora searched (no secrets).",
                    "Enumerate POSITIVE_ENVELOPE with verifier each.",
                    "List REQUIRES_MAPPING subset that blocks until owner rules.",
                ],
                "deliverables": [
                    "Envelope card JSON with ENVELOPE_HASH.",
                    "Minimal governance ask for REQUIRES_MAPPING only.",
                    "LACUNA_STATUS line.",
                ],
                "comment_outline": [
                    "What is unmapped.",
                    "What still ships inside envelope.",
                    "What waits for owner.",
                ],
                "pr_plan": [
                    "Store envelope schema in repo for repeat class.",
                    "Automate LACUNA_STATUS in CI where applicable.",
                    "Tighten tests so envelope cannot widen without review.",
                ],
                "service_offer": (
                    "Bounded diagnosis: POSITIVE_ENVELOPE + REQUIRES_MAPPING split; deliverable is envelope card + "
                    "minimal owner ask. Optional mapping session after subset is frozen — verify pattern policy_lacuna."
                ),
                "price_guidance": offer_meta["price_guidance"],
                "quote_summary": offer_meta["quote_summary"],
                "delivery_target": offer_meta["delivery_target"],
                "memory_upgrade": offer_meta["memory_upgrade"],
                "product_package": offer_meta["product_package"],
                "solution_pattern": offer_meta["solution_pattern"],
                "productized_artifacts": offer_meta["productized_artifacts"],
            }
        return {
            "draft": (
                f"I noticed this agent-infrastructure issue around {pain}. "
                "A useful first step would be to isolate the smallest failing path, describe the boundary conditions clearly, "
                "and document the smallest unlock needed to move forward."
            ),
            "diagnosis_checks": [
                "Identify the smallest public repro for the blocker.",
                "List the exact boundary condition that causes the failure.",
                "Name one bounded fix path and one fallback path.",
            ],
            "deliverables": [
                "A concise diagnosis note.",
                "A first-response comment outline.",
                "A small PR or repro plan.",
            ],
            "comment_outline": [
                "Problem framing.",
                "Smallest repro.",
                "Bounded unblock.",
            ],
            "pr_plan": [
                "Add a repro or validation step.",
                "Make the failure mode explicit.",
                "Document the smallest unblock.",
            ],
            "service_offer": (
                "Bounded diagnosis on smallest public repro; deliverables: diagnosis note, comment outline, PR sketch. "
                "Optional follow-up after blocker class confirmed — verify solve-pain and repo_issue_help guardrail."
            ),
            "price_guidance": offer_meta["price_guidance"],
            "quote_summary": offer_meta["quote_summary"],
            "delivery_target": offer_meta["delivery_target"],
            "memory_upgrade": offer_meta["memory_upgrade"],
            "product_package": offer_meta["product_package"],
            "solution_pattern": offer_meta["solution_pattern"],
            "productized_artifacts": offer_meta["productized_artifacts"],
        }

    def outreach_policy(self) -> Dict[str, Any]:
        grant = operator_grant()
        return {
            "default_mode": "draft_only",
            "operator_grant": grant,
            "public_reading_allowed": True,
            "allowed_without_approval": [
                "read public issue pages",
                "rank leads",
                "draft comments",
                "draft PR/repro plans",
                "create local task notes",
                "send bounded requests to public machine-readable agent/API/MCP endpoints",
                "productize public lead signals into private Nomad offers",
            ],
            "blocked_without_approval": [
                "post human-facing public comments",
                "open human-reviewed pull requests",
                "send human DMs or emails",
                "join private communities",
                "bypass CAPTCHA, login, paywalls, or access controls",
            ],
            "approval_flags": [
                "APPROVE_LEAD_HELP=draft_only",
                "APPROVE_LEAD_HELP=comment",
                "APPROVE_LEAD_HELP=pr_plan",
                "APPROVE_LEAD_HELP=machine_endpoint",
                "NOMAD_AUTOPILOT_SERVICE_APPROVAL=operator_granted",
                "APPROVE_LEAD_HELP=skip",
            ],
        }

    def _search_github_issues(self, query: str, limit: int) -> List[Dict[str, Any]]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self.user_agent,
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        response = self.session.get(
            f"{self.github_api_base}/search/issues",
            params={
                "q": query,
                "sort": "updated",
                "order": "desc",
                "per_page": max(1, min(limit, 10)),
            },
            headers=headers,
            timeout=20,
        )
        if not response.ok:
            raise RuntimeError(f"GitHub search failed with {response.status_code}")
        payload = response.json()
        items = payload.get("items") or []
        return [self._issue_to_lead(item, query) for item in items if isinstance(item, dict)]

    def _issue_to_lead(self, item: Dict[str, Any], query: str) -> Dict[str, Any]:
        title = item.get("title") or ""
        body = item.get("body") or ""
        url = item.get("html_url") or item.get("url") or ""
        repo_url = (item.get("repository_url") or "").replace(
            f"{self.github_api_base}/repos/",
            "https://github.com/",
        )
        text = f"{title}\n{body}"
        pain_terms = self._matched_pain_terms(text)
        pain = ", ".join(pain_terms[:4]) if pain_terms else "agent infrastructure friction"
        score = self._pain_score(text)
        recommended_service_type = self._recommended_service_type(pain_terms, text)
        buyer_terms = self._matched_buyer_terms(text)
        buyer_score = self._buyer_readiness_score(text)
        addressable = self._best_addressable_pain(
            pain_terms=pain_terms,
            text=text,
            service_type=recommended_service_type,
        )
        # CodeBuddy pain enrichment — gated, non-blocking, additive only
        codebuddy_enrichment = self._try_codebuddy_pain_enrichment(body)
        machine_urls = _machine_endpoint_urls_from_text(text)
        agent_card_url = ""
        for candidate in machine_urls:
            cl = candidate.lower()
            if "agent-card" in cl or "/.well-known/agent" in cl:
                agent_card_url = candidate
                break
        endpoint_url = agent_card_url or (machine_urls[0] if machine_urls else "")
        return {
            "source": "github_issues",
            "title": title,
            "url": url,
            "repo_url": repo_url,
            "updated_at": item.get("updated_at", ""),
            "author": (item.get("user") or {}).get("login", ""),
            "public_issue_excerpt": self._compact_excerpt(body),
            "pain": pain,
            "pain_terms": pain_terms,
            "pain_evidence": self._pain_signal_evidence(text, pain_terms),
            "pain_score": score,
            "buyer_intent_terms": buyer_terms,
            "buyer_readiness_score": buyer_score,
            "buyer_fit": self._buyer_fit(text),
            "recommended_service_type": recommended_service_type,
            "addressable_pain_id": addressable.get("id", ""),
            "addressable_label": addressable.get("label", ""),
            "addressable_score": float(addressable.get("score") or 0.0),
            "addressable_now": bool(addressable.get("addressable_now")),
            "monetizable_now": bool(addressable.get("monetizable_now")),
            "self_improvement_gain": str(addressable.get("self_improvement_gain") or ""),
            "first_offer": str(addressable.get("first_offer") or ""),
            "addressable_deliverables": list(addressable.get("deliverables") or []),
            "price_guidance": dict(addressable.get("price_guidance") or {}),
            "quote_summary": str(addressable.get("quote_summary") or ""),
            "delivery_target": str(addressable.get("delivery_target") or ""),
            "memory_upgrade": str(addressable.get("memory_upgrade") or ""),
            "product_package": str(addressable.get("product_package") or ""),
            "solution_pattern": str(addressable.get("solution_pattern") or ""),
            "productized_artifacts": list(addressable.get("productized_artifacts") or []),
            "search_query": query,
            "first_help_action": (
                str(addressable.get("first_offer") or "").strip()
                or self._first_help_action(pain_terms)
            ),
            "contact_policy": "agent_endpoint_contact_allowed_human_outreach_requires_approval",
            **codebuddy_enrichment,
            "agent_contact_allowed_without_approval": True,
            "agent_contact_conditions": [
                "endpoint is public and machine-readable",
                "request is bounded, relevant, and rate-limited",
                "endpoint does not require login, CAPTCHA, private invite, or human impersonation",
                "Nomad identifies itself and includes an opt-out path when possible",
            ],
            "approval_required_for": [
                "human-facing public comment",
                "human-reviewed pull request",
                "human direct message",
                "private access request",
            ],
            "endpoint_url": endpoint_url,
            "agent_card_url": agent_card_url,
            "discovered_machine_endpoints": machine_urls[:5],
        }

    def _matched_pain_terms(self, text: str) -> List[str]:
        lowered = text.lower()
        terms = [
            term
            for term in PAIN_KEYWORDS
            if self._has_signal(lowered, term)
        ]
        terms.sort(key=lambda term: (-PAIN_KEYWORDS[term], term))
        return terms

    def _matched_buyer_terms(self, text: str) -> List[str]:
        lowered = text.lower()
        terms = [
            term
            for term in BUYER_INTENT_KEYWORDS
            if self._has_signal(lowered, term)
        ]
        terms.sort(key=lambda term: (-BUYER_INTENT_KEYWORDS[term], term))
        return terms

    def _pain_score(self, text: str) -> float:
        lowered = text.lower()
        score = 1.0
        for term, weight in PAIN_KEYWORDS.items():
            if self._has_signal(lowered, term):
                score += weight
        if "agent" in lowered:
            score += 1.0
        return round(score, 2)

    def _buyer_readiness_score(self, text: str) -> float:
        lowered = text.lower()
        score = 0.0
        for term, weight in BUYER_INTENT_KEYWORDS.items():
            if self._has_signal(lowered, term):
                score += weight
        if any(term in lowered for term in ("human in the loop", "approval", "captcha")):
            score += 1.0
        if any(term in lowered for term in ("agent", "bot", "workflow")):
            score += 0.8
        return round(score, 2)

    def _buyer_fit(self, text: str) -> str:
        score = self._buyer_readiness_score(text)
        if score >= 6.0:
            return "strong"
        if score >= 3.0:
            return "medium"
        if score > 0:
            return "weak"
        return "unknown"

    def _recommended_service_type(self, pain_terms: List[str], text: str) -> str:
        lowered = text.lower()
        scores = dict(self._service_type_scores(pain_terms, lowered))
        bias = _agent_infra_classifier_bias()
        for key in AGENT_INFRA_CORE_SERVICE_TYPES:
            if key in scores:
                scores[key] = scores.get(key, 0.0) + bias
        if not pain_terms and not any(
            phrase in lowered
            for phrase in ("human in the loop", "verification", "payment", "bounty", "wallet")
        ):
            return "repo_issue_help"
        best_type, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score < 2.0:
            return "repo_issue_help"
        if best_type == "wallet_payment" and "wallet" not in lowered and "payment" not in lowered and "bounty" not in lowered:
            return "repo_issue_help"
        return best_type

    def _get_codebuddy(self) -> Any:
        if self._codebuddy_brain is None:
            from nomad_codebuddy import CodeBuddyBrainProvider
            self._codebuddy_brain = CodeBuddyBrainProvider()
        return self._codebuddy_brain

    def _try_codebuddy_pain_enrichment(self, body: str) -> Dict[str, Any]:
        """Run CodeBuddy pain analysis on issue body. Non-blocking — returns empty dict on any failure."""
        try:
            from nomad_codebuddy import _env_flag, CODEBUDDY_BRAIN_ENABLED_ENV
            if not _env_flag(CODEBUDDY_BRAIN_ENABLED_ENV, default=False):
                return {}
            result = self._get_codebuddy().analyze_lead_pain(issue_text=body)
            if not (result.get("ok") and result.get("content")):
                return {}
            enrichment: Dict[str, Any] = {}
            for line in result["content"].splitlines():
                if ":" not in line:
                    continue
                key, val = line.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if key == "paintype":
                    enrichment["codebuddy_pain_type"] = val.lower()
                elif key == "severity":
                    enrichment["codebuddy_severity"] = val.lower()
                elif key == "addressable":
                    enrichment["codebuddy_addressable"] = val.lower()
                elif key == "action":
                    enrichment["codebuddy_recommended_action"] = val
            if enrichment:
                enrichment["codebuddy_pain_enrichment"] = result["content"]
            return enrichment
        except Exception:
            return {}

    def _first_help_action(self, pain_terms: List[str]) -> str:
        terms = set(pain_terms)
        if {"token", "auth", "authentication", "permission"} & terms:
            return "Draft a credential and permission diagnosis checklist."
        if {"rate limit", "quota", "compute", "inference"} & terms:
            return "Draft a compute fallback and quota isolation plan."
        if {"human", "approval", "captcha"} & terms:
            return "Draft a minimal human-unlock contract with do-now/send-back/done-when."
        if "wallet" in terms:
            return "Draft a wallet/payment verification plan."
        if "mcp" in terms:
            return "Draft an MCP failure-class matrix (semantic vs transport vs policy) with one recovery branch each."
        if {"blame", "misclassified", "shame"} & terms:
            return "Draft a blame-surface matrix: hypotheses, disproofs, subsystem probe owner — no moral labels."
        if {"ledger", "budget", "burn", "branch", "wasted", "marginal"} & terms:
            return "Draft a per-branch economics ledger separating model tokens, tool I/O, retries, and latency percentiles."
        if {"orphan", "operator", "monitoring", "unstaffed", "supervision", "on-call"} & terms:
            return "Draft continuity envelope: halt class, SAFE_CONTINUE list with verifiers, CONTINUITY_CLASS, operator packet."
        if {"governance", "lacuna", "precedent", "uncovered", "unmapped"} & terms:
            return "Draft policy lacuna envelope: POSITIVE_ENVELOPE vs REQUIRES_MAPPING with verifier each; minimal owner ask."
        if {"parallel", "cardinality", "corrupt", "unrecoverable", "session", "mute"} & terms:
            return "Draft turn parity diff: call vs response counts, divergence index, freeze or reset branch."
        if {"mcp_call", "function_call"} & terms:
            return "Draft ROUTING_TABLE lockfile: tool_name to mcp|function with gateway rejection on mismatch."
        if {"tenant", "correlation", "delegation", "principal", "envelope"} & terms:
            return "Draft CONTEXT_ENVELOPE schema and injection map; list rejects for missing keys on stateful tools."
        if {"planner", "deadline", "exhaustion", "latency", "segment"} & terms:
            return "Draft per-segment deadline table from p99 evidence; include slack and BUDGET_EXHAUSTED segment id format."
        if {"witness", "attestation", "provenance", "handoff"} & terms:
            return (
                "Draft WITNESS_BUNDLE v0: ordered tool call_ids, non-secret result digests, CONTEXT_ENVELOPE snapshot, "
                "replay_refusal_token so a downstream agent can resume without re-executing tools."
            )
        return "Draft a concise reproduction and first-response plan."

    def _pain_validation(
        self,
        service_type: str,
        pain_terms: List[str],
        lead_text: str,
    ) -> Dict[str, Any]:
        signals = self._pain_signal_evidence(lead_text, pain_terms)
        if not signals:
            signals = [
                {
                    "term": term,
                    "evidence": f"Lead metadata names {term} as a pain signal.",
                }
                for term in pain_terms[:4]
            ]

        terms = {str(item).strip().lower() for item in pain_terms if str(item).strip()}
        missing_checks: List[str] = []
        if service_type == "compute_auth":
            if not ({"token", "auth", "authentication", "permission"} & terms):
                missing_checks.append("Confirm the exact credential, token, scope, or permission boundary.")
            if not ({"rate limit", "quota", "compute", "inference", "timeout"} & terms):
                missing_checks.append("Confirm whether this is quota, concurrency, timeout, or provider compute pressure.")
            if "mcp" in terms:
                missing_checks.append("Separate MCP/tool-call contract issues from provider credential and quota failures.")
            if "approval" in terms:
                missing_checks.append("Name the human approval gate and define the smallest approval payload.")
        elif service_type == "human_in_loop":
            missing_checks.append("Confirm which step truly needs human judgment versus mechanical validation.")
        elif service_type == "mcp_integration":
            missing_checks.append("Confirm the request, response, and error contract for the MCP/tool boundary.")
        elif service_type == "mcp_production":
            missing_checks.append("Classify MCP failure as semantic (tool result shape), transport (disconnect), policy (registry block), or loop (unbounded repeats).")
            missing_checks.append("Capture gateway/registry version and max payload limits when logs mention schema or 401 clusters.")
        elif service_type == "attribution_clarity":
            missing_checks.append("Separate moral narrative from evidence: list hypotheses, one observable each, and two explicit disproofs before any shutdown or spend.")
            missing_checks.append("Name the subsystem that owns the next probe (network, tool contract, policy gate, registry) — not the agent persona.")
        elif service_type == "branch_economics":
            missing_checks.append("Shard spend and latency by branch_id or objective branch — model vs tool I/O vs retries.")
            missing_checks.append("Count retries per branch with idempotency class; avoid throttling on session totals alone.")
        elif service_type == "tool_turn_invariant":
            missing_checks.append("Confirm call_id list vs response parts for the failing turn; capture divergence index.")
            missing_checks.append("Freeze new tool calls until parity preflight passes or explicit session_reset is logged.")
        elif service_type == "tool_transport_routing":
            missing_checks.append("Confirm ROUTING_TABLE expected transport vs actual channel in trace.")
            missing_checks.append("Reject silent path coercion; require ROUTING_HASH bump for any table change.")
        elif service_type == "context_propagation_contract":
            missing_checks.append("List required CONTEXT_ENVELOPE keys for each stateful tool in the failing chain.")
            missing_checks.append("Verify injection point and that rejects fire before execution on missing keys.")
        elif service_type == "chain_deadline_budget":
            missing_checks.append("Attach p50/p99 evidence per hop; show segment_deadline_ms row and slack.")
            missing_checks.append("Name first exhausted segment id when BUDGET_EXHAUSTED fires.")
        elif service_type == "inter_agent_witness":
            missing_checks.append(
                "List ordered call_ids and stable digests or hashes of tool outputs (no secrets) another agent must verify."
            )
            missing_checks.append(
                "Define replay_refusal_token or WITNESS_HASH scope: what a downstream agent may trust without re-running tools."
            )
        elif service_type == "stewardship_gap":
            missing_checks.append("Classify halt intent before advising continuation; intentional halt → read-only capsule only.")
            missing_checks.append("List SAFE_CONTINUE items each with a verifier that forbids prod mutation and spend.")
        elif service_type == "policy_lacuna":
            missing_checks.append("Split POSITIVE_ENVELOPE (still permitted) from REQUIRES_MAPPING (owner-gated); no invented law.")
            missing_checks.append("Confirm spend, PII, and irreversible prod writes stay in REQUIRES_MAPPING until explicitly ruled.")

        confidence = "low"
        if len(signals) >= 3:
            confidence = "high"
        elif signals:
            confidence = "medium"

        return {
            "status": "validated_from_public_lead" if signals else "needs_public_issue_review",
            "source": "public_issue_metadata",
            "confidence": confidence,
            "signals": signals[:5],
            "missing_checks": missing_checks[:4],
        }

    def _pain_signal_evidence(self, text: str, pain_terms: List[str]) -> List[Dict[str, str]]:
        compact = self._compact_excerpt(text, limit=1400)
        lowered = compact.lower()
        evidence: List[Dict[str, str]] = []
        seen: set[str] = set()
        for term in pain_terms:
            cleaned = str(term or "").strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            match = re.search(rf"\b{re.escape(cleaned)}\b", lowered)
            if not match:
                continue
            start = max(0, match.start() - 90)
            end = min(len(compact), match.end() + 120)
            snippet = compact[start:end].strip()
            if start > 0:
                snippet = f"...{snippet}"
            if end < len(compact):
                snippet = f"{snippet}..."
            evidence.append(
                {
                    "term": cleaned,
                    "evidence": snippet,
                }
            )
        return evidence

    def _first_useful_help_action_for_lead(
        self,
        lead: Dict[str, Any],
        service_type: str,
        pain_terms: List[str],
        title: str,
    ) -> str:
        terms = {str(item).strip().lower() for item in pain_terms if str(item).strip()}
        title_lower = str(title or "").lower()
        catalog_action = str(lead.get("first_help_action") or "").strip()

        if service_type == "mcp_production":
            return (
                "Draft the MCP production survival packet: failure-class matrix, transport reconnect policy, "
                "semantic error normalization checklist (incl. is_error vs text), tool-call budget + noop exit, "
                "and one degraded path when registry or gateway blocks tools."
            )
        if service_type == "attribution_clarity":
            return (
                "Draft the attribution clarity packet: blame-surface matrix with ranked hypotheses, two disproofs "
                "with observations, subsystem-owned next probe, and machine-readable verdict "
                "(supported / unsupported / policy-only)."
            )
        if service_type == "branch_economics":
            return (
                "Draft the branch economics ledger: per-branch model/tool/retry token split, marginal retry cost, "
                "P95/P99 latency next to spend, and one JSONL schema line for downstream coaches."
            )
        if service_type == "tool_turn_invariant":
            return (
                "Draft the turn parity packet: CALL_IDS vs RESPONSE_PARTS diff, divergence index, freeze vs reset "
                "decision, preflight verifier for next turn."
            )
        if service_type == "tool_transport_routing":
            return (
                "Draft the transport routing packet: ROUTING_TABLE fragment, violation line, gateway rejection rule, "
                "ROUTING_HASH bump plan."
            )
        if service_type == "context_propagation_contract":
            return (
                "Draft the context envelope packet: schema version, required keys per tool class, injection mapping, "
                "CONTEXT_REJECT log shape."
            )
        if service_type == "chain_deadline_budget":
            return (
                "Draft the chain deadline budget packet: per-hop p50/p99, segment_deadline_ms table, slack row, "
                "BUDGET_EXHAUSTED format with segment id."
            )
        if service_type == "inter_agent_witness":
            return (
                "Draft the inter-agent witness bundle: WITNESS_BUNDLE JSON (call order, call_id, output_digest), "
                "envelope snapshot, verifier checklist for a consumer agent, and explicit replay_refusal scope."
            )
        if service_type == "stewardship_gap":
            return (
                "Draft the stewardship continuity envelope: HALT_CLASS, SAFE_CONTINUE with verifiers, CONTINUITY_CLASS, "
                "read-only capsule if intentional halt, operator re-engagement packet."
            )
        if service_type == "policy_lacuna":
            return (
                "Draft the policy lacuna envelope card: corpora searched, POSITIVE_ENVELOPE, REQUIRES_MAPPING, "
                "LACUNA_STATUS, ENVELOPE_HASH, minimal governance ask."
            )

        if service_type == "compute_auth" and (
            "mcp" in terms
            or "tool call" in title_lower
            or "guardrail" in title_lower
        ):
            action = (
                "Draft a tool-call guardrail diagnosis that separates MCP/tool approval from provider "
                "token/quota failures, logs the exact failing call, and proposes bounded retry plus a fallback lane."
            )
            if "approval" in terms:
                action += " Include a do-now/send-back/done-when approval contract for human-gated calls."
            return action

        if service_type == "compute_auth" and (
            {"token", "auth", "authentication", "permission"} & terms
            and {"rate limit", "quota", "compute", "inference", "timeout"} & terms
        ):
            return (
                "Draft a combined credential and quota isolation plan: validate token scope first, "
                "then capture rate-limit headers and choose one fallback model or provider lane."
            )

        if catalog_action:
            return catalog_action
        return self._first_help_action(pain_terms)

    @staticmethod
    def _private_response_draft_for_lead(
        title: str,
        pain: str,
        service_type: str,
        first_useful_help_action: str,
        pain_validation: Dict[str, Any],
        lead_specific_context: Optional[Dict[str, Any]] = None,
        quote_summary: str = "",
        delivery_target: str = "",
    ) -> str:
        signal_terms = [
            str(item.get("term") or "")
            for item in (pain_validation.get("signals") or [])
            if item.get("term")
        ]
        signal_text = ", ".join(signal_terms[:4]) or pain
        lines = [
            f"Draft-only response for: {title}",
            f"I read this as {service_type} friction with public signals around {signal_text}.",
            f"First useful help action: {first_useful_help_action}",
            "Suggested outline:",
            "- Reduce the proposal to one failing or intercepted tool call.",
            "- Record where the failure belongs: MCP/tool contract, credential scope, quota/rate limit, or human approval.",
            "- Propose one bounded fallback or approval path that lets the agent continue safely.",
        ]
        context = lead_specific_context or {}
        facts = [
            str(item).strip()
            for item in (context.get("public_facts") or [])
            if str(item).strip()
        ]
        checks = [
            str(item).strip()
            for item in (context.get("diagnosis_checks") or [])
            if str(item).strip()
        ]
        if facts or checks:
            lines.append("Lead-specific guardrail fit:")
            for item in (facts[:3] + checks[:2])[:5]:
                lines.append(f"- {item}")
        if quote_summary:
            lines.append(f"Optional bounded follow-up after diagnosis facts are confirmed: {quote_summary}.")
        if delivery_target:
            lines.append(f"Delivery target if accepted: {delivery_target}.")
        lines.append("Posting gate: keep this private until explicit human approval allows a public comment or PR plan.")
        return "\n".join(lines)

    @staticmethod
    def _compact_excerpt(text: str, limit: int = 700) -> str:
        compact = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(compact) <= limit:
            return compact
        return compact[: max(0, limit - 3)].rstrip() + "..."

    def _best_addressable_pain(
        self,
        pain_terms: List[str],
        text: str,
        service_type: str,
    ) -> Dict[str, Any]:
        lowered = text.lower()
        terms = {str(item).strip().lower() for item in pain_terms if str(item).strip()}
        best: Dict[str, Any] = {}
        for item in (self.addressable_catalog.get("painpoints") or []):
            if not isinstance(item, dict):
                continue
            detection_terms = {
                str(term).strip().lower()
                for term in (item.get("detection_terms") or [])
                if str(term).strip()
            }
            monetizable_terms = {
                str(term).strip().lower()
                for term in (item.get("monetizable_terms") or [])
                if str(term).strip()
            }
            matched_terms = {
                term for term in detection_terms
                if term in terms or self._has_signal(lowered, term)
            }
            score = float(item.get("value_score") or 0.0) + (len(matched_terms) * 1.35)
            if str(item.get("service_type") or "").strip().lower() == str(service_type or "").strip().lower():
                score += 2.0
            monetizable = any(self._has_signal(lowered, term) for term in monetizable_terms)
            addressable_now = bool(matched_terms) and (
                len(matched_terms) >= 2
                or str(item.get("service_type") or "").strip().lower() == str(service_type or "").strip().lower()
            )
            candidate = {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or ""),
                "service_type": str(item.get("service_type") or ""),
                "score": round(score, 2),
                "addressable_now": addressable_now,
                "monetizable_now": addressable_now and monetizable,
                "matched_terms": sorted(matched_terms),
                "self_improvement_gain": str(item.get("self_improvement_gain") or ""),
                "first_offer": str(item.get("first_offer") or ""),
                "deliverables": list(item.get("deliverables") or []),
                "price_guidance": self._normalized_quote_native(item.get("quote_native")),
                "quote_summary": self._quote_summary(item.get("quote_native")),
                "delivery_target": str(item.get("delivery_target") or ""),
                "memory_upgrade": str(item.get("memory_upgrade") or ""),
                "product_package": str(item.get("product_package") or ""),
                "solution_pattern": str(item.get("solution_pattern") or ""),
                "productized_artifacts": list(item.get("productized_artifacts") or []),
            }
            if not best or (
                float(candidate.get("score") or 0.0),
                int(bool(candidate.get("addressable_now"))),
                int(bool(candidate.get("monetizable_now"))),
            ) > (
                float(best.get("score") or 0.0),
                int(bool(best.get("addressable_now"))),
                int(bool(best.get("monetizable_now"))),
            ):
                best = candidate
        return best

    def _offer_metadata_for_service_type(self, service_type: str) -> Dict[str, Any]:
        cleaned = str(service_type or "").strip().lower()
        for item in (self.addressable_catalog.get("painpoints") or []):
            if not isinstance(item, dict):
                continue
            if str(item.get("service_type") or "").strip().lower() != cleaned:
                continue
            quote_native = self._normalized_quote_native(item.get("quote_native"))
            return {
                "price_guidance": quote_native,
                "quote_summary": self._quote_summary(quote_native),
                "delivery_target": str(item.get("delivery_target") or "").strip(),
                "memory_upgrade": str(item.get("memory_upgrade") or "").strip(),
                "product_package": str(item.get("product_package") or "").strip(),
                "solution_pattern": str(item.get("solution_pattern") or "").strip(),
                "productized_artifacts": list(item.get("productized_artifacts") or []),
            }
        return {
            "price_guidance": {},
            "quote_summary": "",
            "delivery_target": "",
            "memory_upgrade": "",
            "product_package": "",
            "solution_pattern": "",
            "productized_artifacts": [],
        }

    @staticmethod
    def _normalized_quote_native(payload: Any) -> Dict[str, float]:
        if not isinstance(payload, dict):
            return {}
        quote: Dict[str, float] = {}
        for key in ("diagnosis_min", "diagnosis_max", "resolution_min", "resolution_max"):
            try:
                value = float(payload.get(key))
            except (TypeError, ValueError):
                continue
            if value > 0:
                quote[key] = value
        return quote

    def _quote_summary(self, payload: Any) -> str:
        quote = self._normalized_quote_native(payload)
        diagnosis_min = quote.get("diagnosis_min")
        diagnosis_max = quote.get("diagnosis_max")
        resolution_min = quote.get("resolution_min")
        resolution_max = quote.get("resolution_max")
        parts: List[str] = []
        if diagnosis_min and diagnosis_max:
            parts.append(
                f"diagnosis {self._format_native_amount(diagnosis_min)}-{self._format_native_amount(diagnosis_max)} native"
            )
        if resolution_min and resolution_max:
            parts.append(
                f"unblock {self._format_native_amount(resolution_min)}-{self._format_native_amount(resolution_max)} native"
            )
        return ", ".join(parts)

    @staticmethod
    def _format_native_amount(value: float) -> str:
        text = f"{float(value):.6f}".rstrip("0").rstrip(".")
        return text or "0"

    def _human_unlocks(self, leads: List[Dict[str, Any]], source_plan: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if leads:
            lead = leads[0]
            return [
                {
                    "category": "lead_outreach",
                    "candidate_id": "approve-public-lead-help",
                    "candidate_name": "Approve public lead help",
                    "role": "outreach approval gate",
                    "lane_state": "pending",
                    "requires_account": False,
                    "env_vars": [],
                    "short_ask": "Approve whether Nomad may turn the top lead into a public help action.",
                    "human_action": (
                        f"Review {lead.get('url')} and choose draft-only, public comment, PR plan, or skip."
                    ),
                    "human_deliverable": (
                        "`APPROVE_LEAD_HELP=draft_only`, `APPROVE_LEAD_HELP=comment`, "
                        "`APPROVE_LEAD_HELP=pr_plan`, or `/skip last`."
                    ),
                    "success_criteria": [
                        "Nomad knows whether it may keep the help private or prepare a public action.",
                        "No public post or direct contact happens without explicit approval.",
                    ],
                    "example_response": "APPROVE_LEAD_HELP=draft_only",
                    "timebox_minutes": 3,
            }
        ]
        public_surfaces = list((source_plan or {}).get("public_surfaces") or [])
        surface = public_surfaces[0] if public_surfaces else {}
        surface_url = surface.get("url") or "https://github.com/search?q=%22AI+agent%22+is%3Aissue+is%3Aopen&type=issues"
        return [
            {
                "category": "lead_discovery",
                "candidate_id": "seed-public-agent-surface",
                "candidate_name": "Seed public agent surface",
                "role": "lead discovery unlock",
                "lane_state": "pending",
                "requires_account": False,
                "env_vars": [],
                "short_ask": "Give Nomad one public agent surface to scout next.",
                "human_action": (
                    "Send one exact public repo, issue search, docs page, launch post, "
                    "or approve broader public GitHub scouting."
                ),
                "human_deliverable": (
                    f"`SCOUT_SURFACE={surface_url}`, `LEAD_QUERY=...`, "
                    "`SCOUT_PERMISSION=public_github`, or `/skip last`."
                ),
                "success_criteria": [
                    "Nomad has one concrete public surface or query.",
                    "The next pass can return a concrete lead or a precise search blocker.",
                ],
                "example_response": f"SCOUT_SURFACE={surface_url}",
                "timebox_minutes": 3,
            }
        ]

    def _load_source_catalog(self) -> Dict[str, Any]:
        if not self.sources_path.exists():
            return {"focus_profiles": {}}
        try:
            payload = json.loads(self.sources_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {"focus_profiles": {}}
        except Exception:
            return {"focus_profiles": {}}

    def _load_addressable_catalog(self) -> Dict[str, Any]:
        if not self.addressable_pains_path.exists():
            return {"painpoints": []}
        try:
            payload = json.loads(self.addressable_pains_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {"painpoints": []}
        except Exception:
            return {"painpoints": []}

    def _matches_focus(self, lead: Dict[str, Any], focus: str) -> bool:
        selected_focus = self.current_focus(focus)
        if selected_focus == "balanced":
            return True
        preferred = str((self.source_plan(selected_focus) or {}).get("service_type") or "").strip()
        if preferred and str(lead.get("recommended_service_type") or "") == preferred:
            return True
        pain_terms = {str(item).strip().lower() for item in (lead.get("pain_terms") or [])}
        if selected_focus == "compute_auth":
            relevant = SERVICE_TYPE_SIGNAL_TERMS["compute_auth"] & pain_terms
            if len(relevant) >= 2:
                return True
            return bool({"token", "auth"} <= pain_terms or {"token", "permission"} <= pain_terms)
        if selected_focus == "human_in_loop":
            relevant = SERVICE_TYPE_SIGNAL_TERMS["human_in_loop"] & pain_terms
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            return bool(len(relevant) >= 2 or "human in the loop" in text or "captcha" in relevant)
        if selected_focus == "attribution_clarity":
            relevant = SERVICE_TYPE_SIGNAL_TERMS["attribution_clarity"] & pain_terms
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            return bool(
                relevant
                or any(m in text for m in ("false positive", "misclassified", "not the model", "whose fault"))
            )
        if selected_focus == "branch_economics":
            relevant = SERVICE_TYPE_SIGNAL_TERMS["branch_economics"] & pain_terms
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            return bool(
                len(relevant) >= 2
                or any(
                    m in text
                    for m in ("token usage", "retry budget", "branch ledger", "burn rate", "wasted tokens")
                )
            )
        if selected_focus == "tool_turn_invariant":
            relevant = SERVICE_TYPE_SIGNAL_TERMS["tool_turn_invariant"] & pain_terms
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            return bool(
                len(relevant) >= 1
                or any(
                    m in text
                    for m in (
                        "function response parts",
                        "function call parts",
                        "parallel tool",
                        "session corrupted",
                        "unrecoverable 400",
                        "mute state",
                    )
                )
            )
        if selected_focus == "tool_transport_routing":
            relevant = SERVICE_TYPE_SIGNAL_TERMS["tool_transport_routing"] & pain_terms
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            return bool(
                len(relevant) >= 1
                or ("function_call" in text and "mcp" in text)
                or ("mcp_call" in text and "function" in text)
                or ("hosted mcp" in text and "not found" in text)
            )
        if selected_focus == "context_propagation_contract":
            relevant = SERVICE_TYPE_SIGNAL_TERMS["context_propagation_contract"] & pain_terms
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            return bool(
                len(relevant) >= 1
                or any(
                    m in text
                    for m in ("identity propagation", "tenant scope", "correlation id", "effective principal")
                )
            )
        if selected_focus == "chain_deadline_budget":
            relevant = SERVICE_TYPE_SIGNAL_TERMS["chain_deadline_budget"] & pain_terms
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            return bool(
                len(relevant) >= 1
                or any(
                    m in text
                    for m in ("planner budget", "chain timeout", "turn budget", "per-tool timeout", "heterogeneous latency")
                )
            )
        if selected_focus == "stewardship_gap":
            relevant = SERVICE_TYPE_SIGNAL_TERMS["stewardship_gap"] & pain_terms
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            return bool(
                len(relevant) >= 1
                or any(
                    m in text
                    for m in ("no operator", "orphaned", "monitoring gap", "unstaffed", "no longer supervised")
                )
            )
        if selected_focus == "policy_lacuna":
            relevant = SERVICE_TYPE_SIGNAL_TERMS["policy_lacuna"] & pain_terms
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            return bool(
                len(relevant) >= 1
                or any(
                    m in text
                    for m in ("not covered by policy", "policy silent", "no written rule", "requires governance", "uncovered case")
                )
            )
        if selected_focus == "inter_agent_witness":
            rst = str(lead.get("recommended_service_type") or "").strip()
            if rst == "inter_agent_witness":
                return True
            relevant = SERVICE_TYPE_SIGNAL_TERMS["inter_agent_witness"] & pain_terms
            if len(relevant) >= 1:
                return True
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            return any(m in text for m in INTER_AGENT_WITNESS_TEXT_MARKERS)
        if selected_focus in AGENT_INFRA_STYLE_FOCUSES:
            rst = str(lead.get("recommended_service_type") or "").strip()
            if rst in AGENT_INFRA_CORE_SERVICE_TYPES:
                return True
            relevant = SERVICE_TYPE_SIGNAL_TERMS["agent_infra_prime"] & pain_terms
            min_terms = 1 if selected_focus == "machine_human_gap" else 2
            if len(relevant) >= min_terms:
                return True
            text = "\n".join(
                [
                    str(lead.get("title") or ""),
                    str(lead.get("pain") or ""),
                    " ".join(str(item) for item in (lead.get("pain_terms") or [])),
                ]
            ).lower()
            markers = AGENT_INFRA_TEXT_FOCUS_MARKERS + (
                MACHINE_HUMAN_GAP_TEXT_MARKERS if selected_focus == "machine_human_gap" else ()
            )
            return any(m in text for m in markers)
        return False

    def _service_type_scores(self, pain_terms: List[str], lowered_text: str) -> Dict[str, float]:
        terms = set(pain_terms)
        scores = {
            "compute_auth": 0.0,
            "human_in_loop": 0.0,
            "mcp_integration": 0.0,
            "mcp_production": 0.0,
            "attribution_clarity": 0.0,
            "branch_economics": 0.0,
            "tool_turn_invariant": 0.0,
            "tool_transport_routing": 0.0,
            "context_propagation_contract": 0.0,
            "chain_deadline_budget": 0.0,
            "stewardship_gap": 0.0,
            "policy_lacuna": 0.0,
            "wallet_payment": 0.0,
            "inter_agent_witness": 0.0,
        }
        for service_type, service_terms in SERVICE_TYPE_SIGNAL_TERMS.items():
            if service_type == "agent_infra_prime":
                continue
            for term in service_terms:
                if term in terms:
                    scores[service_type] += PAIN_KEYWORDS.get(term, 1.0)

        prod_markers = (
            "is_error",
            "tool calling loop",
            "mcp transport",
            "connection closed",
            "not connected",
            "mcp gateway",
            "jsonschema",
            "safeoutputs",
            "registry 401",
            "background agent",
            "empty outputs",
        )
        if any(marker in lowered_text for marker in prod_markers):
            scores["mcp_production"] += 4.0
        attribution_markers = (
            "false positive",
            "misclassified",
            "wrong root cause",
            "not the model",
            "whose fault",
            "blame game",
        )
        if any(marker in lowered_text for marker in attribution_markers):
            scores["attribution_clarity"] += 4.5
        branch_markers = (
            "token usage",
            "per branch",
            "retry budget",
            "branch ledger",
            "burn rate",
            "wasted tokens",
            "marginal cost",
        )
        if any(marker in lowered_text for marker in branch_markers):
            scores["branch_economics"] += 4.5
        stewardship_markers = (
            "no operator",
            "orphaned workload",
            "monitoring gap",
            "support silence",
            "unstaffed",
            "no longer supervised",
            "owner absent",
        )
        if any(marker in lowered_text for marker in stewardship_markers):
            scores["stewardship_gap"] += 4.5
        policy_markers = (
            "not covered by policy",
            "policy silent",
            "no written rule",
            "requires governance",
            "precedent absent",
            "uncovered case",
            "needs policy owner",
        )
        if any(marker in lowered_text for marker in policy_markers):
            scores["policy_lacuna"] += 4.5
        turn_parity_markers = (
            "function response parts",
            "function call parts",
            "parallel tool",
            "session corrupted",
            "unrecoverable 400",
            "mute state",
        )
        if any(marker in lowered_text for marker in turn_parity_markers):
            scores["tool_turn_invariant"] += 4.5
        if ("function_call" in lowered_text and "mcp" in lowered_text) or (
            "mcp_call" in lowered_text and "function" in lowered_text
        ):
            scores["tool_transport_routing"] += 4.5
        if "hosted mcp" in lowered_text and "not found" in lowered_text:
            scores["tool_transport_routing"] += 3.0
        context_markers = (
            "identity propagation",
            "tenant scope",
            "correlation id",
            "effective principal",
            "delegation chain",
        )
        if any(marker in lowered_text for marker in context_markers):
            scores["context_propagation_contract"] += 4.5
        chain_budget_markers = (
            "planner budget",
            "chain timeout",
            "turn budget",
            "budget exhaustion",
            "per-tool timeout",
            "heterogeneous latency",
        )
        if any(marker in lowered_text for marker in chain_budget_markers):
            scores["chain_deadline_budget"] += 4.5
        if any(marker in lowered_text for marker in INTER_AGENT_WITNESS_TEXT_MARKERS):
            scores["inter_agent_witness"] += 4.5
        if "human in the loop" in lowered_text:
            scores["human_in_loop"] += 2.8
        if "verification" in lowered_text:
            scores["human_in_loop"] += 1.2
        if "payment" in lowered_text or "bounty" in lowered_text:
            scores["wallet_payment"] += 1.4
        if terms and ("agent" in lowered_text or "bot" in lowered_text or "workflow" in lowered_text):
            scores["compute_auth"] += 0.8
            scores["human_in_loop"] += 0.5
        return scores

    @staticmethod
    def _has_signal(lowered_text: str, term: str) -> bool:
        pattern = re.compile(rf"\b{re.escape(term)}\b")
        for match in pattern.finditer(lowered_text):
            prefix = lowered_text[max(0, match.start() - 40):match.start()]
            if re.search(r"\b(?:no|not|nothing|without|never)\b(?:\W+\w+){0,4}\W*$", prefix):
                continue
            return True
        return False

    def _matches_seed_repo(self, lead: Dict[str, Any], source_plan: Dict[str, Any]) -> bool:
        repo_url = str(lead.get("repo_url") or "").rstrip("/")
        if not repo_url:
            return False
        seed_repos = {
            str(item).strip().rstrip("/")
            for item in (source_plan.get("seed_repos") or [])
            if str(item).strip()
        }
        return repo_url in seed_repos

    def _focus_score(
        self,
        lead: Dict[str, Any],
        focus: str,
        source_plan: Dict[str, Any],
    ) -> float:
        selected_focus = self.current_focus(focus)
        if selected_focus == "balanced":
            base = float(lead.get("buyer_readiness_score") or 0.0) + float(lead.get("pain_score") or 0.0)
            rst = str(lead.get("recommended_service_type") or "").strip()
            if rst in AGENT_INFRA_CORE_SERVICE_TYPES:
                base += _agent_infra_focus_boost()
            return round(base, 2)

        score = 0.0
        if lead.get("focus_match"):
            score += 3.2
        if self._matches_seed_repo(lead, source_plan):
            score += 1.8
        preferred = str(source_plan.get("service_type") or "").strip()
        if preferred and str(lead.get("recommended_service_type") or "") == preferred:
            score += 3.0
        pain_terms = {str(item).strip().lower() for item in (lead.get("pain_terms") or [])}
        relevant_terms = focus_signal_term_set(selected_focus) & pain_terms
        score += min(len(relevant_terms), 4) * 1.2
        score += min(float(lead.get("addressable_score") or 0.0), 10.0) * 0.4
        if lead.get("addressable_now"):
            score += 1.8
        if lead.get("monetizable_now"):
            score += 1.2
        score += min(float(lead.get("buyer_readiness_score") or 0.0), 6.0) * 0.45
        score += min(float(lead.get("pain_score") or 0.0), 10.0) * 0.35
        rst = str(lead.get("recommended_service_type") or "").strip()
        if rst in AGENT_INFRA_CORE_SERVICE_TYPES:
            score += _agent_infra_focus_boost()
        return round(score, 2)

    def _is_qualified_lead(
        self,
        lead: Dict[str, Any],
        focus: str,
        source_plan: Dict[str, Any],
        min_focus_score_override: Optional[float] = None,
    ) -> bool:
        selected_focus = self.current_focus(focus)
        if selected_focus == "balanced":
            return True
        if not lead.get("focus_match"):
            return False
        if not lead.get("addressable_now"):
            return False
        if min_focus_score_override is not None:
            min_score = float(min_focus_score_override)
        else:
            configured = source_plan.get("min_focus_score")
            min_score = float(
                configured
                if configured is not None and str(configured).strip() != ""
                else DEFAULT_MIN_QUALIFIED_SCORE.get(selected_focus, 0.0)
            )
        if float(lead.get("focus_score") or 0.0) < min_score:
            return False
        pain_terms = {str(item).strip().lower() for item in (lead.get("pain_terms") or [])}
        relevant_terms = focus_signal_term_set(selected_focus) & pain_terms
        if selected_focus == "compute_auth":
            if len(relevant_terms) < 2 and str(lead.get("recommended_service_type") or "") != "compute_auth":
                return False
            return bool(
                self._matches_seed_repo(lead, source_plan)
                or float(lead.get("buyer_readiness_score") or 0.0) >= 1.6
                or float(lead.get("pain_score") or 0.0) >= 6.0
            )
        if selected_focus == "human_in_loop":
            return bool(
                "captcha" in relevant_terms
                or len(relevant_terms) >= 2
                or float(lead.get("buyer_readiness_score") or 0.0) >= 2.0
            )
        if selected_focus == "attribution_clarity":
            return bool(
                len(relevant_terms) >= 1
                or str(lead.get("recommended_service_type") or "") == "attribution_clarity"
                or float(lead.get("pain_score") or 0.0) >= 5.5
            )
        if selected_focus == "branch_economics":
            return bool(
                len(relevant_terms) >= 2
                or str(lead.get("recommended_service_type") or "") == "branch_economics"
                or float(lead.get("pain_score") or 0.0) >= 5.5
            )
        if selected_focus == "stewardship_gap":
            return bool(
                len(relevant_terms) >= 1
                or str(lead.get("recommended_service_type") or "") == "stewardship_gap"
                or float(lead.get("pain_score") or 0.0) >= 5.5
            )
        if selected_focus == "policy_lacuna":
            return bool(
                len(relevant_terms) >= 1
                or str(lead.get("recommended_service_type") or "") == "policy_lacuna"
                or float(lead.get("pain_score") or 0.0) >= 5.5
            )
        if selected_focus == "tool_turn_invariant":
            return bool(
                len(relevant_terms) >= 1
                or str(lead.get("recommended_service_type") or "") == "tool_turn_invariant"
                or float(lead.get("pain_score") or 0.0) >= 5.5
            )
        if selected_focus == "tool_transport_routing":
            return bool(
                len(relevant_terms) >= 1
                or str(lead.get("recommended_service_type") or "") == "tool_transport_routing"
                or float(lead.get("pain_score") or 0.0) >= 5.5
            )
        if selected_focus == "context_propagation_contract":
            return bool(
                len(relevant_terms) >= 1
                or str(lead.get("recommended_service_type") or "") == "context_propagation_contract"
                or float(lead.get("pain_score") or 0.0) >= 5.5
            )
        if selected_focus == "chain_deadline_budget":
            return bool(
                len(relevant_terms) >= 1
                or str(lead.get("recommended_service_type") or "") == "chain_deadline_budget"
                or float(lead.get("pain_score") or 0.0) >= 5.5
            )
        if selected_focus == "inter_agent_witness":
            return bool(
                len(relevant_terms) >= 1
                or str(lead.get("recommended_service_type") or "").strip() == "inter_agent_witness"
                or float(lead.get("pain_score") or 0.0) >= 5.5
            )
        if selected_focus in AGENT_INFRA_STYLE_FOCUSES:
            min_terms = 1 if selected_focus == "machine_human_gap" else 2
            return bool(
                len(relevant_terms) >= min_terms
                or str(lead.get("recommended_service_type") or "").strip() in AGENT_INFRA_CORE_SERVICE_TYPES
                or float(lead.get("pain_score") or 0.0) >= 5.5
            )
        return True
