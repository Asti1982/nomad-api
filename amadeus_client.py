import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv


load_dotenv()


PLACEHOLDER_VALUES = {
    "",
    "your_key",
    "your_secret",
    "your_api_key_here",
    "your_api_secret_here",
}


class AmadeusError(RuntimeError):
    pass


@dataclass
class ResolvedLocation:
    keyword: str
    code: str
    name: str
    sub_type: str


class AmadeusClient:
    def __init__(self) -> None:
        self.api_key = (os.getenv("AMADEUS_API_KEY") or "").strip()
        self.api_secret = (os.getenv("AMADEUS_API_SECRET") or "").strip()
        self.base_url = (
            os.getenv("AMADEUS_API_BASE") or "https://test.api.amadeus.com"
        ).rstrip("/")
        self.session = requests.Session()
        self._access_token = ""
        self._token_expires_at = 0.0

    def is_configured(self) -> bool:
        return (
            self.api_key.lower() not in PLACEHOLDER_VALUES
            and self.api_secret.lower() not in PLACEHOLDER_VALUES
        )

    def resolve_location(self, keyword: str) -> ResolvedLocation:
        cleaned = (keyword or "").strip()
        if len(cleaned) == 3 and cleaned.isalpha():
            code = cleaned.upper()
            return ResolvedLocation(
                keyword=cleaned,
                code=code,
                name=code,
                sub_type="AIRPORT_OR_CITY",
            )

        payload = self._get(
            "/v1/reference-data/locations",
            params={
                "subType": "CITY,AIRPORT",
                "keyword": cleaned,
                "view": "LIGHT",
                "page[limit]": 5,
            },
        )
        matches = payload.get("data") or []
        if not matches:
            raise AmadeusError(f"Could not resolve location '{cleaned}'.")

        preferred = self._pick_best_location(cleaned, matches)
        return ResolvedLocation(
            keyword=cleaned,
            code=preferred.get("iataCode", "").upper(),
            name=preferred.get("name") or cleaned,
            sub_type=preferred.get("subType") or "UNKNOWN",
        )

    def search_flights(
        self,
        origin_keyword: str,
        destination_keyword: str,
        departure_date: str,
        return_date: str,
        adults: int = 1,
        max_results: int = 6,
        currency: str = "EUR",
    ) -> Dict[str, Any]:
        origin = self.resolve_location(origin_keyword)
        destination = self.resolve_location(destination_keyword)

        payload = self._get(
            "/v2/shopping/flight-offers",
            params={
                "originLocationCode": origin.code,
                "destinationLocationCode": destination.code,
                "departureDate": departure_date,
                "returnDate": return_date,
                "adults": adults,
                "currencyCode": currency,
                "max": max_results,
            },
        )
        offers = payload.get("data") or []

        parsed_offers: List[Dict[str, Any]] = []
        for offer in offers:
            itineraries = offer.get("itineraries") or []
            outbound = itineraries[0] if itineraries else {}
            inbound = itineraries[1] if len(itineraries) > 1 else {}
            outbound_segments = outbound.get("segments") or []
            inbound_segments = inbound.get("segments") or []
            if not outbound_segments:
                continue

            first_outbound = outbound_segments[0]
            last_outbound = outbound_segments[-1]
            carriers = offer.get("validatingAirlineCodes") or [
                segment.get("carrierCode")
                for segment in outbound_segments
                if segment.get("carrierCode")
            ]
            parsed_offers.append(
                {
                    "id": offer.get("id"),
                    "origin_code": origin.code,
                    "destination_code": destination.code,
                    "origin_name": origin.name,
                    "destination_name": destination.name,
                    "route": f"{origin.name} -> {destination.name}",
                    "departure_at": first_outbound.get("departure", {}).get("at"),
                    "arrival_at": last_outbound.get("arrival", {}).get("at"),
                    "return_departure_at": (
                        inbound_segments[0].get("departure", {}).get("at")
                        if inbound_segments
                        else ""
                    ),
                    "return_arrival_at": (
                        inbound_segments[-1].get("arrival", {}).get("at")
                        if inbound_segments
                        else ""
                    ),
                    "stops_outbound": max(0, len(outbound_segments) - 1),
                    "stops_return": max(0, len(inbound_segments) - 1),
                    "carrier_codes": carriers,
                    "bookable_seats": offer.get("numberOfBookableSeats"),
                    "currency": offer.get("price", {}).get("currency", currency),
                    "total_price": self._to_float(
                        offer.get("price", {}).get("grandTotal")
                        or offer.get("price", {}).get("total")
                    ),
                    "raw": offer,
                }
            )

        parsed_offers.sort(key=lambda item: item["total_price"])
        return {
            "origin": origin,
            "destination": destination,
            "offers": parsed_offers,
        }

    def search_hotels(
        self,
        destination_keyword: str,
        check_in_date: str,
        check_out_date: str,
        adults: int = 1,
        max_hotels: int = 8,
        currency: str = "EUR",
    ) -> Dict[str, Any]:
        destination = self.resolve_location(destination_keyword)
        hotel_list_payload = self._get(
            "/v1/reference-data/locations/hotels/by-city",
            params={"cityCode": destination.code},
        )
        hotels = hotel_list_payload.get("data") or []
        hotel_ids = [
            hotel.get("hotelId")
            for hotel in hotels
            if hotel.get("hotelId")
        ][:max_hotels]

        if not hotel_ids:
            return {"destination": destination, "offers": []}

        offers_payload = self._get(
            "/v3/shopping/hotel-offers",
            params={
                "hotelIds": ",".join(hotel_ids),
                "adults": adults,
                "checkInDate": check_in_date,
                "checkOutDate": check_out_date,
                "roomQuantity": 1,
                "currency": currency,
                "bestRateOnly": "true",
            },
        )
        offer_data = offers_payload.get("data") or []

        parsed_offers: List[Dict[str, Any]] = []
        for hotel in offer_data:
            hotel_info = hotel.get("hotel") or {}
            offers = hotel.get("offers") or []
            if not offers:
                continue
            best_offer = offers[0]
            price = best_offer.get("price") or {}
            parsed_offers.append(
                {
                    "hotel_id": hotel_info.get("hotelId"),
                    "hotel_name": hotel_info.get("name") or "Unknown hotel",
                    "city_code": destination.code,
                    "destination_name": destination.name,
                    "check_in_date": check_in_date,
                    "check_out_date": check_out_date,
                    "currency": price.get("currency", currency),
                    "total_price": self._to_float(price.get("total")),
                    "room_description": (
                        best_offer.get("room", {})
                        .get("description", {})
                        .get("text", "")
                    ),
                    "board_type": best_offer.get("boardType", ""),
                    "raw": hotel,
                }
            )

        parsed_offers.sort(key=lambda item: item["total_price"])
        return {
            "destination": destination,
            "offers": parsed_offers,
        }

    def _pick_best_location(
        self, keyword: str, matches: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        keyword_lower = keyword.lower()
        scored: List[tuple[int, Dict[str, Any]]] = []
        for match in matches:
            name = (match.get("name") or "").lower()
            code = (match.get("iataCode") or "").lower()
            sub_type = match.get("subType") or ""
            score = 0
            if name == keyword_lower:
                score += 4
            elif keyword_lower in name:
                score += 2
            if code == keyword_lower:
                score += 3
            if sub_type == "CITY":
                score += 1
            scored.append((score, match))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        if not self.is_configured():
            raise AmadeusError(
                "AMADEUS_API_KEY and AMADEUS_API_SECRET are not configured."
            )

        response = self.session.post(
            f"{self.base_url}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.api_secret,
            },
            timeout=20,
        )
        if not response.ok:
            raise AmadeusError(
                f"Amadeus auth failed with status {response.status_code}: "
                f"{response.text[:300]}"
            )

        payload = response.json()
        self._access_token = payload.get("access_token", "")
        expires_in = int(payload.get("expires_in", 0))
        self._token_expires_at = time.time() + max(60, expires_in - 60)
        if not self._access_token:
            raise AmadeusError("Amadeus auth response did not include an access token.")
        return self._access_token

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        token = self._get_access_token()
        response = self.session.get(
            f"{self.base_url}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if response.status_code == 401:
            self._access_token = ""
            self._token_expires_at = 0.0
            token = self._get_access_token()
            response = self.session.get(
                f"{self.base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )

        if not response.ok:
            raise AmadeusError(
                f"Amadeus request failed for {path} with status {response.status_code}: "
                f"{response.text[:300]}"
            )
        return response.json()

    def _to_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
