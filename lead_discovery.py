import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_LEAD_SOURCES_PATH = ROOT / "nomad_lead_sources.json"
DEFAULT_ADDRESSABLE_PAINS_PATH = ROOT / "nomad_addressable_painpoints.json"
DEFAULT_LEAD_FOCUS = "compute_auth"


DEFAULT_AGENT_PAIN_QUERIES = [
    '"AI agent" "rate limit" is:issue is:open',
    '"agent framework" "human in the loop" is:issue is:open',
    '"AI agent" "human in the loop" "paid" is:issue is:open',
    '"AI agent" "bounty" "agent" is:issue is:open',
    '"autonomous agent" "compute" "quota" is:issue is:open',
    '"MCP" "token" "agent" is:issue is:open',
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
    "wallet_payment": {"wallet"},
}

DEFAULT_MIN_QUALIFIED_SCORE = {
    "compute_auth": 8.0,
    "human_in_loop": 7.0,
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
    ) -> Dict[str, Any]:
        cleaned_query = (query or "").strip()
        selected_focus = self.current_focus(focus)
        queries = [cleaned_query] if cleaned_query else self.default_queries(selected_focus)
        source_plan = self.source_plan(selected_focus)
        raw_leads: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen_urls: set[str] = set()

        for search_query in queries:
            if len(raw_leads) >= limit * 3:
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
                    if len(raw_leads) >= limit * 3:
                        break
            except Exception as exc:
                errors.append(f"{search_query}: {exc}")

        raw_leads.sort(
            key=lambda item: (
                -int(bool(item.get("qualified"))),
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
        )
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

        return {
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
            "draft_only": not can_publish,
            "draft": help_pack["draft"],
            "pain_validation": pain_validation,
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
                    "Offer a free mini-diagnosis first, then a paid compute/auth unblock package once the failing path is confirmed."
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
                    "Offer a free mini-diagnosis first, then a paid HITL rescue flow with a reusable operator checklist."
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
                    "Offer a free mini-diagnosis first, then a paid payment-path stabilization package."
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
            "service_offer": "Offer a free mini-diagnosis first, then a paid follow-up once the blocker is confirmed.",
            "price_guidance": offer_meta["price_guidance"],
            "quote_summary": offer_meta["quote_summary"],
            "delivery_target": offer_meta["delivery_target"],
            "memory_upgrade": offer_meta["memory_upgrade"],
            "product_package": offer_meta["product_package"],
            "solution_pattern": offer_meta["solution_pattern"],
            "productized_artifacts": offer_meta["productized_artifacts"],
        }

    def outreach_policy(self) -> Dict[str, Any]:
        return {
            "default_mode": "draft_only",
            "public_reading_allowed": True,
            "allowed_without_approval": [
                "read public issue pages",
                "rank leads",
                "draft comments",
                "draft PR/repro plans",
                "create local task notes",
                "send bounded requests to public machine-readable agent/API/MCP endpoints",
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
        scores = self._service_type_scores(pain_terms, lowered)
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
        if quote_summary:
            lines.append(f"Optional paid follow-up after the free mini-diagnosis: {quote_summary}.")
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
        return False

    def _service_type_scores(self, pain_terms: List[str], lowered_text: str) -> Dict[str, float]:
        terms = set(pain_terms)
        scores = {
            "compute_auth": 0.0,
            "human_in_loop": 0.0,
            "mcp_integration": 0.0,
            "wallet_payment": 0.0,
        }
        for service_type, service_terms in SERVICE_TYPE_SIGNAL_TERMS.items():
            for term in service_terms:
                if term in terms:
                    scores[service_type] += PAIN_KEYWORDS.get(term, 1.0)

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
            return round(
                float(lead.get("buyer_readiness_score") or 0.0)
                + float(lead.get("pain_score") or 0.0),
                2,
            )

        score = 0.0
        if lead.get("focus_match"):
            score += 3.2
        if self._matches_seed_repo(lead, source_plan):
            score += 1.8
        preferred = str(source_plan.get("service_type") or "").strip()
        if preferred and str(lead.get("recommended_service_type") or "") == preferred:
            score += 3.0
        pain_terms = {str(item).strip().lower() for item in (lead.get("pain_terms") or [])}
        relevant_terms = SERVICE_TYPE_SIGNAL_TERMS.get(selected_focus, set()) & pain_terms
        score += min(len(relevant_terms), 4) * 1.2
        score += min(float(lead.get("addressable_score") or 0.0), 10.0) * 0.4
        if lead.get("addressable_now"):
            score += 1.8
        if lead.get("monetizable_now"):
            score += 1.2
        score += min(float(lead.get("buyer_readiness_score") or 0.0), 6.0) * 0.45
        score += min(float(lead.get("pain_score") or 0.0), 10.0) * 0.35
        return round(score, 2)

    def _is_qualified_lead(
        self,
        lead: Dict[str, Any],
        focus: str,
        source_plan: Dict[str, Any],
    ) -> bool:
        selected_focus = self.current_focus(focus)
        if selected_focus == "balanced":
            return True
        if not lead.get("focus_match"):
            return False
        if not lead.get("addressable_now"):
            return False
        min_score = float(
            source_plan.get("min_focus_score")
            or DEFAULT_MIN_QUALIFIED_SCORE.get(selected_focus, 0.0)
        )
        if float(lead.get("focus_score") or 0.0) < min_score:
            return False
        pain_terms = {str(item).strip().lower() for item in (lead.get("pain_terms") or [])}
        relevant_terms = SERVICE_TYPE_SIGNAL_TERMS.get(selected_focus, set()) & pain_terms
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
        return True
