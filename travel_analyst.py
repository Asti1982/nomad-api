import json
import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


load_dotenv()


class TravelAnalyst:
    def __init__(self) -> None:
        self.base_url = (os.getenv("OLLAMA_API_BASE") or "http://127.0.0.1:11434").rstrip("/")
        self.preferred_model = (os.getenv("OLLAMA_MODEL") or "").strip()
        self.session = requests.Session()
        self._resolved_model: Optional[str] = None

    def is_available(self) -> bool:
        return bool(self.resolve_model())

    def resolve_model(self) -> str:
        if self._resolved_model:
            return self._resolved_model

        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return ""

        models = [
            (model.get("name") or "").strip()
            for model in payload.get("models", [])
            if (model.get("name") or "").strip()
        ]
        if not models:
            return ""

        if self.preferred_model and self.preferred_model in models:
            self._resolved_model = self.preferred_model
            return self._resolved_model

        preferred_fallbacks = [
            "llama3.2:1b",
            "llama3",
            "qwen2.5:0.5b-instruct",
        ]
        for candidate in preferred_fallbacks:
            if candidate in models:
                self._resolved_model = candidate
                return self._resolved_model

        self._resolved_model = models[0]
        return self._resolved_model

    def review_opportunities(
        self,
        request_summary: Dict[str, Any],
        opportunities: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        model = self.resolve_model()
        if not model or not opportunities:
            return None

        compact_opportunities = []
        for item in opportunities[:5]:
            compact_opportunities.append(
                {
                    "opportunity_id": item.get("opportunity_id"),
                    "route": item.get("route"),
                    "total_price": item.get("total_price"),
                    "flight_price": item.get("flight_price"),
                    "hotel_price": item.get("hotel_price"),
                    "currency": item.get("currency"),
                    "stops_outbound": item.get("stops_outbound"),
                    "stops_return": item.get("stops_return"),
                    "bookable_seats": item.get("bookable_seats"),
                    "arbitrage_score": item.get("arbitrage_score"),
                    "value_score": item.get("value_score"),
                    "within_budget": item.get("within_budget"),
                    "hotel_name": item.get("hotel_name"),
                }
            )

        prompt = (
            "You are a travel arbitrage analyst.\n"
            "Pick the best opportunity from the provided live search results.\n"
            "Optimize for mispricing and value, not just absolute cheapest price.\n"
            "Consider total price, price gap vs median, stop count, seat availability, "
            "and whether the option stays within the user's budget.\n"
            "Return strict JSON with keys: "
            "selected_opportunity_id, summary, arbitrage_angle, risks, confidence.\n\n"
            f"Request:\n{json.dumps(request_summary, ensure_ascii=True)}\n\n"
            f"Opportunities:\n{json.dumps(compact_opportunities, ensure_ascii=True)}"
        )

        try:
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.2,
                    },
                },
                timeout=45,
            )
            response.raise_for_status()
            payload = response.json()
            content = (payload.get("response") or "").strip()
            if not content:
                return None
            parsed = json.loads(content)
        except Exception:
            return None

        selected_id = str(parsed.get("selected_opportunity_id") or "").strip()
        if not selected_id:
            return None

        risks = parsed.get("risks")
        if isinstance(risks, str):
            risks = [risks]
        if not isinstance(risks, list):
            risks = []

        return {
            "model": model,
            "selected_opportunity_id": selected_id,
            "summary": str(parsed.get("summary") or "").strip(),
            "arbitrage_angle": str(parsed.get("arbitrage_angle") or "").strip(),
            "risks": [str(item).strip() for item in risks if str(item).strip()],
            "confidence": str(parsed.get("confidence") or "").strip(),
        }

    def review_scouting_opportunities(
        self,
        request_summary: Dict[str, Any],
        opportunities: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        model = self.resolve_model()
        if not model or not opportunities:
            return None

        compact_opportunities = []
        for item in opportunities[:5]:
            compact_opportunities.append(
                {
                    "opportunity_id": item.get("opportunity_id"),
                    "candidate_name": item.get("candidate_name"),
                    "anchor_destination": item.get("anchor_destination"),
                    "distance_from_target_km": item.get("distance_from_target_km"),
                    "distance_from_origin_km": item.get("distance_from_origin_km"),
                    "accommodation_count": item.get("accommodation_count"),
                    "hostel_count": item.get("hostel_count"),
                    "budget_food_count": item.get("budget_food_count"),
                    "transit_count": item.get("transit_count"),
                    "attraction_count": item.get("attraction_count"),
                    "airport_count": item.get("airport_count"),
                    "population": item.get("population"),
                    "arbitrage_score": item.get("arbitrage_score"),
                    "value_score": item.get("value_score"),
                    "scout_summary": item.get("scout_summary"),
                }
            )

        prompt = (
            "You are a travel arbitrage scout working from open map data.\n"
            "Pick the strongest hidden-value destination from the candidate list.\n"
            "You are not choosing by ticket price. You are choosing by the best mix of "
            "accommodation supply, hostel depth, food density, transport access, airport access, "
            "tourism pressure, and distance from the user's requested destination.\n"
            "Prefer places that look underpriced or undercrowded relative to the anchor destination.\n"
            "Return strict JSON with keys: "
            "selected_opportunity_id, summary, arbitrage_angle, risks, confidence.\n\n"
            f"Request:\n{json.dumps(request_summary, ensure_ascii=True)}\n\n"
            f"Candidates:\n{json.dumps(compact_opportunities, ensure_ascii=True)}"
        )

        try:
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2},
                },
                timeout=45,
            )
            response.raise_for_status()
            payload = response.json()
            content = (payload.get("response") or "").strip()
            if not content:
                return None
            parsed = json.loads(content)
        except Exception:
            return None

        selected_id = str(parsed.get("selected_opportunity_id") or "").strip()
        if not selected_id:
            return None

        risks = parsed.get("risks")
        if isinstance(risks, str):
            risks = [risks]
        if not isinstance(risks, list):
            risks = []

        return {
            "model": model,
            "selected_opportunity_id": selected_id,
            "summary": str(parsed.get("summary") or "").strip(),
            "arbitrage_angle": str(parsed.get("arbitrage_angle") or "").strip(),
            "risks": [str(item).strip() for item in risks if str(item).strip()],
            "confidence": str(parsed.get("confidence") or "").strip(),
        }
