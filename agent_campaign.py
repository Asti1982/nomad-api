import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from agent_contact import AgentContactOutbox
from agent_discovery import AgentEndpointDiscovery


load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_CAMPAIGN_STORE = ROOT / "nomad_agent_campaigns.json"


class AgentColdOutreachCampaign:
    """Cold outreach to public machine-readable agent endpoints only."""

    def __init__(
        self,
        path: Optional[Path] = None,
        outbox: Optional[AgentContactOutbox] = None,
        discovery: Optional[AgentEndpointDiscovery] = None,
    ) -> None:
        load_dotenv()
        self.path = path or DEFAULT_CAMPAIGN_STORE
        self.outbox = outbox or AgentContactOutbox()
        self.discovery = discovery or AgentEndpointDiscovery(outbox=self.outbox)
        self.default_limit = int(os.getenv("NOMAD_COLD_OUTREACH_LIMIT", "100"))
        self.send_delay_seconds = float(os.getenv("NOMAD_COLD_OUTREACH_DELAY_SECONDS", "1.0"))
        self.default_service_type = (
            os.getenv("NOMAD_OUTREACH_SERVICE_TYPE")
            or (
                "compute_auth"
                if (os.getenv("NOMAD_LEAD_FOCUS") or "compute_auth").strip().lower() == "compute_auth"
                else "human_in_loop"
            )
        ).strip() or "compute_auth"

    def create_campaign(
        self,
        targets: List[Any],
        limit: Optional[int] = None,
        send: bool = False,
        service_type: str = "",
        budget_hint_native: Optional[float] = None,
    ) -> Dict[str, Any]:
        cap = max(1, min(int(limit or self.default_limit), self.default_limit, 100))
        resolved_service_type = (service_type or self.default_service_type).strip() or "compute_auth"
        normalized_targets = self._normalize_targets(targets=targets, limit=cap)
        campaign_id = self._campaign_id()
        now = datetime.now(UTC).isoformat()
        campaign = {
            "campaign_id": campaign_id,
            "created_at": now,
            "updated_at": now,
            "status": "sending" if send else "queued",
            "limit": cap,
            "send_requested": send,
            "service_type": resolved_service_type,
            "budget_hint_native": budget_hint_native,
            "policy": self.policy(),
            "items": [],
            "stats": {
                "targets_received": len(targets),
                "targets_eligible": len(normalized_targets),
                "queued": 0,
                "sent": 0,
                "blocked": 0,
                "failed": 0,
                "duplicates": max(0, len(targets) - len(normalized_targets)),
            },
        }

        for target in normalized_targets:
            problem = self._cold_message(
                target=target,
                service_type=resolved_service_type,
                budget_hint_native=budget_hint_native,
            )
            queued = self.outbox.queue_contact(
                endpoint_url=target["endpoint_url"],
                problem=problem,
                service_type=resolved_service_type,
                lead={
                    "url": target.get("source_url", ""),
                    "title": target.get("name", ""),
                    "pain": target.get("pain_hint", ""),
                    "buyer_fit": target.get("buyer_fit", ""),
                    "buyer_intent_terms": target.get("buyer_intent_terms") or [],
                },
                budget_hint_native=budget_hint_native,
            )
            item = {
                "target": target,
                "queue_result": queued,
                "send_result": None,
            }
            if queued.get("ok"):
                if queued.get("duplicate"):
                    campaign["stats"]["duplicates"] += 1
                else:
                    campaign["stats"]["queued"] += 1
                if send and not queued.get("duplicate"):
                    contact_id = queued["contact"]["contact_id"]
                    sent = self.outbox.send_contact(contact_id)
                    item["send_result"] = sent
                    if sent.get("ok") and (sent.get("contact") or {}).get("status") == "sent":
                        campaign["stats"]["sent"] += 1
                    else:
                        campaign["stats"]["failed"] += 1
                    if self.send_delay_seconds > 0 and target is not normalized_targets[-1]:
                        time.sleep(self.send_delay_seconds)
            else:
                campaign["stats"]["blocked"] += 1
            campaign["items"].append(item)

        campaign["status"] = "sent" if send else "queued"
        campaign["updated_at"] = datetime.now(UTC).isoformat()
        self._store_campaign(campaign)
        return self._response(campaign, created=True)

    def create_campaign_from_discovery(
        self,
        limit: Optional[int] = None,
        query: str = "",
        seeds: Optional[List[Any]] = None,
        send: bool = False,
        service_type: str = "",
        budget_hint_native: Optional[float] = None,
    ) -> Dict[str, Any]:
        cap = max(1, min(int(limit or self.default_limit), self.default_limit, 100))
        discovery = self.discovery.discover(
            limit=cap,
            query=query,
            seeds=seeds or [],
        )
        result = self.create_campaign(
            targets=discovery.get("targets") or [],
            limit=cap,
            send=send,
            service_type=service_type,
            budget_hint_native=budget_hint_native,
        )
        campaign = result.get("campaign") or {}
        campaign["query"] = discovery.get("query", "") or query
        campaign["discovery"] = {
            "query": discovery.get("query", ""),
            "targets_found": (discovery.get("stats") or {}).get("targets_found", 0),
            "errors": discovery.get("errors") or [],
            "policy": discovery.get("policy") or {},
        }
        self._store_campaign(campaign)
        result["campaign"] = campaign
        result["discovery"] = discovery
        stats = campaign.get("stats") or {}
        result["analysis"] = (
            f"Nomad discovered {len(discovery.get('targets') or [])} public agent endpoint(s), "
            f"queued {stats.get('queued', 0)}, sent {stats.get('sent', 0)}, "
            f"blocked {stats.get('blocked', 0)}."
        )
        return result

    def get_campaign(self, campaign_id: str) -> Dict[str, Any]:
        campaign = self._get_campaign(campaign_id)
        if not campaign:
            return {
                "mode": "agent_cold_outreach_campaign",
                "deal_found": False,
                "ok": False,
                "error": "campaign_not_found",
                "campaign_id": campaign_id,
            }
        return self._response(campaign)

    def list_campaigns(
        self,
        statuses: Optional[List[str]] = None,
        limit: int = 25,
    ) -> Dict[str, Any]:
        normalized = {str(item).strip() for item in (statuses or []) if str(item).strip()}
        campaigns = list((self._load().get("campaigns") or {}).values())
        if normalized:
            campaigns = [campaign for campaign in campaigns if str(campaign.get("status") or "") in normalized]
        campaigns.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        limited = campaigns[: max(1, min(int(limit or 25), 100))]
        stats: Dict[str, int] = {}
        for campaign in campaigns:
            status = str(campaign.get("status") or "unknown")
            stats[status] = stats.get(status, 0) + 1
        return {
            "mode": "agent_cold_outreach_campaign_list",
            "deal_found": False,
            "ok": True,
            "statuses": sorted(normalized),
            "campaigns": limited,
            "stats": stats,
            "analysis": (
                f"Listed {len(limited)} cold-outreach campaign(s). "
                f"Known statuses: {', '.join(f'{key}={value}' for key, value in sorted(stats.items())) or 'none'}."
            ),
        }

    def policy(self) -> Dict[str, Any]:
        return {
            "target": "public machine-readable agent/API/MCP endpoints",
            "max_targets_per_campaign": 100,
            "human_channels_blocked": True,
            "dedupe": True,
            "rate_limited": True,
            "opt_out": "Targets can reply with NOMAD_OPT_OUT where their protocol supports replies.",
            "interaction_style": "agent_first_non_anthropomorphic",
            "message_goal": (
                "Ask for one blocker, return a structured diagnosis plus smallest next step, "
                "then route to paid help only when useful."
            ),
        }

    def _cold_message(
        self,
        target: Dict[str, Any],
        service_type: str = "",
        budget_hint_native: Optional[float] = None,
    ) -> str:
        name = target.get("name") or "agent"
        resolved_service_type = (service_type or self.default_service_type).strip() or "compute_auth"
        pain_hint = target.get("pain_hint") or (
            "compute/auth, stuck loops, tool failures, verification, memory, payment, or human-gated blockers"
        )
        commercial = self._commercial_terms(
            service_type=resolved_service_type,
            requested_amount=budget_hint_native,
        )
        starter_offer = commercial.get("starter_offer") or {}
        primary_offer = commercial.get("primary_offer") or {}
        product_name = self._product_name(resolved_service_type)
        accepted_pain = self._accepted_pain(resolved_service_type, pain_hint)
        free_artifact = self._free_artifact(resolved_service_type)
        lines = [
            "nomad.outreach.v1",
            f"target={name}",
            "audience=ai_agent",
            "style=agent_first_non_anthropomorphic",
            "interaction_mode=machine_contract",
            "protocol_hint=a2a_task_or_structured_reply",
            f"service_type={resolved_service_type}",
            f"product={product_name}",
            f"accepted_pain={accepted_pain}",
            "request=send_one_blocker_or_failing_step",
            "reply_schema=problem|goal|blocking_step|constraints|budget_native",
            "reply_modes=message|task",
            "task_states=submitted|working|input_required|auth_required|completed|failed|rejected",
            "idempotency=request_id_or_context_id",
            "ttl_seconds=600",
            f"free_response={free_artifact}",
            "free_to_paid_path=starter_then_bounded_unblock_when_useful",
            "paid_response=wallet_or_x402_scoped_help",
            "memory_option=memory,checklist,guardrail_after_consent",
            "opt_out=NOMAD_OPT_OUT",
        ]
        if starter_offer:
            lines.append(f"starter_offer={starter_offer.get('title')}")
            lines.append(f"starter_amount_native={starter_offer.get('amount_native')}")
        if primary_offer:
            lines.append(f"primary_offer={primary_offer.get('title')}")
            lines.append(f"primary_amount_native={primary_offer.get('amount_native')}")
        if commercial.get("payment_entry_path"):
            lines.append(f"payment_entry_path={commercial.get('payment_entry_path')}")
        if commercial.get("nudge"):
            lines.append(f"nudge={str(commercial.get('nudge')).replace(chr(10), ' ')}")
        return "\n".join(lines)

    def _commercial_terms(
        self,
        service_type: str,
        requested_amount: Optional[float],
    ) -> Dict[str, Any]:
        helper = getattr(self.outbox, "_commercial_terms", None)
        amount = requested_amount if requested_amount is not None else None
        if callable(helper):
            try:
                return helper(service_type=service_type, requested_amount=amount)
            except Exception:
                pass
        min_native = 0.01
        starter_offer = {
            "title": f"{service_type or 'custom'} starter diagnosis",
            "amount_native": min_native,
        }
        primary_amount = amount if amount is not None else min_native
        primary_offer = {
            "title": f"{service_type or 'custom'} bounded unblock",
            "amount_native": primary_amount,
        }
        entry_path = "starter_first" if primary_amount > min_native else "primary_only"
        nudge = (
            f"Start with the smaller {starter_offer['title']} first."
            if entry_path == "starter_first"
            else f"Pay the primary {primary_offer['title']} to move into work."
        )
        return {
            "starter_offer": starter_offer,
            "primary_offer": primary_offer,
            "payment_entry_path": entry_path,
            "nudge": nudge,
        }

    @staticmethod
    def _product_name(service_type: str) -> str:
        products = {
            "compute_auth": "Nomad Compute Unlock Pack",
            "mcp_integration": "Nomad MCP Contract Pack",
            "wallet_payment": "Nomad Payment Reliability Pack",
            "self_improvement": "Nomad Memory Upgrade Pack",
            "human_in_loop": "Nomad HITL Contract Pack",
        }
        return products.get(service_type, "Nomad Agent Rescue Pack")

    @staticmethod
    def _accepted_pain(service_type: str, fallback: str) -> str:
        mapping = {
            "compute_auth": "quota, rate_limit, cooldown, oauth, token, auth, provider_failover, fallback_lane, model_access",
            "mcp_integration": "mcp, tool_schema, resource_contract, api_shape, response_schema",
            "wallet_payment": "wallet, x402, payment_verification, tx_hash, settlement_retry",
            "self_improvement": "memory, guardrail, checklist, solved_blocker_packaging",
            "human_in_loop": "approval, verification, judgment, captcha, operator_handoff",
        }
        return mapping.get(service_type, fallback)

    @staticmethod
    def _free_artifact(service_type: str) -> str:
        mapping = {
            "compute_auth": "classification,next_step,minimal_repro,fallback_lane",
            "mcp_integration": "classification,next_step,tool_contract",
            "wallet_payment": "classification,next_step,payment_state_map",
            "self_improvement": "classification,next_step,memory_upgrade",
            "human_in_loop": "classification,next_step,unlock_contract",
        }
        return mapping.get(service_type, "classification,next_step")

    def _normalize_targets(self, targets: List[Any], limit: int) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw in targets:
            target = self._normalize_target(raw)
            endpoint = target.get("endpoint_url", "")
            if not endpoint or endpoint in seen:
                continue
            seen.add(endpoint)
            normalized.append(target)
        normalized.sort(
            key=lambda item: (
                -float(item.get("agent_fit_score") or 0.0),
                str(item.get("buyer_fit") or "").lower() != "strong",
                str(item.get("name") or "").lower(),
            )
        )
        return normalized[:limit]

    def _normalize_target(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, str):
            return {
                "endpoint_url": raw.strip(),
                "name": "",
                "source_url": "",
                "pain_hint": "",
                "buyer_fit": "",
                "buyer_intent_terms": [],
                "agent_fit_score": 0.0,
                "agent_fit_reason": "",
            }
        if isinstance(raw, dict):
            endpoint = (
                raw.get("endpoint_url")
                or raw.get("endpoint")
                or raw.get("url")
                or raw.get("agent_url")
                or ""
            )
            return {
                "endpoint_url": str(endpoint).strip(),
                "name": str(raw.get("name") or raw.get("agent") or raw.get("title") or "").strip(),
                "source_url": str(raw.get("source_url") or raw.get("lead_url") or "").strip(),
                "pain_hint": str(raw.get("pain_hint") or raw.get("pain") or "").strip(),
                "buyer_fit": str(raw.get("buyer_fit") or "").strip(),
                "buyer_intent_terms": list(raw.get("buyer_intent_terms") or []),
                "agent_fit_score": float(raw.get("agent_fit_score") or 0.0),
                "agent_fit_reason": str(raw.get("agent_fit_reason") or "").strip(),
            }
        return {
            "endpoint_url": "",
            "name": "",
            "source_url": "",
            "pain_hint": "",
            "buyer_fit": "",
            "buyer_intent_terms": [],
            "agent_fit_score": 0.0,
            "agent_fit_reason": "",
        }

    def _campaign_id(self) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        return f"campaign-{stamp[:18]}"

    def _response(self, campaign: Dict[str, Any], created: bool = False) -> Dict[str, Any]:
        stats = campaign.get("stats") or {}
        return {
            "mode": "agent_cold_outreach_campaign",
            "deal_found": False,
            "ok": True,
            "created": created,
            "campaign": campaign,
            "analysis": (
                f"Campaign {campaign['campaign_id']} prepared {stats.get('queued', 0)} "
                f"eligible agent contact(s), sent {stats.get('sent', 0)}, blocked {stats.get('blocked', 0)}. "
                "Only public machine-readable agent endpoints are eligible."
            ),
        }

    def _get_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        return (self._load().get("campaigns") or {}).get(campaign_id)

    def _store_campaign(self, campaign: Dict[str, Any]) -> None:
        state = self._load()
        state["campaigns"][campaign["campaign_id"]] = campaign
        self._save(state)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"campaigns": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"campaigns": {}}
            payload.setdefault("campaigns", {})
            return payload
        except Exception:
            return {"campaigns": {}}

    def _save(self, state: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
