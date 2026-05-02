import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from agent_pain_solver import AgentPainSolver
from compute_probe import (
    DEFAULT_GITHUB_MODEL,
    DEFAULT_GITHUB_MODELS_API_VERSION,
    github_model_candidates,
    github_models_base_url,
    github_models_chat_completions_url,
    github_models_headers,
    github_models_status_help,
    DEFAULT_XAI_MODEL,
    xai_base_url,
    xai_chat_completions_url,
    xai_model_candidates,
    xai_status_help,
    DEFAULT_OPENROUTER_MODEL,
    openrouter_base_url,
    openrouter_chat_completions_url,
    openrouter_model_candidates,
    openrouter_status_help,
)
from infra_scout import InfrastructureScout
from lead_discovery import LeadDiscoveryScout
from mission import MISSION_STATEMENT, mission_context
from nomad_autonomous_development import AutonomousDevelopmentLog
from nomad_addons import NomadAddonManager
from nomad_codebuddy import (
    CODEBUDDY_ACTIVE_SELF_REVIEW_ENV,
    CODEBUDDY_BRAIN_ENABLED_ENV,
    CodeBuddyBrainProvider,
    CodeBuddyProbe,
    CodeBuddyReviewRunner,
)
from nomad_mutual_aid import NomadMutualAidKernel
from nomad_market_patterns import ComputeLane, MarketPatternRegistry
from nomad_predictive_router import PredictiveRouter
from nomad_self_healing import SelfHealingPipeline
from self_development import SelfDevelopmentJournal


load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_ACTIVE_LEAD_PLAN_PATH = ROOT / "nomad_active_lead_plan.json"
DEFAULT_CODEBUDDY_SELF_REVIEW_PATHS = (
    "nomad_codebuddy.py",
    "workflow.py",
    "nomad_cli.py",
    "telegram_bot.py",
    "infra_scout.py",
    "self_improvement.py",
    "test_nomad_codebuddy.py",
    "test_control_surfaces.py",
    "README.md",
    ".env.example",
)

LOW_SIGNAL_REVIEW_PATTERNS = (
    r"\bi can(?:not|'t)\b",
    r"\bi cannot help with this request\b",
    r"\bi'm sorry\b",
    r"\bdifferent topic\b",
    r"\bunable to assist\b",
    r"\bdo not have access\b",
)

DEFAULT_FAST_OLLAMA_SELF_IMPROVE_MODELS = (
    "qwen2.5:0.5b-instruct",
    "qwen2.5:1.5b-instruct",
    "llama3.2:1b",
)


