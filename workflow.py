import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from infra_scout import InfrastructureScout
from mission import MISSION_STATEMENT
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
        self.self_improvement = SelfImprovementEngine(infra=self.infra)

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

        if self._is_self_improvement_request(normalized_query):
            return self._handle_self_improvement_request(normalized_query)

        infra_request = self.infra.parse_request(normalized_query)
        if infra_request:
            return self._handle_infra_request(infra_request)

        if self._parse_travel_request(normalized_query):
            return {
                "mode": "deprecated",
                "deal_found": False,
                "message": (
                    "Nomad now focuses fully on AI infrastructure for agents. "
                    "Travel scouting has been retired. Try /best, /self, /scout compute or /scout wallets."
                ),
            }

        return {
            "mode": "infra_help",
            "deal_found": False,
            "message": (
                f"{MISSION_STATEMENT} "
                "Nomad scouts the best free infrastructure for AI agents and uses that stack on itself. "
                "Try /best, /self, /scout compute, /scout protocols or /scout wallets."
            ),
        }

    def _handle_infra_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        kind = request.get("kind")
        profile = request.get("profile") or "ai_first"
        if kind == "self_audit":
            return self.infra.self_audit(profile_id=profile)
        if kind == "compute_audit":
            return self.infra.compute_assessment(profile_id=profile)
        if kind == "activation_request":
            return self.infra.activation_request(
                category=request.get("category") or "compute",
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

    def _handle_self_improvement_request(self, query: str) -> Dict[str, Any]:
        lowered = query.lower()
        profile = self.infra._extract_profile(lowered)
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
