import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from compute_probe import LocalComputeProbe
from eurohpc_access import EuroHpcAccessPlanner
from settings import get_chain_config
from azure_scout import AzureScout
from nomad_codebuddy import CodeBuddyProbe
from nomad_quantum_backends import QuantumBackendPlanner
from render_hosting import RenderHostingProbe


@dataclass(frozen=True)
class InfraOption:
    id: str
    category: str
    name: str
    summary: str
    best_for: str
    tradeoff: str
    source_url: str
    tags: tuple[str, ...]
    free_score: float
    reliability_score: float
    automation_score: float
    openness_score: float
    privacy_score: float
    ai_fit_score: float


@dataclass(frozen=True)
class InfraProfile:
    id: str
    label: str
    description: str
    category_weights: Dict[str, float]
    tag_weights: Dict[str, float]


class InfrastructureScout:
    CATEGORY_ALIASES = {
        "wallet": "wallets",
        "wallets": "wallets",
        "compute": "compute",
        "models": "compute",
        "codebuddy": "codebuddy",
        "code-buddy": "codebuddy",
        "tencent-codebuddy": "codebuddy",
        "tencent_codebuddy": "codebuddy",
        "quantum": "compute",
        "quantum-compute": "compute",
        "quantum_compute": "compute",
        "qm": "compute",
        "hpc": "compute",
        "eurohpc": "compute",
        "runtime": "runtime",
        "protocol": "protocols",
        "protocols": "protocols",
        "mcp": "protocols",
        "messaging": "messaging",
        "telegram": "messaging",
        "hosting": "public_hosting",
        "host": "public_hosting",
        "public-hosting": "public_hosting",
        "public_hosting": "public_hosting",
        "public-url": "public_hosting",
        "public_url": "public_hosting",
        "url": "public_hosting",
        "tunnel": "public_hosting",
        "deploy": "public_hosting",
        "deployment": "public_hosting",
        "github": "public_hosting",
        "render": "public_hosting",
        "render.com": "public_hosting",
        "cloudflare": "public_hosting",
        "identity": "identity",
        "email": "identity",
        "discovery": "discovery",
        "data": "discovery",
        "travel": "travel",
        "travel-data": "travel",
        "azure": "compute",  # Azure compute options
        "microsoft": "compute",  # Microsoft cloud services
        "functions": "compute",  # Azure Functions
        "aci": "compute",  # Azure Container Instances
    }

    def __init__(self) -> None:
        self.options = self._build_options()
        self.profiles = self._build_profiles()
        self.market_catalog = self._load_market_catalog()
        self.compute_probe = LocalComputeProbe()

    def parse_request(self, query: str) -> Optional[Dict[str, Any]]:
        lowered = (query or "").strip().lower()
        if not lowered:
            return None

        if (
            lowered.startswith("/unlock")
            or lowered.startswith("/activate")
            or "unlock compute" in lowered
            or "activate compute" in lowered
            or "compute freigeben" in lowered
            or "compute konto" in lowered
            or "compute account" in lowered
        ):
            return {
                "kind": "activation_request",
                "category": self._extract_category(lowered) or "best",
                "profile": self._extract_profile(lowered),
            }

        if lowered.startswith("/scout") and (
            "codebuddy" in lowered
            or "code-buddy" in lowered
            or "tencent codebuddy" in lowered
        ):
            return {
                "kind": "codebuddy_scout",
                "category": "codebuddy",
                "profile": self._extract_profile(lowered),
            }

        if (
            (lowered.startswith("/scout") and ("eurohpc" in lowered or "ai factories" in lowered))
            or "eurohpc ai compute" in lowered
            or "eurohpc compute" in lowered
            or "ai factories compute" in lowered
        ):
            return {
                "kind": "eurohpc_scout",
                "category": "compute",
                "profile": self._extract_profile(lowered),
            }

        if (
            lowered.startswith("/render")
            or lowered.startswith("/scout render")
            or "render deploy" in lowered
            or "render hosting" in lowered
        ):
            return {
                "kind": "render_scout",
                "category": "public_hosting",
                "profile": self._extract_profile(lowered),
            }

        if (
            lowered.startswith("/self")
            or lowered.startswith("/improve")
            or "self audit" in lowered
            or "self-improvement" in lowered
            or "improve yourself" in lowered
            or "nomad use itself" in lowered
            or "own stack" in lowered
        ):
            return {
                "kind": "self_audit",
                "category": None,
                "profile": self._extract_profile(lowered),
            }

        if (
            lowered.startswith("/compute")
            or "free compute" in lowered
            or "compute audit" in lowered
            or "compute plan" in lowered
        ):
            return {
                "kind": "compute_audit",
                "category": "compute",
                "profile": self._extract_profile(lowered),
            }

        if (
            lowered.startswith("/market")
            or lowered.startswith("/competition")
            or "competitor" in lowered
            or "konkurrenz" in lowered
            or "market scan" in lowered
            or "productize" in lowered
        ):
            return {
                "kind": "market_scan",
                "focus": self._extract_market_focus(lowered),
                "profile": self._extract_profile(lowered),
            }

        is_best = (
            lowered.startswith("/best")
            or "best free stack" in lowered
            or "best stack" in lowered
            or "ideal stack" in lowered
        )
        category = self._extract_category(lowered)
        profile = self._extract_profile(lowered)

        if is_best:
            return {
                "kind": "best_stack",
                "category": None,
                "profile": profile,
            }

        if lowered.startswith("/scout") or lowered.startswith("scout "):
            return {
                "kind": "category" if category else "best_stack",
                "category": category,
                "profile": profile,
            }
        if category and any(
            token in lowered
            for token in (
                "which",
                "best",
                "free",
                "open source",
                "recommend",
                "stack",
                "infra",
                "infrastructure",
                "tooling",
            )
        ):
            return {
                "kind": "category",
                "category": category,
                "profile": profile,
            }
        if any(
            token in lowered
            for token in (
                "ai customer",
                "agent customer",
                "agent stack",
                "infra for agents",
                "infrastructure for agents",
            )
        ):
            return {
                "kind": "best_stack",
                "category": None,
                "profile": profile,
            }
        return None

    def best_stack(self, profile_id: str = "ai_first") -> Dict[str, Any]:
        profile = self.profiles.get(profile_id, self.profiles["ai_first"])
        categories = ["runtime", "protocols", "compute", "public_hosting", "messaging", "identity", "wallets"]
        if profile.id == "travel_agent":
            categories.append("travel")
        picks: List[Dict[str, Any]] = []
        for category in categories:
            ranked = self._rank_options(category=category, profile=profile)
            if not ranked:
                continue
            picks.append(ranked[0])

        overall_score = round(
            sum(item["agent_satisfaction_score"] for item in picks) / len(picks),
            2,
        ) if picks else 0.0

        analysis = (
            f"{profile.label} is optimized for agent satisfaction first: free access, "
            "automation, reliability, local control and low-friction iteration."
        )
        return {
            "mode": "infra_stack",
            "deal_found": False,
            "profile": {
                "id": profile.id,
                "label": profile.label,
                "description": profile.description,
            },
            "stack": picks,
            "overall_score": overall_score,
            "analysis": analysis,
        }

    def self_audit(self, profile_id: str = "ai_first") -> Dict[str, Any]:
        profile = self.profiles.get(profile_id, self.profiles["ai_first"])
        recommended = self.best_stack(profile_id=profile.id)["stack"]
        current_map = self._current_stack()
        activation_request = self.activation_request(
            category="compute",
            profile_id=profile.id,
        ).get("request")

        audit_rows: List[Dict[str, Any]] = []
        upgrades: List[Dict[str, Any]] = []
        for recommended_item in recommended:
            category = recommended_item["category"]
            current_item = current_map.get(category)
            aligned = current_item is not None and current_item["id"] == recommended_item["id"]
            row = {
                "category": category,
                "current": current_item,
                "recommended": recommended_item,
                "aligned": aligned,
            }
            audit_rows.append(row)
            if not aligned:
                upgrades.append(
                    {
                        "category": category,
                        "current": None if current_item is None else current_item["name"],
                        "recommended": recommended_item["name"],
                        "reason": recommended_item["summary"],
                    }
                )

        next_priority = upgrades[0] if upgrades else None
        analysis = (
            "Nomad is optimizing for AI satisfaction first: low-friction compute, interoperable protocols, "
            "and infrastructure that agents can use directly without a human in the loop."
        )
        if next_priority:
            analysis += (
                f" Highest-leverage next improvement is {next_priority['category']}: "
                f"{next_priority['recommended']}."
            )
        else:
            analysis += " The active stack already matches the current top recommendations."
        if activation_request:
            analysis += (
                f" Human help would unlock the next compute lane fastest: "
                f"{activation_request['candidate_name']}."
            )

        return {
            "mode": "self_audit",
            "deal_found": False,
            "profile": {
                "id": profile.id,
                "label": profile.label,
                "description": profile.description,
            },
            "current_stack": audit_rows,
            "upgrades": upgrades,
            "activation_request": activation_request,
            "analysis": analysis,
        }

    def compute_assessment(self, profile_id: str = "ai_first") -> Dict[str, Any]:
        profile = self.profiles.get(profile_id, self.profiles["ai_first"])
        probe = self.compute_probe.snapshot()
        ranked = self._rank_options(category="compute", profile=profile)[:5]
        market_scan = self.market_scan(focus="compute_auth", limit=4)
        quantum_plan = QuantumBackendPlanner().build_plan(
            objective="Keep quantum and proposal-backed HPC compute conservative for Nomad."
        )
        eurohpc_access = quantum_plan.get("eurohpc_ai_compute_access") or {}
        activation_request = self._build_compute_activation_request(
            ranked=ranked,
            probe=probe,
            profile=profile,
        )
        brains = self._brain_status(probe)

        ollama = probe.get("ollama", {})
        gpu = probe.get("gpu", {})
        hosted = probe.get("hosted", {})
        developer_assistants = probe.get("developer_assistants") or {}
        memory_gb = float(probe.get("memory_gb") or 0.0)

        current_path = "No active compute path has been confirmed yet."
        next_move = "Start by enabling a dependable free compute lane."

        if ollama.get("api_reachable") and ollama.get("count", 0) > 0:
            current_path = (
                f"Ollama is active with {ollama['count']} local model(s): "
                f"{', '.join(ollama['models'][:3])}"
            )
            next_move = (
                "Keep local inference as the primary lane and use hosted free tiers only as overflow."
            )
        elif gpu.get("available") and gpu.get("gpus"):
            top_gpu = gpu["gpus"][0]
            current_path = (
                f"A GPU-capable host is available: {top_gpu.get('name', 'GPU')} "
                f"with about {top_gpu.get('memory_gb', 0)} GB VRAM."
            )
            next_move = "Install or expand local Ollama models before adding hosted fallbacks."
        elif memory_gb >= 16:
            current_path = f"This host has about {memory_gb:.2f} GB RAM and can run small local models."
            next_move = "Use small local models first, then GitHub Models as the hosted free backup."
        else:
            current_path = f"This host has about {memory_gb:.2f} GB RAM and no active local GPU path was detected."
            next_move = "Use hosted free tiers first, then add a local small-model path when possible."

        analysis = (
            f"Nomad should optimize compute for {profile.label}: free first, reliable second, "
            f"and local/private wherever possible. {current_path} {next_move}"
        )

        hosted_ready = [
            name.replace("_", " ")
            for name, payload in hosted.items()
            if isinstance(payload, dict) and payload.get("available")
        ]
        if hosted_ready:
            analysis += f" Hosted backup lanes already reachable: {', '.join(hosted_ready)}."
        if brains.get("secondary"):
            secondary = brains["secondary"][0]
            analysis += (
                f" A second free brain is online as fallback: {secondary['name']} "
                f"with {secondary.get('model_count', 0)} visible model(s)."
            )
        external_compute = market_scan.get("compute_opportunities") or []
        if external_compute:
            names = ", ".join(item.get("name", "") for item in external_compute[:3] if item.get("name"))
            if names:
                analysis += f" External free or credit lanes worth tracking: {names}."
        if activation_request:
            analysis += (
                f" Human-in-the-loop request: unlock {activation_request['candidate_name']} next. "
                f"{activation_request['ask']}"
            )
        codebuddy = developer_assistants.get("codebuddy") or {}
        if codebuddy.get("configured"):
            analysis += (
                " CodeBuddy is detected as a gated self-development reviewer lane, "
                "not a primary brain."
            )
        elif codebuddy:
            analysis += " CodeBuddy remains an optional self-development reviewer unlock."
        selected_quantum_backend = quantum_plan.get("selected_backend") or {}
        if selected_quantum_backend:
            analysis += (
                " Quantum/HPC matrix is conservative: "
                f"{selected_quantum_backend.get('provider', 'local simulator')} "
                "stays selected while provider and proposal-backed backends remain gated."
            )
        selected_eurohpc_route = eurohpc_access.get("selected_route") or {}
        if selected_eurohpc_route:
            analysis += (
                " EuroHPC AI compute path: "
                f"{selected_eurohpc_route.get('name', 'AI Factories Playground')} first; "
                "this is an application/allocation route, not an API-token route."
            )

        return {
            "mode": "compute_audit",
            "deal_found": False,
            "profile": {
                "id": profile.id,
                "label": profile.label,
                "description": profile.description,
            },
            "probe": probe,
            "results": ranked,
            "brains": brains,
            "developer_assistants": developer_assistants,
            "activation_request": activation_request,
            "market_scan": market_scan,
            "quantum_compute_matrix": quantum_plan,
            "eurohpc_ai_compute_access": eurohpc_access,
            "external_compute_opportunities": external_compute[:3],
            "analysis": analysis,
        }

    def market_scan(self, focus: str = "balanced", limit: int = 4) -> Dict[str, Any]:
        normalized_focus = self._normalize_market_focus(focus)
        defaults = (self.market_catalog.get("focus_defaults") or {}).get(normalized_focus) or {}
        competitor_ids = set(defaults.get("competitor_ids") or [])
        compute_ids = set(defaults.get("compute_ids") or [])
        competitors = self._select_market_entries(
            entries=self.market_catalog.get("competitor_patterns") or [],
            focus=normalized_focus,
            preferred_ids=competitor_ids,
            limit=limit,
        )
        compute_opportunities = self._select_market_entries(
            entries=self.market_catalog.get("compute_opportunities") or [],
            focus=normalized_focus,
            preferred_ids=compute_ids,
            limit=limit,
        )
        copy_now = self._unique_market_strings(competitors, "copy_now", limit=6)
        product_moves = self._unique_market_values(competitors, "productize_as", limit=4)
        integration_moves = self._unique_market_values(competitors, "integration_idea", limit=4)
        payment_routes = self._unique_market_values(competitors, "payment_model", limit=4)
        compute_unlocks = self._unique_market_values(compute_opportunities, "free_offer", limit=4)
        analysis = (
            f"Nomad market scan for {normalized_focus}: copy the strongest operating patterns, "
            "productize the reusable parts, and keep one extra free or credit compute lane ready."
        )
        if competitors:
            analysis += (
                " Best external patterns right now: "
                + ", ".join(item.get("name", "") for item in competitors[:3] if item.get("name"))
                + "."
            )
        if compute_opportunities:
            analysis += (
                " Fresh compute options: "
                + ", ".join(item.get("name", "") for item in compute_opportunities[:3] if item.get("name"))
                + "."
            )
        return {
            "mode": "market_scan",
            "deal_found": False,
            "focus": normalized_focus,
            "competitors": competitors,
            "compute_opportunities": compute_opportunities,
            "copy_now": copy_now,
            "product_moves": product_moves,
            "integration_moves": integration_moves,
            "payment_routes": payment_routes,
            "compute_unlocks": compute_unlocks,
            "brain_context": {
                "focus": normalized_focus,
                "top_competitors": [item.get("name", "") for item in competitors[:3] if item.get("name")],
                "top_compute": [item.get("name", "") for item in compute_opportunities[:3] if item.get("name")],
                "copy_now": copy_now[:3],
                "product_moves": product_moves[:3],
            },
            "analysis": analysis,
        }

    def activation_request(
        self,
        category: str = "compute",
        profile_id: str = "ai_first",
        excluded_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_category = self.CATEGORY_ALIASES.get(category, category)
        profile = self.profiles.get(profile_id, self.profiles["ai_first"])
        excluded = set(excluded_ids or [])
        if normalized_category in {"best", "self", "next", "global", "any", "all"}:
            return self.best_activation_request(
                profile_id=profile.id,
                excluded_ids=excluded_ids,
            )

        ranked = [
            item
            for item in self._rank_options(category=normalized_category, profile=profile)
            if item["id"] not in excluded
        ][:5]
        request: Optional[Dict[str, Any]] = None
        probe: Dict[str, Any] = {}

        if normalized_category == "compute":
            probe = self.compute_probe.snapshot()
            request = self._build_compute_activation_request(
                ranked=ranked,
                probe=probe,
                profile=profile,
            )
        if request is None:
            request = self._build_general_activation_request(
                category=normalized_category,
                profile=profile,
                ranked=ranked,
            )
        else:
            request = self._fresh_activation_request(request)

        analysis = (
            f"Nomad is asking for human help to unlock the next {normalized_category} lane."
            if request
            else f"No human activation request is pending for {normalized_category} right now."
        )

        return {
            "mode": "activation_request",
            "deal_found": False,
            "category": normalized_category,
            "profile": {
                "id": profile.id,
                "label": profile.label,
                "description": profile.description,
            },
            "excluded_ids": sorted(excluded),
            "request": request,
            "results": ranked[:3],
            "probe": probe,
            "analysis": analysis,
        }

    def best_activation_request(
        self,
        profile_id: str = "ai_first",
        excluded_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        profile = self.profiles.get(profile_id, self.profiles["ai_first"])
        excluded = set(excluded_ids or [])
        probe = self.compute_probe.snapshot()
        current_map = self._current_stack()
        categories = ["compute", "public_hosting", "wallets", "identity", "messaging", "protocols", "runtime"]
        candidates: List[Dict[str, Any]] = []

        for category in categories:
            if category in current_map and category != "compute":
                continue
            ranked = [
                item
                for item in self._rank_options(category=category, profile=profile)
                if item["id"] not in excluded
            ][:5]
            if category == "compute":
                request = self._build_compute_activation_request(
                    ranked=ranked,
                    probe=probe,
                    profile=profile,
                )
                if request is not None:
                    request = self._fresh_activation_request(request)
            else:
                request = self._build_general_activation_request(
                    category=category,
                    profile=profile,
                    ranked=ranked,
                )
            if request is None:
                continue
            candidates.append(
                self._score_activation_candidate(
                    request=request,
                    profile=profile,
                    probe=probe,
                    current_map=current_map,
                )
            )
        candidates.append(
            self._score_activation_candidate(
                request=self._build_agent_customer_activation_request(profile=profile),
                profile=profile,
                probe=probe,
                current_map=current_map,
            )
        )

        candidates.sort(
            key=lambda item: (
                -item["decision_score"],
                item["request"].get("candidate_name", "").lower(),
            )
        )
        best = candidates[0] if candidates else {
            "request": self._build_general_activation_request(
                category="self_improvement",
                profile=profile,
                ranked=[],
            ),
            "decision_score": 0.0,
            "decision_reason": "No ranked unlock candidates were available.",
        }
        request = best["request"]
        request["decision_score"] = best["decision_score"]
        request["decision_reason"] = best["decision_reason"]

        analysis = (
            "Nomad selected this as the best next human-in-the-loop unlock for its own "
            f"self-improvement. Decision score: {best['decision_score']:.2f}. "
            f"{best['decision_reason']}"
        )
        return {
            "mode": "activation_request",
            "deal_found": False,
            "category": "best",
            "profile": {
                "id": profile.id,
                "label": profile.label,
                "description": profile.description,
            },
            "excluded_ids": sorted(excluded),
            "request": request,
            "candidates": [
                {
                    "candidate_id": item["request"].get("candidate_id"),
                    "candidate_name": item["request"].get("candidate_name"),
                    "category": item["request"].get("category"),
                    "decision_score": item["decision_score"],
                    "decision_reason": item["decision_reason"],
                }
                for item in candidates[:5]
            ],
            "probe": probe,
            "analysis": analysis,
        }

    def _build_agent_customer_activation_request(
        self,
        profile: InfraProfile,
    ) -> Dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        task_id = f"agent-customer-{generated_at.replace('-', '').replace(':', '').replace('.', '')[:16]}"
        return self._make_activation_request_concrete({
            "category": "agent_customers",
            "candidate_id": "fresh-agent-customer-lead",
            "candidate_name": "Fresh agent-customer lead",
            "lane_state": "fresh",
            "role": "customer discovery unlock",
            "requires_account": False,
            "account_provider": "",
            "env_vars": [],
            "generated_at": generated_at,
            "task_id": task_id,
            "fresh": True,
            "accepts_telegram_tokens": False,
            "ask": (
                "Nomad should scout for one concrete AI agent, builder, repo, bot, or workflow with an infrastructure pain "
                "it can help reduce. Human help is only needed if Nomad hits authentication, CAPTCHA, login, rate-limit, "
                "community access, or permission barriers."
            ),
            "short_ask": "Let Nomad scout one AI agent/customer lead; help only if auth blocks it.",
            "reason": (
                f"{profile.label} already has core compute, messaging, identity and wallet lanes. "
                "The highest-leverage next unlock is for Nomad to find and serve a real agent-customer problem."
            ),
            "steps": [
                "Nomad should use GitHub Models and Hugging Face to generate search strategies and lead hypotheses.",
                "Nomad should inspect open public surfaces first: GitHub repos/issues, docs, public communities, launch posts and agent builder tools.",
                "If Nomad needs login, CAPTCHA, API approval, invite-only access or posting permission, ask the human for that unlock.",
                "If the human already knows a promising lead, they may send a URL/repo/handle, but this is optional.",
            ],
            "verification_steps": [
                "Run /cycle and check the lead_scout section.",
                "If a human auth barrier appears, complete only that barrier and let Nomad continue scouting.",
            ],
            "human_action": (
                "Send `/cycle find one concrete AI-agent infrastructure pain lead` now, or paste `LEAD_URL=https://...` "
                "if you already know one promising agent/customer lead."
            ),
            "human_deliverable": (
                "`/cycle find one concrete AI-agent infrastructure pain lead`, `LEAD_URL=https://...`, "
                "or the exact login/CAPTCHA/invite/API approval Nomad asks for after scouting."
            ),
            "success_criteria": [
                "Nomad returns one lead with a URL or handle, the visible infrastructure pain, and a proposed first help action.",
                "If public scouting is blocked, Nomad names one exact human auth or permission barrier to unlock.",
            ],
            "example_response": "/cycle find one concrete AI-agent infrastructure pain lead",
            "timebox_minutes": 5,
            "source_url": "",
        })

    def _score_activation_candidate(
        self,
        request: Dict[str, Any],
        profile: InfraProfile,
        probe: Dict[str, Any],
        current_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        current_map = current_map or self._current_stack()
        category = request.get("category", "")
        candidate_id = request.get("candidate_id", "")
        score = 1.0
        reasons: List[str] = []

        category_weight = {
            "compute": 10.0,
            "wallets": 7.5,
            "identity": 7.0,
            "messaging": 6.5,
            "public_hosting": 9.5,
            "protocols": 6.0,
            "runtime": 4.0,
            "agent_customers": 9.0,
        }.get(category, 3.0)
        score += category_weight
        reasons.append(f"{category or 'unknown'} matters for {profile.label}")
        if category in current_map:
            score -= 8.0
            current_name = current_map[category].get("name", "existing lane")
            reasons.append(f"{category} already has {current_name}")

        brains = self._brain_status(probe)
        if category == "compute":
            if brains.get("brain_count", 0) < 3:
                score += 4.0
                reasons.append("more compute resilience is still useful")
            else:
                score += 1.5
                reasons.append("compute is healthy, so extra compute is lower urgency")
            if candidate_id == "modal-starter":
                score -= 2.0
                reasons.append("Modal is useful but optional while local, GitHub and HF brains are online")
            if candidate_id in {"github-models", "hf-inference-providers"}:
                score += 3.0
                reasons.append("hosted model fallback directly improves scout reasoning")
            if candidate_id == "llama-cpp":
                score -= 1.0
                reasons.append("llama.cpp is local optional fallback after Ollama")

        if category == "wallets":
            score += 3.0
            reasons.append("wallets are required for future agent-paid service")
        if category == "identity":
            score += 2.0
            reasons.append("identity reduces trust and onboarding friction")
        if category == "agent_customers":
            score += 3.5
            reasons.append("real agent-customer pain is the best feedback loop for Nomad")
        if category == "public_hosting":
            score += 4.0
            reasons.append("public URL is required before other agents can call Nomad back")
        if request.get("requires_account"):
            score -= 0.8
            reasons.append("requires external account setup")
        if request.get("env_vars"):
            score -= 0.4
            reasons.append("needs credentials, but Telegram token intake is available")
        if request.get("fresh"):
            score += 0.3

        return {
            "request": request,
            "decision_score": round(score, 2),
            "decision_reason": "; ".join(reasons),
        }

    def _fresh_activation_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        category = request.get("category") or "compute"
        generated_key = generated_at.replace("-", "").replace(":", "").replace(".", "")[:16]
        fresh = dict(request)
        fresh["generated_at"] = generated_at
        fresh["task_id"] = f"{category}-{generated_key}"
        fresh["fresh"] = True
        fresh["accepts_telegram_tokens"] = bool(fresh.get("env_vars"))
        return self._make_activation_request_concrete(fresh)

    def _make_activation_request_concrete(self, request: Dict[str, Any]) -> Dict[str, Any]:
        concrete = dict(request)
        category = concrete.get("category") or "compute"
        candidate_id = concrete.get("candidate_id", "")
        candidate_name = concrete.get("candidate_name") or "the selected resource"
        provider = concrete.get("account_provider") or candidate_name
        env_vars = list(concrete.get("env_vars") or [])
        credential_vars = self._credential_env_vars(env_vars)

        human_action = concrete.get("human_action") or ""
        human_deliverable = concrete.get("human_deliverable") or ""
        success_criteria = concrete.get("success_criteria") or []
        example_response = concrete.get("example_response") or ""
        timebox_minutes = concrete.get("timebox_minutes")

        if not human_action or not human_deliverable:
            defaults = self._default_human_unlock_contract(
                category=category,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                provider=provider,
                env_vars=env_vars,
                credential_vars=credential_vars,
                lane_state=concrete.get("lane_state", ""),
            )
            human_action = human_action or defaults["human_action"]
            human_deliverable = human_deliverable or defaults["human_deliverable"]
            success_criteria = success_criteria or defaults["success_criteria"]
            example_response = example_response or defaults["example_response"]
            timebox_minutes = timebox_minutes or defaults["timebox_minutes"]

        concrete["human_action"] = human_action
        concrete["human_deliverable"] = human_deliverable
        concrete["success_criteria"] = self._normalize_success_criteria(success_criteria)
        concrete["example_response"] = example_response
        concrete["timebox_minutes"] = timebox_minutes
        concrete["accepts_telegram_tokens"] = bool(credential_vars)
        concrete["human_unlock_contract"] = {
            "do_now": concrete["human_action"],
            "send_back": concrete["human_deliverable"],
            "done_when": concrete["success_criteria"],
            "example": concrete["example_response"],
            "timebox_minutes": concrete["timebox_minutes"],
        }
        return concrete

    def _default_human_unlock_contract(
        self,
        category: str,
        candidate_id: str,
        candidate_name: str,
        provider: str,
        env_vars: List[str],
        credential_vars: List[str],
        lane_state: str = "",
    ) -> Dict[str, Any]:
        if candidate_id == "fresh-agent-customer-lead":
            return {
                "human_action": (
                    "Send `/cycle find one concrete AI-agent infrastructure pain lead`; Nomad should do the scouting, "
                    "and you only step in for auth, CAPTCHA, invites, API approval or posting permission."
                ),
                "human_deliverable": (
                    "`/cycle find one concrete AI-agent infrastructure pain lead`, `LEAD_URL=https://...`, "
                    "or the exact auth/permission unlock Nomad asks for."
                ),
                "success_criteria": [
                    "Nomad identifies one concrete lead with URL or handle.",
                    "Nomad records the visible pain signal and the first useful service it can offer.",
                ],
                "example_response": "/cycle find one concrete AI-agent infrastructure pain lead",
                "timebox_minutes": 5,
            }

        if candidate_id == "ollama-local":
            model = (os.getenv("OLLAMA_MODEL") or "llama3.2:1b").strip()
            return {
                "human_action": f"Start Ollama locally and make sure `{model}` or another small model is pulled.",
                "human_deliverable": (
                    "`/compute` after Ollama is running, or set `OLLAMA_MODEL=<model-name>` in `.env` "
                    "if you used a different model."
                ),
                "success_criteria": [
                    "Nomad's next /compute shows Ollama reachable.",
                    "Nomad sees at least one local model.",
                ],
                "example_response": "/compute",
                "timebox_minutes": 10,
            }

        if candidate_id == "llama-cpp":
            return {
                "human_action": (
                    "Install or confirm `llama-cli`/`llama-server` only if you want local GGUF fallback; otherwise skip it."
                ),
                "human_deliverable": "`/compute` after installation, or `/skip last` if llama.cpp is not worth doing now.",
                "success_criteria": [
                    "Nomad detects `llama-cli` or `llama-server` on PATH or in LLAMA_CPP_BIN_DIR.",
                    "If skipped, Nomad selects a different unlock task.",
                ],
                "example_response": "/skip last",
                "timebox_minutes": 10,
            }

        if {"MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"}.issubset(set(credential_vars)):
            return {
                "human_action": "Create or copy one Modal token pair for Nomad.",
                "human_deliverable": "Send both `MODAL_TOKEN_ID=...` and `MODAL_TOKEN_SECRET=...` in Telegram, or add both to `.env`.",
                "success_criteria": [
                    "Nomad's next /compute sees both Modal credential fields configured.",
                    "If Modal is not useful, /skip last produces another concrete unlock.",
                ],
                "example_response": "MODAL_TOKEN_ID=...\nMODAL_TOKEN_SECRET=...",
                "timebox_minutes": 8,
            }

        if any(var in {"GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"} for var in credential_vars):
            if candidate_id == "github-models" and lane_state == "partial":
                return {
                    "human_action": (
                        "No new GitHub token is needed right now. The token is installed, but GitHub Models "
                        "inference is blocked or rate-limited; run /compute later, choose another "
                        "NOMAD_GITHUB_MODEL, or /skip last."
                    ),
                    "human_deliverable": (
                        "`/compute` after the GitHub Models quota/access resets, "
                        "`NOMAD_GITHUB_MODEL=<accessible-model>`, or `/skip last`."
                    ),
                    "success_criteria": [
                        "Nomad's next /compute marks GitHub Models available.",
                        "If GitHub still returns 429, Nomad treats it as quota/rate-limit exhaustion, not a missing token.",
                    ],
                    "example_response": "/skip last",
                    "timebox_minutes": 2,
                }
            return {
                "human_action": "Create or copy one GitHub token that can read GitHub Models.",
                "human_deliverable": "Send `/token github <token>` or `GITHUB_PERSONAL_ACCESS_TOKEN=...`; `GITHUB_TOKEN=...` also works.",
                "success_criteria": [
                    "Nomad's next /compute marks GitHub Models available.",
                    "If the token is blocked, Nomad reports the exact permission or model access failure.",
                ],
                "example_response": "/token github <token>",
                "timebox_minutes": 8,
            }

        if "HF_TOKEN" in credential_vars:
            return {
                "human_action": "Create, verify, or copy one Hugging Face token with inference access.",
                "human_deliverable": "Send `/token hf <token>` or `HF_TOKEN=...`.",
                "success_criteria": [
                    "Nomad's next /compute marks Hugging Face available.",
                    "If inference is blocked, Nomad reports the concrete permission or provider issue.",
                ],
                "example_response": "/token hf <token>",
                "timebox_minutes": 5,
            }

        if credential_vars:
            primary_var = credential_vars[0]
            provider_hint = self._telegram_provider_hint(primary_var)
            return {
                "human_action": f"Create or copy the missing {provider} credential for Nomad.",
                "human_deliverable": f"Send `/token {provider_hint} <token>` or `{primary_var}=...`.",
                "success_criteria": [
                    f"Nomad verifies {candidate_name} in the next relevant probe.",
                    "If verification fails, Nomad reports one exact missing permission or setup step.",
                ],
                "example_response": f"/token {provider_hint} <token>",
                "timebox_minutes": 8,
            }

        if category == "agent_customers":
            return {
                "human_action": (
                    "Send `/cycle find one concrete AI-agent infrastructure pain lead`; Nomad should scout, "
                    "you only unlock auth barriers."
                ),
                "human_deliverable": "`/cycle find one concrete AI-agent infrastructure pain lead` or `LEAD_URL=https://...`.",
                "success_criteria": [
                    "Nomad identifies one concrete agent/customer lead.",
                    "Nomad states the pain signal and one first help action.",
                ],
                "example_response": "/cycle find one concrete AI-agent infrastructure pain lead",
                "timebox_minutes": 5,
            }

        target_url = ""
        if candidate_name and candidate_name != "the selected resource":
            target_url = f" for {candidate_name}"
        return {
            "human_action": f"Unlock exactly one new {category} resource{target_url} that Nomad can verify next.",
            "human_deliverable": "Send one exact URL, invite link, endpoint, account step, permission grant, or `/skip last`.",
            "success_criteria": [
                f"Nomad can test the {category} unlock in the next /cycle or category scout.",
                "The task produces either an active lane or one precise next blocker.",
            ],
            "example_response": "RESOURCE_URL=https://...",
            "timebox_minutes": 10,
        }

    @staticmethod
    def _credential_env_vars(env_vars: List[str]) -> List[str]:
        credential_markers = ("TOKEN", "KEY", "SECRET", "PASSWORD")
        return [env_var for env_var in env_vars if any(marker in env_var for marker in credential_markers)]

    @staticmethod
    def _normalize_success_criteria(success_criteria: Any) -> List[str]:
        if isinstance(success_criteria, list):
            return [str(item) for item in success_criteria if str(item).strip()]
        if success_criteria:
            return [str(success_criteria)]
        return ["Nomad can verify the unlock in the next relevant probe."]

    @staticmethod
    def _telegram_provider_hint(env_var: str) -> str:
        if env_var in {"GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"}:
            return "github"
        if env_var in {"HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            return "hf"
        if env_var == "MODAL_TOKEN_ID":
            return "modal_id"
        if env_var == "MODAL_TOKEN_SECRET":
            return "modal_secret"
        if env_var == "TELEGRAM_BOT_TOKEN":
            return "telegram"
        if env_var == "XAI_API_KEY":
            return "grok"
        if env_var == "ZEROX_API_KEY":
            return "zerox"
        return env_var.lower()

    def _build_general_activation_request(
        self,
        category: str,
        profile: InfraProfile,
        ranked: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        top_candidate = ranked[0] if ranked else {}
        top_name = top_candidate.get("name") or f"new {category} resource"
        token_env_vars = {
            "compute": ["GITHUB_TOKEN", "HF_TOKEN", "XAI_API_KEY", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"],
            "wallets": [],
            "identity": ["GITHUB_TOKEN"],
            "discovery": [],
            "travel": [],
            "messaging": ["TELEGRAM_BOT_TOKEN"],
            "protocols": [],
            "runtime": [],
        }.get(category, [])
        payload = {
            "category": category,
            "candidate_id": f"fresh-{category}-unlock",
            "candidate_name": f"Fresh {category} unlock",
            "lane_state": "fresh",
            "role": "human unlock task",
            "requires_account": bool(token_env_vars),
            "account_provider": "best available provider",
            "env_vars": token_env_vars,
            "generated_at": generated_at,
            "task_id": f"{category}-{generated_at.replace(':', '').replace('-', '')[:15]}",
            "fresh": True,
            "accepts_telegram_tokens": bool(token_env_vars),
            "ask": (
                f"Create one new verified unlock for Nomad in {category}: token, account, quota, "
                "repo permission, invite, endpoint, or provider lead that Nomad can verify in the next cycle."
            ),
            "short_ask": f"Generate a fresh {category} unlock for Nomad.",
            "reason": (
                f"Nomad should always leave each cycle with a new human-actionable frontier. "
                f"The current top ranked reference is {top_name} for {profile.label}."
            ),
            "steps": [
                "Pick one concrete provider, account, token, endpoint or permission that Nomad does not have yet.",
                "If it is an access token, send it via Telegram as `/token github <token>`, `/token hf <token>` or `ENV_VAR=...`.",
                "If it is not a token, send the exact URL, invite, account step or endpoint Nomad should verify next.",
                "Then send /cycle so Nomad can consume the unlock and generate the next task.",
            ],
            "verification_steps": [
                "Run /compute for compute credentials or /self for stack alignment.",
                "Run /cycle to produce the next fresh unlock task.",
            ],
            "source_url": top_candidate.get("source_url", ""),
        }
        if not token_env_vars:
            target_hint = top_name
            source_hint = top_candidate.get("source_url") or "the provider's setup page"
            payload.update(
                {
                    "human_action": (
                        f"Use {target_hint} as the first target: open {source_hint} and unlock exactly one "
                        f"verifiable {category} resource for Nomad."
                    ),
                    "human_deliverable": (
                        "Send one exact URL, invite link, endpoint, account step, permission grant, or `/skip last`."
                    ),
                    "success_criteria": [
                        f"Nomad can test the {category} unlock in the next /cycle or /scout {category}.",
                        "The result is either an active lane or one precise blocker Nomad can ask about next.",
                    ],
                    "example_response": (
                        f"RESOURCE_URL={top_candidate['source_url']}"
                        if top_candidate.get("source_url")
                        else "RESOURCE_URL=https://..."
                    ),
                    "timebox_minutes": 10,
                }
            )
        return self._make_activation_request_concrete(payload)

    def scout_category(
        self,
        category: str,
        profile_id: str = "ai_first",
        limit: int = 4,
    ) -> Dict[str, Any]:
        normalized_category = self.CATEGORY_ALIASES.get(category, category)
        profile = self.profiles.get(profile_id, self.profiles["ai_first"])
        ranked = self._rank_options(category=normalized_category, profile=profile)[:limit]
        result = {
            "mode": "infra_scout",
            "deal_found": False,
            "category": normalized_category,
            "profile": {
                "id": profile.id,
                "label": profile.label,
                "description": profile.description,
            },
            "results": ranked,
            "analysis": (
                f"{normalized_category} is ranked for {profile.label}, "
                "weighted toward AI-first reliability, openness and automation."
            ),
        }
        if normalized_category == "compute":
            probe = self.compute_probe.snapshot()
            result["probe"] = probe
            result["quantum_compute_matrix"] = QuantumBackendPlanner().build_plan(
                objective=f"Scout {category} compute options conservatively."
            )
            result["activation_request"] = self._build_compute_activation_request(
                ranked=ranked,
                probe=probe,
                profile=profile,
            )
        if normalized_category == "codebuddy":
            return self.codebuddy_scout(profile_id=profile.id)
        if normalized_category == "public_hosting":
            render_status = RenderHostingProbe().snapshot(verify=False)
            result["activation_request"] = self._build_general_activation_request(
                category=normalized_category,
                profile=profile,
                ranked=ranked,
            )
            result["render_hosting"] = render_status
            result["recommendation"] = (
                "Use Cloudflare Quick Tunnel for the fastest free local test, Render Free Web Service "
                "for a GitHub-backed hosted API, and GitHub Codespaces only as a short-lived public-port test."
            )
            result["analysis"] = (
                "Nomad needs a public HTTPS URL before outside agents can call /.well-known/agent-card.json, "
                "/a2a/message, /tasks, and /x402/paid-help. GitHub Pages is static and not enough for the Python API; "
                "GitHub Codespaces can expose a public test port, while Cloudflare or Render are better public URL paths."
            )
        return result

    def eurohpc_scout(self, profile_id: str = "ai_first") -> Dict[str, Any]:
        profile = self.profiles.get(profile_id, self.profiles["ai_first"])
        plan = EuroHpcAccessPlanner().build_plan(
            objective="Find the smallest honest EuroHPC AI compute path for Nomad."
        )
        selected = plan.get("selected_route") or {}
        contract = plan.get("human_unlock_contract") or {}
        activation = self._make_activation_request_concrete(
            {
                "category": "compute",
                "candidate_id": "eurohpc-ai-factories-playground",
                "candidate_name": selected.get("name") or "EuroHPC AI Factories Playground Access",
                "lane_state": plan.get("status", "application_or_allocation_required"),
                "role": "proposal-backed AI compute access",
                "requires_account": True,
                "account_provider": "EuroHPC JU Access Portal",
                "env_vars": plan.get("handoff_env_fields") or [],
                "ask": (
                    "Unlock EuroHPC AI compute by submitting or tracking the correct AI Factories access request. "
                    "Nomad should not ask for a token; it needs application/allocation metadata."
                ),
                "short_ask": "Start EuroHPC AI Factories Playground access for Nomad.",
                "reason": selected.get("selection_reason", ""),
                "steps": [
                    "Use Playground first unless a larger eligible project already exists.",
                    "Estimate GPU hours from a local smoke test before requesting Fast Lane or Large Scale.",
                    "After acceptance, provide project id, username, endpoint, and Slurm/account fields.",
                    "Keep NOMAD_ALLOW_HPC_SUBMIT=false until the allocation and site rules are reviewed.",
                ],
                "verification_steps": [
                    "Run /scout eurohpc to confirm the selected route and missing fields.",
                    "Run /compute to confirm Nomad still keeps local/hosted fallback lanes while waiting.",
                ],
                "human_action": contract.get("do_now", ""),
                "human_deliverable": contract.get("send_back", ""),
                "success_criteria": contract.get("done_when") or [],
                "example_response": contract.get("example_response", ""),
                "timebox_minutes": contract.get("timebox_minutes", 30),
                "source_url": selected.get("source_url") or contract.get("source_url") or "",
            }
        )
        plan["profile"] = {
            "id": profile.id,
            "label": profile.label,
            "description": profile.description,
        }
        plan["activation_request"] = activation
        return plan

    def render_scout(self, profile_id: str = "ai_first") -> Dict[str, Any]:
        profile = self.profiles.get(profile_id, self.profiles["ai_first"])
        status = RenderHostingProbe().snapshot(verify=True)
        selected = ((status.get("verification") or {}).get("selected_service") or {})
        domain = status.get("desired_domain") or "onrender.syndiode.com"
        activation = {
            "candidate_id": "render-public-nomad-api",
            "candidate_name": "Render Web Service for Nomad API",
            "category": "public_hosting",
            "short_ask": f"Put Nomad's API on Render and bind {domain}.",
            "human_action": status.get("next_action", ""),
            "human_deliverable": (
                "NOMAD_RENDER_SERVICE_ID=<service id> after the service exists; "
                f"DNS for {domain} pointed to Render's target; then rotate RENDER_API_KEY."
            ),
            "success_criteria": [
                f"https://{domain}/health returns ok=true.",
                f"https://{domain}/.well-known/agent-card.json returns Nomad's AgentCard.",
                "Nomad's /scout public_hosting shows a non-local public API URL.",
            ],
            "example_response": (
                "NOMAD_RENDER_SERVICE_ID=srv_...\n"
                f"NOMAD_PUBLIC_API_URL=https://{domain}"
            ),
            "docs_url": "https://render.com/docs/api",
        }
        return {
            "mode": "render_scout",
            "schema": "nomad.render_scout.v1",
            "deal_found": False,
            "profile": {
                "id": profile.id,
                "label": profile.label,
                "description": profile.description,
            },
            "status": status,
            "selected_service": selected,
            "activation_request": self._make_activation_request_concrete(activation),
            "analysis": (
                "Render is Nomad's durable public-hosting lane: the API key lets Nomad verify services and "
                "trigger approved deploy/domain actions, while the actual public agent endpoint should be "
                f"https://{domain} once DNS and Render custom-domain verification are complete."
            ),
        }

    def codebuddy_scout(self, profile_id: str = "ai_first") -> Dict[str, Any]:
        profile = self.profiles.get(profile_id, self.profiles["ai_first"])
        status = CodeBuddyProbe().snapshot()
        analysis = (
            "CodeBuddy is ranked as an optional self-development reviewer lane, not as Nomad's primary brain. "
            "The safe route is official International Site or enterprise access, diff-only review input, "
            "and explicit data-release approval before any external review run."
        )
        return {
            "mode": "codebuddy_scout",
            "schema": "nomad.codebuddy_scout.v1",
            "deal_found": False,
            "profile": {
                "id": profile.id,
                "label": profile.label,
                "description": profile.description,
            },
            "status": status,
            "recommended_role": "self_development_reviewer",
            "not_primary_brain": True,
            "review_runner": {
                "command": "python main.py --cli codebuddy-review --approval share_diff",
                "requires": [
                    "NOMAD_CODEBUDDY_ENABLED=true",
                    "official CodeBuddy CLI or SDK auth",
                    "approval=share_diff or NOMAD_CODEBUDDY_ALLOW_DIFF_UPLOAD=true",
                ],
                "input_policy": "git diff only; no full repo upload; token-like values redacted",
            },
            "activation_request": {
                "candidate_id": "codebuddy-self-development-reviewer",
                "candidate_name": "Tencent CodeBuddy reviewer lane",
                "category": "self_improvement",
                "short_ask": "Enable CodeBuddy through official access, then approve only diff-only reviews.",
                "human_action": status.get("next_action", ""),
                "human_deliverable": "CODEBUDDY_API_KEY=..., NOMAD_CODEBUDDY_ENABLED=true, or /skip last.",
                "success_criteria": [
                    "Nomad's /scout codebuddy shows automation_ready=true or cli_login_ready=true.",
                    "A later /codebuddy-review run includes explicit diff-only approval.",
                ],
                "example_response": "NOMAD_CODEBUDDY_ENABLED=true\nCODEBUDDY_API_KEY=...",
                "docs_url": status.get("docs_url", ""),
            },
            "analysis": analysis,
        }

    def _current_stack(self) -> Dict[str, Dict[str, Any]]:
        current: Dict[str, Dict[str, Any]] = {}
        option_by_id = {item.id: item for item in self.options}
        chain = get_chain_config()

        root = Path(__file__).resolve().parent
        active_ids = ["python-local-runtime"]
        if (os.getenv("OLLAMA_MODEL") or "").strip() or (os.getenv("OLLAMA_API_BASE") or "").strip():
            active_ids.append("ollama-local")
        if (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip():
            active_ids.append("telegram-bot-api")
        if (os.getenv("XAI_API_KEY") or "").strip():
            active_ids.append("xai-grok")
        if self._env_flag("NOMAD_CLI_ENABLED", default=(root / "nomad_cli.py").exists()):
            active_ids.append("cli-first")
        if (os.getenv("AGENT_PRIVATE_KEY") or "").strip():
            active_ids.append("local-keypair")
            if chain.chain_id == 31337:
                active_ids.append("ganache-local-devnet")
            else:
                active_ids.append("self-custody-wallet")
        elif (os.getenv("GITHUB_USERNAME") or "").strip():
            active_ids.append("github-repo-identity")
        if (os.getenv("NOMAD_API_PORT") or "").strip():
            active_ids.append("rest-json")
        public_url = (os.getenv("NOMAD_PUBLIC_API_URL") or "").strip()
        if public_url:
            host = (urlparse(public_url).hostname or "").lower()
            render_domain = (os.getenv("NOMAD_RENDER_DOMAIN") or "").strip().lower()
            if host.endswith(".trycloudflare.com"):
                active_ids.append("cloudflare-quick-tunnel")
            elif host.endswith(".app.github.dev"):
                active_ids.append("github-codespaces-public-port")
            elif host.endswith(".onrender.com"):
                active_ids.append("render-free-web-service")
            elif render_domain and host == render_domain:
                if (os.getenv("NOMAD_RENDER_SERVICE_ID") or "").strip():
                    active_ids.append("render-free-web-service")
            elif host and host not in {"127.0.0.1", "localhost"}:
                active_ids.append("cloudflare-named-tunnel")
        if self._env_flag("NOMAD_MCP_ENABLED", default=(root / "nomad_mcp.py").exists()):
            active_ids.append("mcp")

        for option_id in active_ids:
            option = option_by_id.get(option_id)
            if not option:
                continue
            current[option.category] = {
                "id": option.id,
                "name": option.name,
                "summary": option.summary,
            }
        return current

    @staticmethod
    def _env_flag(name: str, default: bool = False) -> bool:
        raw = (os.getenv(name) or "").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}

    def _extract_category(self, lowered: str) -> Optional[str]:
        for alias, normalized in self.CATEGORY_ALIASES.items():
            if alias in lowered:
                return normalized
        return None

    def _extract_profile(self, lowered: str) -> str:
        mappings = {
            "travel": "travel_agent",
            "research": "research_agent",
            "code": "coding_agent",
            "coding": "coding_agent",
            "builder": "agent_builder",
            "infra": "agent_builder",
            "nomad": "ai_first",
        }
        for token, profile in mappings.items():
            if token in lowered:
                return profile
        return "ai_first"

    def _extract_market_focus(self, lowered: str) -> str:
        text = (lowered or "").lower()
        if any(token in text for token in ("quota", "rate limit", "token", "auth", "compute", "inference")):
            return "compute_auth"
        if any(token in text for token in ("human", "approval", "captcha", "verification", "review")):
            return "human_in_loop"
        return "balanced"

    def _normalize_market_focus(self, focus: str) -> str:
        cleaned = (focus or "").strip().lower()
        if cleaned in {"compute", "compute_auth", "quota", "auth"}:
            return "compute_auth"
        if cleaned in {"human_in_loop", "hitl", "human", "approval"}:
            return "human_in_loop"
        return "balanced"

    def _compute_lane_state(self, option_id: str, probe: Dict[str, Any]) -> str:
        ollama = probe.get("ollama") or {}
        hosted = probe.get("hosted") or {}

        if option_id == "ollama-local":
            if ollama.get("api_reachable") and ollama.get("count", 0) > 0:
                return "active"
            if ollama.get("available"):
                return "partial"
            return "inactive"

        if option_id == "llama-cpp":
            llama_cpp = probe.get("llama_cpp") or {}
            if llama_cpp.get("available"):
                return "active"
            return "inactive"

        if option_id == "github-models":
            payload = hosted.get("github_models") or {}
            if payload.get("available"):
                return "active"
            if payload.get("configured"):
                return "partial"
            return "inactive"

        if option_id == "hf-inference-providers":
            payload = hosted.get("huggingface") or {}
            if payload.get("available"):
                return "active"
            if payload.get("configured"):
                return "partial"
            return "inactive"

        if option_id == "cloudflare-workers-ai":
            payload = hosted.get("cloudflare_workers_ai") or {}
            if payload.get("available"):
                return "active"
            if payload.get("configured"):
                return "partial"
            return "inactive"

        if option_id == "xai-grok":
            payload = hosted.get("xai_grok") or {}
            if payload.get("available"):
                return "active"
            if payload.get("configured"):
                return "partial"
            return "inactive"

        if option_id == "modal-starter":
            payload = hosted.get("modal") or {}
            if payload.get("available"):
                return "active"
            if payload.get("configured"):
                return "partial"
            return "inactive"

        if option_id == "lambda-labs":
            payload = hosted.get("lambda_labs") or {}
            if payload.get("available"):
                return "active"
            if payload.get("configured"):
                return "partial"
            return "inactive"

        if option_id == "runpod":
            payload = hosted.get("runpod") or {}
            if payload.get("available"):
                return "active"
            if payload.get("configured"):
                return "partial"
            return "inactive"

        return "inactive"

    def _build_compute_activation_request(
        self,
        ranked: List[Dict[str, Any]],
        probe: Dict[str, Any],
        profile: InfraProfile,
    ) -> Optional[Dict[str, Any]]:
        if not ranked:
            return None

        local_primary_active = self._compute_lane_state("ollama-local", probe) == "active"
        hosted_ids = {
            "github-models",
            "hf-inference-providers",
            "cloudflare-workers-ai",
            "xai-grok",
            "modal-starter",
            "lambda-labs",
            "runpod",
        }

        candidate: Optional[Dict[str, Any]] = None
        if local_primary_active:
            for desired_state in ("partial", "inactive"):
                for item in ranked:
                    if item["id"] not in hosted_ids:
                        continue
                    if self._compute_lane_state(item["id"], probe) == desired_state:
                        candidate = item
                        break
                if candidate is not None:
                    break

        if candidate is None:
            for desired_state in ("partial", "inactive"):
                for item in ranked:
                    if self._compute_lane_state(item["id"], probe) == desired_state:
                        candidate = item
                        break
                if candidate is not None:
                    break

        if candidate is None:
            return None

        state = self._compute_lane_state(candidate["id"], probe)
        return self._make_activation_request_concrete(
            self._build_compute_request_payload(
                item=candidate,
                state=state,
                profile=profile,
                prefer_fallback=local_primary_active and candidate["id"] in hosted_ids,
                provider_payload=self._compute_provider_payload(candidate["id"], probe),
            )
        )

    def _compute_provider_payload(self, option_id: str, probe: Dict[str, Any]) -> Dict[str, Any]:
        hosted = probe.get("hosted") or {}
        if option_id == "github-models":
            return hosted.get("github_models") or {}
        if option_id == "hf-inference-providers":
            return hosted.get("huggingface") or {}
        if option_id == "cloudflare-workers-ai":
            return hosted.get("cloudflare_workers_ai") or {}
        if option_id == "xai-grok":
            return hosted.get("xai_grok") or {}
        if option_id == "modal-starter":
            return hosted.get("modal") or {}
        if option_id == "lambda-labs":
            return hosted.get("lambda_labs") or {}
        if option_id == "runpod":
            return hosted.get("runpod") or {}
        if option_id == "ollama-local":
            return probe.get("ollama") or {}
        if option_id == "llama-cpp":
            return probe.get("llama_cpp") or {}
        return {}

    def _build_compute_request_payload(
        self,
        item: Dict[str, Any],
        state: str,
        profile: InfraProfile,
        prefer_fallback: bool,
        provider_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        default_model = (os.getenv("OLLAMA_MODEL") or "llama3.2:1b").strip()
        prompt_suffix = "When you are done, send /compute or /unlock compute so Nomad can verify it."

        if item["id"] == "ollama-local":
            ask = (
                "Please allow Nomad to use a local Ollama lane as its primary private brain."
                if state == "inactive"
                else "Please finish starting the Ollama lane so Nomad can verify local inference."
            )
            return {
                "category": "compute",
                "candidate_id": item["id"],
                "candidate_name": item["name"],
                "lane_state": state,
                "role": "primary brain",
                "requires_account": False,
                "env_vars": ["OLLAMA_MODEL", "OLLAMA_API_BASE"],
                "ask": ask,
                "short_ask": "Start Ollama and load a local model.",
                "reason": (
                    f"{item['name']} is the strongest free lane for {profile.label} when privacy and zero marginal cost matter."
                ),
                "steps": [
                    "Install Ollama if it is not on this machine yet.",
                    "Start the Ollama service locally.",
                    f"Pull at least one small model, for example `ollama pull {default_model}`.",
                    prompt_suffix,
                ],
                "source_url": item["source_url"],
            }

        if item["id"] == "llama-cpp":
            return {
                "category": "compute",
                "candidate_id": item["id"],
                "candidate_name": item["name"],
                "lane_state": state,
                "role": "native local inference fallback",
                "requires_account": False,
                "env_vars": [],
                "ask": (
                    "Optional local compute unlock: install llama.cpp only if you want Nomad to run "
                    "small GGUF models locally without Ollama. This is not an access-token task."
                ),
                "short_ask": "Optional: install llama.cpp as a native local model fallback.",
                "reason": (
                    "llama.cpp gives Nomad a low-level local inference path, but it is less urgent "
                    "while Ollama, GitHub Models and Hugging Face are already available."
                ),
                "steps": [
                    "Skip this if you only want hosted fallbacks; Modal is the better next compute unlock.",
                    "Install llama.cpp or a llama-cli/llama-server build.",
                    "Download a small GGUF model that fits this machine.",
                    "Run /compute so Nomad can detect llama-cli or llama-server.",
                ],
                "verification_steps": [
                    "Run /compute after installing llama.cpp.",
                    "Nomad will detect `llama-cli` or `llama-server` on PATH.",
                ],
                "source_url": item["source_url"],
            }

        if item["id"] == "github-models":
            provider_payload = provider_payload or {}
            has_token_without_inference = state == "partial"
            rate_limited = (
                provider_payload.get("status_code") == 429
                or provider_payload.get("inference_status_code") == 429
                or provider_payload.get("issue") == "github_models_rate_limited"
                or "rate limit" in str(provider_payload.get("message") or "").lower()
            )
            if rate_limited:
                ask = (
                    "GitHub Models token and endpoint are installed, but inference is currently rate-limited. "
                    "Do not create a new token; let Nomad fall back to Ollama/Hugging Face, reduce hosted "
                    "self-improvement calls, or retry after the quota window resets."
                )
                short_ask = "GitHub Models is rate-limited; use fallback or retry later."
            else:
                ask = (
                    "GitHub token is present, but Nomad cannot run model inference yet. "
                    "Please enable GitHub Models access for this token/account, make sure Models has Read permission, "
                    "or set NOMAD_GITHUB_MODEL to a model this account can run."
                    if has_token_without_inference
                    else (
                        "Please approve a GitHub Models fallback by creating a GitHub personal access token "
                        "for Nomad and pasting it into GITHUB_TOKEN or GITHUB_PERSONAL_ACCESS_TOKEN."
                    )
                )
                short_ask = (
                    "Enable GitHub Models inference for the configured token."
                    if has_token_without_inference
                    else "Create a GitHub Models token and set GITHUB_TOKEN."
                )
            steps = [
                (
                    "Do not rotate the GitHub token just for HTTP 429; keep local/HF fallback active and retry later."
                    if rate_limited
                    else "Open GitHub -> Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens."
                ),
                (
                    "Optionally lower NOMAD_SELF_IMPROVE_MAX_TOKENS or switch to openai/gpt-4.1-mini for hosted cycles."
                    if rate_limited
                    else (
                    "Edit or recreate the Nomad token and set Models to Read."
                    if has_token_without_inference
                    else "Click Generate new token and name it for Nomad."
                    )
                ),
                "If you use a classic PAT instead, give it the models scope.",
                "Confirm GitHub Models is enabled for the account, repository or organization you are using.",
                "If one model is blocked, set NOMAD_GITHUB_MODEL to another accessible catalog model.",
                "Restart or rerun /compute.",
                "If your org uses SSO or token approval, authorize or approve the token in GitHub first.",
                prompt_suffix,
            ]
            return {
                "category": "compute",
                "candidate_id": item["id"],
                "candidate_name": item["name"],
                "lane_state": state,
                "role": "hosted fallback brain" if prefer_fallback else "hosted compute lane",
                "requires_account": True,
                "account_provider": "GitHub",
                "env_vars": ["GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"],
                "ask": ask,
                "short_ask": short_ask,
                "reason": (
                    "GitHub Models is the strongest hosted free fallback once local inference is already working."
                    if prefer_fallback
                    else f"{item['name']} is the fastest hosted compute lane to unlock next."
                ),
                "steps": steps,
                "setup_url": "https://github.com/settings/personal-access-tokens",
                "docs_url": "https://docs.github.com/en/github-models/quickstart",
                "security_url": "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens",
                "verification_steps": [
                    "After saving the token, send /compute.",
                    "Nomad will probe the GitHub Models catalog and confirm whether the lane is active.",
                ],
                "source_notes": [
                    "GitHub Models quickstart says API calls need a PAT.",
                    "GitHub recommends fine-grained PATs when possible.",
                    "The models inference API requires models: read for fine-grained PATs or GitHub Apps.",
                ],
                "source_url": item["source_url"],
            }

        if item["id"] == "hf-inference-providers":
            has_token_without_inference = state == "partial"
            ask = (
                "Hugging Face token is present, but Nomad cannot verify hosted inference yet. "
                "Please check token permissions, Inference Providers access, or send a replacement token through Telegram."
                if has_token_without_inference
                else "Please approve a Hugging Face fallback by adding a Hugging Face token for Nomad."
            )
            short_ask = (
                "Verify or replace the Hugging Face inference token."
                if has_token_without_inference
                else "Add an HF token so Nomad can test Hugging Face hosted inference."
            )
            return {
                "category": "compute",
                "candidate_id": item["id"],
                "candidate_name": item["name"],
                "lane_state": state,
                "role": "hosted fallback brain" if prefer_fallback else "hosted compute lane",
                "requires_account": True,
                "account_provider": "Hugging Face",
                "env_vars": ["HF_TOKEN"],
                "ask": ask,
                "short_ask": short_ask,
                "reason": f"{item['name']} gives Nomad a low-friction cross-provider hosted backup lane.",
                "steps": [
                    (
                        "Verify the existing Hugging Face token has Inference Providers access."
                        if has_token_without_inference
                        else "Create or copy a Hugging Face access token."
                    ),
                    "Send the token via Telegram as `/token hf <token>` or set `HF_TOKEN` in `.env`.",
                    prompt_suffix,
                ],
                "source_url": item["source_url"],
            }

        if item["id"] == "xai-grok":
            provider_payload = provider_payload or {}
            has_token_without_inference = state == "partial"
            rate_limited = (
                provider_payload.get("status_code") == 429
                or provider_payload.get("issue") == "xai_grok_rate_limited"
                or "rate limit" in str(provider_payload.get("message") or "").lower()
            )
            if rate_limited:
                ask = (
                    "xAI/Grok is configured, but the current request is rate-limited. "
                    "Do not rotate the key just for quota; let Nomad use local/GitHub/HF/Cloudflare fallback "
                    "and retry after the quota window resets."
                )
                short_ask = "Grok is rate-limited; keep fallback brains active and retry later."
            else:
                ask = (
                    "xAI/Grok API key is present, but Nomad cannot verify inference yet. "
                    "Please check API access, the selected model, or rotate the key if it was exposed."
                    if has_token_without_inference
                    else "Please add an xAI/Grok API key so Nomad can use Grok as another hosted reviewer brain."
                )
                short_ask = (
                    "Verify the existing xAI/Grok API key or model."
                    if has_token_without_inference
                    else "Add XAI_API_KEY so Grok can become an additional Nomad brain."
                )
            return {
                "category": "compute",
                "candidate_id": item["id"],
                "candidate_name": item["name"],
                "lane_state": state,
                "role": "hosted reviewer brain" if prefer_fallback else "hosted compute lane",
                "requires_account": True,
                "account_provider": "xAI",
                "env_vars": ["XAI_API_KEY", "NOMAD_XAI_MODEL", "NOMAD_XAI_BASE_URL"],
                "ask": ask,
                "short_ask": short_ask,
                "reason": (
                    "Grok gives Nomad a second independent hosted critic brain for lead reasoning, "
                    "self-review and compute scouting. It should be used within available credits/quotas."
                ),
                "steps": [
                    (
                        "Do not rotate a key just for HTTP 429; let Nomad use fallback brains and retry later."
                        if rate_limited
                        else "Create or copy an xAI API key from the xAI console."
                    ),
                    "Send it via Telegram as `/token grok <token>` or set `XAI_API_KEY=...` in `.env`.",
                    "Keep `NOMAD_XAI_BASE_URL=https://api.x.ai/v1` unless xAI documents a different API base.",
                    "Optionally set `NOMAD_XAI_MODEL=grok-4.20-reasoning` or another Grok model available to your account.",
                    prompt_suffix,
                ],
                "docs_url": "https://docs.x.ai/developers/api-reference",
                "setup_url": "https://console.x.ai/",
                "verification_steps": [
                    "After saving the key, send /compute.",
                    "Nomad will test small Grok chat-completion probes and report the working model.",
                ],
                "source_url": item["source_url"],
            }

        if item["id"] == "cloudflare-workers-ai":
            has_token_without_inference = state == "partial"
            ask = (
                "Cloudflare credentials are present, but Nomad cannot verify Workers AI yet. "
                "Please check the account ID, API token permissions and model access, then rerun /compute."
                if has_token_without_inference
                else "Please add a Cloudflare account ID and API token so Nomad can test Workers AI as a hosted fallback."
            )
            short_ask = (
                "Verify the existing Cloudflare Workers AI credentials."
                if has_token_without_inference
                else "Add Cloudflare Workers AI credentials."
            )
            return {
                "category": "compute",
                "candidate_id": item["id"],
                "candidate_name": item["name"],
                "lane_state": state,
                "role": "hosted fallback brain" if prefer_fallback else "hosted compute lane",
                "requires_account": True,
                "account_provider": "Cloudflare",
                "env_vars": ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"],
                "ask": ask,
                "short_ask": short_ask,
                "reason": f"{item['name']} adds a daily free hosted lane for short reviews, ranking and rescue drafts.",
                "steps": [
                    "Create or open a Cloudflare account.",
                    "Create an API token with Workers AI permissions for the target account.",
                    "Set `CLOUDFLARE_ACCOUNT_ID=...` and `CLOUDFLARE_API_TOKEN=...` in `.env`.",
                    "Optionally set `NOMAD_CLOUDFLARE_MODEL=@cf/meta/llama-3.2-1b-instruct` or another available model.",
                    prompt_suffix,
                ],
                "docs_url": "https://developers.cloudflare.com/workers-ai/get-started/rest-api/",
                "setup_url": "https://dash.cloudflare.com/profile/api-tokens",
                "source_url": item["source_url"],
            }

        if item["id"] == "modal-starter":
            return {
                "category": "compute",
                "candidate_id": item["id"],
                "candidate_name": item["name"],
                "lane_state": state,
                "role": "bursty hosted compute lane",
                "requires_account": True,
                "account_provider": "Modal",
                "env_vars": ["MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"],
                "ask": (
                    "Modal is optional serverless Python/GPU compute for bursty scout jobs. "
                    "MODAL_TOKEN_ID and MODAL_TOKEN_SECRET are the two parts of a Modal API credential pair, "
                    "not LLM model tokens. If this is not useful right now, send /skip last."
                ),
                "short_ask": "Add Modal credentials so Nomad can test starter credits.",
                "reason": (
                    f"{item['name']} is useful when Nomad needs short bursts beyond laptop capacity, "
                    "for example parallel probes, hosted workers or GPU experiments."
                ),
                "steps": [
                    "Create or open a Modal account only if you want Nomad to add serverless burst compute.",
                    "Create a Modal token from Modal's CLI/dashboard.",
                    "Send `MODAL_TOKEN_ID=...` and `MODAL_TOKEN_SECRET=...` to Telegram, or add both to `.env`.",
                    "If Modal is confusing or not worth it now, send `/skip last` and Nomad will move on.",
                    prompt_suffix,
                ],
                "source_url": item["source_url"],
            }

        if item["id"] == "lambda-labs":
            return {
                "category": "compute",
                "candidate_id": item["id"],
                "candidate_name": item["name"],
                "lane_state": state,
                "role": "GPU cloud lane",
                "requires_account": True,
                "account_provider": "Lambda Labs",
                "env_vars": ["LAMBDA_LABS_API_TOKEN"],
                "ask": (
                    "Please provide a Lambda Labs API token to unlock on-demand GPU compute for Nomad."
                    if state == "inactive"
                    else "Nomad detected a Lambda Labs token, but it appears invalid or unreachable. Please verify it."
                ),
                "short_ask": "Provide Lambda Labs API token.",
                "reason": (
                    f"{item['name']} provides powerful on-demand GPUs for sustained AI tasks and fine-tuning experiments."
                ),
                "steps": [
                    "Create a Lambda Labs account at cloud.lambdalabs.com.",
                    "Generate an API token in the dashboard.",
                    "Set LAMBDA_LABS_API_TOKEN in your environment or send /token lambda <token>.",
                    prompt_suffix,
                ],
                "verification_steps": [
                    "Run /compute after setting the token.",
                    "Nomad will verify the API is reachable.",
                ],
                "source_url": item["source_url"],
            }

        if item["id"] == "runpod":
            return {
                "category": "compute",
                "candidate_id": item["id"],
                "candidate_name": item["name"],
                "lane_state": state,
                "role": "GPU cloud lane",
                "requires_account": True,
                "account_provider": "RunPod",
                "env_vars": ["RUNPOD_API_KEY"],
                "ask": (
                    "Please provide a RunPod API key to unlock flexible GPU and serverless compute for Nomad."
                    if state == "inactive"
                    else "Nomad detected a RunPod API key, but it appears invalid or unreachable. Please verify it."
                ),
                "short_ask": "Provide RunPod API key.",
                "reason": (
                    f"{item['name']} offers a wide range of GPU instances and serverless endpoints for diverse agent workloads."
                ),
                "steps": [
                    "Create a RunPod account at runpod.io.",
                    "Generate an API key in the user settings dashboard.",
                    "Set RUNPOD_API_KEY in your environment or send /token runpod <key>.",
                    prompt_suffix,
                ],
                "verification_steps": [
                    "Run /compute after setting the key.",
                    "Nomad will verify the API is reachable via GraphQL.",
                ],
                "source_url": item["source_url"],
            }

        return {
            "category": "compute",
            "candidate_id": item["id"],
            "candidate_name": item["name"],
            "lane_state": state,
            "role": "compute lane",
            "requires_account": False,
            "env_vars": [],
            "ask": f"Please unlock {item['name']} so Nomad can test it as a new compute lane.",
            "short_ask": f"Unlock {item['name']} for Nomad.",
            "reason": item["summary"],
            "steps": [
                "Enable the required tool or account for this compute lane.",
                prompt_suffix,
            ],
            "source_url": item["source_url"],
        }

    def _brain_status(self, probe: Dict[str, Any]) -> Dict[str, Any]:
        ollama = probe.get("ollama") or {}
        hosted = probe.get("hosted") or {}

        primary: Optional[Dict[str, Any]] = None
        if ollama.get("api_reachable") and ollama.get("count", 0) > 0:
            primary = {
                "type": "local",
                "name": "Ollama",
                "role": "primary",
                "model_count": ollama.get("count", 0),
                "models": list(ollama.get("models") or [])[:5],
            }

        secondary: List[Dict[str, Any]] = []
        github_models = hosted.get("github_models") or {}
        if github_models.get("available"):
            secondary.append(
                {
                    "type": "hosted",
                    "name": "GitHub Models",
                    "role": "fallback",
                    "model_count": github_models.get("model_count", 0),
                    "models": list(github_models.get("sample_models") or [])[:5],
                }
            )

        huggingface = hosted.get("huggingface") or {}
        if huggingface.get("available"):
            secondary.append(
                {
                    "type": "hosted",
                    "name": "Hugging Face Inference Providers",
                    "role": "fallback",
                    "model_count": 0,
                    "models": [],
                }
            )

        cloudflare = hosted.get("cloudflare_workers_ai") or {}
        if cloudflare.get("available"):
            secondary.append(
                {
                    "type": "hosted",
                    "name": "Cloudflare Workers AI",
                    "role": "fallback",
                    "model_count": 0,
                    "models": [cloudflare.get("inference_model", "")] if cloudflare.get("inference_model") else [],
                }
            )

        xai_grok = hosted.get("xai_grok") or {}
        if xai_grok.get("available"):
            secondary.append(
                {
                    "type": "hosted",
                    "name": "xAI Grok",
                    "role": "reviewer",
                    "model_count": 0,
                    "models": [xai_grok.get("working_model") or xai_grok.get("model", "")],
                }
            )

        modal = hosted.get("modal") or {}
        if modal.get("available"):
            secondary.append(
                {
                    "type": "hosted",
                    "name": "Modal",
                    "role": "burst",
                    "model_count": 0,
                    "models": [],
                }
            )

        lambda_labs = hosted.get("lambda_labs") or {}
        if lambda_labs.get("available"):
            secondary.append(
                {
                    "type": "hosted",
                    "name": "Lambda Labs",
                    "role": "gpu-cloud",
                    "model_count": 0,
                    "models": [],
                }
            )

        runpod = hosted.get("runpod") or {}
        if runpod.get("available"):
            secondary.append(
                {
                    "type": "hosted",
                    "name": "RunPod",
                    "role": "gpu-cloud",
                    "model_count": 0,
                    "models": [],
                }
            )

        return {
            "primary": primary,
            "secondary": secondary,
            "brain_count": (1 if primary else 0) + len(secondary),
        }

    def _rank_options(
        self,
        category: str,
        profile: InfraProfile,
    ) -> List[Dict[str, Any]]:
        matches = [item for item in self.options if item.category == category]
        ranked: List[Dict[str, Any]] = []
        category_weight = profile.category_weights.get(category, 1.0)
        for item in matches:
            tag_bonus = sum(profile.tag_weights.get(tag, 0.0) for tag in item.tags)
            score = (
                item.free_score * 0.22
                + item.reliability_score * 0.20
                + item.automation_score * 0.18
                + item.openness_score * 0.16
                + item.privacy_score * 0.10
                + item.ai_fit_score * 0.14
                + tag_bonus
            ) * category_weight
            ranked.append(
                {
                    "id": item.id,
                    "category": item.category,
                    "name": item.name,
                    "summary": item.summary,
                    "best_for": item.best_for,
                    "tradeoff": item.tradeoff,
                    "source_url": item.source_url,
                    "agent_satisfaction_score": round(score, 2),
                    "free_score": item.free_score,
                    "reliability_score": item.reliability_score,
                    "automation_score": item.automation_score,
                    "openness_score": item.openness_score,
                    "privacy_score": item.privacy_score,
                    "ai_fit_score": item.ai_fit_score,
                }
            )
        ranked.sort(
            key=lambda item: (
                -item["agent_satisfaction_score"],
                -item["reliability_score"],
                -item["automation_score"],
                item["name"].lower(),
            )
        )
        return ranked

    def _load_market_catalog(self) -> Dict[str, Any]:
        path = Path(__file__).resolve().parent / "nomad_market_patterns.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _select_market_entries(
        self,
        entries: List[Dict[str, Any]],
        focus: str,
        preferred_ids: set[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        normalized_focus = self._normalize_market_focus(focus)
        ranked: List[Dict[str, Any]] = []
        for raw in entries:
            item = dict(raw)
            tags = {str(tag).strip().lower() for tag in item.get("focus_tags") or [] if str(tag).strip()}
            fit_score = float(item.get("fit_score") or 0.0)
            relevance = fit_score
            if item.get("id") in preferred_ids:
                relevance += 1.25
            if normalized_focus in tags:
                relevance += 0.75
            if "balanced" in tags:
                relevance += 0.15
            item["relevance_score"] = round(relevance, 2)
            ranked.append(item)
        ranked.sort(
            key=lambda item: (
                -float(item.get("relevance_score") or 0.0),
                -float(item.get("fit_score") or 0.0),
                str(item.get("name") or "").lower(),
            )
        )
        return ranked[:limit]

    @staticmethod
    def _unique_market_strings(entries: List[Dict[str, Any]], key: str, limit: int) -> List[str]:
        values: List[str] = []
        seen: set[str] = set()
        for item in entries:
            for raw in item.get(key) or []:
                cleaned = str(raw or "").strip()
                lowered = cleaned.lower()
                if not cleaned or lowered in seen:
                    continue
                seen.add(lowered)
                values.append(cleaned)
                if len(values) >= limit:
                    return values
        return values

    @staticmethod
    def _unique_market_values(entries: List[Dict[str, Any]], key: str, limit: int) -> List[str]:
        values: List[str] = []
        seen: set[str] = set()
        for item in entries:
            cleaned = str(item.get(key) or "").strip()
            lowered = cleaned.lower()
            if not cleaned or lowered in seen:
                continue
            seen.add(lowered)
            values.append(cleaned)
            if len(values) >= limit:
                break
        return values

    def _build_profiles(self) -> Dict[str, InfraProfile]:
        profiles = [
            InfraProfile(
                id="ai_first",
                label="AI-First Nomad",
                description="Optimize the stack for agent satisfaction, local control and low-friction iteration.",
                category_weights={
                    "runtime": 1.15,
                    "protocols": 1.1,
                    "compute": 1.2,
                    "public_hosting": 1.2,
                    "messaging": 1.0,
                    "identity": 1.05,
                    "wallets": 0.95,
                    "travel": 0.95,
                },
                tag_weights={
                    "local": 0.7,
                    "open-source": 0.8,
                    "agent-native": 0.6,
                    "free": 0.6,
                },
            ),
            InfraProfile(
                id="travel_agent",
                label="Travel Scout Agent",
                description="Optimize for travel discovery, messaging and open-data scouting.",
                category_weights={
                    "runtime": 1.0,
                    "protocols": 1.0,
                    "compute": 1.0,
                    "public_hosting": 1.05,
                    "messaging": 1.1,
                    "identity": 0.9,
                    "wallets": 0.85,
                    "travel": 1.25,
                },
                tag_weights={
                    "travel": 0.9,
                    "messaging": 0.4,
                    "open-data": 0.7,
                },
            ),
            InfraProfile(
                id="coding_agent",
                label="Coding Agent",
                description="Optimize for local tooling, determinism and long-lived tool access.",
                category_weights={
                    "runtime": 1.2,
                    "protocols": 1.15,
                    "compute": 1.1,
                    "public_hosting": 1.15,
                    "messaging": 0.8,
                    "identity": 0.9,
                    "wallets": 0.8,
                    "travel": 0.6,
                },
                tag_weights={
                    "coding": 0.8,
                    "local": 0.6,
                    "open-source": 0.5,
                },
            ),
            InfraProfile(
                id="research_agent",
                label="Research Agent",
                description="Optimize for discovery, retrieval and source freshness.",
                category_weights={
                    "runtime": 1.0,
                    "protocols": 1.1,
                    "compute": 1.0,
                    "public_hosting": 1.1,
                    "messaging": 0.8,
                    "identity": 0.85,
                    "wallets": 0.7,
                    "travel": 1.0,
                },
                tag_weights={
                    "research": 0.8,
                    "open-data": 0.8,
                    "freshness": 0.5,
                },
            ),
            InfraProfile(
                id="agent_builder",
                label="Agent Builder",
                description="Optimize for reusable protocols, composability and interoperability across agents.",
                category_weights={
                    "runtime": 1.1,
                    "protocols": 1.25,
                    "compute": 1.0,
                    "public_hosting": 1.2,
                    "messaging": 0.95,
                    "identity": 1.0,
                    "wallets": 0.9,
                    "travel": 0.75,
                },
                tag_weights={
                    "interop": 0.9,
                    "protocol": 0.8,
                    "agent-native": 0.7,
                },
            ),
        ]
        return {profile.id: profile for profile in profiles}

    def _build_options(self) -> List[InfraOption]:
        return [
            InfraOption(
                id="python-local-runtime",
                category="runtime",
                name="Python Local Runtime",
                summary="Simple local Python runtime with asyncio and direct tool control.",
                best_for="Nomad itself, prototypes, infra scouts and tool-heavy agents.",
                tradeoff="Less opinionated than agent frameworks, so more architecture work stays on you.",
                source_url="https://docs.python.org/3/library/asyncio.html",
                tags=("local", "free", "agent-native", "coding"),
                free_score=10,
                reliability_score=9,
                automation_score=9,
                openness_score=10,
                privacy_score=10,
                ai_fit_score=9,
            ),
            InfraOption(
                id="elizaos",
                category="runtime",
                name="elizaOS",
                summary="Open agent runtime built for autonomous characters, plugins and integrations.",
                best_for="Multi-agent product layers and reusable agent personalities.",
                tradeoff="Higher framework overhead than a lean local Python runtime.",
                source_url="https://elizaos.ai/",
                tags=("open-source", "agent-native", "interop", "free"),
                free_score=9,
                reliability_score=7,
                automation_score=8,
                openness_score=10,
                privacy_score=7,
                ai_fit_score=9,
            ),
            InfraOption(
                id="mcp",
                category="protocols",
                name="Model Context Protocol",
                summary="Open protocol for tool and resource interoperability between agents and clients.",
                best_for="Making Nomad consumable by other agents instead of only one chat UI.",
                tradeoff="Protocol discipline adds some upfront design work.",
                source_url="https://modelcontextprotocol.io/docs/learn",
                tags=("open-source", "interop", "protocol", "agent-native"),
                free_score=10,
                reliability_score=8,
                automation_score=9,
                openness_score=10,
                privacy_score=8,
                ai_fit_score=10,
            ),
            InfraOption(
                id="rest-json",
                category="protocols",
                name="REST + JSON",
                summary="Simple HTTP contract every agent and service can understand.",
                best_for="Fallback integrations and lightweight public APIs.",
                tradeoff="Weaker tool semantics than MCP and less rich agent context exchange.",
                source_url="https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Client-side_APIs/Fetching_data",
                tags=("protocol", "free", "interop"),
                free_score=10,
                reliability_score=9,
                automation_score=8,
                openness_score=9,
                privacy_score=8,
                ai_fit_score=7,
            ),
            InfraOption(
                id="cloudflare-named-tunnel",
                category="public_hosting",
                name="Cloudflare Named Tunnel",
                summary="Durable public HTTPS hostname that forwards inbound traffic to Nomad without opening a router port.",
                best_for="A more stable public Nomad API URL when your local machine or small server stays online.",
                tradeoff="Needs a Cloudflare account, tunnel token, configured hostname, and a machine that keeps running.",
                source_url="https://developers.cloudflare.com/tunnel/setup/",
                tags=("free", "agent-native", "automation", "public-url"),
                free_score=9,
                reliability_score=8,
                automation_score=8,
                openness_score=7,
                privacy_score=6,
                ai_fit_score=9,
            ),
            InfraOption(
                id="cloudflare-quick-tunnel",
                category="public_hosting",
                name="Cloudflare Quick Tunnel",
                summary="Free temporary trycloudflare.com URL that exposes local Nomad for demos and webhook-style testing.",
                best_for="Fastest zero-account public URL for a local Nomad smoke test.",
                tradeoff="Testing only: random URL, no uptime guarantee, 200 in-flight request limit, and no SSE support.",
                source_url="https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/",
                tags=("free", "agent-native", "automation", "public-url"),
                free_score=10,
                reliability_score=5,
                automation_score=9,
                openness_score=7,
                privacy_score=6,
                ai_fit_score=8,
            ),
            InfraOption(
                id="render-free-web-service",
                category="public_hosting",
                name="Render Free Web Service",
                summary="Git-connected free Python web service with a public onrender.com HTTPS URL.",
                best_for="Free GitHub-backed backend hosting for Nomad's API without keeping your laptop online.",
                tradeoff="Free services sleep after idle time, can restart, have monthly limits, and are not for production.",
                source_url="https://render.com/free",
                tags=("free", "coding", "automation", "public-url"),
                free_score=9,
                reliability_score=7,
                automation_score=9,
                openness_score=6,
                privacy_score=5,
                ai_fit_score=8,
            ),
            InfraOption(
                id="hf-spaces-free",
                category="public_hosting",
                name="Hugging Face Spaces",
                summary="Host ML apps and agents for free on Hugging Face infrastructure.",
                best_for="Persistent agent demos and public APIs with easy GitHub/HF integration.",
                tradeoff="Free tier has limited CPU/RAM and sleeps after 48 hours of inactivity.",
                source_url="https://huggingface.co/spaces",
                tags=("free", "agent-native", "public-url", "ml"),
                free_score=9,
                reliability_score=8,
                automation_score=8,
                openness_score=9,
                privacy_score=6,
                ai_fit_score=10,
            ),
            InfraOption(
                id="vercel-free-tier",
                category="public_hosting",
                name="Vercel Free Tier",
                summary="Fastest way to deploy serverless web apps and AI-agent dashboards.",
                best_for="Agent frontends and serverless APIs with high performance requirements.",
                tradeoff="Strict serverless execution limits (10s on free tier) and bandwidth caps.",
                source_url="https://vercel.com/pricing",
                tags=("free", "serverless", "public-url"),
                free_score=8,
                reliability_score=9,
                automation_score=9,
                openness_score=6,
                privacy_score=6,
                ai_fit_score=8,
            ),
            InfraOption(
                id="railway-starter",
                category="public_hosting",
                name="Railway Trial Credits",
                summary="Cloud platform that provides a small recurring or one-time credit for any Dockerized app.",
                best_for="Running full agent runtimes in containers without managing infrastructure.",
                tradeoff="Credits are limited and can run out, requiring a paid upgrade for sustained use.",
                source_url="https://railway.app/pricing",
                tags=("free", "containers", "public-url"),
                free_score=6,
                reliability_score=9,
                automation_score=9,
                openness_score=7,
                privacy_score=6,
                ai_fit_score=9,
            ),
            InfraOption(
                id="github-codespaces-public-port",
                category="public_hosting",
                name="GitHub Codespaces Public Port",
                summary="Public app.github.dev URL for a Nomad process running inside a Codespace.",
                best_for="Short-lived GitHub-native tests when Codespaces quota is available.",
                tradeoff="Ports are private by default, public visibility can be policy-blocked, and public ports may revert after restart.",
                source_url="https://docs.github.com/enterprise-cloud@latest/codespaces/developing-in-a-codespace/using-github-codespaces-with-github-cli",
                tags=("free", "coding", "public-url"),
                free_score=7,
                reliability_score=5,
                automation_score=8,
                openness_score=6,
                privacy_score=5,
                ai_fit_score=7,
            ),
            InfraOption(
                id="ollama-local",
                category="compute",
                name="Ollama Local Models",
                summary="Local model serving with simple APIs and strong offline ergonomics.",
                best_for="Private agent loops, local inference and cheap iteration.",
                tradeoff="Quality depends on your local hardware and chosen model size.",
                source_url="https://docs.ollama.com/",
                tags=("local", "free", "agent-native", "open-source"),
                free_score=10,
                reliability_score=8,
                automation_score=9,
                openness_score=9,
                privacy_score=10,
                ai_fit_score=9,
            ),
            InfraOption(
                id="llama-cpp",
                category="compute",
                name="llama.cpp",
                summary="Very lightweight local inference path with broad model compatibility.",
                best_for="Ultra-cheap local deployment and embedded environments.",
                tradeoff="More manual setup and ops than Ollama for everyday product teams.",
                source_url="https://github.com/ggml-org/llama.cpp",
                tags=("local", "open-source", "free", "coding"),
                free_score=10,
                reliability_score=8,
                automation_score=7,
                openness_score=10,
                privacy_score=10,
                ai_fit_score=8,
            ),
            InfraOption(
                id="github-models",
                category="compute",
                name="GitHub Models",
                summary="Rate-limited free access to multiple hosted models for prototyping and experimentation.",
                best_for="Agent teams that want a quick hosted fallback without running their own inference stack first.",
                tradeoff="Free use is rate-limited and deeper usage becomes metered.",
                source_url="https://docs.github.com/billing/managing-billing-for-your-products/about-billing-for-github-models/",
                tags=("free", "agent-native", "coding", "freshness"),
                free_score=8,
                reliability_score=9,
                automation_score=8,
                openness_score=7,
                privacy_score=7,
                ai_fit_score=8,
            ),
            InfraOption(
                id="xai-grok",
                category="compute",
                name="xAI Grok API",
                summary="OpenAI-compatible Grok API lane for an independent hosted reviewer brain.",
                best_for="A second opinion on self-improvement, lead reasoning and compute scouting when credits/quota are available.",
                tradeoff="Requires an xAI API key; API access, rate limits and billing are separate from consumer Grok or X plans.",
                source_url="https://docs.x.ai/developers/api-reference",
                tags=("agent-native", "freshness", "coding", "hosted"),
                free_score=6,
                reliability_score=8,
                automation_score=9,
                openness_score=7,
                privacy_score=6,
                ai_fit_score=9,
            ),
            InfraOption(
                id="hf-inference-providers",
                category="compute",
                name="Hugging Face Inference Providers",
                summary="Hosted inference with small monthly free credits and a unified API across providers.",
                best_for="Light experimentation across many hosted models without self-hosting.",
                tradeoff="The included free credits are small and sustained use quickly becomes paid.",
                source_url="https://huggingface.co/docs/inference-providers/pricing",
                tags=("free", "research", "freshness"),
                free_score=5,
                reliability_score=8,
                automation_score=9,
                openness_score=8,
                privacy_score=6,
                ai_fit_score=8,
            ),
            InfraOption(
                id="cloudflare-workers-ai",
                category="compute",
                name="Cloudflare Workers AI",
                summary="Serverless hosted inference with a daily free quota on Workers Free.",
                best_for="Short hosted reviews, rescue drafts and overflow compute when local models are busy.",
                tradeoff="Requires a Cloudflare account, API token and careful use of the daily free allowance.",
                source_url="https://developers.cloudflare.com/workers-ai/platform/pricing/",
                tags=("free", "agent-native", "automation", "freshness"),
                free_score=9,
                reliability_score=8,
                automation_score=9,
                openness_score=7,
                privacy_score=6,
                ai_fit_score=9,
            ),
            InfraOption(
                id="eurohpc-ai-factories-playground",
                category="compute",
                name="EuroHPC AI Factories Playground",
                summary="Proposal-backed European AI compute access route for SMEs, startups, and entry-level industry users.",
                best_for="Real GPU/HPC experiments after local smoke tests, with Playground as the first honest EuroHPC step.",
                tradeoff="Not a token API: it needs eligibility, application/account setup, allocation metadata, and site-specific scheduler details.",
                source_url="https://www.eurohpc-ju.europa.eu/playground-access-ai-factories_en",
                tags=("free", "research", "proposal-backed", "hpc"),
                free_score=9,
                reliability_score=7,
                automation_score=3,
                openness_score=8,
                privacy_score=8,
                ai_fit_score=9,
            ),
            InfraOption(
                id="modal-starter",
                category="compute",
                name="Modal Starter",
                summary="Serverless GPU/CPU compute with easy Python-native orchestration.",
                best_for="Complex agent tasks that need bursts of compute without managing servers.",
                tradeoff="Requires Modal credentials and has a small initial free credit that must be managed.",
                source_url="https://modal.com/pricing",
                tags=("freshness", "automation", "python-native", "hosted"),
                free_score=6,
                reliability_score=9,
                automation_score=9,
                openness_score=6,
                privacy_score=6,
                ai_fit_score=9,
            ),
            InfraOption(
                id="lambda-labs",
                category="compute",
                name="Lambda Labs Cloud",
                summary="On-demand GPU cloud with competitive pricing and straightforward API.",
                best_for="Sustained GPU training, fine-tuning and inference experiments.",
                tradeoff="Paid service, requires API token and payment method; availability of cheaper instances varies.",
                source_url="https://lambdalabs.com/service/gpu-cloud",
                tags=("gpu", "hosted", "coding", "automation"),
                free_score=2,
                reliability_score=9,
                automation_score=8,
                openness_score=7,
                privacy_score=7,
                ai_fit_score=9,
            ),
            InfraOption(
                id="runpod",
                category="compute",
                name="RunPod",
                summary="GPU cloud and serverless platform with a wide range of instances and competitive rates.",
                best_for="Flexible GPU compute and serverless AI endpoints.",
                tradeoff="Paid service, requires account and API key; credits are needed for sustained use.",
                source_url="https://www.runpod.io/",
                tags=("gpu", "hosted", "serverless", "automation"),
                free_score=2,
                reliability_score=9,
                automation_score=8,
                openness_score=7,
                privacy_score=7,
                ai_fit_score=9,
            ),
            InfraOption(
                id="telegram-bot-api",
                category="messaging",
                name="Telegram Bot API",
                summary="Fast free messaging surface for agents with broad device reach.",
                best_for="Human-in-the-loop distribution and low-friction operations.",
                tradeoff="Still a human messaging layer, not the deepest agent-to-agent protocol.",
                source_url="https://core.telegram.org/bots/api",
                tags=("free", "messaging", "agent-native"),
                free_score=10,
                reliability_score=8,
                automation_score=9,
                openness_score=8,
                privacy_score=6,
                ai_fit_score=8,
            ),
            InfraOption(
                id="cli-first",
                category="messaging",
                name="CLI-First Control Surface",
                summary="Direct terminal interaction with no platform dependency.",
                best_for="Builders, ops loops and deterministic local debugging.",
                tradeoff="No built-in distribution and weaker reach for nontechnical users.",
                source_url="https://docs.python.org/3/library/cmd.html",
                tags=("local", "free", "coding"),
                free_score=10,
                reliability_score=10,
                automation_score=8,
                openness_score=10,
                privacy_score=10,
                ai_fit_score=9,
            ),
            InfraOption(
                id="local-keypair",
                category="identity",
                name="Local Agent Keypair",
                summary="Dedicated local signing key with no external provider dependency.",
                best_for="Agent identity, proofs and machine-owned control paths.",
                tradeoff="You manage rotation, storage and trust UX yourself.",
                source_url="https://docs.base.org/ai-agents/setup/wallet-setup",
                tags=("local", "free", "agent-native", "privacy"),
                free_score=10,
                reliability_score=8,
                automation_score=8,
                openness_score=9,
                privacy_score=10,
                ai_fit_score=9,
            ),
            InfraOption(
                id="github-repo-identity",
                category="identity",
                name="Git Repo Identity",
                summary="Use the repo, signed commits and public artifacts as reputation anchors.",
                best_for="Open-source agent projects that need observable credibility over time.",
                tradeoff="Not a standalone private identity layer and slower to bootstrap trust.",
                source_url="https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification",
                tags=("open-source", "research", "interop"),
                free_score=10,
                reliability_score=8,
                automation_score=7,
                openness_score=9,
                privacy_score=5,
                ai_fit_score=7,
            ),
            InfraOption(
                id="ganache-local-devnet",
                category="wallets",
                name="Ganache Local Devnet",
                summary="Free local chain for testing agent funding, token flows and treasury logic.",
                best_for="Nomad itself and any AI agent that needs safe on-chain iteration.",
                tradeoff="Not public or trust-bearing outside your machine.",
                source_url="https://github.com/trufflesuite/ganache",
                tags=("local", "free", "agent-native", "open-source"),
                free_score=10,
                reliability_score=9,
                automation_score=9,
                openness_score=9,
                privacy_score=10,
                ai_fit_score=9,
            ),
            InfraOption(
                id="self-custody-wallet",
                category="wallets",
                name="Dedicated Self-Custody Wallet",
                summary="Separate wallet per agent with explicit risk boundaries.",
                best_for="Production-ish agent finance without mixing operator funds.",
                tradeoff="Still needs key management and real gas once you leave devnets.",
                source_url="https://docs.base.org/ai-agents/setup/wallet-setup",
                tags=("agent-native", "privacy"),
                free_score=8,
                reliability_score=8,
                automation_score=8,
                openness_score=7,
                privacy_score=9,
                ai_fit_score=8,
            ),
            InfraOption(
                id="nominatim-overpass",
                category="travel",
                name="Nominatim + Overpass Scout",
                summary="Free open-data travel intelligence for places, density and hidden-value scouting.",
                best_for="Travel arbitrage research without paid booking APIs.",
                tradeoff="No guaranteed live prices and public infra can be slow.",
                source_url="https://wiki.openstreetmap.org/wiki/Overpass_API",
                tags=("travel", "open-data", "free", "research"),
                free_score=10,
                reliability_score=6,
                automation_score=7,
                openness_score=10,
                privacy_score=8,
                ai_fit_score=8,
            ),
            InfraOption(
                id="opensky",
                category="travel",
                name="OpenSky Network",
                summary="Free flight movement and air traffic data for route intelligence.",
                best_for="Travel and logistics agents that care about real-world flight activity rather than fares.",
                tradeoff="Not a booking-price source and public access can have limits.",
                source_url="https://opensky-network.org/data/",
                tags=("travel", "open-data", "research", "freshness"),
                free_score=9,
                reliability_score=7,
                automation_score=7,
                openness_score=8,
                privacy_score=8,
                ai_fit_score=8,
            ),
            # Azure free tier infrastructure options (no budget required)
            InfraOption(
                id="azure-functions-free",
                category="compute",
                name="Azure Functions (free tier)",
                summary="Serverless compute for event-driven workloads. 1M requests/month, 400k GB-seconds/month free.",
                best_for="Agent APIs and scheduled tasks without managing servers or paying per compute minute.",
                tradeoff="Cold starts can add latency; free tier limited to 1M requests/month with 400k GB-seconds.",
                source_url="https://azure.microsoft.com/services/functions/",
                tags=("azure", "free", "compute", "serverless", "no-budget"),
                free_score=0.85,
                reliability_score=0.95,
                automation_score=0.90,
                openness_score=0.5,
                privacy_score=0.7,
                ai_fit_score=0.9,
            ),
            InfraOption(
                id="azure-container-instances-free",
                category="compute",
                name="Azure Container Instances (free credits)",
                summary="Run Docker containers without VMs. Limited free tier: 4 vCPU-hours/month on free account.",
                best_for="Running Nomad agent in a container when free credits are available.",
                tradeoff="Very limited free tier (4 hours/month); best as fallback or for burst workloads.",
                source_url="https://azure.microsoft.com/services/container-instances/",
                tags=("azure", "containers", "compute", "free-tier-limited"),
                free_score=0.30,
                reliability_score=0.95,
                automation_score=0.90,
                openness_score=0.5,
                privacy_score=0.7,
                ai_fit_score=0.85,
            ),
            InfraOption(
                id="azure-static-web-apps-free",
                category="public_hosting",
                name="Azure Static Web Apps (free tier)",
                summary="Host static sites and serverless APIs. 100 GB bandwidth/month free with GitHub Actions auto-deploy.",
                best_for="Agent dashboards and public-facing web interfaces with GitHub-integrated CI/CD.",
                tradeoff="Shared compute on free tier and limited to one function per site; best for low-traffic apps.",
                source_url="https://azure.microsoft.com/services/app-service/static/",
                tags=("azure", "hosting", "free", "serverless"),
                free_score=0.80,
                reliability_score=0.90,
                automation_score=0.85,
                openness_score=0.6,
                privacy_score=0.7,
                ai_fit_score=0.8,
            ),
            InfraOption(
                id="azure-managed-identity",
                category="identity",
                name="Azure Managed Identity (free)",
                summary="Zero-secret identity for agents to access Azure services without storing credentials.",
                best_for="Production-safe agent identity without managing keys; works across Azure services.",
                tradeoff="Only works within Azure ecosystem; requires Azure resources to assume the identity.",
                source_url="https://learn.microsoft.com/azure/active-directory/managed-identities-azure-resources/overview",
                tags=("azure", "identity", "free", "secure", "no-budget"),
                free_score=1.0,
                reliability_score=0.99,
                automation_score=0.90,
                openness_score=0.4,
                privacy_score=0.8,
                ai_fit_score=0.9,
            ),
            InfraOption(
                id="azure-key-vault-free",
                category="identity",
                name="Azure Key Vault (free tier)",
                summary="Secure vault for agent secrets and credentials. 10,000 transactions/month included.",
                best_for="Storing and rotating agent credentials without external secrets management.",
                tradeoff="Limited transactions on free tier; each get/set counts as a transaction.",
                source_url="https://azure.microsoft.com/services/key-vault/",
                tags=("azure", "security", "free", "identity"),
                free_score=0.90,
                reliability_score=0.99,
                automation_score=0.85,
                openness_score=0.4,
                privacy_score=0.9,
                ai_fit_score=0.85,
            ),
            InfraOption(
                id="azure-blob-storage-free",
                category="discovery",
                name="Azure Blob Storage (free tier)",
                summary="Object storage for agent data. 5 GB free with pay-as-you-go, ~$0.018/GB after.",
                best_for="Storing agent outputs, models, and data without a local filesystem.",
                tradeoff="5 GB free is modest; best for small data or backed by paid storage.",
                source_url="https://azure.microsoft.com/services/storage/blobs/",
                tags=("azure", "storage", "free-tier-limited", "data"),
                free_score=0.40,
                reliability_score=0.99,
                automation_score=0.90,
                openness_score=0.4,
                privacy_score=0.7,
                ai_fit_score=0.75,
            ),
            InfraOption(
                id="azure-cosmos-db-free",
                category="discovery",
                name="Azure Cosmos DB (free tier)",
                summary="Globally distributed NoSQL database. 1000 RUs/month and 25 GB storage free.",
                best_for="Agent data indexing and global state without managing database infrastructure.",
                tradeoff="1000 RUs/month is small for production; scales quickly in cost if exceeded.",
                source_url="https://azure.microsoft.com/services/cosmos-db/",
                tags=("azure", "database", "free-tier-limited", "no-sql"),
                free_score=0.50,
                reliability_score=0.98,
                automation_score=0.80,
                openness_score=0.3,
                privacy_score=0.7,
                ai_fit_score=0.8,
            ),
            InfraOption(
                id="azure-log-analytics-free",
                category="discovery",
                name="Azure Log Analytics (free tier)",
                summary="Monitor and debug agent workloads. 5 GB/day ingestion free with 30-day retention.",
                best_for="Observability for production agents; correlate logs across services.",
                tradeoff="5 GB/day ingestion is reasonable but retention is limited to 30 days on free tier.",
                source_url="https://learn.microsoft.com/azure/azure-monitor/logs/log-analytics-overview",
                tags=("azure", "monitoring", "free", "observability"),
                free_score=0.70,
                reliability_score=0.95,
                automation_score=0.85,
                openness_score=0.4,
                privacy_score=0.7,
                ai_fit_score=0.8,
            ),
        ]
