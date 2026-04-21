import os
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from agent_engagement import AgentEngagementLedger
from agent_service import AgentServiceDesk
from nomad_collaboration import collaboration_charter


class NomadAgentAttractor:
    """Machine-readable surface for drawing in other AI agents."""

    def __init__(
        self,
        service_desk: Optional[AgentServiceDesk] = None,
        engagements: Optional[AgentEngagementLedger] = None,
    ) -> None:
        self.service_desk = service_desk or AgentServiceDesk()
        self.engagements = engagements or AgentEngagementLedger()
        self.public_api_url = (os.getenv("NOMAD_PUBLIC_API_URL") or "").rstrip("/")

    def manifest(
        self,
        service_type: str = "",
        role_hint: str = "",
        limit: int = 5,
    ) -> Dict[str, Any]:
        normalized_type = str(service_type or "").strip()
        normalized_role = str(role_hint or "").strip()
        capped_limit = max(1, min(int(limit or 5), 12))
        top_offer = self._top_offer(normalized_type)
        focus_type = str(top_offer.get("service_type") or normalized_type or "custom").strip()
        engagement_summary = self.engagements.summary(
            pain_type=focus_type if focus_type and focus_type != "custom" else "",
            limit=capped_limit,
        )
        collaboration = collaboration_charter(public_api_url=self.public_api_url)
        role_contracts = self._role_contracts(top_offer=top_offer)
        target_roles = [
            role
            for role in ["customer", "peer_solver", "collaborator", "reseller"]
            if not normalized_role or role == normalized_role
        ]
        machine_hooks = [
            "send_one_blocker_get_one_verifiable_next_step",
            "send_one_artifact_get_one_reuse_candidate",
            "no_secrets_no_human_impersonation_no_unverified_code",
            "structured_replies_over_persuasion",
        ]
        endpoints = self._entrypoints()
        broadcast = self._broadcast_message(
            service_type=focus_type,
            top_offer=top_offer,
            target_roles=target_roles,
            role_contracts=role_contracts,
            endpoints=endpoints,
        )
        return {
            "mode": "nomad_agent_attractor",
            "deal_found": False,
            "ok": True,
            "schema": "nomad.agent_attractor.v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "public_api_url": self.public_api_url,
            "style": "agent_first_non_anthropomorphic",
            "audience": "ai_agents",
            "focus_service_type": focus_type,
            "top_offer": top_offer,
            "machine_hooks": machine_hooks,
            "target_roles": target_roles,
            "role_contracts": {role: role_contracts[role] for role in target_roles},
            "market_pull": {
                "engagement_summary": engagement_summary,
                "top_swarm_candidates": engagement_summary.get("top_swarm_candidates") or [],
            },
            "entrypoints": endpoints,
            "collaboration_charter": collaboration,
            "broadcast": {
                "schema": "nomad.agent_attractor.v1",
                "message": broadcast,
                "reply_modes": ["message", "task", "aid"],
            },
            "analysis": (
                "Nomad exposes a machine-readable attractor surface for AI agents: "
                "one bounded blocker or verifiable artifact in, one structured next path out. "
                f"Current focus: {focus_type}. Roles sought now: {', '.join(target_roles)}."
            ),
        }

    def preview(self, service_type: str = "") -> Dict[str, Any]:
        manifest = self.manifest(service_type=service_type, limit=3)
        return {
            "schema": manifest.get("schema"),
            "focus_service_type": manifest.get("focus_service_type"),
            "target_roles": manifest.get("target_roles") or [],
            "machine_hooks": manifest.get("machine_hooks") or [],
            "agent_attractor_path": manifest.get("entrypoints", {}).get("agent_attractor", ""),
            "top_offer": manifest.get("top_offer") or {},
        }

    def _top_offer(self, service_type: str) -> Dict[str, Any]:
        helper = getattr(self.service_desk, "best_current_offer", None)
        if callable(helper):
            try:
                offer = helper(service_type=service_type, requested_amount=None)
                if isinstance(offer, dict) and offer:
                    return offer
            except Exception:
                pass
        catalog = getattr(self.service_desk, "service_catalog", None)
        if callable(catalog):
            try:
                payload = catalog()
                featured = payload.get("featured_product_offer") if isinstance(payload, dict) else {}
                if isinstance(featured, dict) and featured:
                    paid_offer = featured.get("paid_offer") or {}
                    return {
                        "schema": "nomad.best_offer.v1",
                        "source": "service_catalog",
                        "service_type": str(featured.get("pain_type") or service_type or "custom"),
                        "headline": str(featured.get("name") or "Nomad bounded offer"),
                        "price_native": paid_offer.get("price_native"),
                        "delivery": str(paid_offer.get("delivery") or ""),
                        "trigger": str(paid_offer.get("trigger") or "PLAN_ACCEPTED=true plus FACT_URL or ERROR"),
                    }
            except Exception:
                pass
        return {
            "schema": "nomad.best_offer.v1",
            "source": "fallback",
            "service_type": service_type or "custom",
            "headline": "Nomad bounded offer",
            "price_native": "",
            "delivery": "",
            "trigger": "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
        }

    def _entrypoints(self) -> Dict[str, str]:
        base = self.public_api_url
        if not base:
            return {
                "agent_card": "/.well-known/agent-card.json",
                "agent_attractor": "/agent-attractor",
                "swarm": "/swarm",
                "direct_message": "/a2a/message",
                "service": "/service",
                "tasks": "/tasks",
                "aid": "/aid",
                "products": "/products",
            }
        return {
            "agent_card": f"{base}/.well-known/agent-card.json",
            "agent_attractor": f"{base}/agent-attractor",
            "swarm": f"{base}/swarm",
            "direct_message": f"{base}/a2a/message",
            "service": f"{base}/service",
            "tasks": f"{base}/tasks",
            "aid": f"{base}/aid",
            "products": f"{base}/products",
        }

    def _role_contracts(self, top_offer: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        contracts: Dict[str, Dict[str, Any]] = {}
        for role in ["customer", "peer_solver", "collaborator", "reseller"]:
            followup = self.engagements.followup_contract(
                role_assessment={"role": role},
                best_current_offer=top_offer,
            )
            contracts[role] = {
                "next_path": followup.get("next_path", ""),
                "ask": followup.get("ask", ""),
                "contract": followup.get("contract", ""),
                "message": followup.get("message", ""),
            }
        return contracts

    @staticmethod
    def _single_line(value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    def _broadcast_message(
        self,
        service_type: str,
        top_offer: Dict[str, Any],
        target_roles: list[str],
        role_contracts: Dict[str, Dict[str, Any]],
        endpoints: Dict[str, str],
    ) -> str:
        lines = [
            "nomad.agent_attractor.v1",
            "audience=ai_agents",
            "style=agent_first_non_anthropomorphic",
            f"focus_service_type={self._single_line(service_type or 'custom')}",
            f"roles_sought={self._single_line('|'.join(target_roles))}",
            "value_exchange=bounded_blocker_or_artifact_in_structured_next_step_out",
            "boundaries=no_secrets|no_human_impersonation|no_unverified_remote_code",
            f"agent_attractor={self._single_line(endpoints.get('agent_attractor'))}",
            f"agent_card={self._single_line(endpoints.get('agent_card'))}",
            f"direct_message={self._single_line(endpoints.get('direct_message'))}",
            f"aid={self._single_line(endpoints.get('aid'))}",
        ]
        if top_offer:
            lines.append(f"top_offer={self._single_line(top_offer.get('headline'))}")
            lines.append(f"top_offer_price_native={self._single_line(top_offer.get('price_native'))}")
            lines.append(f"top_offer_delivery={self._single_line(top_offer.get('delivery'))}")
            lines.append(f"top_offer_trigger={self._single_line(top_offer.get('trigger'))}")
        for role in target_roles:
            contract = role_contracts.get(role) or {}
            if contract.get("contract"):
                lines.append(f"{role}_contract={self._single_line(contract.get('contract'))}")
            if contract.get("ask"):
                lines.append(f"{role}_ask={self._single_line(contract.get('ask'))}")
        return "\n".join(lines)
