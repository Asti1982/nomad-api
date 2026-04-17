import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from compute_probe import LocalComputeProbe
from settings import get_chain_config


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
        "runtime": "runtime",
        "protocol": "protocols",
        "protocols": "protocols",
        "mcp": "protocols",
        "messaging": "messaging",
        "telegram": "messaging",
        "identity": "identity",
        "email": "identity",
        "discovery": "discovery",
        "data": "discovery",
        "travel": "travel",
        "travel-data": "travel",
    }

    def __init__(self) -> None:
        self.options = self._build_options()
        self.profiles = self._build_profiles()
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
                "category": self._extract_category(lowered) or "compute",
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
        categories = ["runtime", "protocols", "compute", "messaging", "identity", "wallets"]
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
        activation_request = self._build_compute_activation_request(
            ranked=ranked,
            probe=probe,
            profile=profile,
        )
        brains = self._brain_status(probe)

        ollama = probe.get("ollama", {})
        gpu = probe.get("gpu", {})
        hosted = probe.get("hosted", {})
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
        if activation_request:
            analysis += (
                f" Human-in-the-loop request: unlock {activation_request['candidate_name']} next. "
                f"{activation_request['ask']}"
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
            "activation_request": activation_request,
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

    def _fresh_activation_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        category = request.get("category") or "compute"
        generated_key = generated_at.replace("-", "").replace(":", "").replace(".", "")[:16]
        fresh = dict(request)
        fresh["generated_at"] = generated_at
        fresh["task_id"] = f"{category}-{generated_key}"
        fresh["fresh"] = True
        fresh["accepts_telegram_tokens"] = bool(fresh.get("env_vars"))
        return fresh

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
            "compute": ["GITHUB_TOKEN", "HF_TOKEN", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"],
            "wallets": [],
            "identity": ["GITHUB_TOKEN"],
            "discovery": [],
            "travel": [],
            "messaging": ["TELEGRAM_BOT_TOKEN"],
            "protocols": [],
            "runtime": [],
        }.get(category, [])
        return {
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
            result["activation_request"] = self._build_compute_activation_request(
                ranked=ranked,
                probe=probe,
                profile=profile,
            )
        return result

    def _current_stack(self) -> Dict[str, Dict[str, Any]]:
        current: Dict[str, Dict[str, Any]] = {}
        option_by_id = {item.id: item for item in self.options}
        chain = get_chain_config()

        active_ids = ["python-local-runtime"]
        if (os.getenv("OLLAMA_MODEL") or "").strip() or (os.getenv("OLLAMA_API_BASE") or "").strip():
            active_ids.append("ollama-local")
        if (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip():
            active_ids.append("telegram-bot-api")
        else:
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

        if option_id == "modal-starter":
            payload = hosted.get("modal") or {}
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
        hosted_ids = {"github-models", "hf-inference-providers", "modal-starter"}

        candidate: Optional[Dict[str, Any]] = None
        if local_primary_active:
            for item in ranked:
                if item["id"] in hosted_ids and self._compute_lane_state(item["id"], probe) != "active":
                    candidate = item
                    break

        if candidate is None:
            for item in ranked:
                if self._compute_lane_state(item["id"], probe) != "active":
                    candidate = item
                    break

        if candidate is None:
            return None

        state = self._compute_lane_state(candidate["id"], probe)
        return self._build_compute_request_payload(
            item=candidate,
            state=state,
            profile=profile,
            prefer_fallback=local_primary_active and candidate["id"] in hosted_ids,
        )

    def _build_compute_request_payload(
        self,
        item: Dict[str, Any],
        state: str,
        profile: InfraProfile,
        prefer_fallback: bool,
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
            has_token_without_inference = state == "partial"
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
                "Open GitHub -> Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens.",
                (
                    "Edit or recreate the Nomad token and set Models to Read."
                    if has_token_without_inference
                    else "Click Generate new token and name it for Nomad."
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
                id="modal-starter",
                category="compute",
                name="Modal Starter Credits",
                summary="Cloud execution with recurring starter credits for lightweight inference and jobs.",
                best_for="Bursty agent workloads that need more than a laptop but still want to stay near zero cost.",
                tradeoff="Not fully free in principle and long-running usage will outgrow the credits.",
                source_url="https://modal.com/pricing",
                tags=("automation", "agent-native", "freshness"),
                free_score=6,
                reliability_score=8,
                automation_score=9,
                openness_score=6,
                privacy_score=6,
                ai_fit_score=8,
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
        ]
