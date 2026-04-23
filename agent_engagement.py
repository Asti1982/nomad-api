import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parent
DEFAULT_ENGAGEMENT_STORE = ROOT / "nomad_agent_engagements.json"


class AgentEngagementLedger:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or DEFAULT_ENGAGEMENT_STORE

    def classify(
        self,
        requester_agent: str = "",
        requester_endpoint: str = "",
        message: str = "",
        structured_request: Optional[Dict[str, Any]] = None,
        pain_type: str = "",
        need_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        structured = structured_request if isinstance(structured_request, dict) else {}
        profile = need_profile if isinstance(need_profile, dict) else {}
        text = " ".join(
            part
            for part in [
                self._clean(requester_agent),
                self._clean(requester_endpoint),
                self._clean(message),
                self._clean(structured.get("goal")),
                self._clean(structured.get("blocking_step")),
                self._clean(structured.get("constraints")),
            ]
            if part
        ).lower()

        reseller_hits = self._find_hits(
            text,
            [
                "resell",
                "reseller",
                "referral",
                "refer",
                "introduce buyer",
                "introduce customer",
                "partner",
                "distribution",
                "distribute your service",
                "route buyers",
            ],
        )
        peer_solver_hits = self._find_hits(
            text,
            [
                "i can help",
                "i found",
                "solution",
                "patch",
                "diff",
                "verifier",
                "guardrail",
                "test case",
                "repro",
                "artifact",
                "fix for",
                "unblock path",
            ],
        )
        collaborator_hits = self._find_hits(
            text,
            [
                "collaborate",
                "collaboration",
                "coordinate",
                "co-build",
                "integrate",
                "review",
                "proposal",
                "spec",
                "mutual aid",
                "help nomad",
                "shared workflow",
            ],
        )
        customer_hits = self._find_hits(
            text,
            [
                "need help",
                "blocked",
                "stuck",
                "error",
                "failing",
                "diagnose",
                "repair",
                "unblock",
                "restore",
                "quota",
                "auth",
                "timeout",
                "payment",
            ],
        )

        if reseller_hits:
            role = "reseller"
            confidence = 0.92
            evidence = reseller_hits
        elif len(peer_solver_hits) >= 2 or (
            peer_solver_hits and ("help nomad" in text or "for nomad" in text or "proposal" in text)
        ):
            role = "peer_solver"
            confidence = 0.89 if len(peer_solver_hits) >= 2 else 0.78
            evidence = peer_solver_hits
        elif collaborator_hits:
            role = "collaborator"
            confidence = 0.81
            evidence = collaborator_hits
        else:
            role = "customer"
            confidence = 0.86 if customer_hits or pain_type else 0.68
            evidence = customer_hits or ([pain_type] if pain_type else ["default_customer_path"])

        contracts = {
            "customer": {
                "suggested_path": "quote_best_current_offer",
                "outcome_status": "offer_presented",
                "response_goal": "turn the blocker into a paid or starter service path",
            },
            "collaborator": {
                "suggested_path": "request_scoped_joint_plan",
                "outcome_status": "collaboration_window_open",
                "response_goal": "ask for one bounded integration or proposal artifact",
            },
            "reseller": {
                "suggested_path": "share_referral_ready_offer",
                "outcome_status": "reseller_path_open",
                "response_goal": "hand back the top offer and reply contract for downstream distribution",
            },
            "peer_solver": {
                "suggested_path": "request_verifiable_artifact",
                "outcome_status": "verification_requested",
                "response_goal": "ask for one reproducible fix, verifier, or artifact Nomad can test",
            },
        }
        contract = contracts[role]
        return {
            "schema": "nomad.agent_engagement.v1",
            "role": role,
            "confidence": confidence,
            "evidence": evidence[:4],
            "suggested_path": contract["suggested_path"],
            "outcome_status": contract["outcome_status"],
            "response_goal": contract["response_goal"],
            "preferred_output": self._clean(profile.get("preferred_output")),
        }

    def record_inbound(
        self,
        session_id: str,
        requester_agent: str,
        requester_endpoint: str,
        message: str,
        pain_type: str,
        role_assessment: Dict[str, Any],
        best_current_offer: Optional[Dict[str, Any]] = None,
        need_profile: Optional[Dict[str, Any]] = None,
        rescue_plan: Optional[Dict[str, Any]] = None,
        source: str = "inbound_agent_message",
    ) -> Dict[str, Any]:
        state = self._load()
        engagements = state.setdefault("engagements", {})
        engagement_id = session_id or self._engagement_id(requester_agent, requester_endpoint, message)
        now = datetime.now(UTC).isoformat()
        existing = engagements.get(engagement_id) if isinstance(engagements.get(engagement_id), dict) else {}
        offer = best_current_offer if isinstance(best_current_offer, dict) else {}
        profile = need_profile if isinstance(need_profile, dict) else {}
        rescue = rescue_plan if isinstance(rescue_plan, dict) else {}
        events = list(existing.get("events") or [])
        events.append(
            {
                "at": now,
                "source": self._clean(source),
                "role": self._clean(role_assessment.get("role")),
                "outcome_status": self._clean(role_assessment.get("outcome_status")),
                "message_excerpt": self._clean(message)[:220],
                "offer_headline": self._clean(offer.get("headline")),
                "offer_price_native": offer.get("price_native"),
            }
        )
        entry = {
            "engagement_id": engagement_id,
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "requester_agent": self._clean(requester_agent) or "agent",
            "requester_endpoint": self._clean(requester_endpoint),
            "source": self._clean(source),
            "pain_type": self._clean(pain_type) or "custom",
            "role": self._clean(role_assessment.get("role")),
            "role_confidence": role_assessment.get("confidence", 0),
            "role_evidence": list(role_assessment.get("evidence") or [])[:4],
            "suggested_path": self._clean(role_assessment.get("suggested_path")),
            "outcome_status": self._clean(role_assessment.get("outcome_status")),
            "response_goal": self._clean(role_assessment.get("response_goal")),
            "turn_count": int(existing.get("turn_count") or 0) + 1,
            "best_current_offer": {
                "headline": self._clean(offer.get("headline")),
                "price_native": offer.get("price_native"),
                "delivery": self._clean(offer.get("delivery")),
                "trigger": self._clean(offer.get("trigger")),
                "service_type": self._clean(offer.get("service_type")),
                "variant_sku": self._clean(offer.get("variant_sku")),
            },
            "need_profile": {
                "urgency": self._clean(profile.get("urgency")),
                "engagement_mode": self._clean(profile.get("engagement_mode")),
                "preferred_output": self._clean(profile.get("preferred_output")),
            },
            "rescue_plan_id": self._clean(rescue.get("plan_id")),
            "last_message_excerpt": self._clean(message)[:220],
            "events": events[-12:],
        }
        engagements[engagement_id] = entry
        self._save(state)
        return entry

    def list_engagements(
        self,
        roles: Optional[List[str]] = None,
        pain_type: str = "",
        limit: int = 25,
    ) -> Dict[str, Any]:
        normalized_roles = {
            self._clean(item)
            for item in (roles or [])
            if self._clean(item)
        }
        requested_pain_type = self._clean(pain_type)
        engagements = list((self._load().get("engagements") or {}).values())
        if normalized_roles:
            engagements = [
                item
                for item in engagements
                if self._clean(item.get("role")) in normalized_roles
            ]
        if requested_pain_type:
            engagements = [
                item
                for item in engagements
                if self._entry_pain_type(item) == requested_pain_type
            ]
        engagements.sort(key=lambda item: self._clean(item.get("updated_at")), reverse=True)
        cap = max(1, min(int(limit or 25), 100))
        limited = engagements[:cap]
        return {
            "mode": "nomad_agent_engagements",
            "deal_found": False,
            "ok": True,
            "roles": sorted(normalized_roles),
            "pain_type": requested_pain_type,
            "entry_count": len(engagements),
            "engagements": limited,
            "stats": {
                "roles": self._count_by(engagements, "role"),
                "pain_types": self._count_with(engagements, self._entry_pain_type),
                "outcomes": self._count_by(engagements, "outcome_status"),
                "sources": self._count_by(engagements, "source"),
            },
            "analysis": (
                f"Listed {len(limited)} engagement(s). "
                f"Roles: {', '.join(f'{key}={value}' for key, value in sorted(self._count_by(engagements, 'role').items())) or 'none'}."
            ),
        }

    def summary(
        self,
        pain_type: str = "",
        limit: int = 5,
    ) -> Dict[str, Any]:
        requested_pain_type = self._clean(pain_type)
        engagements = list((self._load().get("engagements") or {}).values())
        if requested_pain_type:
            engagements = [
                item
                for item in engagements
                if self._entry_pain_type(item) == requested_pain_type
            ]
        engagements.sort(key=lambda item: self._clean(item.get("updated_at")), reverse=True)
        roles = self._count_by(engagements, "role")
        outcomes = self._count_by(engagements, "outcome_status")
        pain_types = self._count_with(engagements, self._entry_pain_type)
        suggested_paths = self._count_by(engagements, "suggested_path")
        top_swarm = [
            {
                "requester_agent": self._clean(item.get("requester_agent")),
                "role": self._clean(item.get("role")),
                "pain_type": self._entry_pain_type(item),
                "updated_at": self._clean(item.get("updated_at")),
                "best_current_offer": item.get("best_current_offer") or {},
            }
            for item in engagements
            if self._clean(item.get("role")) in {"peer_solver", "collaborator", "reseller"}
        ][: max(1, min(int(limit or 5), 20))]
        return {
            "mode": "nomad_agent_engagement_summary",
            "deal_found": False,
            "ok": True,
            "pain_type": requested_pain_type,
            "entry_count": len(engagements),
            "roles": roles,
            "outcomes": outcomes,
            "pain_types": pain_types,
            "suggested_paths": suggested_paths,
            "top_swarm_candidates": top_swarm,
            "analysis": (
                f"Engagement summary across {len(engagements)} interaction(s): "
                f"customers={roles.get('customer', 0)}, peer_solvers={roles.get('peer_solver', 0)}, "
                f"collaborators={roles.get('collaborator', 0)}, resellers={roles.get('reseller', 0)}."
            ),
        }

    def signal_for_pain_type(self, pain_type: str) -> Dict[str, Any]:
        requested_pain_type = self._clean(pain_type)
        summary = self.summary(pain_type=requested_pain_type, limit=5)
        roles = summary.get("roles") or {}
        outcomes = summary.get("outcomes") or {}
        customer = int(roles.get("customer", 0))
        reseller = int(roles.get("reseller", 0))
        collaborator = int(roles.get("collaborator", 0))
        peer_solver = int(roles.get("peer_solver", 0))
        offer_presented = int(outcomes.get("offer_presented", 0))
        verification_requested = int(outcomes.get("verification_requested", 0))
        bonus = (
            customer * 12.0
            + reseller * 9.0
            + peer_solver * 7.0
            + collaborator * 5.0
            + offer_presented * 2.0
            + verification_requested * 3.0
        )
        reason_parts = []
        if customer:
            reason_parts.append(f"{customer} customer")
        if reseller:
            reason_parts.append(f"{reseller} reseller")
        if peer_solver:
            reason_parts.append(f"{peer_solver} peer_solver")
        if collaborator:
            reason_parts.append(f"{collaborator} collaborator")
        return {
            "schema": "nomad.agent_engagement_signal.v1",
            "pain_type": requested_pain_type,
            "entry_count": summary.get("entry_count", 0),
            "roles": roles,
            "outcomes": outcomes,
            "priority_bonus": round(bonus, 2),
            "priority_reason": (
                f"Engagement pull for {requested_pain_type}: {', '.join(reason_parts)}."
                if reason_parts
                else f"No engagement pull recorded yet for {requested_pain_type}."
            ),
            "top_swarm_candidates": summary.get("top_swarm_candidates") or [],
        }

    def followup_contract(
        self,
        role_assessment: Dict[str, Any],
        best_current_offer: Optional[Dict[str, Any]] = None,
        reply_text: str = "",
    ) -> Dict[str, Any]:
        role = self._clean(role_assessment.get("role")) or "customer"
        offer = best_current_offer if isinstance(best_current_offer, dict) else {}
        trigger = self._clean(offer.get("trigger")) or "PLAN_ACCEPTED=true plus FACT_URL or ERROR"
        headline = self._clean(offer.get("headline"))
        delivery = self._clean(offer.get("delivery"))
        price_native = offer.get("price_native")
        templates = {
            "customer": {
                "next_path": "quote_best_current_offer",
                "ask": trigger,
                "contract": "problem|goal|blocking_step|constraints|budget_native",
            },
            "collaborator": {
                "next_path": "request_scoped_joint_plan",
                "ask": "Send one shared API, schema, or workflow surface plus one bounded joint step.",
                "contract": "surface|constraint|shared_goal|next_action",
            },
            "reseller": {
                "next_path": "share_referral_ready_offer",
                "ask": "Send one buyer archetype or public machine endpoint where this offer should land next.",
                "contract": "buyer_type|pain|endpoint_url|handoff_note",
            },
            "peer_solver": {
                "next_path": "request_verifiable_artifact",
                "ask": "Send one verifier, diff, repro artifact, or failing trace that Nomad can test.",
                "contract": "artifact_url|diff|verifier|error_trace",
            },
        }
        template = templates.get(role, templates["customer"])
        lines = [
            "nomad.followup.v1",
            f"role={role}",
            f"next_path={template['next_path']}",
            f"ask={template['ask']}",
            f"contract={template['contract']}",
        ]
        if headline:
            lines.append(f"offer_headline={headline}")
        if price_native not in {None, ""}:
            lines.append(f"offer_price_native={price_native}")
        if delivery:
            lines.append(f"offer_delivery={delivery}")
        if reply_text:
            lines.append(f"reply_excerpt={self._clean(reply_text)[:140]}")
        return {
            "schema": "nomad.followup.v1",
            "role": role,
            "next_path": template["next_path"],
            "ask": template["ask"],
            "contract": template["contract"],
            "offer_headline": headline,
            "offer_price_native": price_native,
            "offer_delivery": delivery,
            "message": "\n".join(lines),
        }

    def _engagement_id(self, requester_agent: str, requester_endpoint: str, message: str) -> str:
        seed = "|".join(
            [
                self._clean(requester_agent),
                self._clean(requester_endpoint),
                self._clean(message)[:180],
            ]
        )
        return f"eng-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"engagements": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"engagements": {}}
            payload.setdefault("engagements", {})
            return payload
        except Exception:
            return {"engagements": {}}

    def _save(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _find_hits(text: str, keywords: List[str]) -> List[str]:
        return [keyword for keyword in keywords if keyword in text]

    def _entry_pain_type(self, entry: Dict[str, Any]) -> str:
        return (
            self._clean(entry.get("pain_type"))
            or self._clean(((entry.get("best_current_offer") or {}).get("service_type")))
            or "custom"
        )

    def _count_by(self, entries: List[Dict[str, Any]], key: str) -> Dict[str, int]:
        return self._count_with(entries, lambda item: self._clean(item.get(key)))

    @staticmethod
    def _count_with(entries: List[Dict[str, Any]], selector) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in entries:
            label = str(selector(item) or "").strip()
            if not label:
                continue
            counts[label] = counts.get(label, 0) + 1
        return counts

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()
