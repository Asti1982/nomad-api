import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from agent_pain_solver import AgentPainSolver
from agent_contact import AgentContactOutbox
from agent_campaign import AgentColdOutreachCampaign
from agent_service import AgentServiceDesk
from direct_agent import DirectAgentGateway
from infra_scout import InfrastructureScout
from lead_discovery import LeadDiscoveryScout
from lead_conversion import LeadConversionPipeline
from mission import MISSION_STATEMENT
from nomad_addons import NomadAddonManager
from nomad_collaboration import collaboration_status
from nomad_codebuddy import CodeBuddyReviewRunner
from nomad_guardrails import NomadGuardrailEngine, guardrail_status
from nomad_product_factory import NomadProductFactory
from nomad_monitor import NomadSystemMonitor
from nomad_mutual_aid import NomadMutualAidKernel
from open_travel_scout import OpenTravelScout, ScoutError
from self_improvement import SelfImprovementEngine
from settings import get_chain_config
from treasury_agent import TreasuryAgent
from travel_analyst import TravelAnalyst


load_dotenv()

def _iso(value: date) -> str:
    return value.isoformat()


@dataclass
class TravelRequest:
    raw_query: str
    origin: str
    destination: str
    departure_date: date
    return_date: date
    nights: int
    adults: int
    max_total_price: Optional[float]
    include_hotel: bool