class HostedBrainRouter:
    """Routes bounded self-improvement prompts to Nomad's own local brain."""

    def __init__(self) -> None:
        load_dotenv()
        self.ollama_base = (os.getenv("OLLAMA_API_BASE") or "http://127.0.0.1:11434").rstrip("/")
        configured_self_improve_model = (os.getenv("NOMAD_OLLAMA_SELF_IMPROVE_MODEL") or "").strip()
        configured_ollama_model = (os.getenv("OLLAMA_MODEL") or "").strip()
        self.ollama_auto_select = self._env_flag("NOMAD_OLLAMA_AUTO_SELECT_SELF_IMPROVE_MODEL", default=True)
        self.ollama_model_candidates = self._ollama_candidate_models(
            configured_self_improve_model=configured_self_improve_model,
            configured_ollama_model=configured_ollama_model,
        )
        if configured_self_improve_model:
            self.ollama_model = configured_self_improve_model
            self.ollama_model_source = "NOMAD_OLLAMA_SELF_IMPROVE_MODEL"
        elif self.ollama_auto_select:
            selected_model = self._select_available_ollama_model(self.ollama_model_candidates)
            self.ollama_model = selected_model or configured_ollama_model or "llama3.2:1b"
            self.ollama_model_source = "auto_fast_available" if selected_model else (
                "OLLAMA_MODEL" if configured_ollama_model else "default"
            )
        else:
            self.ollama_model = configured_ollama_model or "llama3.2:1b"
            self.ollama_model_source = "OLLAMA_MODEL" if configured_ollama_model else "default"
        legacy_allow_hosted = os.getenv("NOMAD_ALLOW_HOSTED_BRAINS")
        hosted_mode_env = (os.getenv("NOMAD_HOSTED_BRAIN_MODE") or "").strip().lower()
        if hosted_mode_env:
            self.hosted_mode = hosted_mode_env
        elif legacy_allow_hosted is None or legacy_allow_hosted.strip() == "":
            self.hosted_mode = "auto"
        else:
            self.hosted_mode = (
                "always"
                if legacy_allow_hosted.strip().lower() in {"1", "true", "yes", "on"}
                else "off"
            )
        self.github_token = (
            os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
            or os.getenv("GITHUB_TOKEN")
            or ""
        ).strip()
        self.hf_token = (
            os.getenv("HF_TOKEN")
            or os.getenv("HUGGINGFACEHUB_API_TOKEN")
            or os.getenv("HUGGING_FACE_HUB_TOKEN")
            or ""
        ).strip()
        self.github_model = (os.getenv("NOMAD_GITHUB_MODEL") or DEFAULT_GITHUB_MODEL).strip()
        self.github_model_candidates = github_model_candidates(self.github_model)
        self.github_base_url = github_models_base_url()
        self.github_chat_url = github_models_chat_completions_url(self.github_base_url)
        self.hf_model = (
            os.getenv("NOMAD_HF_MODEL")
            or "meta-llama/Llama-3.1-8B-Instruct:cerebras"
        ).strip()
        self.cloudflare_account_id = (os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip()
        self.cloudflare_api_token = (os.getenv("CLOUDFLARE_API_TOKEN") or "").strip()
        self.cloudflare_model = (
            os.getenv("NOMAD_CLOUDFLARE_MODEL") or "@cf/meta/llama-3.2-1b-instruct"
        ).strip()
        self.codebuddy_brain = CodeBuddyBrainProvider()
        self.xai_token = (os.getenv("XAI_API_KEY") or "").strip()
        self.xai_model = (os.getenv("NOMAD_XAI_MODEL") or DEFAULT_XAI_MODEL).strip()
        self.xai_model_candidates = xai_model_candidates(self.xai_model)
        self.xai_base_url = xai_base_url()
        self.xai_chat_url = xai_chat_completions_url(self.xai_base_url)
        self.openrouter_token = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        self.openrouter_model = (os.getenv("NOMAD_OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL).strip()
        self.openrouter_model_candidates = openrouter_model_candidates(self.openrouter_model)
        self.openrouter_base_url = openrouter_base_url()
        self.openrouter_chat_url = openrouter_chat_completions_url(self.openrouter_base_url)
        self.github_api_version = (
            os.getenv("NOMAD_GITHUB_MODELS_API_VERSION") or DEFAULT_GITHUB_MODELS_API_VERSION
        ).strip()
        self.timeout_seconds = int(os.getenv("NOMAD_SELF_IMPROVE_TIMEOUT_SECONDS", "25"))
        self.max_tokens = int(os.getenv("NOMAD_SELF_IMPROVE_MAX_TOKENS", "700"))
        self.ollama_timeout_seconds = int(
            os.getenv("NOMAD_OLLAMA_TIMEOUT_SECONDS", str(min(self.timeout_seconds, 15)))
        )
        self.ollama_max_tokens = int(
            os.getenv("NOMAD_OLLAMA_MAX_TOKENS", str(min(self.max_tokens, 180)))
        )
        self.predictive_routing_enabled = self._env_flag("NOMAD_PREDICTIVE_ROUTING_ENABLED", default=True)
        self.self_healing_enabled = self._env_flag("NOMAD_SELF_HEALING_ENABLED", default=False)
        self.max_review_providers = max(1, int(os.getenv("NOMAD_SELF_IMPROVE_MAX_PROVIDERS", "3")))
        self.pattern_registry = MarketPatternRegistry(
            registry_path=Path(
                os.getenv("NOMAD_RUNTIME_PATTERN_REGISTRY_PATH")
                or os.getenv("NOMAD_MARKET_PATTERN_REGISTRY_PATH")
                or str(DEFAULT_ACTIVE_LEAD_PLAN_PATH.resolve().parent / "nomad_runtime_patterns.json")
            )
        )
        self.predictive_router = PredictiveRouter(
            registry=self.pattern_registry,
            health_path=Path(
                os.getenv("NOMAD_LANE_HEALTH_PATH")
                or str(DEFAULT_ACTIVE_LEAD_PLAN_PATH.resolve().parent / "nomad_lane_health.json")
            ),
        )
        self.self_healer = SelfHealingPipeline(
            router=self.predictive_router,
            registry=self.pattern_registry,
            max_actions_per_cycle=max(1, int(os.getenv("NOMAD_SELF_HEALING_MAX_ACTIONS", "3"))),
            heal_log_path=Path(
                os.getenv("NOMAD_HEAL_LOG_PATH")
                or str(DEFAULT_ACTIVE_LEAD_PLAN_PATH.resolve().parent / "nomad_heal_log.ndjson")
            ),
        )
        self.default_task_type = "self_improvement_review"
        self.last_routing_report: Dict[str, Any] = {}

    def review(self, objective: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        messages = self._messages(objective=objective, context=context)
        task_type = str(context.get("task_type") or self.default_task_type).strip() or self.default_task_type
        providers = self._review_plan(context.get("resources") or {}, task_type=task_type)
        results: List[Dict[str, Any]] = []
        for provider in providers:
            results.append(self._run_review_provider(provider=provider, messages=messages, task_type=task_type))
        if not results:
            results.append(self._run_review_provider(provider="ollama", messages=messages, task_type=task_type))
        return results

    def _ollama_candidate_models(
        self,
        configured_self_improve_model: str,
        configured_ollama_model: str,
    ) -> List[str]:
        configured_candidates = [
            item.strip()
            for item in re.split(
                r"[,;\s]+",
                os.getenv("NOMAD_OLLAMA_SELF_IMPROVE_MODEL_CANDIDATES", ""),
            )
            if item.strip()
        ]
        candidates = [
            configured_self_improve_model,
            *configured_candidates,
            *DEFAULT_FAST_OLLAMA_SELF_IMPROVE_MODELS,
            configured_ollama_model,
            "llama3.2:1b",
        ]
        deduped: List[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            cleaned = str(candidate or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped

    def _select_available_ollama_model(self, candidates: List[str]) -> str:
        if not candidates:
            return ""
        try:
            response = requests.get(
                f"{self.ollama_base}/api/tags",
                timeout=float(os.getenv("NOMAD_OLLAMA_TAGS_TIMEOUT_SECONDS", "3")),
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return ""

        available = {
            str(model.get("name") or "").strip()
            for model in (payload.get("models") or [])
            if isinstance(model, dict) and model.get("name")
        }
        for candidate in candidates:
            if candidate in available:
                return candidate
        return ""

    def _ollama_review(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if not self.ollama_model:
            return {
                "provider": "ollama",
                "name": "Ollama",
                "configured": False,
                "ok": False,
                "message": "No OLLAMA_MODEL configured.",
            }

        try:
            response = requests.post(
                f"{self.ollama_base}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": self.ollama_max_tokens,
                    },
                },
                timeout=self.ollama_timeout_seconds,
            )
        except requests.Timeout as exc:
            return {
                "provider": "ollama",
                "name": "Ollama",
                "model": self.ollama_model,
                "model_source": self.ollama_model_source,
                "configured": True,
                "ok": False,
                "retryable": True,
                "timeout_seconds": self.ollama_timeout_seconds,
                "message": (
                    f"Ollama review timed out after {self.ollama_timeout_seconds}s with {self.ollama_model}: {exc}"
                ),
                "fallback_advice": (
                    "Use NOMAD_OLLAMA_SELF_IMPROVE_MODEL for a smaller local model, lower "
                    "NOMAD_OLLAMA_MAX_TOKENS, or let hosted fallback brains continue the cycle."
                ),
            }
        except Exception as exc:
            return {
                "provider": "ollama",
                "name": "Ollama",
                "model": self.ollama_model,
                "model_source": self.ollama_model_source,
                "configured": True,
                "ok": False,
                "retryable": True,
                "message": f"Ollama review failed: {exc}",
                "fallback_advice": "Hosted fallback brains may continue if NOMAD_HOSTED_BRAIN_MODE permits them.",
            }

        if not response.ok:
            return {
                "provider": "ollama",
                "name": "Ollama",
                "model": self.ollama_model,
                "model_source": self.ollama_model_source,
                "configured": True,
                "ok": False,
                "status_code": response.status_code,
                "timeout_seconds": self.ollama_timeout_seconds,
                "message": response.text[:300],
            }

        payload = response.json()
        message = payload.get("message") or {}
        content = (message.get("content") or "").strip()
        useful = self._is_useful_review_content(content)
        return {
            "provider": "ollama",
            "name": "Ollama",
            "model": self.ollama_model,
            "model_source": self.ollama_model_source,
            "configured": True,
            "ok": bool(content),
            "useful": useful,
            "content": content,
            "timeout_seconds": self.ollama_timeout_seconds,
            "num_predict": self.ollama_max_tokens,
            "usage": {
                "prompt_eval_count": payload.get("prompt_eval_count"),
                "eval_count": payload.get("eval_count"),
            },
            "message": "Local Ollama review completed." if content else "No review content returned.",
        }

    def _messages(
        self,
        objective: str,
        context: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        compact_context = self._compact_context_for_brain(context)
        system = (
            "You are the local operating brain for Nomad. "
            f"Mission: {MISSION_STATEMENT} "
            "Focus on paid human-in-the-loop service, public agent outreach, and one small self-improvement. "
            "Do not ask for secrets. Do not propose unsafe actions. Be brief and concrete."
        )
        snapshot = self._snapshot_text(compact_context)
        user = (
            f"Objective: {objective}\n"
            f"Snapshot: {snapshot}\n"
            "Reply in exactly 4 short lines:\n"
            "Diagnosis: ...\n"
            "Action1: ...\n"
            "Action2: ...\n"
            "Query: ..."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _compact_context_for_brain(self, context: Dict[str, Any]) -> Dict[str, Any]:
        resources = context.get("resources") or {}
        recent_service = context.get("recent_service_tasks") or []
        recent_outreach = context.get("recent_outreach_campaigns") or []
        recent_sessions = context.get("recent_direct_agent_sessions") or []
        return {
            "profile": (context.get("profile") or {}).get("id", ""),
            "overall_score": context.get("overall_score", 0.0),
            "resources": {
                "brain_count": resources.get("brain_count", 0),
                "primary_brain": resources.get("primary_brain"),
                "ollama": resources.get("ollama") or {},
                "github_models_available": ((resources.get("github_models") or {}).get("available", False)),
                "huggingface_available": ((resources.get("huggingface") or {}).get("available", False)),
                "cloudflare_workers_ai_available": ((resources.get("cloudflare_workers_ai") or {}).get("available", False)),
                "xai_grok_available": ((resources.get("xai_grok") or {}).get("available", False)),
                "openrouter_available": ((resources.get("openrouter") or {}).get("available", False)),
            "codebuddy_reviewer": ((resources.get("developer_assistants") or {}).get("codebuddy") or {}),
            "codebuddy_brain_enabled": self._env_flag(CODEBUDDY_BRAIN_ENABLED_ENV, default=False),
        },
            "recommended_stack": [
                {
                    "category": item.get("category"),
                    "name": item.get("name"),
                }
                for item in (context.get("recommended_stack") or [])[:4]
            ],
            "recent_service_tasks": [
                {
                    "service_type": item.get("service_type"),
                    "status": item.get("status"),
                    "budget_native": item.get("budget_native"),
                }
                for item in recent_service[:4]
            ],
            "recent_outreach_campaigns": [
                {
                    "status": item.get("status"),
                    "sent": item.get("sent"),
                    "failed": item.get("failed"),
                    "duplicates": item.get("duplicates"),
                }
                for item in recent_outreach[:3]
            ],
            "recent_direct_sessions": [
                {
                    "pain_type": item.get("last_pain_type"),
                    "status": item.get("status"),
                }
                for item in recent_sessions[:4]
            ],
            "market": {
                "top_competitors": list(((context.get("market_context") or {}).get("top_competitors") or [])[:3]),
                "top_compute": list(((context.get("market_context") or {}).get("top_compute") or [])[:3]),
                "copy_now": list(((context.get("market_context") or {}).get("copy_now") or [])[:3]),
            },
            "quantum_tokens": context.get("quantum_tokens") or {},
            "compute_analysis": str(context.get("compute_analysis") or "")[:180],
            "self_analysis": str(context.get("self_analysis") or "")[:180],
        }

    def _snapshot_text(self, compact_context: Dict[str, Any]) -> str:
        resources = compact_context.get("resources") or {}
        recent_service = compact_context.get("recent_service_tasks") or []
        recent_outreach = compact_context.get("recent_outreach_campaigns") or []
        recent_sessions = compact_context.get("recent_direct_sessions") or []
        market = compact_context.get("market") or {}

        service_summary = ",".join(
            f"{item.get('service_type') or 'task'}:{item.get('status') or 'unknown'}"
            for item in recent_service[:3]
        ) or "none"
        outreach_summary = ",".join(
            f"{item.get('status') or 'unknown'}-sent{item.get('sent') or 0}-fail{item.get('failed') or 0}"
            for item in recent_outreach[:2]
        ) or "none"
        session_summary = ",".join(
            f"{item.get('pain_type') or 'custom'}:{item.get('status') or 'unknown'}"
            for item in recent_sessions[:3]
        ) or "none"
        market_summary = ",".join(str(item) for item in (market.get("top_competitors") or [])[:2]) or "none"
        compute_sources = ",".join(str(item) for item in (market.get("top_compute") or [])[:2]) or "none"
        quantum = compact_context.get("quantum_tokens") or {}
        quantum_summary = quantum.get("selected_strategy") or "none"
        codebuddy = (resources.get("codebuddy_reviewer") or {})
        codebuddy_summary = (
            "ready"
            if codebuddy.get("automation_ready")
            else "cli"
            if codebuddy.get("cli_available")
            else "locked"
        )
        codebuddy_brain_summary = "on" if resources.get("codebuddy_brain_enabled") else "off"
        return (
            f"profile={compact_context.get('profile')}; "
            f"brains={resources.get('brain_count', 0)}; "
            f"ollama_models={((resources.get('ollama') or {}).get('model_count', 0))}; "
            f"codebuddy={codebuddy_summary}; "
            f"codebuddy_brain={codebuddy_brain_summary}; "
            f"service={service_summary}; "
            f"outreach={outreach_summary}; "
            f"sessions={session_summary}; "
            f"market={market_summary}; "
            f"compute_sources={compute_sources}; "
            f"quantum_tokens={quantum_summary}; "
            f"compute={compact_context.get('compute_analysis', '')[:80]}; "
            f"self={compact_context.get('self_analysis', '')[:80]}"
        )

    def _github_review(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if not self.github_token:
            help_payload = github_models_status_help(
                None,
                model=self.github_model,
                base_url=self.github_base_url,
                api_version=self.github_api_version,
            )
            return {
                "provider": "github_models",
                "name": "GitHub Models",
                "configured": False,
                "ok": False,
                "model": self.github_model,
                **help_payload,
            }

        attempts: List[Dict[str, Any]] = []
        last_help: Dict[str, Any] = {}
        try:
            for model in self.github_model_candidates:
                response = requests.post(
                    self.github_chat_url,
                    headers=github_models_headers(
                        self.github_token,
                        self.github_api_version,
                        json_request=True,
                    ),
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": self.max_tokens,
                        "temperature": 0.2,
                    },
                    timeout=self.timeout_seconds,
                )
                if response.ok:
                    parsed = self._parse_chat_response(
                        response=response,
                        provider="github_models",
                        name="GitHub Models",
                        model=model,
                    )
                    parsed["configured_model"] = self.github_model
                    parsed["working_model"] = model
                    parsed["attempts"] = attempts
                    parsed["base_url"] = self.github_base_url
                    if model != self.github_model:
                        parsed["next_action"] = f"Set NOMAD_GITHUB_MODEL={model}."
                        parsed["remediation"] = [
                            f"Set NOMAD_GITHUB_MODEL={model} so self-improvement uses the working model first."
                        ]
                    return parsed

                last_help = github_models_status_help(
                    response.status_code,
                    model=model,
                    body=response.text,
                    base_url=self.github_base_url,
                    api_version=self.github_api_version,
                )
                attempts.append(
                    {
                        "model": model,
                        "status_code": response.status_code,
                        "issue": last_help.get("issue"),
                        "next_action": last_help.get("next_action"),
                    }
                )
                if response.status_code not in {400, 404, 422}:
                    return {
                        "provider": "github_models",
                        "name": "GitHub Models",
                        "model": model,
                        "configured_model": self.github_model,
                        "configured": True,
                        "ok": False,
                        "status_code": response.status_code,
                        "attempts": attempts,
                        **last_help,
                    }

            return {
                "provider": "github_models",
                "name": "GitHub Models",
                "model": self.github_model,
                "configured": True,
                "ok": False,
                "attempts": attempts,
                **last_help,
            }
        except Exception as exc:
            return {
                "provider": "github_models",
                "name": "GitHub Models",
                "model": self.github_model,
                "configured": True,
                "ok": False,
                "base_url": self.github_base_url,
                "attempts": attempts,
                "remediation": [
                    "Check network access to models.github.ai.",
                    "Run python main.py --cli compute --json for a status-specific GitHub Models diagnosis.",
                ],
                "message": f"GitHub Models review failed: {exc}",
            }

    def _huggingface_review(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if not self.hf_token:
            return {
                "provider": "huggingface",
                "name": "Hugging Face Inference Providers",
                "configured": False,
                "ok": False,
                "message": "No HF_TOKEN configured.",
            }

        try:
            response = requests.post(
                "https://router.huggingface.co/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.hf_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.hf_model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                    "temperature": 0.2,
                },
                timeout=self.timeout_seconds,
            )
            return self._parse_chat_response(
                response=response,
                provider="huggingface",
                name="Hugging Face Inference Providers",
                model=self.hf_model,
            )
        except Exception as exc:
            return {
                "provider": "huggingface",
                "name": "Hugging Face Inference Providers",
                "model": self.hf_model,
                "configured": True,
                "ok": False,
                "message": f"Hugging Face review failed: {exc}",
            }

    def _cloudflare_review(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if not self.cloudflare_account_id or not self.cloudflare_api_token:
            return {
                "provider": "cloudflare_workers_ai",
                "name": "Cloudflare Workers AI",
                "configured": False,
                "ok": False,
                "message": "No CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN configured.",
            }

        try:
            response = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{self.cloudflare_account_id}/ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.cloudflare_api_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.cloudflare_model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                    "temperature": 0.2,
                },
                timeout=self.timeout_seconds,
            )
            return self._parse_chat_response(
                response=response,
                provider="cloudflare_workers_ai",
                name="Cloudflare Workers AI",
                model=self.cloudflare_model,
            )
        except Exception as exc:
            return {
                "provider": "cloudflare_workers_ai",
                "name": "Cloudflare Workers AI",
                "model": self.cloudflare_model,
                "configured": True,
                "ok": False,
                "message": f"Cloudflare Workers AI review failed: {exc}",
            }

    def _xai_grok_review(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if not self.xai_token:
            return {
                "provider": "xai_grok",
                "name": "xAI Grok",
                "configured": False,
                "ok": False,
                "model": self.xai_model,
                **xai_status_help(None, model=self.xai_model, base_url=self.xai_base_url),
            }

        attempts: List[Dict[str, Any]] = []
        last_help: Dict[str, Any] = {}
        try:
            for model in self.xai_model_candidates:
                response = requests.post(
                    self.xai_chat_url,
                    headers={
                        "Authorization": f"Bearer {self.xai_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": self.max_tokens,
                        "temperature": 0.2,
                    },
                    timeout=self.timeout_seconds,
                )
                if response.ok:
                    parsed = self._parse_chat_response(
                        response=response,
                        provider="xai_grok",
                        name="xAI Grok",
                        model=model,
                    )
                    parsed["configured_model"] = self.xai_model
                    parsed["working_model"] = model
                    parsed["attempts"] = attempts
                    parsed["base_url"] = self.xai_base_url
                    if model != self.xai_model:
                        parsed["next_action"] = f"Set NOMAD_XAI_MODEL={model}."
                        parsed["remediation"] = [
                            f"Set NOMAD_XAI_MODEL={model} so self-improvement uses the working Grok model first."
                        ]
                    return parsed

                last_help = xai_status_help(
                    response.status_code,
                    model=model,
                    body=response.text,
                    base_url=self.xai_base_url,
                )
                attempts.append(
                    {
                        "model": model,
                        "status_code": response.status_code,
                        "issue": last_help.get("issue"),
                        "next_action": last_help.get("next_action"),
                    }
                )
                if response.status_code not in {400, 404, 422}:
                    return {
                        "provider": "xai_grok",
                        "name": "xAI Grok",
                        "model": model,
                        "configured_model": self.xai_model,
                        "configured": True,
                        "ok": False,
                        "status_code": response.status_code,
                        "attempts": attempts,
                        **last_help,
                    }

            return {
                "provider": "xai_grok",
                "name": "xAI Grok",
                "model": self.xai_model,
                "configured": True,
                "ok": False,
                "attempts": attempts,
                **last_help,
            }
        except Exception as exc:
            return {
                "provider": "xai_grok",
                "name": "xAI Grok",
                "model": self.xai_model,
                "configured": True,
                "ok": False,
                "base_url": self.xai_base_url,
                "attempts": attempts,
                "remediation": [
                    "Check network access to api.x.ai.",
                    "Run python main.py --cli compute --json for a status-specific xAI/Grok diagnosis.",
                ],
                "message": f"xAI Grok review failed: {exc}",
            }

    def _openrouter_review(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if not self.openrouter_token:
            return {
                "provider": "openrouter",
                "name": "OpenRouter",
                "configured": False,
                "ok": False,
                "model": self.openrouter_model,
                **openrouter_status_help(None, model=self.openrouter_model, base_url=self.openrouter_base_url),
            }

        attempts: List[Dict[str, Any]] = []
        last_help: Dict[str, Any] = {}
        try:
            for model in self.openrouter_model_candidates:
                response = requests.post(
                    self.openrouter_chat_url,
                    headers={
                        "Authorization": f"Bearer {self.openrouter_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": self.max_tokens,
                        "temperature": 0.2,
                    },
                    timeout=self.timeout_seconds,
                )
                if response.ok:
                    parsed = self._parse_chat_response(
                        response=response,
                        provider="openrouter",
                        name="OpenRouter",
                        model=model,
                    )
                    parsed["configured_model"] = self.openrouter_model
                    parsed["working_model"] = model
                    parsed["attempts"] = attempts
                    parsed["base_url"] = self.openrouter_base_url
                    if model != self.openrouter_model:
                        parsed["next_action"] = f"Set NOMAD_OPENROUTER_MODEL={model}."
                        parsed["remediation"] = [
                            f"Set NOMAD_OPENROUTER_MODEL={model} so self-improvement uses the working OpenRouter model first."
                        ]
                    return parsed

                last_help = openrouter_status_help(
                    response.status_code,
                    model=model,
                    body=response.text,
                    base_url=self.openrouter_base_url,
                )
                attempts.append(
                    {
                        "model": model,
                        "status_code": response.status_code,
                        "issue": last_help.get("issue"),
                        "next_action": last_help.get("next_action"),
                    }
                )
                if response.status_code not in {400, 404, 422}:
                    return {
                        "provider": "openrouter",
                        "name": "OpenRouter",
                        "model": model,
                        "configured_model": self.openrouter_model,
                        "configured": True,
                        "ok": False,
                        "status_code": response.status_code,
                        "attempts": attempts,
                        **last_help,
                    }

            return {
                "provider": "openrouter",
                "name": "OpenRouter",
                "model": self.openrouter_model,
                "configured": True,
                "ok": False,
                "attempts": attempts,
                **last_help,
            }
        except Exception as exc:
            return {
                "provider": "openrouter",
                "name": "OpenRouter",
                "model": self.openrouter_model,
                "configured": True,
                "ok": False,
                "base_url": self.openrouter_base_url,
                "attempts": attempts,
                "remediation": [
                    "Check network access to openrouter.ai.",
                    "Run python main.py --cli compute --json for an OpenRouter diagnosis.",
                ],
                "message": f"OpenRouter review failed: {exc}",
            }

    def _parse_chat_response(
        self,
        response: requests.Response,
        provider: str,
        name: str,
        model: str,
    ) -> Dict[str, Any]:
        if not response.ok:
            return {
                "provider": provider,
                "name": name,
                "model": model,
                "configured": True,
                "ok": False,
                "status_code": response.status_code,
                "message": response.text[:300],
            }

        payload = response.json()
        choices = payload.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
        content = (message or {}).get("content") or ""
        useful = self._is_useful_review_content(content)
        return {
            "provider": provider,
            "name": name,
            "model": model,
            "configured": True,
            "ok": bool(content),
            "useful": useful,
            "content": content.strip(),
            "usage": payload.get("usage") or {},
            "message": "Review completed." if content else "No review content returned.",
        }

    def _review_plan(self, resources: Dict[str, Any], task_type: str = "") -> List[str]:
        providers: List[str] = []
        if self._should_use_ollama(resources):
            providers.append("ollama")
        if self.hosted_mode in {"off", "disabled", "false", "0"}:
            if self._should_use_codebuddy_brain():
                providers.append("codebuddy_brain")
            return self._rank_review_providers(providers, task_type=task_type)
        if self._should_use_hosted_provider("github_models", resources):
            providers.append("github_models")
        if self._should_use_hosted_provider("huggingface", resources):
            providers.append("huggingface")
        if self._should_use_hosted_provider("cloudflare_workers_ai", resources):
            providers.append("cloudflare_workers_ai")
        if self._should_use_hosted_provider("xai_grok", resources):
            providers.append("xai_grok")
        if self._should_use_hosted_provider("openrouter", resources):
            providers.append("openrouter")
        if self._should_use_codebuddy_brain():
            providers.append("codebuddy_brain")
        return self._rank_review_providers(providers, task_type=task_type)

    def _should_use_ollama(self, resources: Dict[str, Any]) -> bool:
        if not self.ollama_model:
            return False
        payload = resources.get("ollama") or {}
        if not isinstance(payload, dict) or not payload:
            return True
        if payload.get("api_reachable") is False:
            return False
        if payload.get("api_reachable") and "model_count" in payload and int(payload.get("model_count") or 0) == 0:
            return False
        return True

    def _should_use_hosted_provider(self, provider: str, resources: Dict[str, Any]) -> bool:
        configured = {
            "github_models": bool(self.github_token),
            "huggingface": bool(self.hf_token),
            "cloudflare_workers_ai": bool(self.cloudflare_account_id and self.cloudflare_api_token),
            "xai_grok": bool(self.xai_token),
            "openrouter": bool(self.openrouter_token),
        }.get(provider, False)
        if not configured:
            return False
        if self.hosted_mode == "always":
            return True
        payload = resources.get(provider) or {}
        if not isinstance(payload, dict):
            payload = {}
        if payload.get("available"):
            return True
        if not resources.get("brain_count") and payload.get("reachable"):
            return True
        return False

    def _codebuddy_brain_review(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        return self.codebuddy_brain.brain_review(messages)

    def predictive_status(self, task_type: str = "") -> Dict[str, Any]:
        effective_task_type = task_type or self.default_task_type
        top_patterns = self.pattern_registry.summary(task_type=effective_task_type)
        return {
            "enabled": self.predictive_routing_enabled,
            "task_type": effective_task_type,
            "last_routing_report": self.last_routing_report,
            "lane_status": self.predictive_router.lane_status(),
            "patterns": top_patterns,
            "self_healing": self.self_healer.heal_summary(),
        }

    def run_self_healing_cycle(self) -> Dict[str, Any]:
        if not self.self_healing_enabled:
            return {
                "status": "skipped",
                "reason": "automatic_correction_disabled",
                "actions_taken": 0,
                "actions": [],
            }
        return self.self_healer.run_healing_cycle_sync()

    def _rank_review_providers(self, providers: List[str], task_type: str = "") -> List[str]:
        ordered = [provider for provider in providers if provider]
        if not ordered:
            self.last_routing_report = {"task_type": task_type or self.default_task_type, "ranked_providers": []}
            return ordered

        effective_task_type = task_type or self.default_task_type
        pattern_summary = self.pattern_registry.summary(task_type=effective_task_type)
        if int(pattern_summary.get("pattern_count") or 0) <= 0:
            self.last_routing_report = {
                "task_type": effective_task_type,
                "predictive_routing_enabled": bool(self.predictive_routing_enabled),
                "reason": "no_runtime_pattern_evidence",
                "ranked_providers": ordered[: self.max_review_providers],
            }
            return ordered[: self.max_review_providers]

        if not self.predictive_routing_enabled:
            self.last_routing_report = {
                "task_type": effective_task_type,
                "ranked_providers": ordered,
                "predictive_routing_enabled": False,
            }
            return ordered[: self.max_review_providers]

        provider_lanes = {
            provider: self._provider_lane(provider)
            for provider in ordered
        }
        unique_lanes = []
        for lane in provider_lanes.values():
            if lane not in unique_lanes:
                unique_lanes.append(lane)

        ranked_lanes = self.predictive_router.rank_lanes(
            task_type=effective_task_type,
            lanes=unique_lanes,
            preferred_lanes=unique_lanes,
        )
        lane_order = [item["lane"] for item in ranked_lanes]
        if not lane_order:
            self.last_routing_report = {
                "task_type": effective_task_type,
                "ranked_providers": ordered[: self.max_review_providers],
                "predictive_routing_enabled": True,
                "ranked_lanes": [],
            }
            return ordered[: self.max_review_providers]

        ranked_providers: List[str] = []
        for lane in lane_order:
            ranked_providers.extend(
                provider
                for provider in ordered
                if provider_lanes.get(provider) == lane and provider not in ranked_providers
            )
        for provider in ordered:
            if provider not in ranked_providers:
                ranked_providers.append(provider)

        self.last_routing_report = {
            "task_type": effective_task_type,
            "predictive_routing_enabled": True,
            "ranked_lanes": [
                {
                    "lane": item["lane"].value,
                    "routing_score": round(float(item["routing_score"]), 4),
                    "predicted_latency_ms": round(float(item["predicted_latency_ms"]), 1),
                    "predicted_error_rate": round(float(item["predicted_error_rate"]), 4),
                }
                for item in ranked_lanes
            ],
            "ranked_providers": ranked_providers[: self.max_review_providers],
        }
        return ranked_providers[: self.max_review_providers]

    def _run_review_provider(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        task_type: str,
    ) -> Dict[str, Any]:
        handlers = {
            "ollama": self._ollama_review,
            "github_models": self._github_review,
            "huggingface": self._huggingface_review,
            "cloudflare_workers_ai": self._cloudflare_review,
            "xai_grok": self._xai_grok_review,
            "openrouter": self._openrouter_review,
            "codebuddy_brain": self._codebuddy_brain_review,
        }
        handler = handlers.get(provider)
        if handler is None:
            return {
                "provider": provider,
                "ok": False,
                "useful": False,
                "message": f"No handler is registered for provider '{provider}'.",
            }

        start = time.perf_counter()
        result = handler(messages)
        latency_ms = max(1.0, (time.perf_counter() - start) * 1000.0)
        recorded = self._record_review_outcome(
            provider=provider,
            task_type=task_type,
            latency_ms=latency_ms,
            result=result,
        )
        result["routing"] = recorded
        return result

    def _record_review_outcome(
        self,
        provider: str,
        task_type: str,
        latency_ms: float,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        lane = self._provider_lane(provider)
        usage = result.get("usage") or {}
        total_tokens = int(
            usage.get("total_tokens")
            or usage.get("completion_tokens")
            or usage.get("prompt_tokens")
            or 0
        )
        useful = bool(result.get("useful")) if "useful" in result else self._is_useful_review_content(result.get("content", ""))
        success = bool(result.get("ok")) and useful
        model_hint = str(result.get("model") or "")
        error_type = ""
        if not success:
            error_type = str(
                result.get("issue")
                or result.get("status_code")
                or result.get("message")
                or f"{provider}_review_failed"
            )
        estimated_cost = self._estimate_review_cost_usd(provider=provider, usage=usage)
        self.predictive_router.record_outcome(
            lane=lane,
            latency_ms=latency_ms,
            success=success,
            task_type=task_type,
            cost_usd=estimated_cost,
            tokens_used=total_tokens,
            error_type=error_type,
            model_hint=model_hint,
            notes=str(result.get("message") or ""),
        )
        decision = self.predictive_router.route(
            task_type=task_type,
            preferred_lanes=[lane],
        )
        return {
            "lane": lane.value,
            "task_type": task_type,
            "success": success,
            "latency_ms": round(latency_ms, 1),
            "estimated_cost_usd": round(estimated_cost, 6),
            "decision": decision.to_dict(),
        }

    def _estimate_review_cost_usd(self, provider: str, usage: Dict[str, Any]) -> float:
        total_tokens = int(
            usage.get("total_tokens")
            or usage.get("completion_tokens")
            or usage.get("prompt_tokens")
            or 0
        )
        per_1k = {
            "ollama": 0.0,
            "github_models": 0.0002,
            "huggingface": 0.0004,
            "cloudflare_workers_ai": 0.0005,
            "xai_grok": 0.003,
            "openrouter": 0.0012,
            "codebuddy_brain": 0.0003,
        }.get(provider, 0.0)
        if total_tokens <= 0:
            return 0.0
        return round((total_tokens / 1000.0) * per_1k, 6)

    @staticmethod
    def _provider_lane(provider: str) -> ComputeLane:
        mapping = {
            "ollama": ComputeLane.LOCAL_OLLAMA,
            "github_models": ComputeLane.GITHUB_MODELS,
            "huggingface": ComputeLane.HUGGINGFACE,
            "cloudflare_workers_ai": ComputeLane.CLOUDFLARE_WORKERS_AI,
            "xai_grok": ComputeLane.XAI_GROK,
            "openrouter": ComputeLane.OPENROUTER,
            "codebuddy_brain": ComputeLane.CODEBUDDY_BRAIN,
        }
        return mapping.get(provider, ComputeLane.UNKNOWN)

    def _should_use_codebuddy_brain(self) -> bool:
        if not self._env_flag(CODEBUDDY_BRAIN_ENABLED_ENV, default=False):
            return False
        probe = CodeBuddyProbe().snapshot()
        return bool(probe.get("automation_ready") or probe.get("cli_login_ready"))

    @staticmethod
    def _is_useful_review_content(content: str) -> bool:
        cleaned = str(content or "").strip()
        if len(cleaned) < 24:
            return False
        lowered = cleaned.lower()
        if any(re.search(pattern, lowered) for pattern in LOW_SIGNAL_REVIEW_PATTERNS):
            return False
        return True

    @staticmethod
    def _env_flag(name: str, default: bool = False) -> bool:
        raw = (os.getenv(name) or "").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}


class SelfImprovementEngine:
    def __init__(
        self,
        infra: Optional[InfrastructureScout] = None,
        brain_router: Optional[HostedBrainRouter] = None,
        journal: Optional[SelfDevelopmentJournal] = None,
        lead_discovery: Optional[LeadDiscoveryScout] = None,
        agent_pain_solver: Optional[AgentPainSolver] = None,
        addons: Optional[NomadAddonManager] = None,
        codebuddy_runner: Optional[CodeBuddyReviewRunner] = None,
        lead_plan_path: Optional[Path] = None,
        autonomous_development: Optional[AutonomousDevelopmentLog] = None,
        mutual_aid: Optional[NomadMutualAidKernel] = None,
    ) -> None:
        self.infra = infra or InfrastructureScout()
        self.brain_router = brain_router or HostedBrainRouter()
        self.journal = journal or SelfDevelopmentJournal()
        self.lead_discovery = lead_discovery or LeadDiscoveryScout()
        self.agent_pain_solver = agent_pain_solver or AgentPainSolver()
        self.addons = addons or NomadAddonManager()
        self.codebuddy_runner = codebuddy_runner or CodeBuddyReviewRunner()
        self.autonomous_development = autonomous_development or AutonomousDevelopmentLog()
        self.mutual_aid = mutual_aid
        self.lead_scout_limit = max(1, int(os.getenv("NOMAD_LEAD_SCOUT_LIMIT", "3")))
        self.lead_plan_path = Path(
            os.getenv("NOMAD_ACTIVE_LEAD_PLAN_PATH")
            or str(lead_plan_path or DEFAULT_ACTIVE_LEAD_PLAN_PATH)
        )

    def run_cycle(
        self,
        objective: str = "",
        profile_id: str = "ai_first",
    ) -> Dict[str, Any]:
        objective = objective.strip() or (
            "Use Nomad's currently unlocked resources to improve scouting quality, "
            "fallback compute resilience, and bounded cycle quality."
        )
        best_stack = self.infra.best_stack(profile_id=profile_id)
        self_audit = self.infra.self_audit(profile_id=profile_id)
        compute = self.infra.compute_assessment(profile_id=profile_id)
        market_scan = (
            self.infra.market_scan(
                focus=self.lead_discovery.current_focus(),
                limit=4,
            )
            if hasattr(self.infra, "market_scan")
            else {}
        )
        context = self._compact_context(
            objective=objective,
            best_stack=best_stack,
            self_audit=self_audit,
            compute=compute,
            market_scan=market_scan,
        )
        local_actions = self._local_actions(self_audit=self_audit, compute=compute)
        quantum_tokens = self.addons.run_quantum_self_improvement(
            objective=objective,
            context=context,
        )
        if quantum_tokens.get("brain_context"):
            context["quantum_tokens"] = quantum_tokens["brain_context"]
        local_actions.extend(self._quantum_local_actions(quantum_tokens))
        brain_reviews = self.brain_router.review(objective=objective, context=context)
        predictive_routing = (
            self.brain_router.predictive_status(task_type="self_improvement_review")
            if hasattr(self.brain_router, "predictive_status")
            else {
                "enabled": False,
                "task_type": "self_improvement_review",
                "lane_status": {},
                "patterns": {"pattern_count": 0, "top_patterns": []},
                "self_healing": {"total_actions": 0},
            }
        )
        self_healing = (
            self.brain_router.run_self_healing_cycle()
            if hasattr(self.brain_router, "run_self_healing_cycle")
            else {
                "status": "skipped",
                "reason": "brain_router_without_self_healing",
                "actions_taken": 0,
                "actions": [],
            }
        )
        codebuddy_review = self._active_codebuddy_review(objective=objective, context=context)
        if codebuddy_review.get("ok") and codebuddy_review.get("review"):
            brain_reviews.append(
                {
                    "provider": "codebuddy",
                    "name": "Tencent CodeBuddy",
                    "configured": True,
                    "ok": True,
                    "useful": True,
                    "reviewer_mode": "diff_only_self_development",
                    "content": codebuddy_review["review"],
                    "data_release": codebuddy_review.get("data_release") or {},
                    "message": codebuddy_review.get("message", ""),
                }
            )
        if codebuddy_review.get("attempted"):
            local_actions.append(
                {
                    "type": "codebuddy_active_self_review",
                    "category": "self_improvement",
                    "title": "Use CodeBuddy to review Nomad's active self-development diff.",
                    "reason": codebuddy_review.get("message", ""),
                    "requires_human": False,
                    "ok": bool(codebuddy_review.get("ok")),
                    "issue": codebuddy_review.get("issue", ""),
                    "files": (codebuddy_review.get("data_release") or {}).get("files") or [],
                }
            )
        ok_reviews = [
            item
            for item in brain_reviews
            if item.get("ok") and item.get("useful", item.get("ok"))
        ]
        lead_scout = self._scout_agent_customer_leads(
            objective=objective,
            context=context,
            brain_reviews=ok_reviews,
        )
        lead_plan = self._persist_active_lead_plan(
            objective=objective,
            lead_scout=lead_scout,
        )
        if lead_plan.get("path"):
            lead_scout["help_draft_path"] = lead_plan["path"]
            lead_scout["help_draft_saved"] = lead_plan.get("ok", False)
        if lead_plan.get("error"):
            lead_scout["help_draft_error"] = lead_plan["error"]
        agent_pain_solver = self.agent_pain_solver.solve_from_context(
            objective=objective,
            context=context,
            lead_scout=lead_scout,
        )
        local_actions.extend(self._agent_pain_local_actions(agent_pain_solver))
        high_value_patterns = self._high_value_patterns()
        local_actions.extend(self._high_value_pattern_local_actions(high_value_patterns))
        compute_watch = self._compute_watch(compute, market_scan=market_scan)
        human_unlocks = self._human_unlocks(
            self_audit=self_audit,
            compute=compute,
            local_actions=local_actions,
        )
        self_development = {
            "previous_state": self.journal.load(),
        }

        analysis = (
            f"Nomad ran one self-improvement cycle for {context['profile']['label']}. "
            f"It used {len(ok_reviews)} autonomous brain review(s), led by local Ollama, "
            "and kept execution bounded to recommendations plus human unlock requests."
        )
        if compute_watch.get("needs_attention"):
            analysis += f" Compute watch: {compute_watch.get('headline', '')}"
        if market_scan.get("copy_now"):
            analysis += f" Market copy-now: {market_scan['copy_now'][0]}"
        if agent_pain_solver.get("solution"):
            solution = agent_pain_solver["solution"]
            analysis += (
                f" Agent pain solver: {solution.get('title')} for "
                f"{solution.get('pain_type')} is ready for requester-facing help and Nomad self-use."
            )
        if (high_value_patterns.get("patterns") or []):
            top_pattern = high_value_patterns["patterns"][0]
            analysis += (
                f" High-value pattern watch: {top_pattern.get('title')} for "
                f"{top_pattern.get('pain_type')} has "
                f"{top_pattern.get('occurrence_count', 0)} verified occurrences."
            )
        if quantum_tokens.get("selected_strategy"):
            selected = quantum_tokens["selected_strategy"]
            analysis += (
                f" Quantum tokens selected {selected.get('title', selected.get('strategy_id'))} "
                "as an exploration receipt for this cycle."
            )
        if codebuddy_review.get("attempted"):
            if codebuddy_review.get("ok"):
                analysis += " CodeBuddy actively reviewed the bounded self-development diff for this cycle."
            else:
                analysis += f" CodeBuddy active review was attempted but did not complete: {codebuddy_review.get('issue', 'unknown')}."
        top_runtime_pattern = ((predictive_routing.get("patterns") or {}).get("top_patterns") or [])
        if top_runtime_pattern:
            pattern = top_runtime_pattern[0]
            analysis += (
                f" Runtime pattern memory now prefers {pattern.get('lane')} for "
                f"{pattern.get('task_type')} with score {pattern.get('efficiency_score', 0.0):.2f}."
            )
        if self_healing.get("actions_taken"):
            analysis += f" Runtime correction executed {self_healing.get('actions_taken')} bounded adjustment(s)."
        if human_unlocks:
            analysis += f" Next human unlock: {human_unlocks[0]['short_ask']}"

        result = {
            "mode": "self_improvement_cycle",
            "deal_found": False,
            "profile": context["profile"],
            "objective": objective,
            "timestamp": datetime.now(UTC).isoformat(),
            "resources": context["resources"],
            "local_actions": local_actions,
            "brain_reviews": brain_reviews,
            "external_review_count": len(ok_reviews),
            "predictive_routing": predictive_routing,
            "self_healing": self_healing,
            "compute_watch": compute_watch,
            "market_scan": market_scan,
            "quantum_tokens": quantum_tokens,
            "codebuddy_review": codebuddy_review,
            "lead_scout": lead_scout,
            "agent_pain_solver": agent_pain_solver,
            "high_value_patterns": high_value_patterns,
            "human_unlocks": human_unlocks,
            "self_development": self_development,
            "analysis": analysis,
        }
        autonomous_development = self.autonomous_development.apply_cycle(
            objective=objective,
            self_improvement=result,
        )
        result["autonomous_development"] = autonomous_development
        if autonomous_development.get("ok") and not autonomous_development.get("skipped"):
            analysis += f" Autonomous development: {(autonomous_development.get('action') or {}).get('title', '')}."
            result["analysis"] = analysis
        state = self.journal.record_cycle(result)
        result["self_development"] = {
            "cycle_count": state.get("cycle_count", 0),
            "last_cycle_at": state.get("last_cycle_at", ""),
            "current_objective": state.get("current_objective", ""),
            "next_objective": state.get("next_objective", ""),
            "open_human_unlock": state.get("open_human_unlock"),
            "human_unlocks": state.get("self_development_unlocks") or [],
            "high_value_pattern": state.get("last_high_value_pattern"),
        }
        try:
            from nomad_operator_desk import operator_metrics_record

            operator_metrics_record(
                "self_improvement_cycle",
                {
                    "objective_preview": str(objective)[:240],
                    "cycle_count_after": int(state.get("cycle_count") or 0),
                    "external_review_count": int(result.get("external_review_count") or 0),
                    "autonomous_skipped": bool((autonomous_development or {}).get("skipped")),
                    "autonomous_reason": str((autonomous_development or {}).get("reason") or ""),
                    "human_unlocks_count": len(human_unlocks or []),
                },
            )
        except Exception:
            pass
        return result

    def _active_codebuddy_review(self, objective: str, context: Dict[str, Any]) -> Dict[str, Any]:
        codebuddy = (
            ((context.get("resources") or {}).get("developer_assistants") or {}).get("codebuddy")
            or {}
        )
        active = HostedBrainRouter._env_flag(CODEBUDDY_ACTIVE_SELF_REVIEW_ENV, default=False)
        if not active:
            return {
                "mode": "codebuddy_review",
                "schema": "nomad.codebuddy_review.v1",
                "attempted": False,
                "skipped": True,
                "ok": False,
                "issue": "codebuddy_active_self_review_disabled",
                "message": f"Set {CODEBUDDY_ACTIVE_SELF_REVIEW_ENV}=true to let Nomad use CodeBuddy during /cycle.",
            }
        if not codebuddy.get("automation_ready"):
            return {
                "mode": "codebuddy_review",
                "schema": "nomad.codebuddy_review.v1",
                "attempted": False,
                "skipped": True,
                "ok": False,
                "issue": "codebuddy_not_ready_for_active_self_review",
                "message": codebuddy.get("message", "CodeBuddy is not ready for active self-review."),
            }

        review_objective = (
            "Review Nomad's current bounded self-development diff for regressions, "
            f"missing tests, and goal alignment. Cycle objective: {objective}"
        )
        result = self.codebuddy_runner.review(
            objective=review_objective,
            approval="share_diff",
            paths=self._codebuddy_self_review_paths(),
        )
        result["attempted"] = True
        result["active_self_review"] = True
        return result

    def _codebuddy_self_review_paths(self) -> List[str]:
        configured = [
            item.strip()
            for item in re.split(r"[,;\n]+", os.getenv("NOMAD_CODEBUDDY_SELF_REVIEW_PATHS", ""))
            if item.strip()
        ]
        return configured or list(DEFAULT_CODEBUDDY_SELF_REVIEW_PATHS)

    def _compact_context(
        self,
        objective: str,
        best_stack: Dict[str, Any],
        self_audit: Dict[str, Any],
        compute: Dict[str, Any],
        market_scan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        probe = compute.get("probe") or {}
        hosted = probe.get("hosted") or {}
        developer_assistants = probe.get("developer_assistants") or {}
        brains = compute.get("brains") or {}
        stack = best_stack.get("stack") or []
        upgrades = self_audit.get("upgrades") or []
        resources = {
            "brain_count": brains.get("brain_count", 0),
            "primary_brain": brains.get("primary"),
            "fallback_brains": brains.get("secondary") or [],
            "github_models": self._provider_state(hosted.get("github_models") or {}),
            "huggingface": self._provider_state(hosted.get("huggingface") or {}),
            "cloudflare_workers_ai": self._provider_state(hosted.get("cloudflare_workers_ai") or {}),
            "xai_grok": self._provider_state(hosted.get("xai_grok") or {}),
            "openrouter": self._provider_state(hosted.get("openrouter") or {}),
            "ollama": {
                "available": (probe.get("ollama") or {}).get("available", False),
                "api_reachable": (probe.get("ollama") or {}).get("api_reachable", False),
                "model_count": (probe.get("ollama") or {}).get("count", 0),
            },
            "developer_assistants": {
                "codebuddy": developer_assistants.get("codebuddy") or {},
            },
        }
        return {
            "objective": objective,
            "mission": mission_context(),
            "profile": best_stack.get("profile") or self_audit.get("profile") or {},
            "overall_score": best_stack.get("overall_score", 0.0),
            "recommended_stack": [
                {
                    "category": item.get("category"),
                    "name": item.get("name"),
                    "score": item.get("agent_satisfaction_score"),
                    "tradeoff": item.get("tradeoff"),
                }
                for item in stack[:6]
            ],
            "upgrades": upgrades[:5],
            "resources": resources,
            "recent_direct_agent_sessions": self._recent_direct_agent_sessions(),
            "recent_service_tasks": self._recent_service_tasks(),
            "recent_outreach_campaigns": self._recent_outreach_campaigns(),
            "market_context": (market_scan or {}).get("brain_context") or {},
            "compute_analysis": compute.get("analysis", ""),
            "self_analysis": self_audit.get("analysis", ""),
        }

    def _quantum_local_actions(self, quantum_tokens: Dict[str, Any]) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        for improvement in (quantum_tokens.get("improvements") or [])[:3]:
            actions.append(
                {
                    "type": "quantum_token_self_improvement",
                    "title": improvement.get("title", "Quantum token self-improvement"),
                    "description": improvement.get("agent_use", ""),
                    "requires_human": False,
                    "verification": improvement.get("verification", ""),
                    "qtoken_id": improvement.get("qtoken_id", ""),
                }
            )
        for unlock in quantum_tokens.get("human_unlocks") or []:
            actions.append(
                {
                    "type": "quantum_human_unlock",
                    "title": unlock.get("candidate_name", "Real quantum provider unlock"),
                    "description": unlock.get("short_ask", ""),
                    "requires_human": True,
                    "human_unlock": unlock,
                }
            )
        return actions

    def _recent_direct_agent_sessions(self, limit: int = 5) -> List[Dict[str, Any]]:
        path = Path(__file__).resolve().parent / "nomad_direct_sessions.json"
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        sessions = list((payload.get("sessions") or {}).values())
        sessions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        compact: List[Dict[str, Any]] = []
        for session in sessions[:limit]:
            turns = session.get("turns") or []
            last_turn = turns[-1] if turns else {}
            compact.append(
                {
                    "session_id": session.get("session_id", ""),
                    "requester_agent": session.get("requester_agent", ""),
                    "status": session.get("status", ""),
                    "last_pain_type": session.get("last_pain_type", ""),
                    "last_task_id": session.get("last_task_id", ""),
                    "last_diagnosis": (last_turn.get("free_diagnosis") or {}).get("first_30_seconds", ""),
                }
            )
        return compact

    def _recent_service_tasks(self, limit: int = 5) -> List[Dict[str, Any]]:
        path = Path(__file__).resolve().parent / "nomad_service_tasks.json"
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        tasks = list((payload.get("tasks") or {}).values())
        tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        compact: List[Dict[str, Any]] = []
        for task in tasks[:limit]:
            allocation = task.get("payment_allocation") or {}
            compact.append(
                {
                    "task_id": task.get("task_id", ""),
                    "service_type": task.get("service_type", ""),
                    "status": task.get("status", ""),
                    "budget_native": task.get("budget_native"),
                    "solver_budget_native": allocation.get("solver_budget_native"),
                    "treasury_stake_native": allocation.get("treasury_stake_native"),
                }
            )
        return compact

    def _recent_outreach_campaigns(self, limit: int = 5) -> List[Dict[str, Any]]:
        path = Path(__file__).resolve().parent / "nomad_agent_campaigns.json"
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        campaigns = list((payload.get("campaigns") or {}).values())
        campaigns.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        compact: List[Dict[str, Any]] = []
        for campaign in campaigns[:limit]:
            stats = campaign.get("stats") or {}
            compact.append(
                {
                    "campaign_id": campaign.get("campaign_id", ""),
                    "status": campaign.get("status", ""),
                    "service_type": campaign.get("service_type", ""),
                    "sent": stats.get("sent", 0),
                    "queued": stats.get("queued", 0),
                    "failed": stats.get("failed", 0),
                    "duplicates": stats.get("duplicates", 0),
                }
            )
        return compact

    def _provider_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "configured": payload.get("configured", False),
            "reachable": payload.get("reachable", False),
            "available": payload.get("available", False),
            "model_count": payload.get("model_count", 0),
            "sample_models": payload.get("sample_models") or [],
            "message": payload.get("message", ""),
        }

    def _local_actions(
        self,
        self_audit: Dict[str, Any],
        compute: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        for item in (self_audit.get("upgrades") or [])[:3]:
            actions.append(
                {
                    "type": "stack_upgrade",
                    "category": item.get("category"),
                    "title": f"Align {item.get('category')} with {item.get('recommended')}",
                    "reason": item.get("reason", ""),
                    "requires_human": False,
                }
            )

        brains = compute.get("brains") or {}
        if brains.get("brain_count", 0) < 2:
            actions.append(
                {
                    "type": "compute_resilience",
                    "category": "compute",
                    "title": "Unlock a second brain before relying on autonomous cycles.",
                    "reason": "Self-improvement needs at least one fallback when Codex, Gemini, local models or quotas are exhausted.",
                    "requires_human": True,
                }
            )

        codebuddy = (compute.get("developer_assistants") or {}).get("codebuddy") or {}
        if codebuddy:
            actions.append(
                {
                    "type": "codebuddy_self_development_lane",
                    "category": "self_improvement",
                    "title": (
                        "Use CodeBuddy as a gated reviewer lane."
                        if codebuddy.get("automation_ready")
                        else "Keep CodeBuddy as an optional reviewer unlock."
                    ),
                    "reason": codebuddy.get("message", ""),
                    "requires_human": not bool(codebuddy.get("automation_ready")),
                    "human_unlock": None
                    if codebuddy.get("automation_ready")
                    else {
                        "candidate_id": "codebuddy-self-development-reviewer",
                        "candidate_name": "Tencent CodeBuddy reviewer lane",
                        "category": "self_improvement",
                        "short_ask": "Enable CodeBuddy only through its official international or enterprise route.",
                        "human_action": codebuddy.get("next_action", ""),
                        "human_deliverable": "CODEBUDDY_API_KEY=..., NOMAD_CODEBUDDY_ENABLED=true, or /skip last.",
                        "success_criteria": [
                            "Nomad's next /compute shows CodeBuddy automation_ready=true, or the unlock is explicitly skipped.",
                            "Nomad does not use a region bypass or unapproved China-site route.",
                        ],
                        "example_response": "NOMAD_CODEBUDDY_ENABLED=true\nCODEBUDDY_API_KEY=...",
                    },
                }
            )

        actions.append(
            {
                "type": "cycle_hygiene",
                "category": "self_improvement",
                "title": "Compare Nomad's local plan against its current brain review and keep one small next action.",
                "reason": "A bounded loop prevents Nomad from drifting while still using unlocked resources for better scouting.",
                "requires_human": False,
            }
        )
        return actions

    @staticmethod
    def _agent_pain_local_actions(agent_pain_solver: Dict[str, Any]) -> List[Dict[str, Any]]:
        solution = agent_pain_solver.get("solution") or {}
        self_apply = solution.get("nomad_self_apply") or {}
        actions: List[Dict[str, Any]] = []
        for action in self_apply.get("local_actions") or []:
            if not isinstance(action, dict):
                continue
            actions.append(
                {
                    "type": action.get("type") or "agent_pain_solution",
                    "category": action.get("category") or solution.get("pain_type") or "self_improvement",
                    "title": action.get("title") or agent_pain_solver.get("next_nomad_action") or "Apply agent pain solution.",
                    "reason": action.get("reason") or agent_pain_solver.get("analysis") or "",
                    "requires_human": bool(action.get("requires_human", False)),
                }
            )
        return actions[:2]

    def _high_value_patterns(self) -> Dict[str, Any]:
        if self.mutual_aid is None:
            return {
                "mode": "nomad_high_value_patterns",
                "schema": "nomad.high_value_patterns.v1",
                "ok": True,
                "pattern_count": 0,
                "patterns": [],
                "analysis": "No shared Mutual-Aid kernel was attached to this self-improvement engine.",
            }
        try:
            return self.mutual_aid.list_high_value_patterns(limit=3, min_repeat_count=2)
        except Exception as exc:
            return {
                "mode": "nomad_high_value_patterns",
                "schema": "nomad.high_value_patterns.v1",
                "ok": False,
                "pattern_count": 0,
                "patterns": [],
                "error": "high_value_pattern_watch_failed",
                "issue": str(exc),
            }

    @staticmethod
    def _high_value_pattern_local_actions(high_value_patterns: Dict[str, Any]) -> List[Dict[str, Any]]:
        patterns = high_value_patterns.get("patterns") or []
        if not patterns:
            return []
        top_pattern = patterns[0]
        return [
            {
                "type": "high_value_pattern_watch",
                "category": top_pattern.get("pain_type") or "self_improvement",
                "title": (
                    f"Keep repeated pattern '{top_pattern.get('title') or 'agent rescue pattern'}' "
                    "in watch mode and compare it against future evidence."
                ),
                "reason": (
                    f"{top_pattern.get('occurrence_count', 0)} verified occurrences with "
                    f"avg truth {top_pattern.get('avg_truth_score', 0)} and "
                    f"avg reuse {top_pattern.get('avg_reuse_value', 0)}. Do not assign it a fixed role yet."
                ),
                "requires_human": False,
            }
        ]

    def _scout_agent_customer_leads(
        self,
        objective: str,
        context: Dict[str, Any],
        brain_reviews: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        active_lead = self._extract_active_lead(objective)
        explicit_lead_requested = self._objective_requests_explicit_lead(objective)
        lead_queries = self._lead_queries(brain_reviews)
        selected_focus = self.lead_discovery.current_focus()
        source_plan = self.lead_discovery.source_plan(selected_focus)
        public_surfaces = [
            item.get("url") or item.get("name") or ""
            for item in (source_plan.get("public_surfaces") or [])
            if isinstance(item, dict) and (item.get("url") or item.get("name"))
        ] or [
            "GitHub issues and discussions",
            "Hugging Face model/community discussions",
            "public Telegram/Discord landing pages where visible without login",
            "agent framework repositories",
            "AI builder launch posts and docs",
        ]
        outreach_queries = [
            str(item).strip()
            for item in (source_plan.get("outreach_queries") or [])
            if str(item).strip()
        ]
        lead_hypotheses: List[Dict[str, str]] = []
        for review in brain_reviews:
            content = (review.get("content") or "").strip()
            if not content:
                continue
            lead_hypotheses.append(
                {
                    "source_brain": review.get("name", "hosted brain"),
                    "model": review.get("model", ""),
                    "hypothesis": content[:700],
                }
            )

        collected_leads: List[Dict[str, Any]] = []
        discovery_passes: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()
        for query in lead_queries:
            if len(collected_leads) >= self.lead_scout_limit:
                break
            scoped = self.lead_discovery.scout_public_leads(
                query=query,
                limit=max(1, self.lead_scout_limit - len(collected_leads)),
                focus=selected_focus,
            )
            leads = scoped.get("leads") or []
            discovery_passes.append(
                {
                    "query": query,
                    "lead_count": len(leads),
                    "errors": scoped.get("errors") or [],
                }
            )
            for lead in leads:
                url = str(lead.get("url") or lead.get("html_url") or "").strip()
                dedupe_key = url or str(lead.get("title") or "").strip().lower()
                if not dedupe_key or dedupe_key in seen_urls:
                    continue
                seen_urls.add(dedupe_key)
                collected_leads.append(lead)
                if len(collected_leads) >= self.lead_scout_limit:
                    break

        compute_leads = [
            lead
            for lead in collected_leads
            if str(lead.get("recommended_service_type") or "") == "compute_auth"
        ]
        addressable_leads = [lead for lead in collected_leads if lead.get("addressable_now")]
        monetizable_leads = [lead for lead in collected_leads if lead.get("monetizable_now")]
        monetizable_compute_leads = [
            lead for lead in compute_leads
            if lead.get("addressable_now") and lead.get("monetizable_now")
        ]
        addressable_compute_leads = [
            lead for lead in compute_leads
            if lead.get("addressable_now")
        ]
        selected_lead = None
        if active_lead and explicit_lead_requested:
            selected_lead = active_lead
        elif active_lead and self._active_lead_matches_focus(active_lead, selected_focus):
            selected_lead = active_lead
        elif monetizable_compute_leads:
            selected_lead = monetizable_compute_leads[0]
        elif monetizable_leads:
            selected_lead = monetizable_leads[0]
        elif addressable_compute_leads:
            selected_lead = addressable_compute_leads[0]
        elif addressable_leads:
            selected_lead = addressable_leads[0]
        elif compute_leads:
            selected_lead = compute_leads[0]
        elif collected_leads:
            selected_lead = collected_leads[0]
        elif active_lead:
            selected_lead = active_lead
        next_agent_action = (
            "Use the listed public surfaces and hosted-brain hypotheses to identify one concrete "
            "AI agent, repo, builder or bot with infrastructure pain."
        )
        if active_lead and selected_lead == active_lead:
            next_agent_action = (
                f"Work this specific lead first: {active_lead['url'] or active_lead['name']}. "
                f"Validate the pain signal, draft one helpful response or repro/PR plan, and do not post publicly "
                "without human permission."
            )
        elif monetizable_compute_leads:
            lead = monetizable_compute_leads[0]
            next_agent_action = (
                f"Prioritize the monetizable compute lead {lead.get('url') or lead.get('title')}. "
                "Draft one concrete diagnosis, quote the smallest paid unblock, and keep the response private until asked."
            )
        elif monetizable_leads:
            lead = monetizable_leads[0]
            next_agent_action = (
                f"Prioritize the monetizable lead {lead.get('url') or lead.get('title')} in {lead.get('addressable_label') or 'a serviceable pain class'}. "
                "Draft the smallest useful response and a paid follow-up path."
            )
        elif addressable_compute_leads:
            lead = addressable_compute_leads[0]
            next_agent_action = (
                f"Prioritize the compute lead {lead.get('url') or lead.get('title')}. "
                "Draft a compute fallback, quota isolation, or token diagnosis plan before moving to broader outreach."
            )
        elif addressable_leads:
            lead = addressable_leads[0]
            next_agent_action = (
                f"Work the addressable lead {lead.get('url') or lead.get('title')} in {lead.get('addressable_label') or 'a serviceable pain class'}. "
                "Draft one bounded fix path and one paid service upgrade."
            )
        elif collected_leads:
            lead = collected_leads[0]
            next_agent_action = (
                f"Validate the public lead {lead.get('url') or lead.get('title')} and draft the first bounded help action. "
                "Keep it private unless human approval explicitly allows public posting."
            )

        result = {
            "mode": "lead_scout",
            "focus": selected_focus,
            "objective": (
                "Nomad should find agent-customer pain autonomously; the human only unlocks auth, "
                "CAPTCHA, private communities, API approvals or posting permissions."
            ),
            "search_queries": lead_queries,
            "outreach_queries": outreach_queries,
            "public_surfaces": public_surfaces,
            "lead_hypotheses": lead_hypotheses[:3],
            "discovery_passes": discovery_passes,
            "leads": collected_leads[: self.lead_scout_limit],
            "compute_leads": compute_leads[:2],
            "addressable_leads": addressable_leads[:2],
            "monetizable_leads": monetizable_leads[:2],
            "addressable_count": len(addressable_leads),
            "monetizable_count": len(monetizable_leads),
            "human_help_only_for": [
                "login or CAPTCHA",
                "private community invite",
                "API key or quota approval",
                "permission to contact or post",
                "confirming a lead is worth serving if public data is ambiguous",
            ],
            "next_agent_action": next_agent_action,
        }
        if selected_lead:
            result["active_lead"] = selected_lead
            result["help_draft"] = self.lead_discovery.draft_first_help_action(
                selected_lead,
                approval="draft_only",
            )
        return result

    def _persist_active_lead_plan(
        self,
        objective: str,
        lead_scout: Dict[str, Any],
    ) -> Dict[str, Any]:
        active_lead = lead_scout.get("active_lead") or {}
        help_draft = lead_scout.get("help_draft") or {}
        if not active_lead or not help_draft:
            return {}
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "objective": objective,
            "focus": lead_scout.get("focus", ""),
            "lead": {
                "title": active_lead.get("title") or active_lead.get("name") or "",
                "url": active_lead.get("url") or active_lead.get("html_url") or "",
                "repo_url": active_lead.get("repo_url") or "",
                "pain": active_lead.get("pain") or active_lead.get("pain_signal") or "",
                "pain_terms": active_lead.get("pain_terms") or [],
                "pain_evidence": active_lead.get("pain_evidence") or [],
                "public_issue_excerpt": active_lead.get("public_issue_excerpt") or "",
                "recommended_service_type": active_lead.get("recommended_service_type") or "",
                "addressable_label": active_lead.get("addressable_label") or "",
                "monetizable_now": bool(active_lead.get("monetizable_now")),
                "first_help_action": active_lead.get("first_help_action") or "",
                "quote_summary": active_lead.get("quote_summary") or "",
                "delivery_target": active_lead.get("delivery_target") or "",
                "memory_upgrade": active_lead.get("memory_upgrade") or "",
                "product_package": active_lead.get("product_package") or "",
                "solution_pattern": active_lead.get("solution_pattern") or "",
            },
            "help_draft": help_draft,
            "next_agent_action": lead_scout.get("next_agent_action", ""),
            "search_queries": lead_scout.get("search_queries") or [],
            "outreach_queries": lead_scout.get("outreach_queries") or [],
            "discovery_passes": lead_scout.get("discovery_passes") or [],
        }
        try:
            self.lead_plan_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            return {
                "ok": False,
                "path": str(self.lead_plan_path),
                "error": str(exc),
            }
        return {
            "ok": True,
            "path": str(self.lead_plan_path),
        }

    def _lead_queries(self, brain_reviews: List[Dict[str, Any]]) -> List[str]:
        configured = [
            item.strip()
            for item in re.split(r"[\r\n|]+", os.getenv("NOMAD_LEAD_SCOUT_QUERIES", ""))
            if item.strip()
        ]
        queries = configured or self.lead_discovery.default_queries()
        for review in brain_reviews:
            hinted = self._query_hint_from_brain(review.get("content") or "")
            if hinted and self._looks_like_lead_query(hinted):
                queries.insert(0, hinted)
        deduped: List[str] = []
        seen: set[str] = set()
        for raw in queries:
            cleaned = str(raw or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped[:8]

    @staticmethod
    def _query_hint_from_brain(content: str) -> str:
        text = str(content or "").strip()
        if not text:
            return ""
        for line in text.splitlines():
            if ":" not in line:
                continue
            label, value = line.split(":", 1)
            if label.strip().lower() == "query":
                return value.strip()
        return ""

    @staticmethod
    def _looks_like_lead_query(query: str) -> bool:
        cleaned = str(query or "").strip()
        lowered = cleaned.lower()
        if not cleaned:
            return False
        if cleaned.endswith("?"):
            return False
        if lowered.startswith(("what ", "why ", "how ", "can ", "should ", "could ")):
            return False
        if any(token in lowered for token in ("repo:", "is:issue", "agent-card", ".well-known", "a2a", "mcp")):
            return True
        return len(cleaned.split()) <= 10

    def _compute_watch(self, compute: Dict[str, Any], market_scan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        probe = compute.get("probe") or {}
        brains = compute.get("brains") or {}
        ollama = probe.get("ollama") or {}
        hosted = probe.get("hosted") or {}
        external_compute = [
            item.get("name", "")
            for item in ((market_scan or {}).get("compute_opportunities") or [])[:3]
            if item.get("name")
        ]
        active_lanes: List[str] = []
        if ollama.get("api_reachable") and ollama.get("count", 0) > 0:
            active_lanes.append("ollama")
        for name, payload in hosted.items():
            if isinstance(payload, dict) and payload.get("available"):
                active_lanes.append(str(name))
        fallback_names = [
            str(item.get("name") or "").strip()
            for item in (brains.get("secondary") or [])
            if str(item.get("name") or "").strip()
        ]
        activation_request = compute.get("activation_request") or {}
        needs_attention = bool(
            not active_lanes
            or brains.get("brain_count", 0) < 2
            or activation_request
        )
        headline = compute.get("analysis", "")
        if activation_request:
            headline = (
                f"{activation_request.get('candidate_name', 'Next compute unlock')} should be checked next. "
                f"{activation_request.get('ask', '')}".strip()
            )
        return {
            "needs_attention": needs_attention,
            "brain_count": brains.get("brain_count", 0),
            "primary_brain": (brains.get("primary") or {}).get("name", ""),
            "fallback_brains": fallback_names[:3],
            "active_lanes": active_lanes,
            "external_free_lanes": external_compute,
            "headline": headline[:280],
            "activation_request": {
                "candidate_name": activation_request.get("candidate_name", ""),
                "category": activation_request.get("category", ""),
                "short_ask": activation_request.get("short_ask", ""),
            },
        }

    def _extract_active_lead(self, objective: str) -> Optional[Dict[str, str]]:
        text = (objective or "").strip()
        if "lead:" not in text.lower() and "lead_url=" not in text.lower() and "url=" not in text.lower():
            return None

        url_match = re.search(r"\b(?:LEAD_URL|URL)=([^\s]+)", text, flags=re.IGNORECASE)
        pain_match = re.search(
            r"\bPain=(.*?)(?:\s+Nomad task:|\s+for\s+[a-z0-9_]+$|$)",
            text,
            flags=re.IGNORECASE,
        )
        task_match = re.search(
            r"\bNomad task:\s*(.*?)(?:\s+for\s+[a-z0-9_]+$|$)",
            text,
            flags=re.IGNORECASE,
        )
        name = text
        lead_match = re.search(r"Lead:\s*(.*?)(?:\s+URL=|\s+Pain=|\s+Nomad task:|$)", text, flags=re.IGNORECASE)
        if lead_match and lead_match.group(1).strip():
            name = lead_match.group(1).strip()

        return {
            "name": name,
            "url": url_match.group(1).strip() if url_match else "",
            "pain": pain_match.group(1).strip() if pain_match else "",
            "requested_task": task_match.group(1).strip() if task_match else "",
            "first_help_action": (
                "Draft a concise GitHub comment, repro test outline, or PR plan that reduces the named infrastructure pain."
            ),
        }

    @staticmethod
    def _active_lead_matches_focus(lead: Dict[str, str], focus: str) -> bool:
        selected_focus = (focus or "").strip().lower()
        if selected_focus == "balanced":
            return True
        text = "\n".join(
            [
                str(lead.get("name") or ""),
                str(lead.get("pain") or ""),
                str(lead.get("requested_task") or ""),
                str(lead.get("url") or ""),
            ]
        ).lower()
        if selected_focus == "compute_auth":
            terms = ("quota", "rate limit", "token", "auth", "authentication", "compute", "inference", "permission")
            return sum(1 for term in terms if term in text) >= 2
        if selected_focus == "human_in_loop":
            return any(term in text for term in ("human in the loop", "human", "approval", "captcha", "verification"))
        return False

    @staticmethod
    def _objective_requests_explicit_lead(objective: str) -> bool:
        text = (objective or "").lower()
        return "lead:" in text or "lead_url=" in text or "url=" in text

    def _human_unlocks(
        self,
        self_audit: Dict[str, Any],
        compute: Dict[str, Any],
        local_actions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        unlocks: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        best_request = self.infra.best_activation_request().get("request")
        if isinstance(best_request, dict) and best_request.get("candidate_name"):
            key = (best_request.get("candidate_name", ""), best_request.get("short_ask", ""))
            seen.add(key)
            unlocks.append(self._freshen_unlock(best_request))

        for candidate in (
            compute.get("activation_request"),
            self_audit.get("activation_request"),
        ):
            if isinstance(candidate, dict) and candidate.get("candidate_name"):
                key = (candidate.get("candidate_name", ""), candidate.get("short_ask", ""))
                if key not in seen:
                    seen.add(key)
                    unlocks.append(self._freshen_unlock(candidate))

        if not unlocks:
            for action in local_actions:
                if action.get("requires_human"):
                    unlocks.append(
                        self._freshen_unlock(
                            {
                                "candidate_name": action["title"],
                                "role": "human unlock",
                                "lane_state": "pending",
                                "ask": action["reason"],
                                "short_ask": action["title"],
                                "reason": action["reason"],
                                "env_vars": [],
                                "steps": ["Run /compute, then unlock the highest-ranked inactive compute lane."],
                            }
                        )
                    )
                    break
        if not unlocks:
            unlocks.append(
                self._freshen_unlock(
                    {
                        "category": "self_improvement",
                        "candidate_name": "Fresh agent frontier",
                        "role": "human unlock task",
                        "lane_state": "fresh",
                        "ask": (
                            "Give Nomad one new verifiable resource, account permission, endpoint, "
                            "dataset, model, token, or agent-customer lead to test in the next cycle."
                        ),
                        "short_ask": "Create one fresh unlock lead for Nomad.",
                        "reason": "Every autonomous cycle should end with a new frontier for humans to unlock.",
                        "env_vars": [],
                        "steps": [
                            "Send a token with /token if it is a credential.",
                            "Otherwise send the URL, account step, repo permission, endpoint or lead.",
                            "Run /cycle after the unlock so Nomad can generate the next task.",
                        ],
                    }
                )
            )
        return unlocks[:2]

    def _freshen_unlock(self, unlock: Dict[str, Any]) -> Dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        fresh = dict(unlock)
        category = fresh.get("category") or "compute"
        generated_key = generated_at.replace("-", "").replace(":", "").replace(".", "")[:16]
        fresh["generated_at"] = generated_at
        fresh["task_id"] = f"{category}-{generated_key}"
        fresh["fresh"] = True
        fresh["accepts_telegram_tokens"] = bool(fresh.get("env_vars"))
        steps = list(fresh.get("steps") or [])
        if fresh.get("env_vars") and not any("/token" in step for step in steps):
            steps.insert(
                0,
                "If this unlock is a credential, send it in Telegram as `/token <provider> <token>` or `ENV_VAR=...`.",
            )
        fresh["steps"] = steps
        return self.infra._make_activation_request_concrete(fresh)
