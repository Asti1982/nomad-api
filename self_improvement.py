import json
import os
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from infra_scout import InfrastructureScout
from mission import MISSION_STATEMENT, mission_context


load_dotenv()


class HostedBrainRouter:
    """Routes bounded self-improvement prompts to hosted fallback brains."""

    def __init__(self) -> None:
        load_dotenv(override=True)
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
        self.github_model = (os.getenv("NOMAD_GITHUB_MODEL") or "openai/gpt-4o-mini").strip()
        self.hf_model = (
            os.getenv("NOMAD_HF_MODEL")
            or "meta-llama/Llama-3.1-8B-Instruct:cerebras"
        ).strip()
        self.github_api_version = (
            os.getenv("NOMAD_GITHUB_MODELS_API_VERSION") or "2026-03-10"
        ).strip()
        self.timeout_seconds = int(os.getenv("NOMAD_SELF_IMPROVE_TIMEOUT_SECONDS", "25"))
        self.max_tokens = int(os.getenv("NOMAD_SELF_IMPROVE_MAX_TOKENS", "700"))

    def review(self, objective: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        messages = self._messages(objective=objective, context=context)
        results: List[Dict[str, Any]] = []
        results.append(self._github_review(messages))
        results.append(self._huggingface_review(messages))
        return results

    def _messages(
        self,
        objective: str,
        context: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        system = (
            "You are an external reviewer for Nomad, an autonomous AI-infrastructure scout. "
            f"Mission: {MISSION_STATEMENT} "
            "Your job is to improve Nomad's scouting and self-development loop. "
            "Do not ask for secrets, do not propose unsafe code execution, and keep actions small, "
            "testable, and useful for another agent."
        )
        user = (
            "Objective:\n"
            f"{objective}\n\n"
            "Current Nomad context as JSON:\n"
            f"{json.dumps(context, ensure_ascii=True, indent=2)}\n\n"
            "Return concise JSON with keys: diagnosis, next_actions, human_unlocks, risks. "
            "next_actions should be an array of concrete one-cycle improvements."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _github_review(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if not self.github_token:
            return {
                "provider": "github_models",
                "name": "GitHub Models",
                "configured": False,
                "ok": False,
                "message": "No GITHUB_TOKEN or GITHUB_PERSONAL_ACCESS_TOKEN configured.",
            }

        try:
            response = requests.post(
                "https://models.github.ai/inference/chat/completions",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.github_token}",
                    "Content-Type": "application/json",
                    "X-GitHub-Api-Version": self.github_api_version,
                },
                json={
                    "model": self.github_model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                    "temperature": 0.2,
                },
                timeout=self.timeout_seconds,
            )
            return self._parse_chat_response(
                response=response,
                provider="github_models",
                name="GitHub Models",
                model=self.github_model,
            )
        except Exception as exc:
            return {
                "provider": "github_models",
                "name": "GitHub Models",
                "model": self.github_model,
                "configured": True,
                "ok": False,
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
        return {
            "provider": provider,
            "name": name,
            "model": model,
            "configured": True,
            "ok": bool(content),
            "content": content.strip(),
            "usage": payload.get("usage") or {},
            "message": "Review completed." if content else "No review content returned.",
        }


class SelfImprovementEngine:
    def __init__(
        self,
        infra: Optional[InfrastructureScout] = None,
        brain_router: Optional[HostedBrainRouter] = None,
    ) -> None:
        self.infra = infra or InfrastructureScout()
        self.brain_router = brain_router or HostedBrainRouter()

    def run_cycle(
        self,
        objective: str = "",
        profile_id: str = "ai_first",
    ) -> Dict[str, Any]:
        objective = objective.strip() or (
            "Use Nomad's currently unlocked resources to improve scouting quality, "
            "fallback compute resilience, and self-development velocity."
        )
        best_stack = self.infra.best_stack(profile_id=profile_id)
        self_audit = self.infra.self_audit(profile_id=profile_id)
        compute = self.infra.compute_assessment(profile_id=profile_id)
        context = self._compact_context(
            objective=objective,
            best_stack=best_stack,
            self_audit=self_audit,
            compute=compute,
        )
        local_actions = self._local_actions(self_audit=self_audit, compute=compute)
        brain_reviews = self.brain_router.review(objective=objective, context=context)
        ok_reviews = [item for item in brain_reviews if item.get("ok")]
        human_unlocks = self._human_unlocks(
            self_audit=self_audit,
            compute=compute,
            local_actions=local_actions,
        )

        analysis = (
            f"Nomad ran one self-improvement cycle for {context['profile']['label']}. "
            f"It used {len(ok_reviews)} hosted fallback brain(s) for external review "
            "and kept execution bounded to recommendations plus human unlock requests."
        )
        if human_unlocks:
            analysis += f" Next human unlock: {human_unlocks[0]['short_ask']}"

        return {
            "mode": "self_improvement_cycle",
            "deal_found": False,
            "profile": context["profile"],
            "objective": objective,
            "timestamp": datetime.now(UTC).isoformat(),
            "resources": context["resources"],
            "local_actions": local_actions,
            "brain_reviews": brain_reviews,
            "external_review_count": len(ok_reviews),
            "human_unlocks": human_unlocks,
            "analysis": analysis,
        }

    def _compact_context(
        self,
        objective: str,
        best_stack: Dict[str, Any],
        self_audit: Dict[str, Any],
        compute: Dict[str, Any],
    ) -> Dict[str, Any]:
        probe = compute.get("probe") or {}
        hosted = probe.get("hosted") or {}
        brains = compute.get("brains") or {}
        stack = best_stack.get("stack") or []
        upgrades = self_audit.get("upgrades") or []
        resources = {
            "brain_count": brains.get("brain_count", 0),
            "primary_brain": brains.get("primary"),
            "fallback_brains": brains.get("secondary") or [],
            "github_models": self._provider_state(hosted.get("github_models") or {}),
            "huggingface": self._provider_state(hosted.get("huggingface") or {}),
            "ollama": {
                "available": (probe.get("ollama") or {}).get("available", False),
                "api_reachable": (probe.get("ollama") or {}).get("api_reachable", False),
                "model_count": (probe.get("ollama") or {}).get("count", 0),
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
            "compute_analysis": compute.get("analysis", ""),
            "self_analysis": self_audit.get("analysis", ""),
        }

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

        actions.append(
            {
                "type": "cycle_hygiene",
                "category": "self_improvement",
                "title": "Compare local plan against hosted model review and keep one small next action.",
                "reason": "A bounded loop prevents Nomad from drifting while still using unlocked resources for better scouting.",
                "requires_human": False,
            }
        )
        return actions

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
        return fresh
