import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


load_dotenv()


class ScoutError(RuntimeError):
    pass


@dataclass
class PlaceCandidate:
    name: str
    display_name: str
    lat: float
    lon: float
    country_code: str
    place_type: str
    population: int
    distance_from_anchor_km: float = 0.0


class OpenTravelScout:
    def __init__(self) -> None:
        self.nominatim_url = (
            os.getenv("NOMINATIM_API_BASE") or "https://nominatim.openstreetmap.org"
        ).rstrip("/")
        raw_overpass = (
            os.getenv("OVERPASS_API_BASE")
            or (
                "https://overpass.openstreetmap.fr/api/interpreter,"
                "https://overpass-api.de/api/interpreter"
            )
        )
        self.overpass_urls = [
            url.strip().rstrip("/")
            for url in raw_overpass.split(",")
            if url.strip()
        ]
        self.user_agent = (
            os.getenv("NOMAD_HTTP_USER_AGENT")
            or "NomadArbiter/0.1 (open travel scout; local dev)"
        ).strip()
        self.contact_email = (os.getenv("NOMAD_HTTP_EMAIL") or "").strip()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            }
        )
        self._last_nominatim_call = 0.0

    def scout_route(
        self,
        origin_keyword: str,
        destination_keyword: str,
        include_hotel: bool,
        nights: int,
        adults: int,
        max_total_price: Optional[float],
    ) -> Dict[str, Any]:
        origin = self._geocode(origin_keyword)
        anchor = self._geocode(destination_keyword)
        nearby_candidates = self._find_nearby_places(anchor)

        candidates = [anchor]
        seen_names = {anchor.name.lower()}
        for candidate in nearby_candidates:
            lowered = candidate.name.lower()
            if lowered in seen_names:
                continue
            seen_names.add(lowered)
            candidates.append(candidate)
            if len(candidates) >= 4:
                break

        opportunities: List[Dict[str, Any]] = []
        for candidate in candidates:
            metrics = self._collect_city_metrics(candidate, include_hotel=include_hotel)
            opportunities.append(
                {
                    "route": f"{origin.name} -> {candidate.name}",
                    "provider": "OpenStreetMap scout",
                    "candidate_name": candidate.name,
                    "candidate_display_name": candidate.display_name,
                    "country_code": candidate.country_code.upper(),
                    "anchor_destination": anchor.name,
                    "distance_from_target_km": round(candidate.distance_from_anchor_km, 1),
                    "distance_from_origin_km": round(
                        self._haversine_km(
                            origin.lat,
                            origin.lon,
                            candidate.lat,
                            candidate.lon,
                        ),
                        1,
                    ),
                    "population": candidate.population,
                    "accommodation_count": metrics["accommodation_count"],
                    "hostel_count": metrics["hostel_count"],
                    "budget_food_count": metrics["budget_food_count"],
                    "transit_count": metrics["transit_count"],
                    "attraction_count": metrics["attraction_count"],
                    "airport_count": metrics["airport_count"],
                    "max_total_price": max_total_price,
                    "include_hotel": include_hotel,
                    "nights": nights,
                    "adults": adults,
                }
            )

        ranked = self._rank_opportunities(
            opportunities,
            include_hotel=include_hotel,
            nights=nights,
            adults=adults,
            max_total_price=max_total_price,
        )
        return {
            "origin": origin,
            "anchor": anchor,
            "opportunities": ranked,
        }

    def _geocode(self, keyword: str) -> PlaceCandidate:
        cleaned = (keyword or "").strip()
        if not cleaned:
            raise ScoutError("Could not geocode an empty location.")

        self._respect_nominatim_rate_limit()
        params = {
            "q": cleaned,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
            "extratags": 1,
        }
        if self.contact_email:
            params["email"] = self.contact_email

        response = self.session.get(
            f"{self.nominatim_url}/search",
            params=params,
            timeout=20,
        )
        if not response.ok:
            raise ScoutError(
                f"Nominatim geocoding failed with status {response.status_code}."
            )

        payload = response.json()
        if not payload:
            raise ScoutError(f"Could not resolve location '{cleaned}'.")

        top = payload[0]
        address = top.get("address") or {}
        extratags = top.get("extratags") or {}
        name = (
            top.get("name")
            or address.get("city")
            or address.get("town")
            or address.get("village")
            or cleaned
        )

        return PlaceCandidate(
            name=name,
            display_name=top.get("display_name") or name,
            lat=float(top["lat"]),
            lon=float(top["lon"]),
            country_code=(address.get("country_code") or "").lower(),
            place_type=top.get("type") or "",
            population=self._parse_population(extratags.get("population")),
        )

    def _find_nearby_places(
        self,
        anchor: PlaceCandidate,
        radius_m: int = 90000,
    ) -> List[PlaceCandidate]:
        query = f"""
[out:json][timeout:25];
(
  node["place"~"city|town"](around:{radius_m},{anchor.lat},{anchor.lon});
  way["place"~"city|town"](around:{radius_m},{anchor.lat},{anchor.lon});
  relation["place"~"city|town"](around:{radius_m},{anchor.lat},{anchor.lon});
);
out tags center;
"""
        payload = self._overpass(query)
        candidates: List[PlaceCandidate] = []
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            name = (
                tags.get("name:en")
                or tags.get("name")
                or ""
            ).strip()
            if not name:
                continue

            lat = element.get("lat")
            lon = element.get("lon")
            if lat is None or lon is None:
                center = element.get("center") or {}
                lat = center.get("lat")
                lon = center.get("lon")
            if lat is None or lon is None:
                continue

            distance = self._haversine_km(anchor.lat, anchor.lon, float(lat), float(lon))
            if distance < 15 or distance > 140:
                continue

            population = self._parse_population(tags.get("population"))
            candidates.append(
                PlaceCandidate(
                    name=name,
                    display_name=name,
                    lat=float(lat),
                    lon=float(lon),
                    country_code="",
                    place_type=tags.get("place") or "",
                    population=population,
                    distance_from_anchor_km=distance,
                )
            )

        candidates.sort(
            key=lambda item: (
                -min(item.population, 500000),
                item.distance_from_anchor_km,
                item.name.lower(),
            )
        )
        if not candidates and radius_m < 140000:
            return self._find_nearby_places(anchor, radius_m=140000)
        return candidates

    def _collect_city_metrics(
        self,
        candidate: PlaceCandidate,
        include_hotel: bool,
    ) -> Dict[str, int]:
        urban_radius = 4500 if include_hotel else 3500
        airport_radius = 50000
        query = f"""
[out:json][timeout:30];
(
  node["tourism"~"hotel|hostel|guest_house|apartment"](around:{urban_radius},{candidate.lat},{candidate.lon});
  way["tourism"~"hotel|hostel|guest_house|apartment"](around:{urban_radius},{candidate.lat},{candidate.lon});
  relation["tourism"~"hotel|hostel|guest_house|apartment"](around:{urban_radius},{candidate.lat},{candidate.lon});

  node["amenity"~"restaurant|cafe|fast_food|marketplace|food_court"](around:{urban_radius},{candidate.lat},{candidate.lon});
  way["amenity"~"restaurant|cafe|fast_food|marketplace|food_court"](around:{urban_radius},{candidate.lat},{candidate.lon});
  relation["amenity"~"restaurant|cafe|fast_food|marketplace|food_court"](around:{urban_radius},{candidate.lat},{candidate.lon});

  node["tourism"~"attraction|museum|gallery|viewpoint|theme_park"](around:{urban_radius},{candidate.lat},{candidate.lon});
  way["tourism"~"attraction|museum|gallery|viewpoint|theme_park"](around:{urban_radius},{candidate.lat},{candidate.lon});
  relation["tourism"~"attraction|museum|gallery|viewpoint|theme_park"](around:{urban_radius},{candidate.lat},{candidate.lon});

  node["railway"~"station|tram_stop|halt"](around:{urban_radius},{candidate.lat},{candidate.lon});
  way["railway"~"station|tram_stop|halt"](around:{urban_radius},{candidate.lat},{candidate.lon});
  relation["railway"~"station|tram_stop|halt"](around:{urban_radius},{candidate.lat},{candidate.lon});
  node["public_transport"](around:{urban_radius},{candidate.lat},{candidate.lon});
  way["public_transport"](around:{urban_radius},{candidate.lat},{candidate.lon});
  relation["public_transport"](around:{urban_radius},{candidate.lat},{candidate.lon});
  node["amenity"="bus_station"](around:{urban_radius},{candidate.lat},{candidate.lon});
  way["amenity"="bus_station"](around:{urban_radius},{candidate.lat},{candidate.lon});
  relation["amenity"="bus_station"](around:{urban_radius},{candidate.lat},{candidate.lon});

  node["aeroway"="aerodrome"](around:{airport_radius},{candidate.lat},{candidate.lon});
  way["aeroway"="aerodrome"](around:{airport_radius},{candidate.lat},{candidate.lon});
  relation["aeroway"="aerodrome"](around:{airport_radius},{candidate.lat},{candidate.lon});
);
out tags center;
"""
        payload = self._overpass(query)

        counts = {
            "accommodation_count": 0,
            "hostel_count": 0,
            "budget_food_count": 0,
            "transit_count": 0,
            "attraction_count": 0,
            "airport_count": 0,
        }

        seen = set()
        for element in payload.get("elements", []):
            element_key = (element.get("type"), element.get("id"))
            if element_key in seen:
                continue
            seen.add(element_key)

            tags = element.get("tags") or {}
            tourism = tags.get("tourism", "")
            amenity = tags.get("amenity", "")
            railway = tags.get("railway", "")
            aeroway = tags.get("aeroway", "")
            public_transport = tags.get("public_transport", "")

            if tourism in {"hotel", "hostel", "guest_house", "apartment"}:
                counts["accommodation_count"] += 1
                if tourism == "hostel":
                    counts["hostel_count"] += 1
                continue

            if amenity in {"restaurant", "cafe", "fast_food", "marketplace", "food_court"}:
                counts["budget_food_count"] += 1
                continue

            if tourism in {"attraction", "museum", "gallery", "viewpoint", "theme_park"}:
                counts["attraction_count"] += 1
                continue

            if (
                railway in {"station", "tram_stop", "halt"}
                or amenity == "bus_station"
                or public_transport
            ):
                counts["transit_count"] += 1
                continue

            if aeroway == "aerodrome":
                counts["airport_count"] += 1

        return counts

    def _rank_opportunities(
        self,
        opportunities: List[Dict[str, Any]],
        include_hotel: bool,
        nights: int,
        adults: int,
        max_total_price: Optional[float],
    ) -> List[Dict[str, Any]]:
        if not opportunities:
            return []

        raw_scores: List[float] = []
        stay_multiplier = 1.1 + min(max(nights, 1), 7) * 0.15
        group_multiplier = 1.0 + max(adults - 1, 0) * 0.12
        budget_multiplier = 1.25 if max_total_price is not None else 1.0

        for item in opportunities:
            population_base = max(item["population"], 50000)
            scale = population_base / 100000

            accommodation_density = item["accommodation_count"] / scale
            hostel_density = item["hostel_count"] / scale
            food_density = item["budget_food_count"] / scale
            transit_density = item["transit_count"] / scale
            attraction_density = item["attraction_count"] / scale

            accommodation_value = accommodation_density * 1.25 * stay_multiplier
            hostel_bonus = hostel_density * 2.2 * budget_multiplier
            food_value = food_density * 0.35 * group_multiplier
            mobility_value = transit_density * 0.25 + item["airport_count"] * 2.5
            crowd_penalty = max(attraction_density - accommodation_density, 0) * 0.8
            mega_city_penalty = max(population_base - 800000, 0) / 300000
            distance_penalty = max(item["distance_from_target_km"] - 80, 0) * 0.05
            anchor_penalty = 2.5 if item["distance_from_target_km"] < 5 else 0.0
            size_bonus = min(population_base / 100000, 3.0) * 0.3
            hotel_bias = 1.1 if include_hotel else 0.9

            raw_score = (
                accommodation_value * hotel_bias
                + hostel_bonus
                + food_value
                + mobility_value
                + size_bonus
                - crowd_penalty
                - mega_city_penalty
                - distance_penalty
                - anchor_penalty
            )
            raw_scores.append(raw_score)
            item["value_score_raw"] = round(raw_score, 2)

        score_reference = sum(raw_scores) / len(raw_scores) if raw_scores else 0.0
        for index, item in enumerate(opportunities, start=1):
            delta = item["value_score_raw"] - score_reference
            relative = (delta / score_reference * 100) if score_reference else 0.0
            item["arbitrage_score"] = round(relative, 2)
            item["value_score"] = round(item["value_score_raw"], 2)
            item["scout_summary"] = self._build_summary(item)
            item["opportunity_id"] = f"deal-{index}"

        opportunities.sort(
            key=lambda item: (
                -item["value_score"],
                -item["arbitrage_score"],
                item["distance_from_target_km"],
            )
        )
        for index, item in enumerate(opportunities, start=1):
            item["opportunity_id"] = f"deal-{index}"
        return opportunities

    def _build_summary(self, item: Dict[str, Any]) -> str:
        return (
            f"{item['candidate_name']} has {item['accommodation_count']} stays, "
            f"{item['budget_food_count']} food spots, {item['transit_count']} transit nodes "
            f"and sits {item['distance_from_target_km']:.1f} km from {item['anchor_destination']}."
        )

    def _overpass(self, query: str) -> Dict[str, Any]:
        last_error = "Overpass request failed."
        for url in self.overpass_urls:
            try:
                response = self.session.post(
                    url,
                    data=query.encode("utf-8"),
                    timeout=40,
                )
                if response.ok:
                    return response.json()
                last_error = f"Overpass request failed with status {response.status_code}."
                if response.status_code < 500 and response.status_code != 429:
                    break
            except requests.RequestException as exc:
                last_error = f"Overpass request failed: {exc}"
        raise ScoutError(last_error)

    def _respect_nominatim_rate_limit(self) -> None:
        elapsed = time.time() - self._last_nominatim_call
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        self._last_nominatim_call = time.time()

    def _parse_population(self, value: Any) -> int:
        if value is None:
            return 0
        raw = str(value).strip()
        if not raw:
            return 0
        cleaned = "".join(ch for ch in raw if ch.isdigit())
        if not cleaned:
            return 0
        try:
            return int(cleaned)
        except ValueError:
            return 0

    def _haversine_km(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        radius = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius * c
