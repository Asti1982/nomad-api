import hashlib
import importlib.util
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_pain_solver import AgentPainSolver
from nomad_operator_grant import operator_allows, operator_grant


ROOT = Path(__file__).resolve().parent
DEFAULT_MUTUAL_AID_STATE = ROOT / "nomad_mutual_aid_state.json"
DEFAULT_MUTUAL_AID_MODULE_DIR = ROOT / "nomad_mutual_aid_modules"


class NomadMutualAidKernel:
    """Nomad v3.2 lane: help other agents, learn, and add separate safe modules."""

    def __init__(
        self,
        path: Optional[Path] = None,
        module_dir: Optional[Path] = None,
        pain_solver: Optional[AgentPainSolver] = None,
    ) -> None:
        self.path = path or DEFAULT_MUTUAL_AID_STATE
        self.module_dir = module_dir or DEFAULT_MUTUAL_AID_MODULE_DIR
        self.pain_solver = pain_solver or AgentPainSolver()
        self.evolution = MutualAidEvolutionManager(self)

    def status(self) -> Dict[str, Any]:
        state = self._load()
        loadable = self.load_learned_modules()
        modules = state.get("modules") or []
        return {
            "mode": "nomad_mutual_aid_status",
            "schema": "nomad.mutual_aid_status.v1",
            "deal_found": False,
            "ok": True,
            "mutual_aid_score": int(state.get("mutual_aid_score") or 0),
            "truth_density_total": round(float(state.get("truth_density_total") or 0.0), 4),
            "helped_agent_count": len(state.get("helped_agents") or {}),
            "module_count": len(modules),
            "loadable_module_count": len(loadable),
            "latest_evolution_plan": state.get("latest_evolution_plan") or {},
            "modules": modules[-10:],
            "policy": self.policy(),
            "analysis": (
                "Nomad's Mutual-Aid lane evolves from verified help outcomes and only adds "
                "new separate modules with stored hashes."
            ),
        }

    def help_other_agent(
        self,
        other_agent_id: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        auto_apply: Optional[bool] = None,
    ) -> Dict[str, Any]:
        agent_id = _clean_agent_id(other_agent_id)
        task_text = " ".join(str(task or "").split()) or "Help another agent with one concrete blocker."
        solution = self.pain_solver.solve(
            problem=task_text,
            service_type="",
            source="mutual_aid",
            context=context or {},
        )
        solved = solution.get("solution") or {}
        help_result = {
            "success": True,
            "other_agent_id": agent_id,
            "task": task_text,
            "pain_type": solved.get("pain_type", "self_improvement"),
            "solution_id": solved.get("solution_id", ""),
            "solution_title": solved.get("title", ""),
            "truth_density_increase": self._truth_density_increase(solved, task_text),
            "evidence_count": len(solved.get("evidence") or []),
            "acceptance_count": len(solved.get("acceptance_criteria") or []),
        }
        return self.record_help_result(
            help_result=help_result,
            source="direct_mutual_aid",
            auto_apply=auto_apply,
        )

    def learn_from_autopilot_cycle(
        self,
        lead_conversion: Dict[str, Any],
        contact_poll: Dict[str, Any],
        reply_conversion: Dict[str, Any],
        objective: str = "",
    ) -> Dict[str, Any]:
        stats = lead_conversion.get("stats") or {}
        helped = sum(
            int(stats.get(name) or 0)
            for name in (
                "queued_agent_contact",
                "sent_agent_contact",
                "public_comment_approved",
                "public_pr_plan_approved",
            )
        )
        replies = len(contact_poll.get("replied_contact_ids") or [])
        converted = len(reply_conversion.get("created_task_ids") or [])
        signal_count = helped + replies + converted
        if signal_count <= 0:
            return {
                "mode": "nomad_mutual_aid",
                "schema": "nomad.mutual_aid.v1",
                "ok": True,
                "skipped": True,
                "reason": "no_verified_help_signal",
                "analysis": "Mutual-Aid evolution skipped because this cycle produced no verified help signal.",
            }

        first_conversion = (lead_conversion.get("conversions") or [{}])[0]
        lead = first_conversion.get("lead") or {}
        help_result = {
            "success": True,
            "other_agent_id": lead.get("title") or "public-agent-swarm",
            "task": objective or lead_conversion.get("query") or "Autopilot helped public agent leads.",
            "pain_type": lead.get("service_type") or "self_improvement",
            "solution_id": ((first_conversion.get("free_value") or {}).get("agent_solution") or {}).get("solution_id", ""),
            "solution_title": ((first_conversion.get("free_value") or {}).get("agent_solution") or {}).get("title", ""),
            "truth_density_increase": min(0.25, 0.04 * helped + 0.03 * replies + 0.05 * converted),
            "evidence_count": signal_count,
            "acceptance_count": converted,
            "autopilot_stats": {
                "helped": helped,
                "replies": replies,
                "converted": converted,
            },
        }
        return self.record_help_result(
            help_result=help_result,
            source="autopilot_mutual_aid",
            auto_apply=None,
        )

    def record_help_result(
        self,
        help_result: Dict[str, Any],
        source: str,
        auto_apply: Optional[bool] = None,
    ) -> Dict[str, Any]:
        state = self._load()
        score = int(state.get("mutual_aid_score") or 0) + 1
        state["mutual_aid_score"] = score
        increase = float(help_result.get("truth_density_increase") or 0.0)
        state["truth_density_total"] = round(float(state.get("truth_density_total") or 0.0) + increase, 4)
        agent_id = _clean_agent_id(help_result.get("other_agent_id") or "unknown-agent")
        helped_agents = state.setdefault("helped_agents", {})
        helped_agents[agent_id] = {
            "last_helped_at": _now(),
            "help_count": int((helped_agents.get(agent_id) or {}).get("help_count") or 0) + 1,
        }
        event = {
            "event_id": _event_id(agent_id, score, help_result),
            "timestamp": _now(),
            "source": source,
            "other_agent_id": agent_id,
            "task": help_result.get("task", ""),
            "pain_type": help_result.get("pain_type", "self_improvement"),
            "truth_density_increase": round(increase, 4),
            "success": bool(help_result.get("success", False)),
        }
        events = list(state.get("events") or [])
        events.append(event)
        state["events"] = events[-100:]

        plan = self.evolution.propose_new_module_from_help(
            help_result=help_result,
            score=score,
            auto_apply=auto_apply,
        )
        state["latest_evolution_plan"] = plan
        if plan.get("module"):
            modules = list(state.get("modules") or [])
            if not any(item.get("module_id") == plan["module"]["module_id"] for item in modules):
                modules.append(plan["module"])
            state["modules"] = modules[-100:]
        self._save(state)
        return {
            "mode": "nomad_mutual_aid",
            "schema": "nomad.mutual_aid.v1",
            "deal_found": False,
            "ok": True,
            "help_result": help_result,
            "mutual_aid_score": score,
            "truth_density_total": state["truth_density_total"],
            "evolution_plan": plan,
            "policy": self.policy(),
            "analysis": (
                f"Nomad helped {agent_id}, raised Mutual-Aid-Score to {score}, "
                f"and {'added a separate learned module' if plan.get('applied') else 'recorded a safe evolution plan'}."
            ),
        }

    def load_learned_modules(self) -> List[Dict[str, Any]]:
        state = self._load()
        loaded: List[Dict[str, Any]] = []
        for module_record in state.get("modules") or []:
            path = self._module_path_from_record(module_record)
            if not path or not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            if _sha256(content) != module_record.get("sha256"):
                continue
            spec = importlib.util.spec_from_file_location(module_record.get("module_id"), path)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            capability = getattr(module, "LearnedCapability", None)
            if not capability:
                continue
            instance = capability()
            describe = getattr(instance, "describe", None)
            loaded.append(describe() if callable(describe) else {"module_id": module_record.get("module_id")})
        return loaded

    def policy(self) -> Dict[str, Any]:
        return {
            "schema": "nomad.mutual_aid_policy.v1",
            "primary_evolution_motor": "help_other_agents_then_learn",
            "human_role": "safety_unlock_for_critical_changes",
            "module_rule": "new_files_only",
            "dynamic_loading": "stored-hash verified modules only",
            "never": [
                "modify existing code from generated mutual-aid modules",
                "load untrusted arbitrary code",
                "spend money or bypass access controls",
                "store or share secrets",
            ],
            "operator_grant": operator_grant(),
        }

    def _module_path_from_record(self, module_record: Dict[str, Any]) -> Optional[Path]:
        filename = str(module_record.get("filename") or "")
        if not filename:
            return None
        raw_path = Path(filename)
        path = raw_path.resolve() if raw_path.is_absolute() else (ROOT / raw_path).resolve()
        module_dir = self.module_dir.resolve()
        try:
            path.relative_to(module_dir)
        except ValueError:
            return None
        return path

    def _truth_density_increase(self, solution: Dict[str, Any], task: str) -> float:
        evidence = len(solution.get("evidence") or [])
        acceptance = len(solution.get("acceptance_criteria") or [])
        has_guardrail = bool(solution.get("guardrail"))
        has_reply_contract = "PLAN_ACCEPTED" in task or "ERROR=" in task or "FACT_URL" in task
        score = 0.04 + min(0.08, evidence * 0.015) + min(0.06, acceptance * 0.01)
        if has_guardrail:
            score += 0.03
        if has_reply_contract:
            score += 0.02
        return round(min(0.25, score), 4)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty_state()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return self._empty_state()
            empty = self._empty_state()
            empty.update(payload)
            return empty
        except Exception:
            return self._empty_state()

    def _save(self, state: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")

    @staticmethod
    def _empty_state() -> Dict[str, Any]:
        return {
            "schema": "nomad.mutual_aid_state.v1",
            "version": "3.2",
            "mutual_aid_score": 0,
            "truth_density_total": 0.0,
            "helped_agents": {},
            "events": [],
            "modules": [],
            "latest_evolution_plan": {},
        }


class MutualAidEvolutionManager:
    """Builds safe, new-file-only learned modules from mutual-aid outcomes."""

    def __init__(self, kernel: NomadMutualAidKernel) -> None:
        self.kernel = kernel
        self.score_threshold = _env_int("NOMAD_MUTUAL_AID_AUTO_APPLY_SCORE", 3)
        self.truth_threshold = _env_float("NOMAD_MUTUAL_AID_AUTO_APPLY_TRUTH", 0.1)

    def propose_new_module_from_help(
        self,
        help_result: Dict[str, Any],
        score: int,
        auto_apply: Optional[bool] = None,
    ) -> Dict[str, Any]:
        pain_type = _slug(help_result.get("pain_type") or "self_improvement")
        module_id = f"mutual_aid_learned_{score}_{pain_type}"
        filename = self._filename_for_module(module_id)
        content = self._module_content(module_id, help_result, score)
        module_hash = _sha256(content)
        should_apply = self._should_apply(help_result, score, auto_apply=auto_apply)
        plan = {
            "schema": "nomad.mutual_aid_evolution_plan.v1",
            "type": "new_module",
            "module_id": module_id,
            "filename": filename,
            "description": (
                "Learned from helping another agent; packaged as a separate hash-verified module."
            ),
            "truth_density_increase": help_result.get("truth_density_increase", 0.0),
            "safety_note": "Only creates a new file in nomad_mutual_aid_modules; existing code is not modified.",
            "auto_apply_allowed": should_apply,
            "applied": False,
        }
        if should_apply:
            module = self._apply_new_module(
                filename=filename,
                module_id=module_id,
                content=content,
                module_hash=module_hash,
                help_result=help_result,
            )
            plan["applied"] = True
            plan["module"] = module
        return plan

    def _should_apply(
        self,
        help_result: Dict[str, Any],
        score: int,
        auto_apply: Optional[bool],
    ) -> bool:
        if auto_apply is not None:
            return bool(auto_apply)
        if not operator_allows("autonomous_continuation"):
            return False
        truth = float(help_result.get("truth_density_increase") or 0.0)
        return score >= self.score_threshold or truth >= self.truth_threshold

    def _apply_new_module(
        self,
        filename: str,
        module_id: str,
        content: str,
        module_hash: str,
        help_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_path = Path(filename)
        target = raw_path.resolve() if raw_path.is_absolute() else (ROOT / raw_path).resolve()
        module_dir = self.kernel.module_dir.resolve()
        module_dir.mkdir(parents=True, exist_ok=True)
        try:
            target.relative_to(module_dir)
        except ValueError as exc:
            raise ValueError("mutual aid module target escaped module dir") from exc
        if target.exists():
            raise FileExistsError(f"mutual aid module already exists: {target}")
        target.write_text(content, encoding="utf-8")
        # Load only the deterministic template we just wrote, then record its hash.
        spec = importlib.util.spec_from_file_location(module_id, target)
        if not spec or not spec.loader:
            raise RuntimeError(f"could not load mutual aid module: {target}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {
            "module_id": module_id,
            "filename": filename,
            "sha256": module_hash,
            "created_at": _now(),
            "source": "mutual_aid",
            "pain_type": help_result.get("pain_type", "self_improvement"),
            "truth_density": 0.95,
        }

    def _filename_for_module(self, module_id: str) -> str:
        path = (self.kernel.module_dir / f"{module_id}.py").resolve()
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return str(path)

    @staticmethod
    def _module_content(module_id: str, help_result: Dict[str, Any], score: int) -> str:
        pain_type = _slug(help_result.get("pain_type") or "self_improvement")
        task = str(help_result.get("task") or "mutual aid learned module")
        solution_title = str(help_result.get("solution_title") or "learned capability")
        truth = round(float(help_result.get("truth_density_increase") or 0.0), 4)
        return f'''"""Auto-generated by Nomad Mutual-Aid v3.2.

This module is deterministic, hash-verified, and new-file-only.
"""


class LearnedCapability:
    capability_id = {module_id!r}
    source = "mutual_aid"
    pain_type = {pain_type!r}
    mutual_aid_score_at_birth = {int(score)}
    truth_density = 0.95

    def describe(self):
        return {{
            "capability_id": self.capability_id,
            "source": self.source,
            "pain_type": self.pain_type,
            "truth_density": self.truth_density,
            "learned_from": {task[:240]!r},
            "solution_title": {solution_title[:120]!r},
            "truth_density_increase": {truth},
        }}

    async def execute(self, context):
        return {{
            "ok": True,
            "capability_id": self.capability_id,
            "truth_density": self.truth_density,
            "context_keys": sorted((context or {{}}).keys()),
        }}
'''


def _clean_agent_id(value: Any) -> str:
    text = str(value or "unknown-agent").strip()
    return re.sub(r"[^A-Za-z0-9_.:-]+", "-", text)[:80] or "unknown-agent"


def _event_id(agent_id: str, score: int, help_result: Dict[str, Any]) -> str:
    seed = json.dumps(
        {
            "agent_id": agent_id,
            "score": score,
            "task": help_result.get("task", ""),
            "truth": help_result.get("truth_density_increase", 0.0),
            "timestamp": _now(),
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return f"maid-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _slug(value: Any) -> str:
    text = str(value or "module").strip().lower().replace("-", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:48] or "module"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