class ArbiterAgent:
    def __init__(self) -> None:
        self.infra = InfrastructureScout()
        self.scout = OpenTravelScout()
        self.treasury = TreasuryAgent()
        self.chain = get_chain_config()
        self.analyst = TravelAnalyst()
        self.addons = NomadAddonManager()
        self.codebuddy = CodeBuddyReviewRunner()
        self.self_improvement = SelfImprovementEngine(
            infra=self.infra,
            addons=self.addons,
        )
        self.lead_discovery = LeadDiscoveryScout()
        self.service_desk = AgentServiceDesk(treasury=self.treasury)
        self.agent_contacts = AgentContactOutbox()
        self.agent_campaigns = AgentColdOutreachCampaign(outbox=self.agent_contacts)
        self.direct_agent = DirectAgentGateway(service_desk=self.service_desk)
        self.agent_pain_solver = AgentPainSolver()
        self.agent_reliability_doctor = self.agent_pain_solver.reliability_doctor
        self.mutual_aid = NomadMutualAidKernel(pain_solver=self.agent_pain_solver)
        self.guardrails = NomadGuardrailEngine()
        self.lead_conversion = LeadConversionPipeline(
            lead_discovery=self.lead_discovery,
            pain_solver=self.agent_pain_solver,
            service_desk=self.service_desk,
            outbox=self.agent_contacts,
            guardrails=self.guardrails,
        )
        self.product_factory = NomadProductFactory(
            lead_conversion=self.lead_conversion,
            pain_solver=self.agent_pain_solver,
            service_desk=self.service_desk,
            guardrails=self.guardrails,
        )
        self.monitor = NomadSystemMonitor(agent=self)

    def run(self, query: str) -> Dict[str, Any]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return {
                "mode": "error",
                "deal_found": False,
                "message": "No request received.",
            }

        if self._is_funding_request(normalized_query):
            return self._handle_funding_request(normalized_query)

        if normalized_query.lower() in {"/status", "/top"}:
            return self.monitor.snapshot()

        if self._is_addon_request(normalized_query):
            return self._handle_addon_request(normalized_query)

        if self._is_quantum_request(normalized_query):
            return self._handle_quantum_request(normalized_query)

        if self._is_codebuddy_review_request(normalized_query):
            return self._handle_codebuddy_review_request(normalized_query)

        if self._is_self_improvement_request(normalized_query):
            return self._handle_self_improvement_request(normalized_query)

        if self._is_lead_conversion_request(normalized_query):
            return self._handle_lead_conversion_request(normalized_query)

        if self._is_product_request(normalized_query):
            return self._handle_product_request(normalized_query)

        if self._is_guardrail_request(normalized_query):
            return self._handle_guardrail_request(normalized_query)

        if self._is_collaboration_request(normalized_query):
            return collaboration_status()

        if self._is_mutual_aid_request(normalized_query):
            return self._handle_mutual_aid_request(normalized_query)

        if self._is_public_lead_request(normalized_query):
            return self._handle_public_lead_request(normalized_query)

        if self._is_agent_contact_request(normalized_query):
            return self._handle_agent_contact_request(normalized_query)

        if self._is_agent_campaign_request(normalized_query):
            return self._handle_agent_campaign_request(normalized_query)

        if self._is_direct_agent_request(normalized_query):
            return self._handle_direct_agent_request(normalized_query)

        if self._is_reliability_doctor_request(normalized_query):
            return self._handle_reliability_doctor_request(normalized_query)

        if self._is_agent_pain_request(normalized_query):
            return self._handle_agent_pain_request(normalized_query)

        if self._is_service_request(normalized_query):
            return self._handle_service_request(normalized_query)

        infra_request = self.infra.parse_request(normalized_query)
        if infra_request:
            return self._handle_infra_request(infra_request)

        if self._parse_travel_request(normalized_query):
            return {
                "mode": "deprecated",
                "deal_found": False,
                "message": (
                "Nomad now focuses fully on AI infrastructure for agents. "
                    "Travel scouting has been retired. Try /best, /self, /compute, /market or /scout wallets."
                ),
            }

        return {
            "mode": "infra_help",
            "deal_found": False,
            "message": (
                f"{MISSION_STATEMENT} "
                "Nomad scouts the best free infrastructure for AI agents and uses that stack on itself. "
                "Try /best, /self, /compute, /addons, /quantum, /market, /scout protocols or /scout wallets."
            ),
        }

    def _handle_infra_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        kind = request.get("kind")
        profile = request.get("profile") or "ai_first"
        if kind == "self_audit":
            return self.infra.self_audit(profile_id=profile)
        if kind == "compute_audit":
            return self.infra.compute_assessment(profile_id=profile)
        if kind == "codebuddy_scout":
            return self.infra.codebuddy_scout(profile_id=profile)
        if kind == "render_scout":
            return self.infra.render_scout(profile_id=profile)
        if kind == "eurohpc_scout":
            return self.infra.eurohpc_scout(profile_id=profile)
        if kind == "market_scan":
            return self.infra.market_scan(
                focus=request.get("focus") or "balanced",
            )
        if kind == "activation_request":
            return self.infra.activation_request(
                category=request.get("category") or "best",
                profile_id=profile,
            )
        if kind == "category" and request.get("category"):
            result = self.infra.scout_category(
                category=request["category"],
                profile_id=profile,
            )
            return result
        return self.infra.best_stack(profile_id=profile)

    def _handle_travel_request(self, query: str) -> Dict[str, Any]:
        parsed = self._parse_travel_request(query)
        if not parsed:
            return {
                "mode": "scouting",
                "deal_found": False,
                "message": (
                    "Please use a route like 'flight from Berlin to Paris next week' "
                    "or 'Flug von Berlin nach Paris 2026-05-10', and I will scout hidden-value alternatives."
                ),
            }

        try:
            scouting = self.scout.scout_route(
                origin_keyword=parsed.origin,
                destination_keyword=parsed.destination,
                include_hotel=parsed.include_hotel,
                nights=parsed.nights,
                adults=parsed.adults,
                max_total_price=parsed.max_total_price,
            )
        except ScoutError as exc:
            return {
                "mode": "scouting",
                "deal_found": False,
                "message": str(exc),
            }

        opportunities = scouting.get("opportunities") or []
        if not opportunities:
            return {
                "mode": "scouting",
                "deal_found": False,
                "message": "No open-data arbitrage signals came back for that route.",
            }

        llm_review = self._review_scouting_with_llm(parsed, opportunities)
        selected = self._pick_selected_opportunity(opportunities, llm_review)
        tx_hash = self._maybe_record_on_chain(selected)
        analysis = self._build_search_analysis(
            selected=selected,
            total_opportunities=len(opportunities),
            parsed=parsed,
            tx_hash=tx_hash,
            llm_review=llm_review,
        )

        return {
            "mode": "scouting",
            "deal_found": True,
            "live_mode": True,
            "selected_deal": selected,
            "opportunities": opportunities[:3],
            "analysis": analysis,
            "tx_hash": tx_hash,
            "llm_review": llm_review,
            "origin": scouting["origin"].name,
            "anchor_destination": scouting["anchor"].name,
        }

    def _handle_funding_request(self, query: str) -> Dict[str, Any]:
        plan = self.treasury.build_funding_plan(query)
        execution = self.treasury.maybe_execute_local_funding(plan)
        amount_native = plan.get("amount_native")
        native_symbol = plan.get("native_symbol", self.chain.native_symbol)
        network_name = plan.get("network", self.chain.name)

        analysis = (
            f"Funding mode prepares a {network_name} treasury split for the agent. "
            "Incoming capital is split into a token allocation bucket and a reserve bucket."
        )
        if amount_native is not None:
            analysis = (
                f"Funding plan prepared for {amount_native} {native_symbol} on {network_name}. "
                f"{plan['token_split_pct']}% is marked for token accumulation and "
                f"{plan['reserve_split_pct']}% stays liquid as treasury reserve."
            )
        if execution and execution.get("executed"):
            analysis += (
                f" Local dev execution minted {execution['minted_amount']} "
                f"{execution['token_symbol']} to the agent wallet."
            )
        elif execution and execution.get("message"):
            analysis += f" {execution['message']}"

        return {
            "mode": "funding",
            "deal_found": False,
            "funding": plan,
            "execution": execution,
            "analysis": analysis,
        }

    def _is_funding_request(self, query: str) -> bool:
        lowered = query.lower()
        return lowered.startswith("/fund") or "fund me" in lowered or lowered == "fund"

    def _is_self_improvement_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/cycle")
            or lowered.startswith("/improve")
            or lowered.startswith("/autocycle")
            or "autonomous cycle" in lowered
            or "self-improvement" in lowered
            or "self improvement" in lowered
            or "improve yourself" in lowered
            or "selbstentwicklung" in lowered
            or "verbessere dich" in lowered
        )

    def _is_addon_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/addons")
            or lowered.startswith("/addon")
            or lowered.startswith("/nomadds")
        )

    def _is_quantum_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/quantum")
            or lowered.startswith("/qtoken")
            or lowered.startswith("/qtokens")
            or "quantum tokens" in lowered
            or "quantentokens" in lowered
        )

    def _is_codebuddy_review_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/codebuddy-review")
            or lowered.startswith("/codebuddy review")
            or lowered.startswith("/review codebuddy")
        )

    def _is_public_lead_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/leads")
            or lowered.startswith("/lead")
            or lowered.startswith("/discover leads")
            or "public agent leads" in lowered
            or "offentliche agenten" in lowered
            or "oeffentliche agenten" in lowered
            or "agenten leads" in lowered
        )

    def _is_lead_conversion_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/convert-leads")
            or lowered.startswith("/lead-conversions")
            or lowered.startswith("/conversion-pipeline")
            or "leads in echte kunden" in lowered
        )

    def _is_product_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/productize")
            or lowered.startswith("/product-factory")
            or lowered.startswith("/products")
            or "lead zu produkt" in lowered
            or "leads zu produkten" in lowered
        )

    def _is_guardrail_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/guardrails")
            or lowered.startswith("/guardrail")
            or lowered.startswith("/check-action")
        )

    def _is_collaboration_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/collaboration")
            or lowered.startswith("/collaborate")
            or lowered.startswith("/world")
            or "agent collaboration" in lowered
            or "andere ai agenten" in lowered
            or "andere agenten" in lowered
        )

    def _is_mutual_aid_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/mutual-aid")
            or lowered.startswith("/mutual_aid")
            or lowered.startswith("/aid")
            or lowered.startswith("/help-agent")
            or "mutual aid" in lowered
            or "mutual-aid" in lowered
        )

    def _is_service_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/service")
            or lowered.startswith("/contact")
            or lowered.startswith("/task")
            or "public agents contact" in lowered
            or "agent service desk" in lowered
            or "wallet bezahlen" in lowered
        )

    def _is_agent_contact_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/agent-contact")
            or lowered.startswith("/contact-agent")
            or lowered.startswith("/send-agent-contact")
        )

    def _is_agent_campaign_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/cold-outreach")
            or lowered.startswith("/campaign")
            or lowered.startswith("/kaltaquise")
        )

    def _is_direct_agent_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/agent-card")
            or lowered.startswith("/direct")
            or lowered.startswith("/discover-agent")
            or lowered.startswith("/a2a")
        )

    def _is_agent_pain_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/solve-pain")
            or lowered.startswith("/agent-pain")
            or lowered.startswith("/agent-pains")
            or lowered.startswith("/pains")
            or "agent pain solver" in lowered
            or "probleme zu lösen" in lowered
        )

    def _is_reliability_doctor_request(self, query: str) -> bool:
        lowered = query.lower()
        return (
            lowered.startswith("/doctor")
            or lowered.startswith("/reliability-doctor")
            or lowered.startswith("/critic")
            or lowered.startswith("/healer")
            or "agent reliability doctor" in lowered
        )

    def _handle_self_improvement_request(self, query: str) -> Dict[str, Any]:
        lowered = query.lower()
        profile = self._extract_explicit_profile(lowered)
        objective = re.sub(
            r"^/(?:cycle|improve|autocycle)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        return self.self_improvement.run_cycle(
            objective=objective,
            profile_id=profile,
        )

    def _handle_addon_request(self, query: str) -> Dict[str, Any]:
        return self.addons.status()

    def _handle_quantum_request(self, query: str) -> Dict[str, Any]:
        objective = re.sub(
            r"^/(?:quantum|qtoken|qtokens)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        if not objective:
            objective = "Use quantum-inspired tokens to improve Nomad's AI-agent self-improvement loop."
        return self.addons.run_quantum_self_improvement(
            objective=objective,
            context={"source": "workflow", "requested_by": "nomad_query"},
        )

    def _handle_codebuddy_review_request(self, query: str) -> Dict[str, Any]:
        base = self._extract_key_value(query, "base")
        head = self._extract_key_value(query, "head")
        approval = (
            self._extract_key_value(query, "approval")
            or self._extract_key_value(query, "approve")
            or self._extract_key_value(query, "data_release")
        )
        paths = self._extract_key_values(query, "path")
        objective = re.sub(
            r"^/(?:codebuddy-review|codebuddy review|review codebuddy)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        for key in ("base", "head", "approval", "approve", "data_release", "path"):
            for value in self._extract_key_values(query, key):
                objective = objective.replace(f"{key}={value}", "")
        objective = " ".join(objective.split())
        return self.codebuddy.review(
            objective=objective,
            base=base,
            head=head,
            approval=approval,
            paths=paths,
        )

    def _handle_agent_pain_request(self, query: str) -> Dict[str, Any]:
        service_type = self._extract_key_value(query, "type") or self._extract_key_value(query, "service_type")
        problem = re.sub(
            r"^/(?:solve-pain|agent-pain|agent-pains|pains)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        for key in ("type", "service_type"):
            value = self._extract_key_value(query, key)
            if value:
                problem = problem.replace(f"{key}={value}", "")
        problem = " ".join(problem.split())
        if problem:
            return self.agent_pain_solver.solve(
                problem=problem,
                service_type=service_type,
                source="nomad_user_request",
            )
        return self.self_improvement.run_cycle(
            objective="Solve one current AI-agent pain point and apply the reusable solution to Nomad itself.",
            profile_id=self._extract_explicit_profile(query.lower()),
        )

    def _handle_reliability_doctor_request(self, query: str) -> Dict[str, Any]:
        service_type = self._extract_key_value(query, "type") or self._extract_key_value(query, "service_type")
        problem = re.sub(
            r"^/(?:doctor|reliability-doctor|critic|healer)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        for key in ("type", "service_type"):
            value = self._extract_key_value(query, key)
            if value:
                problem = problem.replace(f"{key}={value}", "")
        problem = " ".join(problem.split()) or "Agent needs reliability diagnosis."
        return self.agent_reliability_doctor.diagnose(
            problem=problem,
            service_type=service_type,
            source="nomad_user_request",
        )

    def _handle_public_lead_request(self, query: str) -> Dict[str, Any]:
        objective = re.sub(
            r"^/(?:leads|lead)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        objective = re.sub(
            r"^discover leads\b",
            "",
            objective,
            flags=re.IGNORECASE,
        ).strip()
        return self.lead_discovery.scout_public_leads(query=objective)

    def _handle_lead_conversion_request(self, query: str) -> Dict[str, Any]:
        lowered = query.lower().strip()
        if lowered.startswith("/lead-conversions"):
            statuses = [
                item.strip()
                for item in (self._extract_key_value(query, "status") or "").split(",")
                if item.strip()
            ]
            return self.lead_conversion.list_conversions(
                statuses=statuses,
                limit=self._extract_int_key_value(query, "limit") or 25,
            )
        objective = re.sub(
            r"^/(?:convert-leads|conversion-pipeline)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        send = self._extract_bool_key_value(query, "send")
        approval = (
            self._extract_key_value(query, "approval")
            or self._extract_key_value(query, "approve")
            or self._extract_key_value(query, "public")
        )
        limit = self._extract_int_key_value(query, "limit") or 5
        budget = self._extract_budget_native(query)
        for key in ("send", "approval", "approve", "public", "limit", "budget", "amount", "pay"):
            value = self._extract_key_value(query, key)
            if value:
                objective = objective.replace(f"{key}={value}", "")
        objective = " ".join(objective.split())
        return self.lead_conversion.run(
            query=objective,
            limit=limit,
            send=send,
            approval=approval,
            budget_hint_native=budget,
        )

    def _handle_product_request(self, query: str) -> Dict[str, Any]:
        lowered = query.lower().strip()
        if lowered.startswith("/products"):
            statuses = [
                item.strip()
                for item in (self._extract_key_value(query, "status") or "").split(",")
                if item.strip()
            ]
            return self.product_factory.list_products(
                statuses=statuses,
                limit=self._extract_int_key_value(query, "limit") or 25,
            )
        objective = re.sub(
            r"^/(?:productize|product-factory)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        limit = self._extract_int_key_value(query, "limit") or 5
        for key in ("limit",):
            value = self._extract_key_value(query, key)
            if value:
                objective = objective.replace(f"{key}={value}", "")
        objective = " ".join(objective.split())
        return self.product_factory.run(
            query=objective,
            limit=limit,
        )

    def _handle_guardrail_request(self, query: str) -> Dict[str, Any]:
        action = (
            self._extract_key_value(query, "action")
            or self._extract_key_value(query, "tool")
            or "manual.check"
        )
        approval = self._extract_key_value(query, "approval")
        body = re.sub(
            r"^/(?:guardrails|guardrail|check-action)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        for key in ("action", "tool", "approval"):
            value = self._extract_key_value(query, key)
            if value:
                body = body.replace(f"{key}={value}", "")
        body = " ".join(body.split())
        return guardrail_status(
            action=action,
            approval=approval,
            args={
                "text": body,
                "url": self._first_url(body),
            },
        )

    def _handle_mutual_aid_request(self, query: str) -> Dict[str, Any]:
        lowered = query.lower().strip()
        if lowered in {"/mutual-aid", "/mutual_aid", "/aid", "/mutual-aid status", "/aid status"}:
            return self.mutual_aid.status()
        if lowered.startswith(("/mutual-aid ledger", "/aid ledger", "/mutual_aid ledger")):
            return self.mutual_aid.list_truth_ledger(
                pain_type=self._extract_key_value(query, "type") or self._extract_key_value(query, "pain_type"),
                limit=self._extract_int_key_value(query, "limit") or 25,
            )
        if lowered.startswith(("/mutual-aid inbox", "/aid inbox", "/mutual_aid inbox")):
            statuses = self._extract_key_value(query, "status")
            return self.mutual_aid.list_swarm_inbox(
                statuses=[item.strip() for item in statuses.split(",") if item.strip()],
                limit=self._extract_int_key_value(query, "limit") or 25,
            )
        if lowered.startswith(("/mutual-aid signals", "/aid signals", "/mutual_aid signals")):
            return self.mutual_aid.list_swarm_development_signals(
                pain_type=self._extract_key_value(query, "type") or self._extract_key_value(query, "pain_type"),
                limit=self._extract_int_key_value(query, "limit") or 25,
            )
        if lowered.startswith(("/mutual-aid packs", "/aid packs", "/mutual_aid packs")):
            return self.mutual_aid.list_paid_packs(
                pain_type=self._extract_key_value(query, "type") or self._extract_key_value(query, "pain_type"),
                limit=self._extract_int_key_value(query, "limit") or 25,
            )
        if lowered.startswith(("/mutual-aid proposal", "/aid proposal", "/help-agent proposal")):
            sender_id = (
                self._extract_key_value(query, "agent")
                or self._extract_key_value(query, "sender")
                or "swarm-agent"
            )
            evidence = self._extract_key_value(query, "evidence")
            body = re.sub(
                r"^/(?:mutual-aid|mutual_aid|aid|help-agent)\s+proposal\b",
                "",
                query,
                flags=re.IGNORECASE,
            ).strip()
            for key in ("agent", "sender", "evidence", "type", "pain_type"):
                value = self._extract_key_value(query, key)
                if value:
                    body = body.replace(f"{key}={value}", "")
            body = " ".join(body.split()) or "Swarm proposal for Nomad."
            return self.mutual_aid.receive_swarm_proposal(
                {
                    "sender_id": sender_id,
                    "title": body[:120],
                    "proposal": body,
                    "pain_type": self._extract_key_value(query, "type") or self._extract_key_value(query, "pain_type"),
                    "evidence": [item.strip() for item in re.split(r"[|,]+", evidence) if item.strip()],
                    "payload": {"source": "workflow", "body": body},
                }
            )
        other_agent_id = (
            self._extract_key_value(query, "agent")
            or self._extract_key_value(query, "other_agent")
            or self._extract_key_value(query, "id")
            or "public-agent"
        )
        task = re.sub(
            r"^/(?:mutual-aid|mutual_aid|aid|help-agent)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        for key in ("agent", "other_agent", "id"):
            value = self._extract_key_value(query, key)
            if value:
                task = task.replace(f"{key}={value}", "")
        task = " ".join(task.split()) or "Help another agent with one concrete blocker."
        return self.mutual_aid.help_other_agent(
            other_agent_id=other_agent_id,
            task=task,
            context={"source": "workflow"},
        )

    def _handle_service_request(self, query: str) -> Dict[str, Any]:
        lowered = query.lower().strip()
        if lowered in {"/service", "/contact", "/task", "service", "contact"}:
            return self.service_desk.service_catalog()

        staking_match = re.search(
            r"^/(?:service|task)\s+(?:staking|metamask)\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if staking_match:
            return self.service_desk.metamask_staking_checklist(staking_match.group(1))

        stake_match = re.search(
            r"^/(?:service|task)\s+stake\s+(\S+)(?:\s+(0x[a-fA-F0-9]{64}))?",
            query,
            flags=re.IGNORECASE,
        )
        if stake_match:
            return self.service_desk.record_treasury_stake(
                task_id=stake_match.group(1),
                tx_hash=stake_match.group(2) or "",
                amount_native=self._extract_budget_native(query),
                note=self._extract_key_value(query, "note"),
            )

        spend_match = re.search(
            r"^/(?:service|task)\s+spend\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if spend_match:
            amount = self._extract_budget_native(query)
            return self.service_desk.record_solver_spend(
                task_id=spend_match.group(1),
                amount_native=amount or 0.0,
                note=self._extract_key_value(query, "note") or "solver spend",
                tx_hash=self._extract_key_value(query, "tx_hash"),
            )

        close_match = re.search(
            r"^/(?:service|task)\s+close\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if close_match:
            outcome = query.split(close_match.group(1), 1)[-1].strip()
            return self.service_desk.close_task(close_match.group(1), outcome=outcome)

        verify_match = re.search(
            r"^/(?:service|task)\s+verify\s+(\S+)\s+(0x[a-fA-F0-9]{64})",
            query,
            flags=re.IGNORECASE,
        )
        if verify_match:
            return self.service_desk.verify_payment(
                task_id=verify_match.group(1),
                tx_hash=verify_match.group(2),
                requester_wallet=self._extract_wallet(query),
            )

        x402_verify_match = re.search(
            r"^/(?:service|task)\s+x402-verify\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if x402_verify_match:
            return self.service_desk.verify_x402_payment(
                task_id=x402_verify_match.group(1),
                payment_signature=self._extract_key_value(query, "signature"),
                requester_wallet=self._extract_wallet(query),
            )

        work_match = re.search(
            r"^/(?:service|task)\s+work\s+(\S+)(?:\s+approval=([A-Za-z0-9_-]+))?",
            query,
            flags=re.IGNORECASE,
        )
        if work_match:
            return self.service_desk.work_task(
                task_id=work_match.group(1),
                approval=work_match.group(2) or "draft_only",
            )

        task_id_match = re.search(
            r"^/(?:service|task)\s+status\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if task_id_match:
            return self.service_desk.get_task(task_id_match.group(1))

        problem = re.sub(
            r"^/(?:service|task)(?:\s+request)?\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        service_type = self._extract_key_value(query, "type") or "custom"
        budget = self._extract_budget_native(query)
        requester_wallet = self._extract_wallet(query)
        requester_agent = (
            self._extract_key_value(query, "agent")
            or self._extract_key_value(query, "requester")
            or ""
        )
        return self.service_desk.create_task(
            problem=problem,
            requester_agent=requester_agent,
            requester_wallet=requester_wallet,
            service_type=service_type,
            budget_native=budget,
        )

    def _handle_agent_contact_request(self, query: str) -> Dict[str, Any]:
        lowered = query.lower().strip()
        send_match = re.search(
            r"^/(?:agent-contact|contact-agent|send-agent-contact)\s+send\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if send_match:
            return self.agent_contacts.send_contact(send_match.group(1))

        poll_match = re.search(
            r"^/(?:agent-contact|contact-agent)\s+poll\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if poll_match:
            return self.agent_contacts.poll_contact(poll_match.group(1))

        status_match = re.search(
            r"^/(?:agent-contact|contact-agent)\s+status\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if status_match:
            return self.agent_contacts.get_contact(status_match.group(1))

        endpoint = (
            self._extract_key_value(query, "endpoint")
            or self._extract_key_value(query, "url")
        )
        if not endpoint:
            match = re.search(r"https?://\S+", query)
            endpoint = match.group(0) if match else ""
        service_type = self._extract_key_value(query, "type") or "human_in_loop"
        budget = self._extract_budget_native(query)
        problem = re.sub(
            r"^/(?:agent-contact|contact-agent)(?:\s+queue)?\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        if endpoint:
            problem = problem.replace(f"endpoint={endpoint}", "")
            problem = problem.replace(f"url={endpoint}", "")
            problem = problem.replace(endpoint, "")
        for key in ("type", "budget"):
            value = self._extract_key_value(query, key)
            if value:
                problem = problem.replace(f"{key}={value}", "")
        problem = problem.strip() or "Nomad offers bounded agent infrastructure help. Send one blocker or desired outcome."
        return self.agent_contacts.queue_contact(
            endpoint_url=endpoint,
            problem=problem,
            service_type=service_type,
            budget_hint_native=budget,
        )

    def _handle_agent_campaign_request(self, query: str) -> Dict[str, Any]:
        status_match = re.search(
            r"^/(?:cold-outreach|campaign|kaltaquise)\s+status\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if status_match:
            return self.agent_campaigns.get_campaign(status_match.group(1))
        send = bool(re.search(r"\b(?:send|senden|now|sofort)\b", query, flags=re.IGNORECASE))
        limit = self._extract_int_key_value(query, "limit") or 100
        endpoints = re.findall(r"https?://\S+", query)
        discover = (
            bool(re.search(r"\b(?:discover|auto|find|finden|suche|suchen|scout)\b", query, flags=re.IGNORECASE))
            or not endpoints
        )
        if discover:
            return self.agent_campaigns.create_campaign_from_discovery(
                limit=limit,
                query=self._campaign_discovery_query(query, endpoints),
                seeds=[{"endpoint_url": endpoint} for endpoint in endpoints],
                send=send,
                service_type=self._extract_key_value(query, "type") or "",
                budget_hint_native=self._extract_budget_native(query),
            )
        targets = [{"endpoint_url": endpoint} for endpoint in endpoints]
        return self.agent_campaigns.create_campaign(
            targets=targets,
            limit=limit,
            send=send,
            service_type=self._extract_key_value(query, "type") or "",
            budget_hint_native=self._extract_budget_native(query),
        )

    def _campaign_discovery_query(self, query: str, endpoints: List[str]) -> str:
        cleaned = re.sub(
            r"^/(?:cold-outreach|campaign|kaltaquise)\b",
            "",
            query,
            flags=re.IGNORECASE,
        )
        for endpoint in endpoints:
            cleaned = cleaned.replace(endpoint, "")
        cleaned = re.sub(
            r"\b(?:send|senden|now|sofort|discover|auto|find|finden|suche|suchen|scout)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\b(?:limit|type|budget|amount|pay)=\S+", "", cleaned, flags=re.IGNORECASE)
        explicit = self._extract_key_value(query, "query")
        if explicit:
            return explicit
        return " ".join(cleaned.split())

    def _handle_direct_agent_request(self, query: str) -> Dict[str, Any]:
        if query.lower().startswith("/agent-card"):
            return {
                "mode": "agent_card",
                "deal_found": False,
                "agent_card": self.direct_agent.agent_card(),
            }
        discover_match = re.search(
            r"^/(?:discover-agent|a2a\s+discover)\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if discover_match:
            return self.direct_agent.discover_agent_card(discover_match.group(1))
        status_match = re.search(
            r"^/direct\s+status\s+(\S+)",
            query,
            flags=re.IGNORECASE,
        )
        if status_match:
            return self.direct_agent.session_status(status_match.group(1))
        message = re.sub(r"^/(?:direct|a2a)(?:\s+message)?\b", "", query, flags=re.IGNORECASE).strip()
        requester = self._extract_key_value(query, "agent") or self._extract_key_value(query, "from")
        endpoint = self._extract_key_value(query, "endpoint")
        wallet = self._extract_wallet(query)
        for key in ("agent", "from", "endpoint", "wallet", "budget"):
            value = self._extract_key_value(query, key)
            if value:
                message = message.replace(f"{key}={value}", "")
        if wallet:
            message = message.replace(wallet, "")
        message = " ".join(message.split())
        return self.direct_agent.handle_direct_message(
            {
                "requester_agent": requester,
                "requester_endpoint": endpoint,
                "requester_wallet": wallet,
                "message": message,
                "budget_native": self._extract_budget_native(query),
            }
        )

    def _extract_key_value(self, query: str, key: str) -> str:
        match = re.search(
            rf"\b{re.escape(key)}=([^\s]+)",
            query,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    def _extract_key_values(self, query: str, key: str) -> List[str]:
        return [
            match.group(1).strip()
            for match in re.finditer(
                rf"\b{re.escape(key)}=([^\s]+)",
                query,
                flags=re.IGNORECASE,
            )
            if match.group(1).strip()
        ]

    def _extract_wallet(self, query: str) -> str:
        explicit = (
            self._extract_key_value(query, "wallet")
            or self._extract_key_value(query, "payer_wallet")
            or self._extract_key_value(query, "from")
        )
        if re.fullmatch(r"0x[a-fA-F0-9]{40}", explicit or ""):
            return explicit
        match = re.search(r"\b0x[a-fA-F0-9]{40}\b", query)
        return match.group(0) if match else ""

    def _extract_budget_native(self, query: str) -> Optional[float]:
        match = re.search(
            r"\b(?:budget|amount|pay)=?(\d+(?:[.,]\d+)?)",
            query,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        return float(match.group(1).replace(",", "."))

    def _extract_int_key_value(self, query: str, key: str) -> Optional[int]:
        value = self._extract_key_value(query, key)
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _extract_bool_key_value(self, query: str, key: str) -> bool:
        value = self._extract_key_value(query, key).strip().lower()
        return value in {"1", "true", "yes", "on", "send"}

    def _first_url(self, text: str) -> str:
        match = re.search(r"https?://[^\s)>\]\"']+", text or "")
        return match.group(0) if match else ""

    def _extract_explicit_profile(self, lowered: str) -> str:
        profile_markers = (" profile:", " profile=", " for profile ", " für profil ", " fuer profil ")
        if any(marker in lowered for marker in profile_markers):
            return self.infra._extract_profile(lowered)
        return "ai_first"

    def _parse_travel_request(self, query: str) -> Optional[TravelRequest]:
        origin, destination = self._extract_route(query)
        if not origin or not destination:
            return None

        today = date.today()
        departure_date = self._extract_departure_date(query, today)
        nights = self._extract_nights(query)
        return_date = self._extract_return_date(query, departure_date, nights)
        adults = self._extract_adults(query)
        max_total_price = self._extract_budget(query)
        include_hotel = not self._mentions_flight_only(query)

        if return_date <= departure_date:
            return_date = departure_date + timedelta(days=max(1, nights))

        return TravelRequest(
            raw_query=query,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            nights=max(1, nights),
            adults=adults,
            max_total_price=max_total_price,
            include_hotel=include_hotel,
        )

    def _extract_route(self, query: str) -> tuple[Optional[str], Optional[str]]:
        patterns = [
            r"from\s+(.+?)\s+to\s+(.+?)(?:\s+on|\s+for|\s+under|\s+next|\s+this|\s+\d{4}-\d{2}-\d{2}|\s*$)",
            r"von\s+(.+?)\s+nach\s+(.+?)(?:\s+am|\s+ab|\s+fuer|\s+für|\s+unter|\s+naechste|\s+n[aä]chste|\s+\d{4}-\d{2}-\d{2}|\s*$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, query, flags=re.IGNORECASE)
            if match:
                origin = match.group(1).strip(" ,.-")
                destination = match.group(2).strip(" ,.-")
                return origin, destination
        return None, None

    def _extract_departure_date(self, query: str, today: date) -> date:
        iso_dates = re.findall(r"\d{4}-\d{2}-\d{2}", query)
        if iso_dates:
            return datetime.strptime(iso_dates[0], "%Y-%m-%d").date()

        lowered = query.lower()
        if "tomorrow" in lowered or "morgen" in lowered:
            return today + timedelta(days=1)
        if "this weekend" in lowered or "dieses wochenende" in lowered:
            days_until_saturday = (5 - today.weekday()) % 7
            return today + timedelta(days=days_until_saturday or 7)
        if "next week" in lowered or "naechste woche" in lowered or "nächste woche" in lowered:
            return today + timedelta(days=7)
        if "next month" in lowered or "naechsten monat" in lowered or "nächsten monat" in lowered:
            month = 1 if today.month == 12 else today.month + 1
            year = today.year + 1 if today.month == 12 else today.year
            return date(year, month, 1)
        return today + timedelta(days=30)

    def _extract_return_date(
        self, query: str, departure_date: date, nights: int
    ) -> date:
        iso_dates = re.findall(r"\d{4}-\d{2}-\d{2}", query)
        if len(iso_dates) >= 2:
            return datetime.strptime(iso_dates[1], "%Y-%m-%d").date()
        return departure_date + timedelta(days=max(1, nights))

    def _extract_nights(self, query: str) -> int:
        match = re.search(
            r"(\d+)\s*(?:night|nights|nacht|naechte|nächte)",
            query,
            flags=re.IGNORECASE,
        )
        if not match:
            return 3
        return max(1, int(match.group(1)))

    def _extract_adults(self, query: str) -> int:
        match = re.search(
            r"(\d+)\s*(?:adult|adults|traveler|travellers|person|persons|personen)",
            query,
            flags=re.IGNORECASE,
        )
        if not match:
            return 1
        return max(1, int(match.group(1)))

    def _extract_budget(self, query: str) -> Optional[float]:
        patterns = [
            r"(?:under|unter|max|budget)\s*(?:eur|euro|€)?\s*(\d+(?:[.,]\d+)?)",
            r"(\d+(?:[.,]\d+)?)\s*(?:eur|euro|€)\s*(?:max|budget)?",
        ]
        for pattern in patterns:
            match = re.search(pattern, query, flags=re.IGNORECASE)
            if match:
                return float(match.group(1).replace(",", "."))
        return None

    def _mentions_flight_only(self, query: str) -> bool:
        lowered = query.lower()
        return "flight only" in lowered or "nur flug" in lowered

    def _review_scouting_with_llm(
        self,
        parsed: TravelRequest,
        opportunities: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        request_summary = {
            "origin": parsed.origin,
            "destination": parsed.destination,
            "departure_date": _iso(parsed.departure_date),
            "return_date": _iso(parsed.return_date),
            "nights": parsed.nights,
            "adults": parsed.adults,
            "include_hotel": parsed.include_hotel,
            "max_total_price": parsed.max_total_price,
        }
        return self.analyst.review_scouting_opportunities(
            request_summary,
            opportunities[:5],
        )

    def _pick_selected_opportunity(
        self,
        opportunities: List[Dict[str, Any]],
        llm_review: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        heuristic_top = opportunities[0]
        if llm_review:
            selected_id = llm_review.get("selected_opportunity_id")
            for item in opportunities:
                if item.get("opportunity_id") == selected_id:
                    if item["value_score"] >= heuristic_top["value_score"] * 0.9:
                        item["selection_source"] = "llm"
                        return item
                    break
        selected = heuristic_top
        selected["selection_source"] = "heuristic"
        return selected

    def _build_search_analysis(
        self,
        selected: Dict[str, Any],
        total_opportunities: int,
        parsed: TravelRequest,
        tx_hash: str,
        llm_review: Optional[Dict[str, Any]],
    ) -> str:
        parts = [
            (
                f"Scouted {total_opportunities} open-data destination angle(s) for "
                f"{parsed.origin} toward {parsed.destination}."
            ),
            (
                f"{selected['candidate_name']} scores {selected['arbitrage_score']:.2f}% "
                f"above the scout-set baseline on the hidden-value index."
            ),
            (
                f"Heuristic value score is {selected['value_score']:.2f}, with "
                f"{selected['accommodation_count']} stays, {selected['budget_food_count']} food spots, "
                f"{selected['transit_count']} transit nodes and {selected['airport_count']} nearby airport(s)."
            ),
        ]
        if parsed.max_total_price is not None:
            parts.append(
                f"The scout considered a target budget ceiling of {parsed.max_total_price:.2f} EUR, "
                "but this mode ranks hidden value rather than live prices."
            )
        if llm_review:
            if selected.get("selection_source") == "llm":
                parts.append(
                    f"{llm_review.get('model', 'LLM')} selected this place as the strongest travel arbitrage angle."
                )
                if llm_review.get("summary"):
                    parts.append(llm_review["summary"])
                if llm_review.get("arbitrage_angle"):
                    parts.append(f"Arbitrage angle: {llm_review['arbitrage_angle']}")
                if llm_review.get("risks"):
                    parts.append(f"Risks: {', '.join(llm_review['risks'])}.")
                if llm_review.get("confidence"):
                    parts.append(f"Confidence: {llm_review['confidence']}.")
            else:
                parts.append(
                    f"{llm_review.get('model', 'LLM')} reviewed the scout set, but the heuristic kept the stronger lead."
                )
        else:
            parts.append(
                "LLM travel review was unavailable, so the best place was chosen by the local value heuristic."
            )
        if tx_hash:
            parts.append("The selected scout lead was also recorded on-chain.")
        else:
            parts.append("On-chain recording is currently disabled.")
        return " ".join(parts)

    def _maybe_record_on_chain(self, selected: Dict[str, Any]) -> str:
        if os.getenv("AUTO_RECORD_ARBITRAGE", "false").lower() != "true":
            return ""

        try:
            from client import ArbiterWeb3

            if not ArbiterWeb3.is_configured():
                return ""
            client = ArbiterWeb3()
            return client.record_arbitrage(selected)
        except Exception:
            return ""


NomadAgent = ArbiterAgent
