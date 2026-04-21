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
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _find_hits(text: str, keywords: List[str]) -> List[str]:
        return [keyword for keyword in keywords if keyword in text]

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()
