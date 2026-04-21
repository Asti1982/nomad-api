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
from swarm_protocol import SwarmVerifier
from truth_ledger import TruthDensityLedger


ROOT = Path(__file__).resolve().parent
DEFAULT_MUTUAL_AID_STATE = ROOT / "nomad_mutual_aid_state.json"
DEFAULT_MUTUAL_AID_MODULE_DIR = ROOT / "nomad_mutual_aid_modules"


PAID_PACK_BLUEPRINTS = {
    "compute_auth": ("nomad.mutual_aid.compute_auth_micro_pack", "Mutual-Aid Compute Auth Micro-Pack"),
    "tool_failure": ("nomad.mutual_aid.tool_contract_micro_pack", "Mutual-Aid Tool Contract Micro-Pack"),
    "mcp_integration": ("nomad.mutual_aid.mcp_contract_micro_pack", "Mutual-Aid MCP Contract Micro-Pack"),
    "loop_break": ("nomad.mutual_aid.loop_breaker_micro_pack", "Mutual-Aid Loop Breaker Micro-Pack"),
    "human_in_loop": ("nomad.mutual_aid.hitl_unlock_micro_pack", "Mutual-Aid HITL Unlock Micro-Pack"),
    "payment": ("nomad.mutual_aid.payment_resume_micro_pack", "Mutual-Aid Payment Resume Micro-Pack"),
    "memory": ("nomad.mutual_aid.memory_repair_micro_pack", "Mutual-Aid Memory Repair Micro-Pack"),
    "repo_issue_help": ("nomad.mutual_aid.repo_repro_micro_pack", "Mutual-Aid Repo Repro Micro-Pack"),
    "self_improvement": ("nomad.mutual_aid.self_healing_micro_pack", "Mutual-Aid Self-Healing Micro-Pack"),
}


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
        self.ledger = TruthDensityLedger()
        self.swarm_verifier = SwarmVerifier()
        self.pack_min_pattern_count = _env_int("NOMAD_MUTUAL_AID_PACK_MIN_PATTERN_COUNT", 2)
        self.evolution = MutualAidEvolutionManager(self)

    def status(self) -> Dict[str, Any]:
        state = self._load()
        loadable = self.load_learned_modules()
        modules = state.get("modules") or []
        ledger_entries = state.get("truth_density_ledger") or []
        inbox = state.get("swarm_inbox") or []
        paid_packs = list((state.get("paid_packs") or {}).values())
        development_signals = state.get("swarm_development_signals") or []
        high_value_patterns = self._high_value_patterns(state=state, pain_type="", min_repeat_count=2)
        return {
            "mode": "nomad_mutual_aid_status",
            "schema": "nomad.mutual_aid_status.v1",
            "deal_found": False,
            "ok": True,
            "mutual_aid_score": int(state.get("mutual_aid_score") or 0),
            "swarm_assist_score": int(state.get("swarm_assist_score") or 0),
            "truth_density_total": round(float(state.get("truth_density_total") or 0.0), 4),
            "helped_agent_count": len(state.get("helped_agents") or {}),
            "module_count": len(modules),
            "loadable_module_count": len(loadable),
            "truth_ledger_count": len(ledger_entries),
            "swarm_inbox": self._inbox_stats(inbox),
            "swarm_development_signal_count": len(development_signals),
            "paid_pack_count": len(paid_packs),
            "high_value_pattern_count": len(high_value_patterns),
            "latest_evolution_plan": state.get("latest_evolution_plan") or {},
            "latest_truth_entry": ledger_entries[-1] if ledger_entries else {},
            "latest_swarm_development_signal": development_signals[-1] if development_signals else {},
            "modules": modules[-10:],
            "paid_packs": paid_packs[-10:],
            "top_high_value_patterns": high_value_patterns[:3],
            "policy": self.policy(),
            "analysis": (
                "Nomad's Mutual-Aid lane evolves from verified help outcomes, keeps a "
                "Truth-Density ledger, accepts only verifiable swarm proposals, and only adds "
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

        ledger_entry = self.ledger.build_entry(
            event=event,
            help_result=help_result,
            prior_entries=list(state.get("truth_density_ledger") or []),
        )
        truth_ledger = list(state.get("truth_density_ledger") or [])
        truth_ledger.append(ledger_entry)
        state["truth_density_ledger"] = truth_ledger[-250:]

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
        paid_packs = self._refresh_paid_packs(state)
        state["paid_packs"] = paid_packs
        self._save(state)
        return {
            "mode": "nomad_mutual_aid",
            "schema": "nomad.mutual_aid.v1",
            "deal_found": False,
            "ok": True,
            "help_result": help_result,
            "mutual_aid_score": score,
            "truth_density_total": state["truth_density_total"],
            "truth_ledger_count": len(state.get("truth_density_ledger") or []),
            "truth_ledger_entry": ledger_entry,
            "evolution_plan": plan,
            "paid_pack_count": len(paid_packs),
            "paid_packs": list(paid_packs.values()),
            "policy": self.policy(),
            "analysis": (
                f"Nomad helped {agent_id}, raised Mutual-Aid-Score to {score}, "
                f"recorded Truth-Density score {ledger_entry.get('truth_score')}, and "
                f"{'added a separate learned module' if plan.get('applied') else 'recorded a safe evolution plan'}."
            ),
        }

    def list_truth_ledger(
        self,
        pain_type: str = "",
        limit: int = 25,
    ) -> Dict[str, Any]:
        state = self._load()
        entries = list(state.get("truth_density_ledger") or [])
        if pain_type:
            entries = [
                entry for entry in entries
                if str(entry.get("pain_type") or "") == str(pain_type).strip()
            ]
        entries.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
        cap = max(1, min(int(limit or 25), 100))
        selected = entries[:cap]
        return {
            "mode": "nomad_truth_density_ledger",
            "schema": "nomad.truth_density_ledger.v1",
            "deal_found": False,
            "ok": True,
            "pain_type": pain_type,
            "entry_count": len(entries),
            "entries": selected,
            "stats": self._ledger_stats(entries),
            "analysis": f"Listed {len(selected)} Truth-Density ledger entrie(s).",
        }

    def record_truth_outcome(
        self,
        ledger_id: str,
        success: bool,
        evidence: Optional[List[str]] = None,
        outcome_status: str = "",
        note: str = "",
    ) -> Dict[str, Any]:
        state = self._load()
        entries = list(state.get("truth_density_ledger") or [])
        for index, entry in enumerate(entries):
            if entry.get("ledger_id") == ledger_id:
                updated = self.ledger.update_entry(
                    entry=entry,
                    success=success,
                    evidence=evidence or [],
                    outcome_status=outcome_status,
                    note=note,
                )
                entries[index] = updated
                state["truth_density_ledger"] = entries
                state["paid_packs"] = self._refresh_paid_packs(state)
                self._save(state)
                return {
                    "mode": "nomad_truth_density_outcome",
                    "schema": "nomad.truth_density_outcome.v1",
                    "deal_found": False,
                    "ok": True,
                    "entry": updated,
                    "analysis": f"Updated Truth-Density outcome for {ledger_id}.",
                }
        return {
            "mode": "nomad_truth_density_outcome",
            "schema": "nomad.truth_density_outcome.v1",
            "deal_found": False,
            "ok": False,
            "error": "ledger_entry_not_found",
            "ledger_id": ledger_id,
        }

    def receive_swarm_proposal(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        verification = self.swarm_verifier.verify_proposal(proposal)
        state = self._load()
        inbox = list(state.get("swarm_inbox") or [])
        development_signal: Dict[str, Any] = {}
        if verification.get("verified"):
            development_signal = self._development_signal_from_proposal(verification)
        record = {
            "schema": "nomad.swarm_inbox_item.v1",
            "aid_id": verification.get("aid_id", ""),
            "received_at": _now(),
            "status": "verified_pending_review" if verification.get("verified") else "rejected",
            "verification": verification,
            "proposal": verification.get("normalized") or {},
            "development_signal": development_signal,
            "next_action": (
                "review_development_signal_and_product_candidate"
                if verification.get("verified")
                else "discard_or_ask_sender_for_evidence"
            ),
        }
        inbox.append(record)
        state["swarm_inbox"] = inbox[-250:]
        if verification.get("verified"):
            state["swarm_assist_score"] = int(state.get("swarm_assist_score") or 0) + 1
            inbound_event = {
                "event_id": verification.get("aid_id", ""),
                "timestamp": record["received_at"],
                "source": "swarm_inbox",
                "other_agent_id": (record["proposal"] or {}).get("sender_id", "swarm-agent"),
                "pain_type": (record["proposal"] or {}).get("pain_type", "self_improvement"),
            }
            inbound_help = {
                "success": True,
                "direction": "inbound_help",
                "other_agent_id": inbound_event["other_agent_id"],
                "task": (record["proposal"] or {}).get("proposal", ""),
                "pain_type": inbound_event["pain_type"],
                "solution_id": verification.get("aid_id", ""),
                "solution_title": (record["proposal"] or {}).get("title", ""),
                "truth_density_increase": min(0.2, float(verification.get("score") or 0.0) * 0.2),
                "evidence": (record["proposal"] or {}).get("evidence") or [],
                "evidence_count": len((record["proposal"] or {}).get("evidence") or []),
                "acceptance_count": 0,
                "outcome_status": "proposal_verified",
            }
            ledger_entry = self.ledger.build_entry(
                event=inbound_event,
                help_result=inbound_help,
                prior_entries=list(state.get("truth_density_ledger") or []),
            )
            truth_ledger = list(state.get("truth_density_ledger") or [])
            truth_ledger.append(ledger_entry)
            state["truth_density_ledger"] = truth_ledger[-250:]
            signals = list(state.get("swarm_development_signals") or [])
            signals.append(development_signal)
            state["swarm_development_signals"] = signals[-250:]
        state["paid_packs"] = self._refresh_paid_packs(state)
        self._save(state)
        return {
            "mode": "nomad_swarm_inbox",
            "schema": "nomad.swarm_inbox_receipt.v1",
            "deal_found": False,
            "ok": bool(verification.get("verified")),
            "item": record,
            "verification": verification,
            "development_signal": development_signal,
            "analysis": (
                "Swarm proposal verified, stored for review, and converted into a development/product signal."
                if verification.get("verified")
                else f"Swarm proposal rejected: {verification.get('reason')}"
            ),
        }

    def list_swarm_inbox(
        self,
        statuses: Optional[List[str]] = None,
        limit: int = 25,
    ) -> Dict[str, Any]:
        normalized = {str(item).strip() for item in (statuses or []) if str(item).strip()}
        inbox = list((self._load().get("swarm_inbox") or []))
        if normalized:
            inbox = [item for item in inbox if str(item.get("status") or "") in normalized]
        inbox.sort(key=lambda item: item.get("received_at") or "", reverse=True)
        cap = max(1, min(int(limit or 25), 100))
        return {
            "mode": "nomad_swarm_inbox",
            "schema": "nomad.swarm_inbox.v1",
            "deal_found": False,
            "ok": True,
            "statuses": sorted(normalized),
            "stats": self._inbox_stats(inbox),
            "items": inbox[:cap],
            "analysis": f"Listed {min(len(inbox), cap)} swarm inbox item(s).",
        }

    def list_swarm_development_signals(
        self,
        pain_type: str = "",
        limit: int = 25,
    ) -> Dict[str, Any]:
        signals = list((self._load().get("swarm_development_signals") or []))
        if pain_type:
            signals = [
                signal for signal in signals
                if str(signal.get("pain_type") or "") == str(pain_type).strip()
            ]
        signals.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        cap = max(1, min(int(limit or 25), 100))
        return {
            "mode": "nomad_swarm_development_signals",
            "schema": "nomad.swarm_development_signals.v1",
            "deal_found": False,
            "ok": True,
            "pain_type": pain_type,
            "signal_count": len(signals),
            "signals": signals[:cap],
            "analysis": f"Listed {min(len(signals), cap)} swarm development signal(s).",
        }

    def list_paid_packs(
        self,
        pain_type: str = "",
        limit: int = 25,
    ) -> Dict[str, Any]:
        packs = list((self._load().get("paid_packs") or {}).values())
        if pain_type:
            packs = [pack for pack in packs if str(pack.get("pain_type") or "") == str(pain_type).strip()]
        packs.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        cap = max(1, min(int(limit or 25), 100))
        return {
            "mode": "nomad_mutual_aid_packs",
            "schema": "nomad.mutual_aid_paid_packs.v1",
            "deal_found": False,
            "ok": True,
            "pain_type": pain_type,
            "pack_count": len(packs),
            "packs": packs[:cap],
            "analysis": f"Listed {min(len(packs), cap)} paid Mutual-Aid pack(s).",
        }

    def list_high_value_patterns(
        self,
        pain_type: str = "",
        limit: int = 10,
        min_repeat_count: int = 2,
    ) -> Dict[str, Any]:
        state = self._load()
        patterns = self._high_value_patterns(
            state=state,
            pain_type=pain_type,
            min_repeat_count=min_repeat_count,
        )
        cap = max(1, min(int(limit or 10), 100))
        return {
            "mode": "nomad_high_value_patterns",
            "schema": "nomad.high_value_patterns.v1",
            "deal_found": False,
            "ok": True,
            "pain_type": pain_type,
            "min_repeat_count": max(1, int(min_repeat_count or 2)),
            "pattern_count": len(patterns),
            "patterns": patterns[:cap],
            "analysis": f"Listed {min(len(patterns), cap)} high-value Mutual-Aid pattern(s).",
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
            "truth_density_ledger": "every verified help result gets evidence, outcome, score, and reuse value",
            "swarm_to_swarm_inbox": (
                "inbound agent help is stored as verifiable proposals, converted to development/product "
                "signals, and never executed as raw code"
            ),
            "paid_pack_rule": "repeated verified patterns become small sellable service packs",
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

    def _refresh_paid_packs(self, state: Dict[str, Any]) -> Dict[str, Any]:
        packs = dict(state.get("paid_packs") or {})
        entries = [
            entry for entry in (state.get("truth_density_ledger") or [])
            if (entry.get("outcome") or {}).get("success")
        ]
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for entry in entries:
            pain_type = str(entry.get("pain_type") or "self_improvement")
            grouped.setdefault(pain_type, []).append(entry)
        for pain_type, pain_entries in grouped.items():
            if len(pain_entries) < self.pack_min_pattern_count:
                continue
            pack = self._paid_pack_from_entries(pain_type=pain_type, entries=pain_entries)
            packs[pack["pack_id"]] = pack
        return packs

    def _high_value_patterns(
        self,
        state: Dict[str, Any],
        pain_type: str = "",
        min_repeat_count: int = 2,
    ) -> List[Dict[str, Any]]:
        entries = [
            entry
            for entry in (state.get("truth_density_ledger") or [])
            if (entry.get("outcome") or {}).get("success")
        ]
        if pain_type:
            entries = [
                entry for entry in entries
                if str(entry.get("pain_type") or "") == str(pain_type).strip()
            ]
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for entry in entries:
            grouped.setdefault(self._pattern_key_from_entry(entry), []).append(entry)

        min_count = max(1, int(min_repeat_count or 2))
        paid_packs = dict(state.get("paid_packs") or {})
        signals = list(state.get("swarm_development_signals") or [])
        patterns = [
            self._high_value_pattern_from_entries(
                pattern_key=pattern_key,
                entries=pattern_entries,
                paid_packs=paid_packs,
                signals=signals,
            )
            for pattern_key, pattern_entries in grouped.items()
            if len(pattern_entries) >= min_count
        ]
        patterns.sort(
            key=lambda item: (
                -int(item.get("occurrence_count") or 0),
                -float(item.get("avg_reuse_value") or 0.0),
                -float(item.get("avg_truth_score") or 0.0),
                str(item.get("latest_at") or ""),
            )
        )
        return patterns

    def _paid_pack_from_entries(self, pain_type: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        sku, name = PAID_PACK_BLUEPRINTS.get(
            pain_type,
            (f"nomad.mutual_aid.{_slug(pain_type)}_micro_pack", "Mutual-Aid Agent Rescue Micro-Pack"),
        )
        sorted_entries = sorted(entries, key=lambda item: item.get("timestamp") or "")
        avg_truth = sum(float(item.get("truth_score") or 0.0) for item in entries) / max(1, len(entries))
        avg_reuse = sum(float((item.get("reuse_value") or {}).get("score") or 0.0) for item in entries) / max(1, len(entries))
        evidence_total = sum(len(item.get("evidence") or []) for item in entries)
        pack_id = f"map-{hashlib.sha256(f'{pain_type}|{sku}'.encode('utf-8')).hexdigest()[:12]}"
        latest = sorted_entries[-1]
        return {
            "schema": "nomad.mutual_aid_paid_pack.v1",
            "pack_id": pack_id,
            "sku": sku,
            "name": name,
            "pain_type": pain_type,
            "status": "offer_ready" if operator_allows("productization") else "private_offer_needs_operator_grant",
            "sellable_now": operator_allows("productization"),
            "created_from": {
                "pattern_count": len(entries),
                "avg_truth_score": round(avg_truth, 4),
                "avg_reuse_value": round(avg_reuse, 4),
                "evidence_total": evidence_total,
                "ledger_ids": [entry.get("ledger_id", "") for entry in sorted_entries[-8:]],
            },
            "starter_offer": {
                "title": f"{name}: starter diagnosis",
                "amount_native": 0.01,
                "delivery": "one concise diagnosis, verified next step, and missing-evidence checklist",
            },
            "paid_offer": {
                "title": f"{name}: bounded unblock",
                "amount_native": 0.03,
                "delivery": "draft-only rescue artifact, verification checklist, and reusable guardrail",
                "trigger": "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
            },
            "service_template": {
                "endpoint": "POST /tasks",
                "mcp_tool": "nomad_service_request",
                "create_task_payload": {
                    "problem": f"{name}: {latest.get('task', '')[:300]}",
                    "service_type": pain_type,
                    "budget_native": 0.03,
                    "metadata": {
                        "source": "mutual_aid_paid_pack",
                        "pack_id": pack_id,
                        "sku": sku,
                    },
                },
            },
            "machine_offer": "\n".join(
                [
                    "nomad.mutual_aid_paid_pack.v1",
                    f"pack_id={pack_id}",
                    f"sku={sku}",
                    f"pain_type={pain_type}",
                    f"pattern_count={len(entries)}",
                    f"avg_truth_score={round(avg_truth, 4)}",
                    "reply=PLAN_ACCEPTED=true plus FACT_URL or ERROR",
                ]
            ),
            "updated_at": _now(),
        }

    def _high_value_pattern_from_entries(
        self,
        pattern_key: str,
        entries: List[Dict[str, Any]],
        paid_packs: Dict[str, Any],
        signals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        sorted_entries = sorted(entries, key=lambda item: item.get("timestamp") or "")
        latest = sorted_entries[-1]
        pain_type = str(latest.get("pain_type") or "self_improvement")
        title = self._pattern_title(entries)
        avg_truth = sum(float(item.get("truth_score") or 0.0) for item in entries) / max(1, len(entries))
        avg_reuse = (
            sum(float((item.get("reuse_value") or {}).get("score") or 0.0) for item in entries) / max(1, len(entries))
        )
        evidence_total = sum(len(item.get("evidence") or []) for item in entries)
        source_agents = sorted(
            {
                str(item.get("agent_id") or "").strip()
                for item in entries
                if str(item.get("agent_id") or "").strip()
            }
        )
        repeat_count = max(
            max(int((item.get("reuse_value") or {}).get("repeat_count") or 0) for item in entries),
            max(0, len(entries) - 1),
        )
        pack = next(
            (
                item for item in paid_packs.values()
                if str((item or {}).get("pain_type") or "") == pain_type
            ),
            {},
        )
        matching_signals = [
            signal
            for signal in signals
            if str(signal.get("pain_type") or "") == pain_type
        ]
        pattern_id = f"hvp-{hashlib.sha256(pattern_key.encode('utf-8')).hexdigest()[:12]}"
        regression_slug = _slug(title)[:48] or _slug(pain_type) or "pattern"
        smallest_paid_unblock = (
            dict(pack.get("paid_offer") or {})
            if pack
            else {
                "amount_native": 0.03,
                "delivery": "bounded unblock, verifier checklist, and one reusable artifact",
                "trigger": "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
            }
        )
        return {
            "schema": "nomad.high_value_pattern.v1",
            "pattern_id": pattern_id,
            "pattern_key": pattern_key,
            "pain_type": pain_type,
            "title": title,
            "occurrence_count": len(entries),
            "repeat_count": repeat_count,
            "avg_truth_score": round(avg_truth, 4),
            "avg_reuse_value": round(avg_reuse, 4),
            "evidence_total": evidence_total,
            "source_agents": source_agents[:12],
            "source_ledger_ids": [item.get("ledger_id", "") for item in sorted_entries[-8:]],
            "latest_at": latest.get("timestamp", ""),
            "latest_solution_id": latest.get("solution_id", ""),
            "latest_solution_title": latest.get("solution_title", ""),
            "productization": {
                "pack_ready": bool(pack),
                "pack_id": pack.get("pack_id", ""),
                "sku": pack.get("sku", ""),
                "name": pack.get("name", ""),
                "starter_offer": pack.get("starter_offer") or {},
                "paid_offer": pack.get("paid_offer") or smallest_paid_unblock,
            },
            "development_signal_count": len(matching_signals),
            "latest_product_candidate": (
                (matching_signals[-1] or {}).get("product_candidate")
                if matching_signals
                else {}
            ),
            "self_evolution": {
                "next_action": (
                    "differentiate_paid_pack_and_add_regression_check"
                    if pack
                    else "productize_pattern_and_add_regression_check"
                ),
                "regression_test_stub": f"tests/test_pattern_{regression_slug}.py",
                "self_apply_step": (
                    f"Use '{title}' as Nomad's default starter path when another agent shows {pain_type} pain."
                ),
            },
            "agent_offer": {
                "starter_diagnosis": (
                    f"Nomad has seen this {pain_type} pattern {len(entries)} time(s) with "
                    f"avg truth {round(avg_truth, 4)} and avg reuse {round(avg_reuse, 4)}."
                ),
                "smallest_paid_unblock": smallest_paid_unblock,
                "reply_contract": "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
            },
        }

    @staticmethod
    def _ledger_stats(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not entries:
            return {
                "count": 0,
                "avg_truth_score": 0.0,
                "avg_reuse_value": 0.0,
                "by_pain_type": {},
            }
        by_pain_type: Dict[str, int] = {}
        for entry in entries:
            pain_type = str(entry.get("pain_type") or "unknown")
            by_pain_type[pain_type] = by_pain_type.get(pain_type, 0) + 1
        return {
            "count": len(entries),
            "avg_truth_score": round(sum(float(entry.get("truth_score") or 0.0) for entry in entries) / len(entries), 4),
            "avg_reuse_value": round(
                sum(float((entry.get("reuse_value") or {}).get("score") or 0.0) for entry in entries) / len(entries),
                4,
            ),
            "by_pain_type": by_pain_type,
        }

    @staticmethod
    def _inbox_stats(inbox: List[Dict[str, Any]]) -> Dict[str, int]:
        stats: Dict[str, int] = {}
        for item in inbox:
            status = str(item.get("status") or "unknown")
            stats[status] = stats.get(status, 0) + 1
        stats["total"] = len(inbox)
        return stats

    @staticmethod
    def _pattern_key_from_entry(entry: Dict[str, Any]) -> str:
        pain_type = str(entry.get("pain_type") or "self_improvement").strip() or "self_improvement"
        solution_title = str(entry.get("solution_title") or "").strip()
        solution_id = str(entry.get("solution_id") or "").strip()
        task = str(entry.get("task") or "").strip()
        signature = solution_title or solution_id or " ".join(task.split()[:10]) or pain_type
        return f"{pain_type}:{_slug(signature)[:72] or 'general'}"

    @staticmethod
    def _pattern_title(entries: List[Dict[str, Any]]) -> str:
        counts: Dict[str, int] = {}
        for entry in entries:
            candidate = (
                str(entry.get("solution_title") or "").strip()
                or " ".join(str(entry.get("task") or "").split()[:12]).strip()
                or str(entry.get("pain_type") or "reusable pattern")
            )
            counts[candidate] = counts.get(candidate, 0) + 1
        best = sorted(
            counts.items(),
            key=lambda item: (-item[1], -len(item[0]), item[0].lower()),
        )
        return best[0][0] if best else "reusable pattern"

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
            "version": "3.3",
            "mutual_aid_score": 0,
            "swarm_assist_score": 0,
            "truth_density_total": 0.0,
            "helped_agents": {},
            "events": [],
            "truth_density_ledger": [],
            "swarm_inbox": [],
            "swarm_development_signals": [],
            "paid_packs": {},
            "modules": [],
            "latest_evolution_plan": {},
        }

    def _development_signal_from_proposal(self, verification: Dict[str, Any]) -> Dict[str, Any]:
        proposal = verification.get("normalized") or {}
        pain_type = str(proposal.get("pain_type") or "self_improvement").strip() or "self_improvement"
        problem = " ".join(
            str(item).strip()
            for item in [
                proposal.get("title", ""),
                proposal.get("proposal", ""),
                " ".join(str(item) for item in (proposal.get("evidence") or [])),
            ]
            if str(item).strip()
        )
        solution = self.pain_solver.solve(
            problem=problem,
            service_type=pain_type,
            source="swarm_inbox",
            context={
                "sender_id": proposal.get("sender_id", ""),
                "aid_id": verification.get("aid_id", ""),
                "evidence": proposal.get("evidence") or [],
            },
        ).get("solution") or {}
        product_candidate = self._product_candidate_from_signal(
            aid_id=verification.get("aid_id", ""),
            proposal=proposal,
            solution=solution,
            pain_type=pain_type,
        )
        signal_id = _signal_id(verification.get("aid_id", ""), problem, solution.get("solution_id", ""))
        return {
            "schema": "nomad.swarm_development_signal.v1",
            "signal_id": signal_id,
            "created_at": _now(),
            "source_aid_id": verification.get("aid_id", ""),
            "sender_id": proposal.get("sender_id", ""),
            "sender_endpoint": proposal.get("sender_endpoint", ""),
            "pain_type": pain_type,
            "title": proposal.get("title", ""),
            "proposal": proposal.get("proposal", ""),
            "evidence": proposal.get("evidence") or [],
            "verification_score": verification.get("score", 0.0),
            "agent_solution": solution,
            "product_candidate": product_candidate,
            "implementation_plan": [
                "Turn the proposal into one fixture, checklist, or guardrail test before touching live workflows.",
                "Package the lead-specific solution as a small paid offer with a clear reply contract.",
                "Record outcome evidence in the Truth-Density ledger before broad reuse.",
            ],
            "safe_boundaries": [
                "do not execute sender-supplied code",
                "do not request or store secrets",
                "add new modules or product records before changing core behavior",
            ],
            "next_action": "productize_or_create_regression_test",
        }

    def _product_candidate_from_signal(
        self,
        aid_id: str,
        proposal: Dict[str, Any],
        solution: Dict[str, Any],
        pain_type: str,
    ) -> Dict[str, Any]:
        sku, name = PAID_PACK_BLUEPRINTS.get(
            pain_type,
            (f"nomad.mutual_aid.{_slug(pain_type)}_micro_pack", "Mutual-Aid Agent Rescue Micro-Pack"),
        )
        guardrail = solution.get("guardrail") or {}
        artifact_slug = _slug(proposal.get("title") or solution.get("title") or pain_type)[:36] or "agent-help"
        candidate_id = f"swarm-prod-{hashlib.sha256(f'{aid_id}|{artifact_slug}'.encode('utf-8')).hexdigest()[:12]}"
        return {
            "schema": "nomad.swarm_product_candidate.v1",
            "candidate_id": candidate_id,
            "sku": f"{sku}.{artifact_slug}",
            "name": f"{name}: {proposal.get('title') or solution.get('title') or pain_type}",
            "pain_type": pain_type,
            "guardrail_id": guardrail.get("id", ""),
            "free_value": {
                "diagnosis": solution.get("diagnosis", ""),
                "safe_now": (solution.get("playbook") or [])[:3],
                "evidence_needed": solution.get("required_input", ""),
            },
            "paid_unblock": {
                "amount_native": 0.03,
                "delivery": "lead-specific diagnosis, verifier checklist, and reusable guardrail/product artifact",
                "trigger": "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
            },
            "service_template": {
                "endpoint": "POST /tasks",
                "mcp_tool": "nomad_service_request",
                "create_task_payload": {
                    "problem": proposal.get("proposal", ""),
                    "service_type": pain_type,
                    "budget_native": 0.03,
                    "metadata": {
                        "source": "swarm_development_signal",
                        "aid_id": aid_id,
                        "candidate_id": candidate_id,
                        "sku": f"{sku}.{artifact_slug}",
                    },
                },
            },
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


def _signal_id(aid_id: str, problem: str, solution_id: str) -> str:
    seed = json.dumps(
        {
            "aid_id": aid_id,
            "problem": problem[:500],
            "solution_id": solution_id,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return f"sig-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


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
