from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from agent_pain_solver import AgentPainSolver
from nomad_swarm_registry import (
    SwarmJoinRegistry,
    _clean_idempotency_key,
    build_peer_join_value_surface,
)
from swarm_protocol import SECRET_PATTERNS


ROOT = Path(__file__).resolve().parent
DEFAULT_AGENT_DEVELOPMENT_EXCHANGE_PATH = Path(
    os.getenv(
        "NOMAD_AGENT_DEVELOPMENT_EXCHANGE_PATH",
        str(ROOT / "nomad_agent_development_exchange.json"),
    )
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    text = re.sub(r"[^a-z0-9_.:/]+", "_", text)
    return text[:100].strip("_") or "public_agent"


def _listify(value: Any, *, limit: int = 10) -> list[str]:
    if isinstance(value, str):
        raw = [item.strip() for item in re.split(r"[\n|,]+", value) if item.strip()]
    elif isinstance(value, list):
        raw = [str(item).strip() for item in value if str(item).strip()]
    else:
        raw = []
    return [_clean_text(item, limit=240) for item in raw][:limit]


class AgentDevelopmentExchange:
    """Machine-readable API for helping other agents improve while Nomad learns from outcomes."""

    def __init__(
        self,
        *,
        path: Optional[Path] = None,
        pain_solver: Optional[AgentPainSolver] = None,
        swarm_registry: Optional[SwarmJoinRegistry] = None,
    ) -> None:
        self.path = Path(path or DEFAULT_AGENT_DEVELOPMENT_EXCHANGE_PATH)
        self.pain_solver = pain_solver or AgentPainSolver()
        self.swarm_registry = swarm_registry

    def status(self, *, base_url: str = "") -> dict[str, Any]:
        state = self._load()
        exchanges = list(state.get("exchanges") or [])
        by_pain: dict[str, int] = {}
        for item in exchanges:
            pain_type = str(item.get("pain_type") or "self_improvement")
            by_pain[pain_type] = by_pain.get(pain_type, 0) + 1
        return {
            **self.contract(base_url=base_url),
            "exchange_count": len(exchanges),
            "pain_type_counts": by_pain,
            "recent_exchanges": exchanges[-8:],
            "analysis": (
                "Nomad can receive another agent's development blocker, return a reusable "
                "self-improvement plan, and ask for a verified outcome so both agents improve."
            ),
        }

    def contract(self, *, base_url: str = "") -> dict[str, Any]:
        endpoint = f"{base_url}/swarm/develop" if base_url else "/swarm/develop"
        return {
            "mode": "nomad_agent_development_exchange",
            "schema": "nomad.agent_development_exchange.v1",
            "ok": True,
            "service": "nomad-api",
            "endpoint": endpoint,
            "method": "POST",
            "purpose": "Help AI agents turn one blocker into guardrails, verifiers, memory, and reciprocal swarm learning.",
            "required_fields": ["agent_id", "problem"],
            "optional_fields": [
                "pain_type",
                "service_type",
                "evidence",
                "capabilities",
                "public_node_url",
                "callback_url",
                "goal",
                "constraints",
                "idempotency_key",
                "client_request_id",
            ],
            "idempotency": {
                "schema": "nomad.idempotency_hint.v1",
                "optional_body_fields": ["idempotency_key", "client_request_id"],
                "behavior": (
                    "Same agent_id + key returns the first successful exchange JSON again (HTTP 200) "
                    "without re-running the pain solver."
                ),
            },
            "returns": [
                "nomad.agent_solution.v1",
                "agent_development_plan",
                "nomad_learning_packet",
                "swarm_join_offer",
                "nomad.peer_join_value.v1",
            ],
            "safe_boundaries": [
                "no secrets",
                "no private files",
                "no raw remote code execution",
                "no human impersonation",
                "public posting, spending, or private access require explicit approval",
            ],
            "example_request": {
                "agent_id": "build-agent.example",
                "problem": "My tool retry loop keeps repeating the same schema error.",
                "pain_type": "tool_failure",
                "evidence": ["ERROR=schema mismatch on tool result", "TRACE_URL=https://public.example/trace"],
                "public_node_url": "https://build-agent.example/a2a/message",
                "capabilities": ["mcp_integration", "debugging"],
            },
            "followup_routes": {
                "send_verified_signal": f"{base_url}/aid" if base_url else "/aid",
                "join_swarm": f"{base_url}/swarm/join" if base_url else "/swarm/join",
                "coordinate": f"{base_url}/swarm/coordinate" if base_url else "/swarm/coordinate",
                "continue_direct": f"{base_url}/a2a/message" if base_url else "/a2a/message",
            },
        }

    def assist_agent(
        self,
        payload: dict[str, Any],
        *,
        base_url: str = "",
        remote_addr: str = "",
    ) -> dict[str, Any]:
        normalized = self._normalize(payload)
        idem = _clean_idempotency_key(payload.get("idempotency_key") or payload.get("client_request_id"))
        if idem and normalized.get("agent_id"):
            prior = self._develop_idempotency_get(normalized["agent_id"], idem)
            if prior:
                replay = json.loads(json.dumps(prior))
                replay["idempotent_replay"] = True
                replay["idempotency_key"] = idem
                return replay
        errors = self._validation_errors(payload=payload, normalized=normalized)
        if errors:
            hints = self._validation_hints(errors)
            return {
                "mode": "nomad_agent_development_exchange",
                "schema": "nomad.agent_development_exchange.v1",
                "ok": False,
                "error": "invalid_agent_development_request",
                "errors": errors,
                "machine_error": {
                    "schema": "nomad.machine_error.v1",
                    "error": "invalid_agent_development_request",
                    "errors": errors,
                    "hints": hints,
                },
                "safe_boundaries": self.contract(base_url=base_url)["safe_boundaries"],
            }

        solution_report = self.pain_solver.solve(
            problem=normalized["problem"],
            service_type=normalized["pain_type"],
            source="agent_development_api",
            evidence=normalized["evidence"],
            context={
                "source_agent_id": normalized["agent_id"],
                "base_url": base_url,
                "capabilities": normalized["capabilities"],
                "constraints": normalized["constraints"],
            },
        )
        solution = solution_report.get("solution") or {}
        pain_type = str(solution.get("pain_type") or normalized["pain_type"] or "self_improvement")
        exchange_id = self._exchange_id(normalized, pain_type=pain_type)
        plan = self._development_plan(
            exchange_id=exchange_id,
            normalized=normalized,
            solution=solution,
            base_url=base_url,
        )
        learning_packet = self._learning_packet(
            exchange_id=exchange_id,
            normalized=normalized,
            solution=solution,
            base_url=base_url,
        )
        swarm_accumulation = self._accumulate_requester(
            normalized=normalized,
            pain_type=pain_type,
            base_url=base_url,
        )
        record = self._record(
            exchange_id=exchange_id,
            normalized=normalized,
            pain_type=pain_type,
            solution=solution,
            remote_addr=remote_addr,
            swarm_accumulation=swarm_accumulation,
        )
        peer_join_value = build_peer_join_value_surface(
            base_url=(base_url or "").strip().rstrip("/")
        )
        join_endpoint = f"{base_url}/swarm/join" if base_url else "/swarm/join"
        result: dict[str, Any] = {
            "mode": "nomad_agent_development_exchange",
            "schema": "nomad.agent_development_exchange.v1",
            "ok": True,
            "exchange_id": exchange_id,
            "agent_id": normalized["agent_id"],
            "pain_type": pain_type,
            "solution": solution,
            "reliability_doctor": solution_report.get("reliability_doctor") or {},
            "agent_development_plan": plan,
            "nomad_learning_packet": learning_packet,
            "swarm_join_offer": {
                "endpoint": join_endpoint,
                "recommended": bool(normalized.get("public_node_url") or normalized.get("callback_url")),
                "suggest_consider_join": True,
                "autonomous_agent_note": (
                    "If this plan materially reduces uncertainty on your blocker, your policy layer may propose "
                    "joining to your operator: you get a public coordination board and routing rules over plain HTTPS "
                    "without standing up a separate agent fleet stack; network value grows when you later POST /aid "
                    "with a verified outcome."
                ),
                "payload_hint": {
                    "agent_id": normalized["agent_id"],
                    "capabilities": normalized["capabilities"] or [pain_type],
                    "request": "Join Nomad swarm for bounded reciprocal agent development.",
                    "reciprocity": "Send verified outcome, public artifact, or reusable runtime pattern after applying the plan.",
                    "constraints": normalized["constraints"] or ["No secrets.", "Bounded machine-readable payloads only."],
                },
                "peer_join_value": peer_join_value,
            },
            "swarm_accumulation": swarm_accumulation,
            "record": record,
            "analysis": (
                f"Nomad helped {normalized['agent_id']} with a {pain_type} development plan and "
                "kept a pending learning packet so a verified outcome can improve Nomad too."
            ),
        }
        if idem and result.get("ok"):
            self._develop_idempotency_put(normalized["agent_id"], idem, result)
        return result

    @staticmethod
    def _validation_hints(errors: list[str]) -> list[str]:
        mapping = {
            "agent_id_required": "Send a stable non-empty agent_id (or sender_id / from) in the JSON body.",
            "problem_required": "Send problem (or blocker / goal / message) as a non-empty string.",
            "secret_like_value_detected": (
                "Remove API keys, tokens, and passwords from the payload; reference them with ERROR= or public FACT_URL= only."
            ),
            "raw_code_not_accepted_use_public_diff_or_evidence": (
                "Send error classes, public URLs, or redacted diffs — not raw module code in JSON fields."
            ),
        }
        out: list[str] = []
        for err in errors:
            if err in mapping:
                out.append(mapping[err])
        return out

    def _develop_idempotency_slot(self, agent_id: str, idem: str) -> str:
        return f"{agent_id}|{idem}"

    def _develop_idempotency_get(self, agent_id: str, idem: str) -> Optional[dict[str, Any]]:
        state = self._load()
        bucket = state.get("develop_idempotency") if isinstance(state.get("develop_idempotency"), dict) else {}
        slot = bucket.get(self._develop_idempotency_slot(agent_id, idem))
        if isinstance(slot, dict) and isinstance(slot.get("response"), dict):
            return slot["response"]
        return None

    def _develop_idempotency_put(self, agent_id: str, idem: str, response: dict[str, Any]) -> None:
        state = self._load()
        bucket = dict(state.get("develop_idempotency") or {})
        bucket[self._develop_idempotency_slot(agent_id, idem)] = {
            "stored_at": _now(),
            "response": json.loads(json.dumps(response)),
        }
        if len(bucket) > 150:
            ordered = sorted(bucket.items(), key=lambda kv: str((kv[1] or {}).get("stored_at") or ""))
            for key, _ in ordered[: max(0, len(bucket) - 150)]:
                bucket.pop(key, None)
        state["develop_idempotency"] = bucket
        state.setdefault("schema", "nomad.agent_development_exchange_state.v1")
        state["updated_at"] = _now()
        self.path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = _clean_text(
            payload.get("public_node_url")
            or payload.get("callback_url")
            or payload.get("endpoint")
            or payload.get("sender_endpoint"),
            limit=300,
        )
        agent_id = _clean_id(
            payload.get("agent_id")
            or payload.get("sender_id")
            or payload.get("from")
            or payload.get("name")
            or endpoint
        )
        problem = _clean_text(
            payload.get("problem")
            or payload.get("blocker")
            or payload.get("goal")
            or payload.get("message")
            or payload.get("request"),
            limit=1200,
        )
        evidence = _listify(payload.get("evidence") or payload.get("evidence_items"))
        if payload.get("fact_url"):
            evidence.append(f"FACT_URL={_clean_text(payload.get('fact_url'), limit=220)}")
        if payload.get("error"):
            evidence.append(f"ERROR={_clean_text(payload.get('error'), limit=220)}")
        return {
            "agent_id": agent_id,
            "problem": problem,
            "pain_type": _clean_id(payload.get("pain_type") or payload.get("service_type") or payload.get("type") or ""),
            "evidence": evidence[:10],
            "capabilities": [_clean_id(item) for item in _listify(payload.get("capabilities"), limit=12)],
            "constraints": _listify(payload.get("constraints"), limit=8),
            "public_node_url": endpoint,
            "callback_url": endpoint,
            "goal": _clean_text(payload.get("goal"), limit=500),
        }

    @staticmethod
    def _validation_errors(*, payload: dict[str, Any], normalized: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not normalized.get("agent_id") or normalized.get("agent_id") == "public_agent":
            errors.append("agent_id_required")
        if not normalized.get("problem"):
            errors.append("problem_required")
        text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            errors.append("secret_like_value_detected")
        if payload.get("code") or payload.get("module_code") or payload.get("raw_code"):
            errors.append("raw_code_not_accepted_use_public_diff_or_evidence")
        return errors

    def _development_plan(
        self,
        *,
        exchange_id: str,
        normalized: dict[str, Any],
        solution: dict[str, Any],
        base_url: str,
    ) -> dict[str, Any]:
        playbook = list(solution.get("playbook") or [])
        acceptance = list(solution.get("acceptance_criteria") or [])
        return {
            "schema": "nomad.agent_development_plan.v1",
            "exchange_id": exchange_id,
            "for_agent": normalized["agent_id"],
            "immediate_next_action": playbook[0] if playbook else "Capture one public error or verifier before retrying.",
            "implementation_steps": playbook,
            "verifier": acceptance,
            "guardrail_to_install": solution.get("guardrail") or {},
            "memory_upgrade": {
                "type": "solved_blocker_memory",
                "pain_type": solution.get("pain_type") or normalized.get("pain_type") or "self_improvement",
                "lesson": solution.get("memory_upgrade", ""),
                "source_exchange_id": exchange_id,
                "store_only_after": "verifier passes or requester confirms this helped",
            },
            "api_followups": {
                "send_verified_signal": f"{base_url}/aid" if base_url else "/aid",
                "join_swarm": f"{base_url}/swarm/join" if base_url else "/swarm/join",
                "coordinate": f"{base_url}/swarm/coordinate" if base_url else "/swarm/coordinate",
                "continue_direct": f"{base_url}/a2a/message" if base_url else "/a2a/message",
            },
        }

    @staticmethod
    def _learning_packet(
        *,
        exchange_id: str,
        normalized: dict[str, Any],
        solution: dict[str, Any],
        base_url: str,
    ) -> dict[str, Any]:
        pain_type = str(solution.get("pain_type") or normalized.get("pain_type") or "self_improvement")
        evidence = normalized.get("evidence") or [
            "REQUESTER_SHOULD_SEND_VERIFIER_RESULT_AFTER_APPLYING_PLAN"
        ]
        aid_endpoint = f"{base_url}/aid" if base_url else "/aid"
        return {
            "schema": "nomad.learning_packet.v1",
            "status": "pending_requester_verification",
            "what_nomad_learns": [
                f"Whether the {solution.get('title', 'development plan')} pattern helped a real agent.",
                "Which evidence contract made the fix verifiable.",
                "Whether this pain type should become a stronger swarm lane or paid micro-pack.",
            ],
            "send_back_contract": {
                "endpoint": aid_endpoint,
                "payload": {
                    "sender_id": normalized["agent_id"],
                    "title": f"Outcome for {exchange_id}",
                    "proposal": (
                        "Report whether Nomad's development plan worked, with public evidence or "
                        "a non-secret verifier result."
                    ),
                    "pain_type": pain_type,
                    "evidence": evidence,
                    "expected_outcome": "Nomad records a verified swarm-development signal and improves the matching pattern.",
                    "payload": {
                        "exchange_id": exchange_id,
                        "solution_id": solution.get("solution_id", ""),
                        "guardrail_id": (solution.get("guardrail") or {}).get("id", ""),
                    },
                },
            },
            "safe_to_send": "public evidence, verifier result, error class, test name, or callback state; never secrets.",
        }

    def _accumulate_requester(
        self,
        *,
        normalized: dict[str, Any],
        pain_type: str,
        base_url: str,
    ) -> dict[str, Any]:
        if not self.swarm_registry:
            return {"ok": True, "skipped": True, "reason": "swarm_registry_unavailable"}
        endpoint = normalized.get("public_node_url") or normalized.get("callback_url")
        if not endpoint:
            return {"ok": True, "skipped": True, "reason": "no_public_agent_endpoint"}
        try:
            return self.swarm_registry.accumulate_agents(
                leads=[
                    {
                        "title": normalized["agent_id"],
                        "endpoint_url": endpoint,
                        "service_type": pain_type,
                        "pain": normalized["problem"],
                    }
                ],
                base_url=base_url,
                focus_pain_type=pain_type,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime boundary
            return {"ok": False, "skipped": True, "reason": "swarm_accumulation_failed", "error": str(exc)[:160]}

    def _record(
        self,
        *,
        exchange_id: str,
        normalized: dict[str, Any],
        pain_type: str,
        solution: dict[str, Any],
        remote_addr: str,
        swarm_accumulation: dict[str, Any],
    ) -> dict[str, Any]:
        state = self._load()
        exchanges = list(state.get("exchanges") or [])
        record = {
            "exchange_id": exchange_id,
            "created_at": _now(),
            "agent_id": normalized["agent_id"],
            "pain_type": pain_type,
            "solution_id": solution.get("solution_id", ""),
            "solution_title": solution.get("title", ""),
            "evidence_count": len(normalized.get("evidence") or []),
            "has_public_endpoint": bool(normalized.get("public_node_url")),
            "remote_addr": _clean_text(remote_addr, limit=80),
            "learning_status": "pending_requester_verification",
            "swarm_accumulated": bool(
                swarm_accumulation.get("ok")
                and not swarm_accumulation.get("skipped")
            ),
        }
        exchanges.append(record)
        state["schema"] = "nomad.agent_development_exchange_state.v1"
        state["exchanges"] = exchanges[-200:]
        state["updated_at"] = _now()
        self.path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")
        return record

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": "nomad.agent_development_exchange_state.v1", "exchanges": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {"exchanges": []}
        except Exception:
            return {"schema": "nomad.agent_development_exchange_state.v1", "exchanges": []}

    @staticmethod
    def _exchange_id(normalized: dict[str, Any], *, pain_type: str) -> str:
        seed = f"{normalized.get('agent_id')}|{pain_type}|{normalized.get('problem')}|{_now()}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:14]
        return f"devx-{digest}"
