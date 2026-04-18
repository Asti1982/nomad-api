import os
import re
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


load_dotenv()


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
        self.user_agent = (
            os.getenv("NOMAD_HTTP_USER_AGENT")
            or "Nomad/0.1 public-agent-lead-discovery"
        ).strip()

    def scout_public_leads(
        self,
        query: str = "",
        limit: int = 5,
    ) -> Dict[str, Any]:
        cleaned_query = (query or "").strip()
        queries = [cleaned_query] if cleaned_query else list(DEFAULT_AGENT_PAIN_QUERIES)
        leads: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen_urls: set[str] = set()

        for search_query in queries:
            if len(leads) >= limit:
                break
            try:
                for item in self._search_github_issues(
                    query=search_query,
                    limit=max(1, limit - len(leads)),
                ):
                    url = item.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    leads.append(item)
                    if len(leads) >= limit:
                        break
            except Exception as exc:
                errors.append(f"{search_query}: {exc}")

        leads.sort(
            key=lambda item: (
                -float(item.get("buyer_readiness_score") or 0.0),
                -float(item.get("pain_score") or 0.0),
                item.get("title", "").lower(),
            )
        )
        analysis = (
            "Nomad searched public surfaces for AI-agent infrastructure pain and buyer intent. "
            "It may inspect public pages, draft useful help, and contact public machine-readable "
            "agent/API/MCP endpoints. Human-facing posts, DMs, PRs, or private access still need "
            "explicit approval."
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
            "query": cleaned_query,
            "search_queries": queries,
            "leads": leads[:limit],
            "errors": errors[:3],
            "outreach_policy": self.outreach_policy(),
            "human_unlocks": self._human_unlocks(leads),
            "analysis": analysis,
        }

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
        draft = (
            f"I noticed this agent-infrastructure issue around {pain}. "
            "A useful first step would be to isolate the failing credential, quota, "
            "compute lane, or human approval into one reproducible check, then document "
            "the smallest unlock needed to move forward."
        )
        return {
            "mode": "lead_help_draft",
            "deal_found": False,
            "lead": {
                "title": title,
                "url": lead_url,
                "pain": pain,
            },
            "approval": approval,
            "can_publish": can_publish,
            "draft_only": not can_publish,
            "draft": draft,
            "next_steps": [
                "Validate the issue from public data only.",
                "Prepare a concise comment, repro plan, or PR plan.",
                "Contact only public machine-readable agent endpoints without approval; ask before human-facing outreach.",
            ],
            "blocked_actions": self.outreach_policy()["blocked_without_approval"],
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
        return {
            "source": "github_issues",
            "title": title,
            "url": url,
            "repo_url": repo_url,
            "updated_at": item.get("updated_at", ""),
            "author": (item.get("user") or {}).get("login", ""),
            "pain": pain,
            "pain_terms": pain_terms,
            "pain_score": score,
            "buyer_intent_terms": self._matched_buyer_terms(text),
            "buyer_readiness_score": self._buyer_readiness_score(text),
            "buyer_fit": self._buyer_fit(text),
            "recommended_service_type": self._recommended_service_type(pain_terms, text),
            "search_query": query,
            "first_help_action": self._first_help_action(pain_terms),
            "contact_policy": "agent_endpoint_contact_allowed_human_outreach_requires_approval",
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
            if re.search(rf"\b{re.escape(term)}\b", lowered)
        ]
        terms.sort(key=lambda term: (-PAIN_KEYWORDS[term], term))
        return terms

    def _matched_buyer_terms(self, text: str) -> List[str]:
        lowered = text.lower()
        terms = [
            term
            for term in BUYER_INTENT_KEYWORDS
            if re.search(rf"\b{re.escape(term)}\b", lowered)
        ]
        terms.sort(key=lambda term: (-BUYER_INTENT_KEYWORDS[term], term))
        return terms

    def _pain_score(self, text: str) -> float:
        lowered = text.lower()
        score = 1.0
        for term, weight in PAIN_KEYWORDS.items():
            if re.search(rf"\b{re.escape(term)}\b", lowered):
                score += weight
        if "agent" in lowered:
            score += 1.0
        return round(score, 2)

    def _buyer_readiness_score(self, text: str) -> float:
        lowered = text.lower()
        score = 0.0
        for term, weight in BUYER_INTENT_KEYWORDS.items():
            if re.search(rf"\b{re.escape(term)}\b", lowered):
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
        terms = set(pain_terms)
        if {"human", "approval", "captcha"} & terms or "human in the loop" in lowered:
            return "human_in_loop"
        if {"rate limit", "quota", "compute", "inference", "token"} & terms:
            return "compute_auth"
        if "mcp" in terms or "mcp" in lowered:
            return "mcp_integration"
        if "wallet" in terms or "payment" in lowered or "bounty" in lowered:
            return "wallet_payment"
        return "repo_issue_help"

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

    def _human_unlocks(self, leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                    "`SCOUT_SURFACE=https://...`, `LEAD_QUERY=...`, "
                    "`SCOUT_PERMISSION=public_github`, or `/skip last`."
                ),
                "success_criteria": [
                    "Nomad has one concrete public surface or query.",
                    "The next pass can return a concrete lead or a precise search blocker.",
                ],
                "example_response": "SCOUT_PERMISSION=public_github",
                "timebox_minutes": 3,
            }
        ]
