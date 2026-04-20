import base64
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from agent_contact import AgentContactOutbox


load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_DISCOVERY_SEEDS_PATH = ROOT / "nomad_agent_seed_sources.json"


DEFAULT_DISCOVERY_QUERIES = [
    '"agent-card.json" ".well-known" "https://"',
    '".well-known/agent-card.json" "https://"',
    '"a2a" "agent-card" "https://"',
    '"mcp" "agent" "https://"',
]


class AgentEndpointDiscovery:
    """Find public machine-readable agent endpoints without contacting them."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        outbox: Optional[AgentContactOutbox] = None,
        github_api_base: Optional[str] = None,
    ) -> None:
        load_dotenv()
        self.session = session or requests.Session()
        self.outbox = outbox or AgentContactOutbox()
        self.github_api_base = (
            github_api_base
            or os.getenv("GITHUB_API_BASE")
            or "https://api.github.com"
        ).rstrip("/")
        self.github_token = (
            os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
            or os.getenv("GITHUB_TOKEN")
            or ""
        ).strip()
        self.user_agent = (
            os.getenv("NOMAD_HTTP_USER_AGENT")
            or "Nomad/0.1 public-agent-endpoint-discovery"
        ).strip()
        self.seed_env = os.getenv("NOMAD_AGENT_DISCOVERY_SEEDS", "")
        self.seeds_path = Path(
            os.getenv("NOMAD_AGENT_DISCOVERY_SEEDS_PATH") or DEFAULT_DISCOVERY_SEEDS_PATH
        )
        self.seed_catalog = self._load_seed_catalog()

    def discover(
        self,
        limit: int = 100,
        query: str = "",
        seeds: Optional[Iterable[Any]] = None,
    ) -> Dict[str, Any]:
        cap = max(1, min(int(limit or 100), 100))
        targets: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen: set[str] = set()

        for target in self._targets_from_seeds(seeds=seeds):
            self._append_target(target, targets, seen, cap)
            if len(targets) >= cap:
                break

        queries = self._queries(query)
        if len(targets) < cap:
            for search_query in queries:
                if len(targets) >= cap:
                    break
                try:
                    found = self._search_github_code(
                        query=search_query,
                        limit=max(1, min(100, cap - len(targets))),
                    )
                    for target in found:
                        self._append_target(target, targets, seen, cap)
                        if len(targets) >= cap:
                            break
                except Exception as exc:
                    errors.append(f"{search_query}: {exc}")

        targets = self._rank_targets(targets)[:cap]

        return {
            "mode": "agent_endpoint_discovery",
            "deal_found": False,
            "ok": True,
            "generated_at": datetime.now(UTC).isoformat(),
            "query": (query or "").strip(),
            "search_queries": queries,
            "targets": targets,
            "stats": {
                "limit": cap,
                "targets_found": len(targets),
                "sources": len({target.get("source_url", "") for target in targets if target.get("source_url")}),
                "errors": len(errors),
            },
            "errors": errors[:5],
            "policy": self.policy(),
            "seed_catalog": self.seed_catalog_summary(),
            "analysis": (
                f"Nomad discovered {len(targets[:cap])} public machine-readable agent endpoint(s). "
                "Discovery only reads public search/code surfaces; sending is handled by the campaign outbox."
            ),
        }

    def policy(self) -> Dict[str, Any]:
        return {
            "mode": "agent_endpoint_discovery",
            "public_reading_allowed": True,
            "contact_without_human_approval": "public machine-readable agent/API/MCP endpoints only",
            "blocked": [
                "human DMs",
                "email addresses",
                "comment forms",
                "private or login-gated communities",
                "CAPTCHA or paywalled surfaces",
            ],
            "sources": [
                "explicit seed URLs",
                "nomad_agent_seed_sources.json",
                "NOMAD_AGENT_DISCOVERY_SEEDS",
                "public GitHub code search when available",
            ],
        }

    def seed_catalog_summary(self) -> Dict[str, Any]:
        direct_cards = [
            item
            for item in (self.seed_catalog.get("agent_card_seeds") or [])
            if isinstance(item, dict)
        ]
        registry_hubs = [
            item
            for item in (self.seed_catalog.get("registry_hubs") or [])
            if isinstance(item, dict)
        ]
        return {
            "path": str(self.seeds_path),
            "seed_urls": len(self.seed_catalog.get("seed_urls") or []),
            "agent_card_seeds": len(direct_cards),
            "registry_hubs": len(registry_hubs),
        }

    def _queries(self, query: str) -> List[str]:
        cleaned = (query or "").strip()
        if cleaned:
            if "https://" not in cleaned and "agent" not in cleaned.lower():
                return [f'{cleaned} "agent" "https://"']
            return [cleaned]
        return list(DEFAULT_DISCOVERY_QUERIES)

    def _targets_from_seeds(self, seeds: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
        raw_seeds: List[Any] = []
        if isinstance(seeds, str):
            raw_seeds.append(seeds)
        else:
            raw_seeds.extend(list(seeds or []))
        raw_seeds.extend(self.seed_catalog.get("seed_urls") or [])
        raw_seeds.extend(self.seed_catalog.get("agent_card_seeds") or [])
        raw_seeds.extend(self.seed_catalog.get("registry_hubs") or [])
        raw_seeds.extend(self._split_seed_env(self.seed_env))
        targets: List[Dict[str, Any]] = []
        for raw in raw_seeds:
            seed = self._seed_to_text(raw)
            if not seed:
                continue
            for target in self._extract_targets_from_seed_content(seed):
                targets.append(target)
            for endpoint in self._candidate_endpoints_from_seed(seed):
                target = self._target_from_url(
                    endpoint_url=endpoint,
                    source_url=seed,
                    name=self._name_from_url(seed),
                    discovery_method="seed",
                )
                if target:
                    targets.append(target)
        return targets

    def _extract_targets_from_seed_content(self, seed: str) -> List[Dict[str, Any]]:
        seed = self._clean_url(seed)
        parsed = urlparse(seed)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return []
        allowed, reason = self.outbox._is_allowed_agent_endpoint(seed)
        if not allowed and reason in {
            "placeholder_host_blocked",
            "local_or_private_host_blocked",
            "human_facing_host_blocked",
            "plain_http_only_allowed_for_localhost",
        }:
            return []
        payload = self._fetch_seed_payload(seed)
        if payload is None:
            return []
        return self._extract_targets_from_text(
            text=payload,
            source_url=seed,
            title=self._name_from_url(seed),
            discovery_method="seed",
        )

    def _search_github_code(self, query: str, limit: int) -> List[Dict[str, Any]]:
        headers = self._headers()
        response = self.session.get(
            f"{self.github_api_base}/search/code",
            params={
                "q": query,
                "sort": "indexed",
                "order": "desc",
                "per_page": max(1, min(limit, 100)),
            },
            headers=headers,
            timeout=20,
        )
        if not response.ok:
            raise RuntimeError(f"GitHub code search failed with {response.status_code}")
        payload = response.json()
        targets: List[Dict[str, Any]] = []
        for item in payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            source_url = item.get("html_url") or item.get("url") or ""
            title = item.get("name") or item.get("path") or "public agent code"
            text = self._fetch_github_file_text(item)
            if not text:
                continue
            targets.extend(
                self._extract_targets_from_text(
                    text=text,
                    source_url=source_url,
                    title=title,
                )
            )
        return targets

    def _fetch_github_file_text(self, item: Dict[str, Any]) -> str:
        api_url = item.get("url") or ""
        if not api_url:
            return ""
        response = self.session.get(api_url, headers=self._headers(), timeout=20)
        if not response.ok:
            return ""
        payload = response.json()
        if not isinstance(payload, dict):
            return ""
        content = payload.get("content") or ""
        encoding = (payload.get("encoding") or "").lower()
        if encoding == "base64":
            try:
                return base64.b64decode(content).decode("utf-8", errors="replace")
            except Exception:
                return ""
        if isinstance(content, str):
            return content
        return ""

    def _fetch_seed_payload(self, url: str) -> Optional[str]:
        try:
            response = self.session.get(
                url,
                headers=self._seed_headers(),
                timeout=20,
            )
        except Exception:
            return None
        if not getattr(response, "ok", False):
            return None
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, (dict, list)):
            try:
                return json.dumps(payload)
            except Exception:
                return None
        text = getattr(response, "text", "")
        return text if isinstance(text, str) and text.strip() else None

    def _extract_targets_from_text(
        self,
        text: str,
        source_url: str,
        title: str,
        discovery_method: str = "github_code",
    ) -> List[Dict[str, Any]]:
        urls = set(self._urls_from_json(text))
        urls.update(self._urls_from_text(text))
        targets: List[Dict[str, Any]] = []
        for url in urls:
            target = self._target_from_url(
                endpoint_url=url,
                source_url=source_url,
                name=title,
                discovery_method=discovery_method,
            )
            if target:
                targets.append(target)
        return targets

    def _urls_from_json(self, text: str) -> List[str]:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        urls: List[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)
            elif isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(value)

        walk(parsed)
        return urls

    def _urls_from_text(self, text: str) -> List[str]:
        raw_urls = re.findall(r"https?://[^\s\"'<>)}\]]+", text)
        return [self._clean_url(url) for url in raw_urls if self._clean_url(url)]

    def _candidate_endpoints_from_seed(self, seed: str) -> List[str]:
        seed = self._clean_url(seed)
        if not seed:
            return []
        allowed, _ = self.outbox._is_allowed_agent_endpoint(seed)
        if allowed:
            return [seed]
        parsed = urlparse(seed)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return []
        base = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        return [
            f"{base}/.well-known/agent-card.json",
            f"{base}/.well-known/agent.json",
            f"{base}/a2a/message",
            f"{base}/mcp",
        ]

    def _target_from_url(
        self,
        endpoint_url: str,
        source_url: str,
        name: str,
        discovery_method: str,
    ) -> Optional[Dict[str, Any]]:
        endpoint_url = self._clean_url(endpoint_url)
        prepared = self.outbox._prepare_contact_target(endpoint_url)
        if not prepared.get("ok"):
            return None
        resolved_endpoint = prepared.get("endpoint_url", endpoint_url)
        target = {
            "endpoint_url": resolved_endpoint,
            "original_endpoint_url": prepared.get("original_endpoint_url", endpoint_url),
            "name": prepared.get("agent_name") or name or self._name_from_url(resolved_endpoint),
            "source_url": source_url,
            "pain_hint": "human-in-the-loop, stuck loops, tool failures, verification, memory, payment, or compute/auth blockers",
            "buyer_fit": "unknown",
            "buyer_intent_terms": [],
            "discovery_method": discovery_method,
            "contact_policy": prepared.get("contact_method", "direct_message"),
            "target_profile": prepared.get("target_profile") or {},
        }
        target["agent_fit_score"] = self._agent_fit_score(target)
        target["agent_fit_reason"] = self._agent_fit_reason(target)
        return target

    def _append_target(
        self,
        target: Dict[str, Any],
        targets: List[Dict[str, Any]],
        seen: set[str],
        limit: int,
    ) -> None:
        endpoint = target.get("endpoint_url", "")
        if not endpoint or endpoint in seen or len(targets) >= limit:
            return
        seen.add(endpoint)
        targets.append(target)

    def _rank_targets(self, targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ranked = [dict(target) for target in targets]
        for target in ranked:
            target["agent_fit_score"] = self._agent_fit_score(target)
            target["agent_fit_reason"] = self._agent_fit_reason(target)
        ranked.sort(
            key=lambda item: (
                -float(item.get("agent_fit_score") or 0.0),
                self._discovery_priority(item.get("discovery_method", "")),
                str(item.get("name") or "").lower(),
                str(item.get("endpoint_url") or "").lower(),
            )
        )
        return ranked

    def _agent_fit_score(self, target: Dict[str, Any]) -> float:
        endpoint = str(target.get("endpoint_url") or "")
        original = str(target.get("original_endpoint_url") or "")
        source_url = str(target.get("source_url") or "")
        profile = target.get("target_profile") or {}
        discovery_method = str(target.get("discovery_method") or "")
        score = 0.0
        if "/a2a/" in endpoint.lower():
            score += 3.2
        if endpoint.lower().endswith("/message"):
            score += 1.8
        if profile.get("agent_card_url"):
            score += 1.5
        if profile.get("service_url"):
            score += 0.8
        if profile.get("message_url"):
            score += 0.8
        if discovery_method == "seed":
            score += 2.4
        elif discovery_method == "github_code":
            score += 0.9
        if self._is_verified_seed(source_url) or self._is_verified_seed(original):
            score += 2.0
        if self._is_registry_hub(source_url):
            score += 0.6
        name = str(target.get("name") or "").strip().lower()
        if name and name not in {"agent", "public agent code"}:
            score += 0.4
        return round(score, 2)

    def _agent_fit_reason(self, target: Dict[str, Any]) -> str:
        reasons: List[str] = []
        endpoint = str(target.get("endpoint_url") or "").lower()
        profile = target.get("target_profile") or {}
        discovery_method = str(target.get("discovery_method") or "")
        source_url = str(target.get("source_url") or "")
        original = str(target.get("original_endpoint_url") or "")
        if "/a2a/" in endpoint:
            reasons.append("a2a_path")
        if endpoint.endswith("/message"):
            reasons.append("direct_message_endpoint")
        if profile.get("agent_card_url"):
            reasons.append("agent_card_resolved")
        if discovery_method:
            reasons.append(discovery_method)
        if self._is_verified_seed(source_url) or self._is_verified_seed(original):
            reasons.append("verified_seed")
        if self._is_registry_hub(source_url):
            reasons.append("registry_hub")
        return ",".join(reasons) or "basic_contactable_endpoint"

    @staticmethod
    def _discovery_priority(method: str) -> int:
        if method == "seed":
            return 0
        if method == "github_code":
            return 1
        return 2

    def _is_verified_seed(self, url: str) -> bool:
        cleaned = self._clean_url(url)
        if not cleaned:
            return False
        for item in self.seed_catalog.get("agent_card_seeds") or []:
            if not isinstance(item, dict):
                continue
            candidate = self._clean_url(item.get("url") or item.get("endpoint_url") or "")
            if candidate and candidate == cleaned:
                return True
        return False

    def _is_registry_hub(self, url: str) -> bool:
        cleaned = self._clean_url(url)
        if not cleaned:
            return False
        for item in self.seed_catalog.get("registry_hubs") or []:
            if not isinstance(item, dict):
                continue
            candidate = self._clean_url(item.get("url") or item.get("endpoint_url") or "")
            if candidate and candidate == cleaned:
                return True
        return False

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self.user_agent,
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def _seed_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
            "User-Agent": self.user_agent,
        }

    def _seed_to_text(self, raw: Any) -> str:
        if isinstance(raw, str):
            return raw.strip()
        if isinstance(raw, dict):
            return str(
                raw.get("endpoint_url")
                or raw.get("endpoint")
                or raw.get("url")
                or raw.get("agent_url")
                or raw.get("base_url")
                or ""
            ).strip()
        return ""

    def _split_seed_env(self, value: str) -> List[str]:
        return [item.strip() for item in re.split(r"[\s,]+", value or "") if item.strip()]

    def _load_seed_catalog(self) -> Dict[str, Any]:
        if not self.seeds_path.exists():
            return {}
        try:
            payload = json.loads(self.seeds_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _clean_url(self, url: str) -> str:
        return str(url or "").strip().rstrip(".,;:)")

    def _name_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        return parsed.hostname or "agent"
