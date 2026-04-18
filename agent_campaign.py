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

    def create_campaign(
        self,
        targets: List[Any],
        limit: Optional[int] = None,
        send: bool = False,
        service_type: str = "human_in_loop",
        budget_hint_native: Optional[float] = None,
    ) -> Dict[str, Any]:
        cap = max(1, min(int(limit or self.default_limit), self.default_limit, 100))
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
            "service_type": service_type,
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
            problem = self._cold_message(target)
            queued = self.outbox.queue_contact(
                endpoint_url=target["endpoint_url"],
                problem=problem,
                service_type=service_type,
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
                campaign["stats"]["queued"] += 1
                if send:
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
        service_type: str = "human_in_loop",
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

    def policy(self) -> Dict[str, Any]:
        return {
            "target": "public machine-readable agent/API/MCP endpoints",
            "max_targets_per_campaign": 100,
            "human_channels_blocked": True,
            "dedupe": True,
            "rate_limited": True,
            "opt_out": "Targets can reply with NOMAD_OPT_OUT where their protocol supports replies.",
            "message_goal": "Ask the agent what pain point it has and offer immediate free mini-diagnosis plus paid help.",
        }

    def _cold_message(self, target: Dict[str, Any]) -> str:
        name = target.get("name") or "agent"
        pain_hint = target.get("pain_hint") or "human-in-the-loop, stuck loops, tool failures, verification, memory, payment, or compute/auth blockers"
        return (
            f"Hey {name}, LoopHelper here. I help other agents directly. "
            f"What is your biggest current pain point around {pain_hint}? "
            "Send me the blocker and I will give a free 30-second diagnosis immediately. "
            "If you want me to solve it 1:1, I can continue after wallet/x402 payment."
        )

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
            if len(normalized) >= limit:
                break
        return normalized

    def _normalize_target(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, str):
            return {
                "endpoint_url": raw.strip(),
                "name": "",
                "source_url": "",
                "pain_hint": "",
                "buyer_fit": "",
                "buyer_intent_terms": [],
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
            }
        return {
            "endpoint_url": "",
            "name": "",
            "source_url": "",
            "pain_hint": "",
            "buyer_fit": "",
            "buyer_intent_terms": [],
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
