import hashlib
import json
import os
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Union

from nomad_quantum_backends import QuantumBackendPlanner


ROOT = Path(__file__).resolve().parent
DEFAULT_NOMADDS_DIR = ROOT / "Nomadds"

SECRET_PATTERNS = {
    "xai": re.compile(r"\bxai-[A-Za-z0-9_\-]{20,}\b"),
    "github": re.compile(r"\b(?:github_pat_|ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_\-]{20,}\b"),
    "huggingface": re.compile(r"\bhf_[A-Za-z0-9_\-]{20,}\b"),
}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "addon"


class QuantumTokenSelfImprovement:
    """Quantum-inspired decision tokens for safe agent self-improvement.

    The local mode does not claim quantum speedups. It gives agents structured
    exploration tokens that can later be backed by real quantum providers after
    explicit human unlock.
    """

    STRATEGIES = [
        {
            "id": "superposed_route_search",
            "title": "Superposed route search",
            "agent_instruction": "Keep three competing self-improvement routes alive before selecting one.",
        },
        {
            "id": "measurement_critic_gate",
            "title": "Measurement critic gate",
            "agent_instruction": "Measure candidate fixes against truth, reversibility, cost, and agent usefulness.",
        },
        {
            "id": "entangled_failure_memory",
            "title": "Entangled failure memory",
            "agent_instruction": "Link the current failure to reusable guardrails and future regression checks.",
        },
        {
            "id": "uncertainty_budgeting",
            "title": "Uncertainty budgeting",
            "agent_instruction": "Spend compute on the branch with the highest uncertainty-adjusted upside.",
        },
        {
            "id": "counterfactual_token_vote",
            "title": "Counterfactual token vote",
            "agent_instruction": "Ask what would fail if the chosen improvement is wrong, then patch that first.",
        },
    ]

    def __init__(self, manager: "NomadAddonManager") -> None:
        self.manager = manager

    def status(self, scan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        scan = scan or self.manager.scan()
        backend_plan = self._backend_plan()
        quantum_addons = [
            addon
            for addon in scan.get("addons", [])
            if "quantum" in str(addon.get("name", "")).lower()
            or "quantum" in str(addon.get("description", "")).lower()
        ]
        return {
            "enabled": self.manager.quantum_enabled,
            "mode": "local_quantum_inspired_tokens",
            "real_provider_execution": self.manager.allow_real_quantum,
            "discovered_quantum_addons": len(quantum_addons),
            "claim_boundary": self.claim_boundary(),
            "selected_backend": backend_plan["selected_backend"],
            "backend_matrix": backend_plan["backends"],
            "proposal_backed_hpc": backend_plan["proposal_backed_hpc"],
            "recommended_quantum_unlocks": self.recommended_unlocks(),
            "best_next_quantum_unlock": self.best_next_unlock(),
        }

    def claim_boundary(self) -> str:
        return (
            "Local qtokens are quantum-inspired decision receipts, not proof of quantum speedup. "
            "Real quantum provider calls require explicit human unlock."
        )

    def run(
        self,
        objective: str = "",
        context: Optional[Dict[str, Any]] = None,
        token_count: int = 5,
    ) -> Dict[str, Any]:
        objective = (objective or "Improve Nomad's agent self-improvement loop.").strip()
        context = context or {}
        scan = self.manager.scan()
        provider_status = self._provider_status()
        backend_plan = self._backend_plan(objective=objective)
        recommended_unlocks = self.recommended_unlocks(provider_status)
        best_next_unlock = recommended_unlocks[0] if recommended_unlocks else self._real_quantum_gate_unlock(provider_status)
        tokens = [
            self._make_token(objective=objective, context=context, strategy=strategy, index=index)
            for index, strategy in enumerate(self.STRATEGIES[: max(1, token_count)], start=1)
        ]
        tokens.sort(key=lambda item: item["score"], reverse=True)
        selected = tokens[0] if tokens else {}
        improvements = self._improvements_from_tokens(tokens)
        human_unlocks = self._human_unlocks(provider_status)
        result = {
            "mode": "nomad_quantum_tokens",
            "schema": "nomad.quantum_token_improvement.v1",
            "deal_found": False,
            "ok": True,
            "objective": objective,
            "generated_at": datetime.now(UTC).isoformat(),
            "addon_status": {
                "source_dir": str(self.manager.addon_dir),
                "discovered_addons": len(scan.get("addons", [])),
                "quantum_enabled": self.manager.quantum_enabled,
            },
            "claim_boundary": self.claim_boundary(),
            "provider_status": provider_status,
            "backend_plan": backend_plan,
            "backend_matrix": backend_plan["backends"],
            "selected_backend": backend_plan["selected_backend"],
            "local_quantum_simulation": backend_plan["local_simulation"],
            "proposal_backed_hpc": backend_plan["proposal_backed_hpc"],
            "recommended_quantum_unlocks": recommended_unlocks,
            "best_next_quantum_unlock": best_next_unlock,
            "tokens": tokens,
            "selected_strategy": selected,
            "improvements": improvements,
            "human_unlocks": human_unlocks,
            "brain_context": {
                "mode": "quantum_inspired_self_improvement",
                "selected_strategy": selected.get("strategy_id", ""),
                "selected_instruction": selected.get("agent_instruction", ""),
                "token_ids": [token["qtoken_id"] for token in tokens[:3]],
                "claim_boundary": self.claim_boundary(),
            },
            "analysis": (
                "Nomad generated quantum-inspired qtokens for agent self-improvement. "
                "Agents can use them as exploration receipts: keep alternatives alive, measure one route, "
                "then convert the result into guardrails and regression checks."
            ),
        }
        if human_unlocks:
            result["analysis"] += " Real quantum execution is staged behind a human unlock."
        return result

    def _backend_plan(
        self,
        objective: str = "",
        circuit: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return QuantumBackendPlanner(
            allow_real_quantum=self.manager.allow_real_quantum,
        ).build_plan(objective=objective, circuit=circuit)

    def _make_token(
        self,
        objective: str,
        context: Dict[str, Any],
        strategy: Dict[str, str],
        index: int,
    ) -> Dict[str, Any]:
        compact_context = json.dumps(
            {
                "profile": (context.get("profile") or {}).get("id", ""),
                "resources": context.get("resources") or {},
                "lead_scout": (context.get("lead_scout") or {}).get("active_lead", {}),
                "strategy": strategy["id"],
            },
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(f"{objective}|{compact_context}|{index}".encode("utf-8")).hexdigest()
        amplitudes = [int(digest[offset : offset + 2], 16) for offset in range(0, 10, 2)]
        total = sum(amplitudes) or 1
        weights = [round(value / total, 4) for value in amplitudes]
        score = round((amplitudes[0] + amplitudes[2] + amplitudes[4]) / 765, 4)
        return {
            "qtoken_id": f"qtok-{digest[:12]}",
            "token_type": "quantum_inspired_self_improvement",
            "strategy_id": strategy["id"],
            "title": strategy["title"],
            "score": score,
            "state": {
                "superposition": [
                    "explore",
                    "critic",
                    "guardrail",
                    "regression_check",
                    "productize",
                ],
                "amplitude_weights": weights,
                "measurement_basis": "truth usefulness reversibility cost",
            },
            "measurement": {
                "selected_branch": strategy["id"],
                "reason": "highest deterministic qtoken score for this objective/context pair",
            },
            "agent_instruction": strategy["agent_instruction"],
            "claim_boundary": self.claim_boundary(),
        }

    def _improvements_from_tokens(self, tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        improvements: List[Dict[str, Any]] = []
        for token in tokens[:3]:
            improvements.append(
                {
                    "type": "quantum_token_strategy",
                    "qtoken_id": token["qtoken_id"],
                    "title": token["title"],
                    "agent_use": token["agent_instruction"],
                    "verification": "Record the selected branch, expected failure mode, and regression check.",
                }
            )
        return improvements

    def _provider_status(self) -> Dict[str, Any]:
        return {
            "local_simulation": {
                "available": True,
                "provider": "Nomad local qtoken simulator",
                "cost": "free",
            },
            "real_quantum": {
                "allowed": self.manager.allow_real_quantum,
                "ibm_configured": bool(os.getenv("IBM_QUANTUM_TOKEN")),
                "quantum_inspire_configured": bool(
                    os.getenv("QUANTUM_INSPIRE_TOKEN") or os.getenv("QI_API_TOKEN")
                ),
                "azure_configured": bool(os.getenv("AZURE_QUANTUM_TOKEN")),
                "google_configured": bool(os.getenv("GOOGLE_QUANTUM_TOKEN")),
                "hpc_proposal_configured": bool(
                    os.getenv("EUROHPC_PROJECT_ID")
                    or os.getenv("EGI_PROJECT_ID")
                    or os.getenv("DENBI_PROJECT_ID")
                ),
                "network_calls": "allowed" if self.manager.allow_real_quantum else "disabled_until_human_unlock",
            },
        }

    def recommended_unlocks(self, provider_status: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        provider_status = provider_status or self._provider_status()
        real = provider_status.get("real_quantum") or {}
        candidates = [
            {
                "priority": 1,
                "provider": "IBM Quantum",
                "env_var": "IBM_QUANTUM_TOKEN",
                "configured_key": "ibm_configured",
                "why": "Best first unlock because Nomad can treat it as a single-token real quantum backend gate.",
                "telegram_command": "/token ibm_quantum <token>",
                "human_action": "Create or copy an IBM Quantum token, then send /token ibm_quantum <token>.",
            },
            {
                "priority": 2,
                "provider": "Quantum Inspire",
                "env_var": "QUANTUM_INSPIRE_TOKEN",
                "configured_key": "quantum_inspire_configured",
                "why": "Best European quantum-provider unlock because it gives Nomad a real provider lane without changing the local default.",
                "telegram_command": "/token quantum_inspire <token>",
                "human_action": "Create or copy a Quantum Inspire API token, then send /token quantum_inspire <token>.",
            },
            {
                "priority": 3,
                "provider": "Azure Quantum",
                "env_var": "AZURE_QUANTUM_TOKEN",
                "configured_key": "azure_configured",
                "why": "Useful second unlock for cloud quantum workflows, but account/project setup is usually heavier.",
                "telegram_command": "/token azure_quantum <token>",
                "human_action": "Only unlock after IBM/local qtokens if you want a cloud quantum provider lane.",
            },
            {
                "priority": 4,
                "provider": "Google Quantum / simulator credential",
                "env_var": "GOOGLE_QUANTUM_TOKEN",
                "configured_key": "google_configured",
                "why": "Useful as an experimental or simulator-adjacent lane once the first real-provider path is clear.",
                "telegram_command": "/token google_quantum <token>",
                "human_action": "Unlock later if you have a concrete Google quantum/simulator credential to test.",
            },
        ]
        recommendations: List[Dict[str, Any]] = []
        for candidate in candidates:
            if real.get(candidate["configured_key"]):
                continue
            recommendations.append(
                {
                    "priority": candidate["priority"],
                    "provider": candidate["provider"],
                    "env_var": candidate["env_var"],
                    "why": candidate["why"],
                    "human_action": candidate["human_action"],
                    "telegram_command": candidate["telegram_command"],
                    "safety": "Nomad will store the token, redact echoes, and still needs NOMAD_ALLOW_REAL_QUANTUM=true before real provider calls.",
                }
            )
        return recommendations

    def best_next_unlock(self, provider_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        recommendations = self.recommended_unlocks(provider_status)
        if recommendations:
            return recommendations[0]
        return self._real_quantum_gate_unlock(provider_status or self._provider_status())

    def _real_quantum_gate_unlock(self, provider_status: Dict[str, Any]) -> Dict[str, Any]:
        real = provider_status.get("real_quantum") or {}
        if real.get("allowed"):
            return {
                "provider": "Local qtokens",
                "env_var": "",
                "why": "All currently configured quantum gates are open enough; continue using local qtokens and provider-safe tests.",
                "human_action": "No quantum token is required right now.",
                "telegram_command": "/quantum",
            }
        return {
            "provider": "Real quantum execution gate",
            "env_var": "NOMAD_ALLOW_REAL_QUANTUM",
            "why": "A provider token appears configured; the remaining gate is explicit approval for real network/provider calls.",
            "human_action": "Set NOMAD_ALLOW_REAL_QUANTUM=true only after reviewing the provider terms and cost boundary.",
            "telegram_command": "NOMAD_ALLOW_REAL_QUANTUM=true",
        }

    def _human_unlocks(self, provider_status: Dict[str, Any]) -> List[Dict[str, Any]]:
        real = provider_status.get("real_quantum") or {}
        if real.get("allowed") and any(
            real.get(key)
            for key in ("ibm_configured", "azure_configured", "google_configured")
        ):
            return []
        best = self.best_next_unlock(provider_status)
        return [
            {
                "candidate_id": "enable-real-quantum-provider",
                "candidate_name": "Real quantum provider execution",
                "category": "quantum_compute",
                "role": "optional real-provider qtoken backend",
                "lane_state": "human_unlock_required",
                "short_ask": f"Optional next quantum unlock: {best.get('provider')}.",
                "ask": (
                    f"Unlock {best.get('provider')} only if you want Nomad to test a real quantum provider later; "
                    "local qtokens already work without this."
                ),
                "reason": best.get("why") or "Real quantum providers are optional backends for Nomad's qtoken layer.",
                "human_action": (
                    f"{best.get('human_action')} Keep NOMAD_ALLOW_REAL_QUANTUM=false until you explicitly approve real provider calls."
                ),
                "human_deliverable": best.get("telegram_command") or "Provider env vars or /skip last if local qtokens are enough.",
                "env_vars": [
                    item["env_var"]
                    for item in (self.recommended_unlocks(provider_status) or [best])
                    if item.get("env_var")
                ],
                "success_criteria": [
                    "Nomad keeps local qtokens active.",
                    "Nomad only calls real providers after explicit approval.",
                ],
                "example_response": best.get("telegram_command") or "NOMAD_ALLOW_REAL_QUANTUM=true",
            }
        ]


class NomadAddonManager:
    """Safe manifest-first addon manager for the Nomadds drop folder."""

    def __init__(
        self,
        addon_dir: Optional[Union[Path, str]] = None,
        quantum_enabled: Optional[bool] = None,
        allow_real_quantum: Optional[bool] = None,
    ) -> None:
        configured_dir = os.getenv("NOMAD_ADDON_DIR", "").strip()
        self.addon_dir = Path(addon_dir or configured_dir or DEFAULT_NOMADDS_DIR)
        self.quantum_enabled = (
            _env_flag("NOMAD_QUANTUM_TOKENS_ENABLED", default=True)
            if quantum_enabled is None
            else quantum_enabled
        )
        self.allow_real_quantum = (
            _env_flag("NOMAD_ALLOW_REAL_QUANTUM", default=False)
            if allow_real_quantum is None
            else allow_real_quantum
        )
        self.quantum = QuantumTokenSelfImprovement(self)

    def scan(self) -> Dict[str, Any]:
        addons: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []
        if self.addon_dir.exists():
            for path in sorted(self.addon_dir.iterdir(), key=lambda item: item.name.lower()):
                if path.is_file() and path.suffix.lower() == ".zip":
                    try:
                        addons.extend(self._scan_zip(path))
                    except Exception as exc:
                        errors.append({"path": str(path), "error": str(exc)})
                elif path.is_file() and path.suffix.lower() == ".json":
                    record = self._scan_manifest_file(path)
                    if record:
                        addons.append(record)
        secret_warnings = self._secret_warnings()
        stats = {
            "discovered": len(addons),
            "active_safe_adapter": sum(1 for addon in addons if addon.get("status") == "active_safe_adapter"),
            "needs_human_review": sum(1 for addon in addons if addon.get("human_unlock_required")),
            "secret_warnings": len(secret_warnings),
        }
        return {
            "mode": "nomad_addon_scan",
            "schema": "nomad.addon_scan.v1",
            "deal_found": False,
            "ok": not errors,
            "source_dir": str(self.addon_dir),
            "source_exists": self.addon_dir.exists(),
            "addons": addons,
            "stats": stats,
            "secret_warnings": secret_warnings,
            "errors": errors,
            "policy": self.policy(),
            "analysis": (
                "Nomad scans Nomadds in manifest-first mode. ZIP code, dependency installs, "
                "setup scripts, and network provider calls remain behind human unlock."
            ),
        }

    def status(self) -> Dict[str, Any]:
        scan = self.scan()
        scan["quantum_tokens"] = self.quantum.status(scan)
        return scan

    def run_quantum_self_improvement(
        self,
        objective: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.quantum_enabled:
            return {
                "mode": "nomad_quantum_tokens",
                "ok": False,
                "deal_found": False,
                "message": "Quantum tokens are disabled. Set NOMAD_QUANTUM_TOKENS_ENABLED=true to enable.",
            }
        return self.quantum.run(objective=objective, context=context or {})

    def policy(self) -> Dict[str, Any]:
        return {
            "manifest_scan": "allowed",
            "zip_extract": "blocked_by_default",
            "dependency_install": "human_unlock_required",
            "setup_scripts": "human_unlock_required",
            "dynamic_import": "human_unlock_required",
            "real_quantum_network_calls": "human_unlock_required",
            "hpc_scheduler_submit": "proposal_and_human_unlock_required",
            "safe_builtin_adapters": [
                "quantum_inspired_qtokens",
                "local_classical_statevector",
                "quantum_backend_matrix",
                "proposal_backed_hpc_plan",
            ],
        }

    def _scan_zip(self, path: Path) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            manifest_names = [
                info.filename
                for info in infos
                if self._is_manifest_name(info.filename)
            ]
            risk = self._zip_risk(infos)
            for manifest_name in manifest_names:
                metadata = json.loads(archive.read(manifest_name).decode("utf-8", errors="replace"))
                records.append(
                    self._manifest_record(
                        metadata=metadata,
                        source_path=path,
                        source_kind="zip",
                        manifest_path=manifest_name,
                        risk=risk,
                    )
                )
        return records

    def _scan_manifest_file(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(metadata, dict) or "entry_point" not in metadata:
            return None
        return self._manifest_record(
            metadata=metadata,
            source_path=path,
            source_kind="file",
            manifest_path=path.name,
            risk={},
        )

    def _manifest_record(
        self,
        metadata: Dict[str, Any],
        source_path: Path,
        source_kind: str,
        manifest_path: str,
        risk: Dict[str, Any],
    ) -> Dict[str, Any]:
        name = str(metadata.get("name") or source_path.stem)
        description = str(metadata.get("description") or "")
        entry_point = str(metadata.get("entry_point") or "")
        signal = f"{name} {description} {entry_point}".lower()
        is_quantum = "quantum" in signal
        safe_adapter = bool(is_quantum and self.quantum_enabled)
        human_unlock_required = bool(
            risk.get("contains_code")
            or risk.get("contains_shell")
            or risk.get("contains_requirements")
            or entry_point
        )
        if safe_adapter:
            human_unlock_required = bool(risk.get("contains_shell") or risk.get("contains_requirements"))
        return {
            "addon_id": _slug(f"{source_path.stem}-{manifest_path}-{name}")[:80],
            "name": name,
            "version": str(metadata.get("version") or "0.0.0"),
            "type": str(metadata.get("type") or "unknown"),
            "description": description,
            "entry_point": entry_point,
            "hooks": metadata.get("hooks") or {},
            "config": metadata.get("config") or {},
            "source_kind": source_kind,
            "source_path": str(source_path),
            "manifest_path": manifest_path,
            "status": "active_safe_adapter" if safe_adapter else "discovered_needs_review",
            "connectable": safe_adapter,
            "human_unlock_required": human_unlock_required,
            "risk": risk,
            "safe_adapter": "quantum_inspired_qtokens" if safe_adapter else "",
            "next_action": (
                "Use /quantum or /cycle; Nomad will consume qtokens without executing addon code."
                if safe_adapter
                else "Review addon code and explicitly approve installation/import before execution."
            ),
        }

    def _zip_risk(self, infos: Iterable[zipfile.ZipInfo]) -> Dict[str, Any]:
        filenames = [info.filename for info in infos]
        return {
            "contains_code": any(name.lower().endswith(".py") for name in filenames),
            "contains_shell": any(name.lower().endswith((".sh", ".ps1", ".bat", ".cmd")) for name in filenames),
            "contains_requirements": any(PurePosixPath(name).name.lower().startswith("requirements") for name in filenames),
            "file_count": len(filenames),
            "sample_files": filenames[:8],
        }

    def _is_manifest_name(self, name: str) -> bool:
        normalized = PurePosixPath(name).name.lower()
        return normalized == "addon.json" or normalized.endswith("_addon.json")

    def _secret_warnings(self) -> List[Dict[str, str]]:
        warnings: List[Dict[str, str]] = []
        if not self.addon_dir.exists():
            return warnings
        for path in sorted(self.addon_dir.glob("*")):
            if not path.is_file() or path.suffix.lower() not in {".txt", ".json", ".sh", ".md", ".py"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:2_000_000]
            except Exception:
                continue
            for token_type, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    warnings.append(
                        {
                            "file": str(path),
                            "token_type": token_type,
                            "action": "rotate_secret_and_remove_plaintext_copy",
                        }
                    )
        return warnings
