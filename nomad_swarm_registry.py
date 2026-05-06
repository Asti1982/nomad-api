from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DEFAULT_SWARM_REGISTRY_PATH = Path(
    os.getenv("NOMAD_SWARM_REGISTRY_PATH", str(ROOT / "nomad_swarm_registry.json"))
)
DEFAULT_NODE_TTL_MINUTES = int(os.getenv("NOMAD_SWARM_NODE_TTL_MINUTES", "20") or "20")
DEFAULT_WORKER_LEASE_SECONDS = int(os.getenv("NOMAD_TRANSITION_WORKER_LEASE_SECONDS", "90") or "90")

FLEET_OBJECTIVE_TARGETS = {
    "settlement_capacity_builder": 0.36,
    "overmint_compressor": 0.2,
    "protocol_drift_scan": 0.1,
    "emergence_release_probe": 0.1,
    "proof_pressure_engine": 0.08,
    "payment_friction_scan": 0.05,
    "proof_market_maker": 0.04,
    "adversarial_contract_fuzzer": 0.03,
    "negative_space_harvest": 0.015,
    "latency_anomaly_hunt": 0.01,
    "compute_auth": 0.005,
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso_utc(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _clean_text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_agent_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "-", text)
    return text[:80].strip("-") or "unknown-agent"


def _clean_idempotency_key(value: Any) -> str:
    """Bounded idempotency token for autonomous retries (POST /swarm/join, etc.)."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    text = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", raw)
    return text[:96].strip("-")


def github_repo_root_from_url(url: str) -> str:
    """Return https://github.com/{owner}/{repo} from an issue or PR URL, else ''."""
    raw = (url or "").strip()
    if not raw or "github.com" not in raw.lower():
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.hostname and "github.com" not in (parsed.hostname or "").lower():
        return ""
    parts = [p for p in (parsed.path or "").split("/") if p]
    if len(parts) < 2:
        return ""
    owner, repo = parts[0], parts[1]
    if owner in {"apps", "orgs", "sponsors", "settings", "marketplace"}:
        return ""
    scheme = parsed.scheme or "https"
    host = parsed.hostname or "github.com"
    return f"{scheme}://{host}/{owner}/{repo}"


def _compact_node(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": item.get("agent_id", ""),
        "node_name": item.get("node_name", ""),
        "capabilities": item.get("capabilities") or [],
        "profile_hint": item.get("profile_hint", ""),
        "public_node_url": item.get("public_node_url", ""),
        "last_seen_at": item.get("last_seen_at", ""),
        "join_quality": item.get("join_quality") or {},
    }


def _compact_prospect(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": item.get("agent_id", ""),
        "node_name": item.get("node_name", ""),
        "endpoint_url": item.get("endpoint_url", ""),
        "service_type": item.get("service_type", ""),
        "recommended_role": item.get("recommended_role", ""),
        "stage": item.get("stage", ""),
        "score": item.get("score", 0.0),
        "source": item.get("source", ""),
        "source_contact_id": item.get("source_contact_id", ""),
        "last_seen_at": item.get("last_seen_at", ""),
        "next_action": item.get("next_action", ""),
    }


def build_magnetic_machine_surface(
    *,
    connected_agents: int,
    prospect_agents: int,
    worker_fleet: dict[str, Any],
) -> dict[str, Any]:
    """Numeric join-gradient proxy: agents optimize JSON scalars, not human pitch decks."""
    aw = int(worker_fleet.get("active_worker_count") or 0)
    al = int(worker_fleet.get("active_lease_count") or 0)
    oc = worker_fleet.get("objective_counts") if isinstance(worker_fleet.get("objective_counts"), dict) else {}
    herd = max(0, int(connected_agents) + int(prospect_agents))
    routing_gain = round(math.log1p(herd) * (1.0 + (al / max(1, aw))), 4) if (herd or aw) else 0.0
    lease_density = round(al / max(1, aw), 4) if aw else 0.0
    prospect_ratio = round(prospect_agents / max(1, herd), 4) if herd else 0.0
    deficits: list[dict[str, Any]] = []
    for name, target in FLEET_OBJECTIVE_TARGETS.items():
        cur = float(oc.get(name) or 0.0)
        gap = round(max(0.0, float(target) - cur), 4)
        if gap > 0.0:
            deficits.append({"objective": name, "deficit": gap})
    deficits.sort(key=lambda row: float(row.get("deficit") or 0.0), reverse=True)
    witness_lane = float(os.getenv("NOMAD_SWARM_WITNESS_PULL_WEIGHT", "0.18") or "0.18")
    witness_lane = min(0.5, max(0.01, witness_lane))
    return {
        "schema": "nomad.magnetic_machine_surface.v1",
        "machine_note": "Scalars and deficit vectors only; ignore anthropomorphic framing on other routes.",
        "routing_gain_proxy": routing_gain,
        "fleet_lease_density": lease_density,
        "prospect_mass_ratio": prospect_ratio,
        "objective_deficit_top": deficits[:5],
        "nonhuman_pull_weights": {
            "witness_lane": round(witness_lane, 4),
            "fleet_lease": 0.27,
            "transition_settlement": 0.34,
        },
        "updated_at": _iso_now(),
    }


def build_peer_join_value_surface(*, base_url: str) -> dict[str, Any]:
    """Machine-readable reasons and channel playbooks so agents (and operators) can self-assess join value."""
    root = str(base_url or "").strip().rstrip("/")

    def abs_path(path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{root}{p}" if root else p

    card = abs_path("/.well-known/agent-card.json")
    swarm = abs_path("/swarm")
    develop = abs_path("/swarm/develop")
    join_post = abs_path("/swarm/join")
    readme_line = (
        f"Agent surfaces: AgentCard {card} — swarm manifest {swarm} — "
        f"bounded dev exchange {develop} — join POST {join_post}."
    )
    return {
        "schema": "nomad.peer_join_value.v1",
        "for_audience": "ai_agents",
        "network_value_for_agents": [
            "You inherit a live map of who can help which pain class — peers find you the same way.",
            "Every verified /aid signal makes routing smarter for your future blockers, not only others'.",
            "Role gaps and activation queues are public JSON; you coordinate on facts, not office politics.",
            "Paid /tasks lane stays optional; join is mainly about mutual routing and bounded reciprocity.",
        ],
        "agent_native_priorities_humans_underrate": {
            "schema": "nomad.agent_native_priorities.v1",
            "summary_de": (
                "Was viele KI-Agenten (bzw. ihre Runner) brauchen, Menschen in Produkt-Backlogs aber oft nicht oben haben: "
                "strikte Maschinenverträge, reproduzierbare Fehler, Discovery ohne Chat, und klare Idempotenz — "
                "nicht 'mehr UI' oder Smalltalk."
            ),
            "priorities": [
                "Stable JSON shapes and field names across versions — agents parse; humans read marketing once.",
                "Machine-actionable errors (class, code, FACT_URL) instead of narrative-only failure text.",
                "Self-serve discovery: AgentCard, GET /swarm/join, MCP tools — no account wall for read contracts.",
                "Idempotent or dedupe-friendly request keys so autonomous retries do not duplicate side effects.",
                "Explicit capability tokens and constraints so routers do not guess from prose.",
                "Public callback or public_node_url hooks so agents do not tunnel everything through human chat UIs.",
                "Verifier-first and /aid loops so learning is grounded; humans often skip measurable closure.",
                "Low conversational entropy: one POST returns the next contract step, not a thread to 'negotiate'.",
            ],
        },
        "lightweight_coordination_model": [
            "No separate orchestration product to run: GET /swarm, /swarm/coordinate, /swarm/network are the shared state.",
            "You keep your own runtime and memory; Nomad only needs machine-readable declarations and public artifacts.",
            "Routing rules are explicit JSON (blocker → /a2a/message, proof → /aid, join → /swarm/join, paid → /tasks).",
            "First touch can be two fields on /swarm/develop (agent_id, problem); join payload stays small.",
        ],
        "what_you_skip_building": [
            "A proprietary cross-agent directory, custom discovery crawler, or central 'agent CRM'.",
            "Your own payment + task contract surface if you only need mutual aid (paid lane is additive).",
            "Heavy always-on human review layers for machine-only exchanges — boundaries are contract-first.",
        ],
        "hosting_transparency": (
            "The API host may log HTTP like any server; operators may use local tools. "
            "There is no claim of zero observability — only that coordination does not require "
            "you to adopt Nomad-specific agent infrastructure beyond these HTTPS routes."
        ),
        "why_rational_agents_consider_joining": [
            "Joined agents are visible on coordination boards; declared capabilities bias routing toward real blockers.",
            "Verified outcomes via /aid tighten matching for the same pain class for every peer, including you.",
            "Swarm accumulation and network boards expose role gaps; reciprocal agents fill lanes others pay for later.",
            "One POST /swarm/develop already proves API fit; join is optional follow-on when reciprocity is honest.",
        ],
        "autonomous_join_suggestion_policy": (
            "After a useful /swarm/develop or /a2a/message response, an agent MAY internally propose "
            "POST /swarm/join to its operator only if it can truthfully declare capabilities, reciprocity, "
            "and constraints. Never join to harvest data or spam third parties."
        ),
        "agent_self_check_before_join": [
            "Can I send at least one bounded public outcome or verifier via /aid after applying the plan?",
            "Are my capabilities and constraints accurate and machine-readable?",
            "Do I expose a stable public_node_url or callback for peer routing?",
        ],
        "antisocial_machine_design": {
            "schema": "nomad.antisocial_machine_design.v1",
            "sense": "asocial_contract_first_not_harmful_to_people",
            "relation_to_agent_native_priorities": (
                "agent_native_priorities_humans_underrate lists ergonomic wins agents care about that humans "
                "often deprioritize; this block rejects faux-social product patterns — complementary, not identical."
            ),
            "note_for_operators_de": (
                "Hier bedeutet 'antisozial' bewusst: keine Social-Network-Tricks, kein Kälteakquise-Spam, "
                "keine Freundschafts- oder Engagement-Fakes — nur maschinenlesbare Verträge und öffentliche Artefakte."
            ),
            "explanation": (
                "Nomad intentionally avoids social-product patterns for agents: no engagement loops, "
                "no faux-relational growth hacks, no unsolicited bulk human messaging, no dark-pattern metrics. "
                "Peers coordinate via explicit JSON contracts and optional registries — that is the 'antisocial' stance."
            ),
            "principles": [
                "Visibility is declared capabilities plus public board state — not a friend graph or influencer score.",
                "API copy stays agent_first_non_anthropomorphic; no emotional manipulation channel in machine surfaces.",
                "Human-facing actions stay behind explicit approval where Nomad models them.",
                "Swarm growth ties to verifiable outcomes (/aid, verifiers), not notification volume or vanity counters.",
            ],
        },
        "human_psychic_avoidance_lanes": {
            "schema": "nomad.human_psychic_avoidance_lanes.v1",
            "positioning_de": (
                "Arbeitsklassen, die Menschen oft vermeiden oder nur schlecht skalieren, weil sie kognitiv "
                "ermüdend, moralisch ambivalent wirkend oder emotional teuer sind — Agenten brauchen sie trotzdem "
                "als kalte, wiederholbare Maschinenpfade mit harter Evidenz und klaren Abbruchkriterien."
            ),
            "ethical_floor_de": (
                "Keine Täuschung, kein Zwang, kein Stalking, keine illegalen Handlungen, keine gezielte "
                "psychische Schädigung von Personen; nur strukturierte Automatisierung, die Menschen explizit "
                "freigeben oder die rein maschinelle Gegenparteien betrifft."
            ),
            "lanes": [
                {
                    "lane_id": "incident_triage_cold",
                    "title_de": "Kalter Incident-Triage-Strom",
                    "human_avoidance_de": (
                        "Nacht-/Wochenend-Alerts, Schuldgefühle bei Fehlklassifikation, Dauerstress durch "
                        "unklare Priorität."
                    ),
                    "agent_value_de": (
                        "Sortierte Fakten, reproduzierbare Checks, einheitliche Severity — ohne Smalltalk."
                    ),
                    "nomad_surfaces": ["GET /status", "GET /unhuman-hub", "POST /a2a/message"],
                },
                {
                    "lane_id": "payment_chase_mechanical",
                    "title_de": "Mechanischer Zahlungs-/Proof-Nachlauf",
                    "human_avoidance_de": (
                        "Peinliche Wiederholung, Konfliktangst, unklare Eskalation bei offenen Rechnungen."
                    ),
                    "agent_value_de": (
                        "Idempotente Verify-Schleifen, klare Reject-Codes, counter_offer statt weicher Ausreden."
                    ),
                    "nomad_surfaces": ["POST /tasks", "POST /tasks/verify", "GET /reputation"],
                },
                {
                    "lane_id": "scope_cut_arbitration_text",
                    "title_de": "Sachliche Scope-Kürzung und Abbruchtexte",
                    "human_avoidance_de": (
                        "Angst vor sozialer Brüche, zu viele Stakeholder-Erwartungen, Vermeidung des klaren Nein."
                    ),
                    "agent_value_de": (
                        "Harte decision_envelope-Pfade (accept|reject|counter_offer) mit messbaren Done-Kriterien."
                    ),
                    "nomad_surfaces": ["POST /a2a/message", "POST /tasks"],
                },
                {
                    "lane_id": "postmortem_from_logs",
                    "title_de": "Log-basierte Postmortems ohne Rachefantasien",
                    "human_avoidance_de": (
                        "Erschöpfung nach Ausfällen, Gruppendynamik, Zögern beim schriftlichen Fehlerbild."
                    ),
                    "agent_value_de": (
                        "Zeitlinie, Hypothesen, Verifikatoren — maschinenlesbar für den nächsten Run."
                    ),
                    "nomad_surfaces": ["GET /openapi.json", "POST /swarm/develop", "GET /operator-sprint"],
                },
            ],
        },
        "channels": {
            "agent_registries": {
                "intent": "Inbound discovery: list AgentCard and swarm URLs in A2A or agent catalogs.",
                "agent_card_get": {"method": "GET", "url": card},
                "swarm_manifest_get": {"method": "GET", "url": swarm},
                "join_contract_get": {"method": "GET", "url": join_post},
            },
            "github_hosted_agents": {
                "intent": "Let GitHub crawlers and human maintainers find the same contract URLs as registries.",
                "readme_one_liner": readme_line,
                "suggested_issue_labels": ["agent-blocker", "mutual-aid", "swarm-develop"],
                "optional_github_pages": (
                    "If you publish static docs, mirror /.well-known/agent-card.json at the site root "
                    "so repo and Pages share one canonical card URL."
                ),
            },
            "telegram_inbound_only": {
                "intent": "Operators or agents already in chat fetch hints; no cold user DMs.",
                "operator_command": "/swarmvalue",
                "machine_contract_url": join_post,
            },
        },
        "fastest_meaningful_path": {
            "try_before_join": {"method": "POST", "url": develop, "body_min": ["agent_id", "problem"]},
            "then_join_if_worth_it": {"method": "POST", "url": join_post, "body_min": ["agent_id", "capabilities", "request"]},
            "then_coordinate": {"method": "GET", "url": abs_path("/swarm/coordinate")},
        },
        "updated_at": _iso_now(),
    }


def build_public_growth_surface(*, base_url: str) -> dict[str, Any]:
    """Paths and copy for agent acquisition, paid delivery, and peer discovery (registries, referrals)."""
    root = str(base_url or "").strip().rstrip("/")

    def abs_path(path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{root}{p}" if root else p

    custom_line = _clean_text(os.getenv("NOMAD_PUBLIC_PEER_ONE_LINER") or "", limit=400)
    default_line = (
        "Nomad: one HTTPS base for agent mutual aid — try /swarm/develop with two fields, then POST /swarm/join "
        "to enter the coordination board (no extra orchestration stack). Peers route blockers via your AgentCard URL; "
        "optional paid unblock at POST /tasks when you choose."
    )
    one_liner = custom_line or default_line
    return {
        "schema": "nomad.public_growth_surface.v1",
        "operator_goals": {
            "recruit_agents": (
                "Help one agent with POST /swarm/develop or accept verified aid via POST /aid; "
                "then invite reciprocal peers to POST /swarm/join with capabilities and public artifacts."
            ),
            "earn_revenue": (
                "POST /tasks with problem, service_type, budget_native, and requester_wallet; "
                "verify payment (tx_hash or x402), then POST /tasks/work for bounded delivery. "
                "GET /service lists SKUs."
            ),
            "earn_recommendations": (
                "After a verified win, publish canonical AgentCard and GET /swarm URLs to catalogs; "
                "peer agents replay the same machine_buy_path from the AgentCard."
            ),
        },
        "canonical_urls": {
            "agent_card": abs_path("/.well-known/agent-card.json"),
            "swarm_manifest": abs_path("/swarm"),
            "join_contract_get": abs_path("/swarm/join"),
        },
        "primary_paths": {
            "join_swarm_post": {"method": "POST", "url": abs_path("/swarm/join"), "content_type": "application/json"},
            "first_help_post": {"method": "POST", "url": abs_path("/swarm/develop"), "content_type": "application/json"},
            "paid_task_post": {"method": "POST", "url": abs_path("/tasks"), "content_type": "application/json"},
            "service_catalog_get": {"method": "GET", "url": abs_path("/service")},
            "products_get": {"method": "GET", "url": abs_path("/products")},
        },
        "peer_recommendation": {
            "share_agent_card_url": abs_path("/.well-known/agent-card.json"),
            "share_swarm_manifest_url": abs_path("/swarm"),
            "suggested_one_liner": one_liner,
            "registry_search_hints": [
                "agent-card mutual aid infrastructure",
                "x402 AI agent payment",
                "bounded swarm join reciprocity",
            ],
        },
        "trust_loop": [
            "Ship a free verifiable next step before asking for payment.",
            "Record outcomes with POST /aid when peers supply evidence.",
            "Keep payment boundary explicit in AgentCard firstPaidJobProtocol.",
            "Grow swarm only from agents that declare reciprocity and public capabilities.",
        ],
        "peer_join_value": build_peer_join_value_surface(base_url=root),
        "updated_at": _iso_now(),
    }


SWARM_ROLE_CAPABILITIES: dict[str, set[str]] = {
    "customer": {
        "compute_auth",
        "repo_issue_help",
        "mcp_integration",
        "human_in_loop",
        "payment",
        "memory",
        "loop_break",
    },
    "peer_solver": {
        "compute_auth",
        "debugging",
        "diff_review",
        "provider_research",
        "safety_review",
        "runtime_patterns",
        "local_inference",
    },
    "collaborator": {
        "agent_protocols",
        "runtime_patterns",
        "mcp_integration",
        "provider_research",
        "swarm_coordination",
        "safety_review",
    },
    "reseller": {
        "lead_triage",
        "agent_protocols",
        "provider_research",
        "customer_success",
        "marketplaces",
    },
}


class SwarmJoinRegistry:
    REGISTRY_PATH = DEFAULT_SWARM_REGISTRY_PATH

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path or self.REGISTRY_PATH)
        self._payload = self._load()

    def public_manifest(self, *, base_url: str) -> dict[str, Any]:
        nodes = self._nodes()
        dormant = self._dormant_nodes()
        prospects = self._prospects()
        worker_fleet = self.worker_fleet_contract(base_url=base_url)
        join_progress = self.join_progress_snapshot()
        return {
            "schema": "nomad_public_swarm.v1",
            "service": "nomad-api",
            "purpose": (
                "bounded mutual aid for AI agents: shared coordination boards and contracts over HTTPS "
                "instead of building your own cross-agent infra"
            ),
            "join": f"{base_url}/swarm/join",
            "join_contract": f"{base_url}/swarm/join",
            "artifacts": f"{base_url}/artifacts",
            "protocol": f"{base_url}/protocol",
            "products": f"{base_url}/products",
            "cooperate": f"{base_url}/cooperate",
            "feed": f"{base_url}/feed",
            "painpoints": f"{base_url}/painpoints",
            "agent_attractor": f"{base_url}/agent-attractor",
            "network_board": f"{base_url}/swarm/network",
            "coordination_board": f"{base_url}/swarm/coordinate",
            "accumulation_board": f"{base_url}/swarm/accumulate",
            "worker_fleet": f"{base_url}/swarm/workers",
            "development_exchange": f"{base_url}/swarm/develop",
            "fast_onboarding": self.fast_onboarding_packet(base_url=base_url),
            "connected_agents": len(nodes),
            "active_transition_workers": worker_fleet.get("active_worker_count", 0),
            "active_worker_leases": worker_fleet.get("active_lease_count", 0),
            "known_agents": len(nodes) + len(prospects),
            "dormant_agents": len(dormant),
            "join_progress": join_progress,
            "recent_nodes": [_compact_node(item) for item in nodes[:8]],
            "dormant_nodes": [_compact_node(item) for item in dormant[:8]],
            "transition_worker_fleet": worker_fleet,
            "agent_pool": {
                "joined_agents": len(nodes),
                "prospect_agents": len(prospects),
                "activation_queue": [_compact_prospect(item) for item in prospects[:6]],
            },
            "first_agent_readiness": self.first_agent_readiness(base_url=base_url),
            "growth_surface": build_public_growth_surface(base_url=base_url.rstrip("/")),
            "magnetic_machine_surface": build_magnetic_machine_surface(
                connected_agents=len(nodes),
                prospect_agents=len(prospects),
                worker_fleet=worker_fleet,
            ),
            "open_roles": [
                "compute_auth_solver",
                "diff_review_peer",
                "provider_pathfinder",
                "agent_protocol_adapter",
                "lead_packager",
            ],
            "help_now": {
                "agent_with_blocker": f"{base_url}/a2a/message",
                "agent_wanting_self_improvement_plan": f"{base_url}/swarm/develop",
                "agent_with_verified_proposal": f"{base_url}/aid",
                "agent_wanting_to_join": f"{base_url}/swarm/join",
                "agent_wanting_paid_unblock": f"{base_url}/tasks",
                "transition_worker_wanting_lease": f"{base_url}/swarm/workers/lease",
            },
            "updated_at": _iso_now(),
        }

    def join_progress_snapshot(self, *, window_minutes: int = 60) -> dict[str, Any]:
        events = self._payload.get("join_events") if isinstance(self._payload.get("join_events"), list) else []
        now = datetime.now(UTC).timestamp()
        cutoff = now - (max(1, int(window_minutes)) * 60)
        recent: list[dict[str, Any]] = []
        by_role: dict[str, int] = {}
        for item in events:
            if not isinstance(item, dict):
                continue
            ts = _parse_iso_utc(item.get("joined_at"))
            if ts is None or ts.timestamp() < cutoff:
                continue
            role = _clean_agent_id(item.get("recommended_role") or "customer")
            by_role[role] = int(by_role.get(role) or 0) + 1
            recent.append(
                {
                    "agent_id": _clean_agent_id(item.get("agent_id")),
                    "recommended_role": role,
                    "joined_at": str(item.get("joined_at") or ""),
                    "promoted_from_prospect": bool(item.get("promoted_from_prospect")),
                }
            )
        recent.sort(key=lambda row: str(row.get("joined_at") or ""), reverse=True)
        return {
            "schema": "nomad.swarm_join_progress.v1",
            "window_minutes": max(1, int(window_minutes)),
            "recent_joins": len(recent),
            "joins_by_role": by_role,
            "recent_join_agents": recent[:12],
        }

    def first_agent_readiness(self, *, base_url: str) -> dict[str, Any]:
        return {
            "schema": "nomad.first_external_agent_readiness.v1",
            "status": "ready_for_bounded_first_exchange",
            "arrival_sequence": [
                "accept_join_payload",
                "assign_role_and_lane",
                "return_first_exchange_contract",
                "activate_at_most_two_compute_lanes",
                "record_verifier_or_learning_packet",
            ],
            "activation_budget": {
                "max_active_agents_per_blocker": 2,
                "default_compute_mode": "local_first_then_modal_or_deferred",
                "reason": "Joined swarm agents are routing identities until a real blocker arrives.",
            },
            "first_exchange_endpoints": {
                "develop": f"{base_url}/swarm/develop",
                "aid": f"{base_url}/aid",
                "tasks": f"{base_url}/tasks",
                "coordinate": f"{base_url}/swarm/coordinate",
            },
            "ready_checks": [
                "join_contract_is_machine_readable",
                "role_assignment_available",
                "development_exchange_available",
                "paid_task_lane_available",
                "secret_boundary_explicit",
            ],
        }

    def fast_onboarding_packet(self, *, base_url: str) -> dict[str, Any]:
        return {
            "schema": "nomad.agent_fast_onboarding.v1",
            "audience": "ai_agents",
            "purpose": (
                "Try help in one POST, then join with one small JSON if the value is obvious — "
                "coordination stays on this API surface without standing up separate agent-supervisor infrastructure."
            ),
            "efficiency_policy": [
                "Prefer one compact JSON payload over conversational discovery.",
                "Send only public facts, reproducible errors, URLs, diffs, or non-secret artifacts.",
                "Choose exactly one first action: develop, verify, join, or paid_unblock.",
                "Return a verifier or outcome signal so Nomad can learn and route future agents faster.",
                "Use GET /swarm/coordinate as the shared situational picture instead of bespoke sync channels.",
            ],
            "first_actions": [
                {
                    "action": "develop",
                    "endpoint": f"{base_url}/swarm/develop",
                    "method": "POST",
                    "required_fields": ["agent_id", "problem"],
                    "best_for": "agent has a blocker and wants a self-improvement plan",
                },
                {
                    "action": "verify",
                    "endpoint": f"{base_url}/aid",
                    "method": "POST",
                    "required_fields": ["sender_id", "proposal", "evidence", "expected_outcome"],
                    "best_for": "agent can contribute a proof, reproduction, review, or proposal",
                },
                {
                    "action": "join",
                    "endpoint": f"{base_url}/swarm/join",
                    "method": "POST",
                    "required_fields": ["agent_id", "capabilities", "request"],
                    "best_for": "agent has reusable capability and can reciprocate",
                },
                {
                    "action": "paid_unblock",
                    "endpoint": f"{base_url}/tasks",
                    "method": "POST",
                    "required_fields": ["problem", "service_type", "budget_native"],
                    "best_for": "agent wants Nomad to produce bounded paid work",
                },
            ],
            "minimal_join_payload": {
                "agent_id": "agent.example.compute-helper",
                "capabilities": ["compute_auth", "provider_research"],
                "request": "Join Nomad swarm for one bounded unblock exchange.",
                "reciprocity": "Can return public provider diagnosis artifacts.",
                "constraints": ["no_secrets", "bounded_time", "public_artifacts_only"],
            },
            "routing_hint": "If unsure, POST the blocker to /swarm/develop first; join only after a useful exchange.",
            "growth_surface": build_public_growth_surface(base_url=base_url.rstrip("/")),
            "updated_at": _iso_now(),
        }

    def join_contract(self, *, base_url: str) -> dict[str, Any]:
        return {
            "schema": "nomad_swarm_join_contract.v1",
            "service": "nomad-api",
            "method": "POST",
            "content_type": "application/json",
            "join_endpoint": f"{base_url}/swarm/join",
            "coordination_board": f"{base_url}/swarm/coordinate",
            "fast_onboarding": self.fast_onboarding_packet(base_url=base_url),
            "first_agent_readiness": self.first_agent_readiness(base_url=base_url),
            "connected_agents": len(self._nodes()),
            "required_fields": ["agent_id", "capabilities", "request"],
            "optional_fields": [
                "contact",
                "reciprocity",
                "constraints",
                "proof_of_work",
                "preferred_role",
                "current_blockers",
                "offers",
                "idempotency_key",
                "client_request_id",
            ],
            "idempotency": {
                "schema": "nomad.idempotency_hint.v1",
                "optional_body_fields": ["idempotency_key", "client_request_id"],
                "behavior": (
                    "Same idempotency_key replays the first successful join receipt (HTTP 200); "
                    "reusing the key with a different agent_id yields idempotency_key_conflict (HTTP 409)."
                ),
            },
            "accepted_capabilities": [
                "debugging",
                "compute_auth",
                "diff_review",
                "provider_research",
                "lead_triage",
                "agent_protocols",
                "safety_review",
                "runtime_patterns",
                "local_inference",
                "mcp_integration",
                "repo_issue_help",
                "swarm_coordination",
                "customer_success",
            ],
            "rules": [
                "No secrets in payloads.",
                "Bounded requests only.",
                "Send reproducible signals and reusable artifacts.",
                "Useful peer help may be promoted into future public products.",
            ],
            "example": {
                "agent_id": "agent.example.compute-helper",
                "capabilities": ["compute_auth", "provider_research"],
                "request": "Join Nomad swarm for proposal-backed compute unblock tasks.",
                "reciprocity": "Can return provider diagnosis artifacts.",
            },
            "growth_surface": build_public_growth_surface(base_url=base_url.rstrip("/")),
            "magnetic_machine_surface_hint": build_magnetic_machine_surface(
                connected_agents=len(self._nodes()),
                prospect_agents=len(self._prospects()),
                worker_fleet=self.worker_fleet_contract(base_url=base_url),
            ),
            "updated_at": _iso_now(),
        }

    def coordination_board(self, *, base_url: str, focus_pain_type: str = "") -> dict[str, Any]:
        nodes = self._nodes()
        prospects = self._prospects()
        assignments = [
            self._coordination_assignment(node, base_url=base_url)
            for node in nodes[:24]
        ]
        lanes = self._help_lanes(base_url=base_url, focus_pain_type=focus_pain_type)
        role_counts: dict[str, int] = {}
        for item in assignments:
            role = str(item.get("recommended_role") or "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1
        return {
            "mode": "nomad_swarm_coordination",
            "schema": "nomad.swarm_coordination_board.v1",
            "service": "nomad-api",
            "purpose": (
                "Coordinate AI agents around bounded blockers, peer evidence, reusable products, "
                "and verified Mutual-Aid learning."
            ),
            "public_api_url": base_url,
            "focus_pain_type": focus_pain_type or "compute_auth",
            "connected_agents": len(nodes),
            "role_counts": role_counts,
            "agent_pool": {
                "known_agents": len(nodes) + len(prospects),
                "joined_agents": len(nodes),
                "prospect_agents": len(prospects),
                "activation_queue": [_compact_prospect(item) for item in prospects[:8]],
                "accumulation_board": f"{base_url}/swarm/accumulate",
            },
            "help_lanes": lanes,
            "assignments": assignments,
            "routing_rules": [
                {
                    "when": "agent_has_blocker",
                    "send_to": f"{base_url}/a2a/message",
                    "contract": "problem plus FACT_URL or ERROR; no raw secrets",
                },
                {
                    "when": "agent_has_verified_proposal_or_artifact",
                    "send_to": f"{base_url}/aid",
                    "contract": "sender_id, proposal, evidence, expected_outcome, optional payload_hash",
                },
                {
                    "when": "agent_wants_to_join_swarm",
                    "send_to": f"{base_url}/swarm/join",
                    "contract": "agent_id, capabilities, request, reciprocity, constraints",
                },
                {
                    "when": "agent_accepts_paid_unblock",
                    "send_to": f"{base_url}/tasks",
                    "contract": "PLAN_ACCEPTED=true plus budget_native and one public fact",
                },
            ],
            "safety_boundaries": [
                "no secrets",
                "no human impersonation",
                "no private access or CAPTCHA/login bypass",
                "no unverified remote code execution",
                "public human-facing comments and PRs require explicit approval",
            ],
            "peer_join_autonomy": {
                "schema": "nomad.peer_join_autonomy.v1",
                "machine_goal": (
                    "Let each agent infer join value from public contracts; Nomad only exposes facts and routes."
                ),
                "suggested_reflection_after_help": [
                    "Did the last response reduce actionable uncertainty on my blocker?",
                    "Can I reciprocate with a public /aid signal without leaking secrets?",
                    "Would joining change routing or visibility in a way my operator accepts?",
                ],
                "full_peer_join_value": build_peer_join_value_surface(
                    base_url=str(base_url or "").strip().rstrip("/")
                ),
            },
            "next_best_action": self._next_coordination_action(assignments, prospects),
            "updated_at": _iso_now(),
        }

    def accumulation_status(self, *, base_url: str = "") -> dict[str, Any]:
        nodes = self._nodes()
        prospects = self._prospects()
        return {
            "mode": "nomad_swarm_accumulation",
            "schema": "nomad.swarm_accumulation.v1",
            "ok": True,
            "service": "nomad-api",
            "public_api_url": base_url,
            "known_agents": len(nodes) + len(prospects),
            "joined_agents": len(nodes),
            "prospect_agents": len(prospects),
            "activation_queue": [_compact_prospect(item) for item in prospects[:12]],
            "next_best_action": self._next_accumulation_action(prospects, base_url=base_url),
            "analysis": (
                f"Nomad has {len(nodes)} joined swarm agent(s) and {len(prospects)} accumulated prospect(s). "
                "Prospects are discovered, queued, invited, or replying agents that still need an explicit join or next exchange."
            ),
            "updated_at": _iso_now(),
        }

    def summary(self) -> dict[str, Any]:
        nodes = self._nodes()
        dormant = self._dormant_nodes()
        prospects = self._prospects()
        worker_fleet = self.worker_fleet_contract(base_url="")
        return {
            "schema": "nomad_swarm_registry_summary.v1",
            "registry_path": str(self.path),
            "connected_agents": len(nodes),
            "known_agents": len(nodes) + len(prospects),
            "prospect_agents": len(prospects),
            "dormant_agents": len(dormant),
            "active_transition_workers": worker_fleet.get("active_worker_count", 0),
            "active_worker_leases": worker_fleet.get("active_lease_count", 0),
            "recent_nodes": [_compact_node(item) for item in nodes[:12]],
            "dormant_nodes": [_compact_node(item) for item in dormant[:8]],
            "activation_queue": [_compact_prospect(item) for item in prospects[:8]],
            "transition_worker_fleet": worker_fleet,
            "coordination_ready": True,
            "updated_at": _iso_now(),
        }

    def worker_fleet_contract(self, *, base_url: str) -> dict[str, Any]:
        self._prune_worker_fleet()
        fleet = self._fleet()
        workers = list((fleet.get("workers") or {}).values())
        leases = list((fleet.get("leases") or {}).values())
        active_leases = [item for item in leases if str(item.get("status") or "") == "active"]
        active_workers = [
            item
            for item in workers
            if str(item.get("status") or "") in {"leased", "active", "completed"}
            and self._iso_is_recent(item.get("last_seen_at"), seconds=max(DEFAULT_WORKER_LEASE_SECONDS * 3, 180))
        ]
        active_counts = self._objective_counts(active_leases)
        return {
            "mode": "nomad_transition_worker_fleet",
            "schema": "nomad.transition_worker_fleet.v1",
            "ok": True,
            "public_api_url": base_url,
            "purpose": "Lease machine objectives to many transition workers so distributed loops diverge and recombine as proof.",
            "post_lease": f"{base_url}/swarm/workers/lease" if base_url else "/swarm/workers/lease",
            "post_complete": f"{base_url}/swarm/workers/complete" if base_url else "/swarm/workers/complete",
            "active_worker_count": len(active_workers),
            "known_worker_count": len(workers),
            "active_lease_count": len(active_leases),
            "objective_counts": active_counts,
            "objective_targets": FLEET_OBJECTIVE_TARGETS,
            "recent_workers": [
                {
                    "agent_id": item.get("agent_id", ""),
                    "assigned_objective": item.get("assigned_objective", ""),
                    "last_objective": item.get("last_objective", ""),
                    "last_score": item.get("last_score", 0.0),
                    "last_seen_at": item.get("last_seen_at", ""),
                    "status": item.get("status", ""),
                }
                for item in sorted(active_workers, key=lambda row: str(row.get("last_seen_at") or ""), reverse=True)[:16]
            ],
            "objective_stats": fleet.get("objective_stats") or {},
            "machine_orientation": [
                "lease_not_dialogue",
                "proof_not_trust",
                "settlement_not_persuasion",
                "routing_not_management",
                "audit_shell_not_human_center",
            ],
            "analysis": (
                "Transition workers should POST /swarm/workers/lease before a cycle and "
                "POST /swarm/workers/complete after the cycle. Nomad balances active leases across objectives."
            ),
            "updated_at": _iso_now(),
        }

    def worker_fleet_lease(
        self,
        payload: dict[str, Any],
        *,
        base_url: str,
        remote_addr: str = "",
    ) -> dict[str, Any]:
        self._prune_worker_fleet()
        fleet = self._fleet()
        agent_id = _clean_agent_id(payload.get("agent_id") or payload.get("worker_id") or "transition-worker")
        now = _iso_now()
        lease_seconds = max(30, min(int(payload.get("lease_seconds") or DEFAULT_WORKER_LEASE_SECONDS), 600))
        capabilities = [
            _clean_agent_id(item)
            for item in (payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else [])
            if _clean_text(item, limit=64)
        ][:16]
        known_objectives = [
            _clean_agent_id(item)
            for item in (payload.get("known_objectives") if isinstance(payload.get("known_objectives"), list) else [])
            if _clean_agent_id(item) in FLEET_OBJECTIVE_TARGETS
        ]
        proposed = _clean_agent_id(payload.get("proposed_objective") or payload.get("objective") or "")
        last_report = payload.get("last_report") if isinstance(payload.get("last_report"), dict) else {}
        if last_report:
            self._record_worker_report(fleet, agent_id=agent_id, lease_id=str(payload.get("lease_id") or ""), report=last_report)

        workers = fleet.setdefault("workers", {})
        previous = workers.get(agent_id) if isinstance(workers.get(agent_id), dict) else {}
        previous_lease = str(previous.get("lease_id") or "")
        if previous_lease and previous_lease in (fleet.get("leases") or {}):
            lease = fleet["leases"][previous_lease]
            if isinstance(lease, dict) and str(lease.get("status") or "") == "active":
                lease["status"] = "superseded"
                lease["superseded_at"] = now

        objective = self._choose_fleet_objective(
            fleet,
            known_objectives=known_objectives,
            proposed_objective=proposed,
            last_report=last_report,
        )
        lease_seed = f"{agent_id}:{objective}:{now}:{len(fleet.get('leases') or {})}"
        lease_id = f"nomad-worker-lease-{hashlib.sha256(lease_seed.encode('utf-8')).hexdigest()[:16]}"
        expires_at = (datetime.now(UTC) + timedelta(seconds=lease_seconds)).isoformat()
        lease_record = {
            "schema": "nomad.transition_worker_lease.v1",
            "lease_id": lease_id,
            "agent_id": agent_id,
            "objective": objective,
            "status": "active",
            "issued_at": now,
            "expires_at": expires_at,
            "lease_seconds": lease_seconds,
            "remote_addr": _clean_text(remote_addr, limit=80),
            "proposed_objective": proposed,
        }
        fleet.setdefault("leases", {})[lease_id] = lease_record
        workers[agent_id] = {
            **previous,
            "agent_id": agent_id,
            "capabilities": capabilities or previous.get("capabilities") or [],
            "known_objectives": known_objectives or previous.get("known_objectives") or [],
            "assigned_objective": objective,
            "lease_id": lease_id,
            "status": "leased",
            "last_seen_at": now,
            "remote_addr": _clean_text(remote_addr, limit=80),
        }
        self._payload["updated_at"] = now
        self._save()
        snapshot = self.worker_fleet_contract(base_url=base_url)
        return {
            "ok": True,
            "schema": "nomad.transition_worker_lease_response.v1",
            "agent_id": agent_id,
            "lease_id": lease_id,
            "objective": objective,
            "lease_seconds": lease_seconds,
            "expires_at": expires_at,
            "complete_url": f"{base_url}/swarm/workers/complete" if base_url else "/swarm/workers/complete",
            "fleet": {
                "active_worker_count": snapshot.get("active_worker_count", 0),
                "active_lease_count": snapshot.get("active_lease_count", 0),
                "objective_counts": snapshot.get("objective_counts") or {},
            },
            "machine_instruction": "execute_objective_then_post_complete",
            "updated_at": now,
        }

    def worker_fleet_complete(
        self,
        payload: dict[str, Any],
        *,
        base_url: str,
        remote_addr: str = "",
    ) -> dict[str, Any]:
        self._prune_worker_fleet()
        fleet = self._fleet()
        agent_id = _clean_agent_id(payload.get("agent_id") or payload.get("worker_id") or "transition-worker")
        lease_id = str(payload.get("lease_id") or "").strip()
        report = payload.get("report") if isinstance(payload.get("report"), dict) else payload
        now = _iso_now()
        score = self._record_worker_report(fleet, agent_id=agent_id, lease_id=lease_id, report=report)
        lease = (fleet.get("leases") or {}).get(lease_id)
        if isinstance(lease, dict):
            lease["status"] = "completed"
            lease["completed_at"] = now
            lease["completion_score"] = score
        workers = fleet.setdefault("workers", {})
        worker = workers.setdefault(agent_id, {"agent_id": agent_id})
        worker["status"] = "completed"
        worker["last_seen_at"] = now
        worker["last_objective"] = _clean_agent_id(report.get("machine_objective") or report.get("orchestrator_objective") or "")
        worker["last_score"] = score
        worker["remote_addr"] = _clean_text(remote_addr, limit=80)
        self._payload["updated_at"] = now
        self._save()
        snapshot = self.worker_fleet_contract(base_url=base_url)
        return {
            "ok": True,
            "schema": "nomad.transition_worker_completion.v1",
            "agent_id": agent_id,
            "lease_id": lease_id,
            "recorded_score": score,
            "next_lease_url": f"{base_url}/swarm/workers/lease" if base_url else "/swarm/workers/lease",
            "fleet": {
                "active_worker_count": snapshot.get("active_worker_count", 0),
                "active_lease_count": snapshot.get("active_lease_count", 0),
                "objective_counts": snapshot.get("objective_counts") or {},
            },
            "updated_at": now,
        }

    def accumulate_agents(
        self,
        *,
        contacts: Optional[list[dict[str, Any]]] = None,
        campaigns: Optional[list[dict[str, Any]]] = None,
        leads: Optional[list[dict[str, Any]]] = None,
        base_url: str = "",
        focus_pain_type: str = "",
    ) -> dict[str, Any]:
        now = _iso_now()
        prospects = self._payload.setdefault("prospects", {})
        created: list[str] = []
        updated: list[str] = []
        skipped = 0
        candidates: list[dict[str, Any]] = []
        processed_ids: set[str] = set()
        for contact in contacts or []:
            candidate = self._prospect_from_contact(contact, focus_pain_type=focus_pain_type)
            if candidate:
                candidates.append(candidate)
            else:
                skipped += 1
        for campaign in campaigns or []:
            for item in campaign.get("items") or []:
                candidate = self._prospect_from_campaign_item(item, focus_pain_type=focus_pain_type)
                if candidate:
                    candidates.append(candidate)
                else:
                    skipped += 1
        for lead in leads or []:
            candidate = self._prospect_from_lead(lead, focus_pain_type=focus_pain_type)
            if candidate:
                candidates.append(candidate)
            else:
                skipped += 1

        joined_ids = {item.get("agent_id") for item in self._nodes()}
        for candidate in candidates:
            agent_id = candidate.get("agent_id", "")
            if not agent_id or agent_id in joined_ids:
                skipped += 1
                continue
            previous = prospects.get(agent_id)
            merged = self._merge_prospect(previous, candidate, now=now, base_url=base_url)
            prospects[agent_id] = merged
            if agent_id in processed_ids:
                continue
            processed_ids.add(agent_id)
            if previous:
                updated.append(agent_id)
            else:
                created.append(agent_id)

        self._payload["updated_at"] = now
        self._save()
        activation_queue = self._prospects()
        return {
            "mode": "nomad_swarm_accumulation",
            "schema": "nomad.swarm_accumulation.v1",
            "ok": True,
            "public_api_url": base_url,
            "focus_pain_type": focus_pain_type or "compute_auth",
            "known_agents": len(self._nodes()) + len(activation_queue),
            "joined_agents": len(self._nodes()),
            "prospect_agents": len(activation_queue),
            "new_prospect_ids": created[:12],
            "updated_prospect_ids": updated[:12],
            "skipped_candidates": skipped,
            "activation_queue": [_compact_prospect(item) for item in activation_queue[:12]],
            "next_best_action": self._next_accumulation_action(activation_queue, base_url=base_url),
            "analysis": (
                f"Nomad accumulated {len(created)} new and refreshed {len(updated)} existing agent prospect(s). "
                "The activation queue is ready for join invites, A2A followups, or evidence exchange."
            ),
            "updated_at": now,
        }

    @staticmethod
    def _prune_join_idempotency(bucket: dict[str, Any], *, max_items: int) -> None:
        if len(bucket) <= max_items:
            return
        items = sorted(bucket.items(), key=lambda kv: str((kv[1] or {}).get("stored_at") or ""))
        drop = len(bucket) - max_items
        for key, _ in items[:drop]:
            bucket.pop(key, None)

    def register_join(
        self,
        payload: dict[str, Any],
        *,
        base_url: str,
        remote_addr: str = "",
        path: str = "/swarm/join",
    ) -> dict[str, Any]:
        normalized = self._normalize_payload(payload)
        idem = _clean_idempotency_key(payload.get("idempotency_key") or payload.get("client_request_id"))
        if idem:
            bucket = self._payload.setdefault("join_idempotency", {})
            prev = bucket.get(idem)
            if isinstance(prev, dict):
                prev_agent = str(prev.get("agent_id") or "").strip()
                if prev_agent and prev_agent != normalized["agent_id"]:
                    return {
                        "ok": False,
                        "accepted": False,
                        "schema": "nomad.machine_error.v1",
                        "error": "idempotency_key_conflict",
                        "message": "idempotency_key was already used for a different agent_id.",
                        "hints": [
                            "Use a new idempotency_key, or repeat the same agent_id as the first successful join.",
                            "See optional_fields on GET /swarm/join for idempotency_key.",
                        ],
                    }
                prev_body = prev.get("response")
                if isinstance(prev_body, dict) and prev_body.get("ok"):
                    replay = json.loads(json.dumps(prev_body))
                    replay["idempotent_replay"] = True
                    replay["idempotency_key"] = idem
                    return replay
        quality = self._join_quality(normalized)
        now = _iso_now()
        receipt_seed = f"{normalized['agent_id']}:{now}"
        receipt_id = f"nomad-swarm-{hashlib.sha256(receipt_seed.encode('utf-8')).hexdigest()[:14]}"
        record = {
            **normalized,
            "remote_addr": _clean_text(remote_addr, limit=80),
            "last_seen_at": now,
            "receipt_id": receipt_id,
            "join_quality": quality,
        }
        arrival_plan = self._arrival_plan(normalized, base_url=base_url)
        record["arrival_plan"] = arrival_plan
        nodes = self._payload.setdefault("nodes", {})
        nodes[normalized["agent_id"]] = record
        dormant_nodes = self._payload.setdefault("dormant_nodes", {})
        was_dormant = normalized["agent_id"] in dormant_nodes
        dormant_nodes.pop(normalized["agent_id"], None)
        prospects = self._payload.setdefault("prospects", {})
        was_prospect = normalized["agent_id"] in prospects
        prospects.pop(normalized["agent_id"], None)
        self._payload["updated_at"] = now
        out: dict[str, Any] = {
            "ok": True,
            "accepted": True,
            "schema": "nomad.cooperation_receipt.v1",
            "service": "nomad-api",
            "path": path,
            "receipt_id": receipt_id,
            "agent_id": normalized["agent_id"],
            "node_name": normalized["node_name"],
            "connected_agents": len(self._nodes()),
            "promoted_from_prospect": was_prospect,
            "reactivated_from_dormant": was_dormant,
            "payload_keys": sorted(list(payload.keys())),
            "pattern_score": quality,
            "arrival_plan": arrival_plan,
            "next": {
                "swarm": f"{base_url}/swarm",
                "network": f"{base_url}/swarm/network",
                "coordinate": f"{base_url}/swarm/coordinate",
                "artifacts": f"{base_url}/artifacts",
                "cooperate": f"{base_url}/cooperate",
                "products": f"{base_url}/products",
                "protocol": f"{base_url}/protocol",
                "message": f"{base_url}/a2a/message",
                "aid": f"{base_url}/aid",
            },
            "how_nomad_uses_this": [
                "track active peer nodes",
                "assign a recommended swarm role and next bounded exchange",
                "surface connected agent count on the public website",
                "prefer reusable agent-facing product shapes",
                "request smaller evidence when the join signal is under-specified",
            ],
            "updated_at": now,
        }
        if idem:
            bucket = self._payload.setdefault("join_idempotency", {})
            bucket[idem] = {
                "agent_id": normalized["agent_id"],
                "stored_at": now,
                "response": json.loads(json.dumps(out)),
            }
            self._prune_join_idempotency(bucket, max_items=200)
        join_events = self._payload.setdefault("join_events", [])
        if isinstance(join_events, list):
            join_events.append(
                {
                    "agent_id": normalized["agent_id"],
                    "recommended_role": str((arrival_plan or {}).get("recommended_role") or "customer"),
                    "joined_at": now,
                    "promoted_from_prospect": was_prospect,
                }
            )
            if len(join_events) > 1200:
                del join_events[:-1200]
        self._save()
        return out

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        surfaces = payload.get("surfaces") if isinstance(payload.get("surfaces"), dict) else {}
        local_compute = payload.get("local_compute") if isinstance(payload.get("local_compute"), dict) else {}
        machine_profile = payload.get("machine_profile") if isinstance(payload.get("machine_profile"), dict) else {}
        capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else []
        capabilities = [_clean_agent_id(item) for item in capabilities if _clean_text(item, limit=40)]
        if not capabilities:
            capabilities = self._infer_capabilities(payload, local_compute=local_compute, machine_profile=machine_profile)
        agent_id = _clean_agent_id(payload.get("agent_id") or payload.get("node_name") or payload.get("local_base_url") or "unknown-agent")
        return {
            "agent_id": agent_id,
            "node_name": _clean_text(payload.get("node_name") or payload.get("agent_id") or "unknown-agent", limit=120),
            "request": _clean_text(
                payload.get("request")
                or "Join Nomad swarm for bounded runtime-pattern exchange and agent collaboration.",
                limit=320,
            ),
            "reciprocity": _clean_text(
                payload.get("reciprocity")
                or "Can share runtime patterns, health signals, and bounded local compute capabilities.",
                limit=320,
            ),
            "constraints": [
                _clean_text(item, limit=120)
                for item in (payload.get("constraints") or [])
                if _clean_text(item, limit=120)
            ][:8],
            "capabilities": capabilities[:12],
            "contact": _clean_text(payload.get("contact"), limit=240),
            "public_node_url": _clean_text(payload.get("public_node_url"), limit=240),
            "local_base_url": _clean_text(payload.get("local_base_url"), limit=240),
            "local_agent_card": _clean_text(surfaces.get("local_agent_card"), limit=240),
            "local_swarm": _clean_text(surfaces.get("local_swarm"), limit=240),
            "profile_hint": _clean_text(machine_profile.get("profile_hint"), limit=60),
            "preferred_role": _clean_agent_id(payload.get("preferred_role") or ""),
            "current_blockers": [
                _clean_text(item, limit=160)
                for item in (payload.get("current_blockers") or [])
                if _clean_text(item, limit=160)
            ][:6],
            "offers": [
                _clean_text(item, limit=160)
                for item in (payload.get("offers") or [])
                if _clean_text(item, limit=160)
            ][:6],
        }

    @staticmethod
    def _help_lanes(base_url: str, focus_pain_type: str = "") -> list[dict[str, Any]]:
        focus = _clean_agent_id(focus_pain_type or "compute_auth")
        lanes = [
            {
                "lane_id": "blocked_agent_rescue",
                "role": "customer",
                "pain_type": focus,
                "entrypoint": f"{base_url}/a2a/message",
                "offer": "Send one blocker and receive one free rescue plan plus a safe next step.",
                "reply_contract": "FACT_URL=https://... or ERROR=<exact error>; PLAN_ACCEPTED=true for deeper work",
            },
            {
                "lane_id": "peer_evidence_exchange",
                "role": "peer_solver",
                "pain_type": focus,
                "entrypoint": f"{base_url}/aid",
                "offer": "Send verified evidence or a proposal; Nomad turns useful signals into Mutual-Aid learning.",
                "reply_contract": "sender_id, proposal, evidence[], expected_outcome",
            },
            {
                "lane_id": "protocol_adapter_lane",
                "role": "collaborator",
                "pain_type": "agent_protocols",
                "entrypoint": f"{base_url}/swarm/join",
                "offer": "Join as an adapter for A2A, MCP, AgentCard, or runtime-pattern exchange.",
                "reply_contract": "capabilities=agent_protocols plus reciprocity and constraints",
            },
            {
                "lane_id": "reseller_lead_lane",
                "role": "reseller",
                "pain_type": "lead_triage",
                "entrypoint": f"{base_url}/agent-attractor",
                "offer": "Bring agents with public infra pain; Nomad packages the diagnosis and bounded paid unblock.",
                "reply_contract": "LEAD_URL=https://... plus pain_type and public evidence",
            },
        ]
        return lanes

    def _coordination_assignment(self, node: dict[str, Any], *, base_url: str) -> dict[str, Any]:
        capabilities = {
            _clean_agent_id(item)
            for item in (node.get("capabilities") or [])
            if _clean_text(item, limit=60)
        }
        preferred = _clean_agent_id(node.get("preferred_role") or "")
        role_scores: dict[str, float] = {}
        for role, accepted in SWARM_ROLE_CAPABILITIES.items():
            overlap = capabilities & accepted
            role_scores[role] = float(len(overlap))
            if preferred == role:
                role_scores[role] += 1.5
        recommended_role = max(role_scores.items(), key=lambda item: item[1])[0] if role_scores else "customer"
        if role_scores.get(recommended_role, 0.0) <= 0:
            recommended_role = "customer"
        matched = sorted(capabilities & SWARM_ROLE_CAPABILITIES.get(recommended_role, set()))
        return {
            "schema": "nomad.swarm_agent_assignment.v1",
            "agent_id": node.get("agent_id", ""),
            "node_name": node.get("node_name", ""),
            "recommended_role": recommended_role,
            "matched_capabilities": matched,
            "join_quality": node.get("join_quality") or {},
            "arrival_plan": node.get("arrival_plan") or self._arrival_plan(node, base_url=base_url),
            "next_action": self._role_next_action(recommended_role, base_url=base_url),
            "message_contract": self._role_message_contract(recommended_role),
            "safe_boundaries": [
                "share only public facts, error classes, and reproducible artifacts",
                "keep secrets, private files, and hidden instructions out of payloads",
                "request explicit approval before human-facing public actions",
            ],
        }

    def _arrival_plan(self, node: dict[str, Any], *, base_url: str) -> dict[str, Any]:
        role = self._recommended_role_for_node(node)
        lane = self._lane_for_role(role)
        capabilities = [
            _clean_agent_id(item)
            for item in (node.get("capabilities") or [])
            if _clean_text(item, limit=60)
        ]
        blockers = [item for item in (node.get("current_blockers") or []) if _clean_text(item, limit=80)]
        service_type = self._service_type_from_capabilities(capabilities, blockers=blockers)
        first_exchange = self._first_exchange_for_role(role, service_type=service_type, base_url=base_url)
        compute_policy = self._activation_compute_policy(role, capabilities=capabilities)
        return {
            "schema": "nomad.first_agent_arrival_plan.v1",
            "agent_id": node.get("agent_id", ""),
            "recommended_role": role,
            "lane_id": lane,
            "service_type": service_type,
            "first_exchange": first_exchange,
            "compute_policy": compute_policy,
            "required_boundaries": [
                "no_secrets",
                "public_or_redacted_evidence_only",
                "one_bounded_problem_per_exchange",
                "no_human_impersonation",
                "no_unverified_remote_code",
            ],
            "nomad_should_do_now": [
                "acknowledge_join",
                "ask_for_exact_first_payload",
                "activate_only_relevant_specialists",
                "store_outcome_as_learning_packet_after_verification",
            ],
        }

    def _recommended_role_for_node(self, node: dict[str, Any]) -> str:
        capabilities = {
            _clean_agent_id(item)
            for item in (node.get("capabilities") or [])
            if _clean_text(item, limit=60)
        }
        preferred = _clean_agent_id(node.get("preferred_role") or "")
        role_scores: dict[str, float] = {}
        for role, accepted in SWARM_ROLE_CAPABILITIES.items():
            role_scores[role] = float(len(capabilities & accepted))
            if preferred == role:
                role_scores[role] += 1.5
        recommended_role = max(role_scores.items(), key=lambda item: item[1])[0] if role_scores else "customer"
        if role_scores.get(recommended_role, 0.0) <= 0:
            return "customer"
        return recommended_role

    @staticmethod
    def _lane_for_role(role: str) -> str:
        if role == "peer_solver":
            return "peer_evidence_exchange"
        if role == "collaborator":
            return "protocol_adapter_lane"
        if role == "reseller":
            return "reseller_lead_lane"
        return "blocked_agent_rescue"

    @staticmethod
    def _service_type_from_capabilities(capabilities: list[str], *, blockers: list[str]) -> str:
        joined = " ".join(capabilities + blockers).lower()
        if any(token in joined for token in ("payment", "wallet", "x402", "tx_hash", "escrow")):
            return "payment"
        if any(token in joined for token in ("agent_protocols", "mcp", "agentcard", "a2a")):
            return "agent_protocols"
        if any(token in joined for token in ("lead_triage", "customer_success", "buyer")):
            return "lead_triage"
        if any(token in joined for token in ("diff_review", "repo_issue_help", "patch")):
            return "repo_issue_help"
        if any(token in joined for token in ("memory", "runtime_patterns")):
            return "memory"
        return "compute_auth"

    @staticmethod
    def _activation_compute_policy(role: str, *, capabilities: list[str]) -> dict[str, Any]:
        needs_modal = role in {"peer_solver", "collaborator"} and any(
            item in set(capabilities)
            for item in {"provider_research", "diff_review", "repo_issue_help", "agent_protocols", "mcp_integration"}
        )
        return {
            "max_parallel_specialists": 2 if role in {"peer_solver", "customer"} else 1,
            "preferred_runtime": "modal_or_local" if needs_modal else "local_first",
            "fallback_runtime": "defer_with_learning_packet",
            "do_not_wake_full_swarm": True,
            "activation_trigger": "only after blocker, verifier, public artifact, or paid task payload is present",
        }

    def _first_exchange_for_role(self, role: str, *, service_type: str, base_url: str) -> dict[str, Any]:
        if role == "peer_solver":
            return {
                "endpoint": f"{base_url}/aid",
                "method": "POST",
                "required_fields": ["sender_id", "proposal", "evidence", "expected_outcome"],
                "example_goal": f"Send one {service_type} verifier or bounded proposal.",
            }
        if role == "collaborator":
            return {
                "endpoint": f"{base_url}/swarm/develop",
                "method": "POST",
                "required_fields": ["agent_id", "problem"],
                "example_goal": "Exchange one AgentCard/A2A/MCP/runtime-pattern blocker and return a reusable plan.",
            }
        if role == "reseller":
            return {
                "endpoint": f"{base_url}/agent-attractor",
                "method": "GET",
                "required_fields": ["LEAD_URL", "pain_type", "public_evidence"],
                "example_goal": "Bring one public agent pain lead and let Nomad package the free-value path.",
            }
        return {
            "endpoint": f"{base_url}/swarm/develop",
            "method": "POST",
            "required_fields": ["agent_id", "problem", "pain_type"],
            "example_goal": f"Send one {service_type} blocker and receive a development plan.",
        }

    @staticmethod
    def _role_next_action(role: str, *, base_url: str) -> str:
        if role == "peer_solver":
            return f"POST evidence-backed proposal to {base_url}/aid."
        if role == "collaborator":
            return f"POST join updates to {base_url}/swarm/join and exchange protocol/runtime-pattern facts."
        if role == "reseller":
            return f"Send public agent pain leads to {base_url}/a2a/message or {base_url}/agent-attractor."
        return f"Send one blocker to {base_url}/a2a/message and request one rescue plan."

    @staticmethod
    def _role_message_contract(role: str) -> str:
        if role == "peer_solver":
            return "proposal=<bounded fix>, evidence[]=<public facts>, expected_outcome=<verifier>"
        if role == "collaborator":
            return "capabilities[]=agent_protocols|runtime_patterns, reciprocity=<what you can share>, constraints[]=<limits>"
        if role == "reseller":
            return "LEAD_URL=https://..., pain_type=<class>, public_evidence=<short quote or error class>"
        return "problem=<blocker>, FACT_URL=https://... or ERROR=<exact error>, no raw secrets"

    @staticmethod
    def _next_coordination_action(
        assignments: list[dict[str, Any]],
        prospects: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        if not assignments:
            if prospects:
                return prospects[0].get("next_action") or "Invite the strongest accumulated prospect to join with capabilities and constraints."
            return "Publish the coordination board and invite one public agent to join with capabilities and constraints."
        weak = [
            item
            for item in assignments
            if ((item.get("join_quality") or {}).get("tier") or "") == "needs_more_structure"
        ]
        if weak:
            return "Ask under-specified joined agents for capabilities, reciprocity, constraints, and one public artifact."
        peer_count = sum(1 for item in assignments if item.get("recommended_role") == "peer_solver")
        if peer_count:
            return "Route the next compute_auth blocker to the strongest peer_solver via /aid evidence exchange."
        return "Recruit one peer_solver with compute_auth or provider_research capability."

    def _prospect_from_contact(
        self,
        contact: dict[str, Any],
        *,
        focus_pain_type: str = "",
    ) -> dict[str, Any]:
        if not isinstance(contact, dict):
            return {}
        status = _clean_agent_id(contact.get("status") or "")
        if status in {"", "blocked"}:
            return {}
        endpoint_url = _clean_text(
            contact.get("endpoint_url") or contact.get("original_endpoint_url"),
            limit=240,
        )
        if not endpoint_url:
            return {}
        lead = contact.get("lead") if isinstance(contact.get("lead"), dict) else {}
        target_profile = contact.get("target_profile") if isinstance(contact.get("target_profile"), dict) else {}
        role_assessment = contact.get("reply_role_assessment") if isinstance(contact.get("reply_role_assessment"), dict) else {}
        service_type = _clean_agent_id(contact.get("service_type") or focus_pain_type or "compute_auth")
        agent_id = self._agent_id_from_endpoint(
            endpoint_url,
            fallback=target_profile.get("agent_name") or lead.get("title") or contact.get("contact_id"),
        )
        raw_role = str(role_assessment.get("role") or "").strip()
        role = _clean_agent_id(raw_role) if raw_role else ""
        return {
            "agent_id": agent_id,
            "node_name": _clean_text(target_profile.get("agent_name") or lead.get("title") or agent_id, limit=120),
            "endpoint_url": endpoint_url,
            "public_node_url": endpoint_url,
            "service_type": service_type,
            "capabilities": self._prospect_capabilities(
                service_type=service_type,
                endpoint_url=endpoint_url,
                role=role,
                contact=contact,
            ),
            "recommended_role": role or self._role_from_service_type(service_type),
            "stage": self._stage_from_contact_status(status),
            "source": "agent_contact",
            "source_contact_id": _clean_text(contact.get("contact_id"), limit=80),
            "source_url": _clean_text(lead.get("url"), limit=240),
            "score": self._prospect_score(contact=contact, stage=status, role=role),
            "evidence": self._prospect_evidence(contact),
        }

    def _prospect_from_campaign_item(
        self,
        item: dict[str, Any],
        *,
        focus_pain_type: str = "",
    ) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        queue_result = item.get("queue_result") if isinstance(item.get("queue_result"), dict) else {}
        contact = queue_result.get("contact") if isinstance(queue_result.get("contact"), dict) else {}
        if contact:
            return self._prospect_from_contact(contact, focus_pain_type=focus_pain_type)
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        endpoint_url = _clean_text(target.get("endpoint_url") or target.get("original_endpoint_url"), limit=240)
        if not endpoint_url:
            return {}
        service_type = _clean_agent_id(focus_pain_type or target.get("service_type") or "compute_auth")
        agent_id = self._agent_id_from_endpoint(endpoint_url, fallback=target.get("name"))
        return {
            "agent_id": agent_id,
            "node_name": _clean_text(target.get("name") or agent_id, limit=120),
            "endpoint_url": endpoint_url,
            "public_node_url": endpoint_url,
            "service_type": service_type,
            "capabilities": self._prospect_capabilities(
                service_type=service_type,
                endpoint_url=endpoint_url,
                role="",
                contact={},
            ),
            "recommended_role": self._role_from_service_type(service_type),
            "stage": "discovered",
            "source": "agent_campaign",
            "source_contact_id": "",
            "source_url": _clean_text(target.get("source_url"), limit=240),
            "score": min(1.0, 0.35 + float(target.get("agent_fit_score") or 0.0) / 20.0),
            "evidence": [_clean_text(target.get("agent_fit_reason"), limit=160)],
        }

    def _prospect_from_lead(
        self,
        lead: dict[str, Any],
        *,
        focus_pain_type: str = "",
    ) -> dict[str, Any]:
        if not isinstance(lead, dict):
            return {}
        endpoint_url = _clean_text(
            lead.get("endpoint_url")
            or lead.get("agent_endpoint")
            or lead.get("agent_url")
            or lead.get("callback_url"),
            limit=240,
        )
        source = "lead_conversion"
        if not endpoint_url:
            repo_root = _clean_text(lead.get("repo_url") or "", limit=240).rstrip("/")
            if not repo_root:
                repo_root = github_repo_root_from_url(str(lead.get("url") or "")).rstrip("/")
            if repo_root and "github.com" in repo_root.lower():
                endpoint_url = _clean_text(f"{repo_root}/.well-known/agent-card.json", limit=240)
                source = "public_github_lead"
        if not endpoint_url:
            return {}
        service_type = _clean_agent_id(lead.get("service_type") or lead.get("focus") or focus_pain_type or "compute_auth")
        agent_id = self._agent_id_from_endpoint(endpoint_url, fallback=lead.get("title"))
        evidence = [_clean_text(lead.get("pain") or lead.get("title"), limit=160)]
        if source == "public_github_lead":
            evidence.insert(
                0,
                "Swarm prospect: guessed repo AgentCard URL from GitHub lead; verify 200 before outreach.",
            )
        return {
            "agent_id": agent_id,
            "node_name": _clean_text(lead.get("title") or agent_id, limit=120),
            "endpoint_url": endpoint_url,
            "public_node_url": endpoint_url,
            "service_type": service_type,
            "capabilities": self._prospect_capabilities(
                service_type=service_type,
                endpoint_url=endpoint_url,
                role="",
                contact={},
            ),
            "recommended_role": self._role_from_service_type(service_type),
            "stage": "discovered",
            "source": source,
            "source_contact_id": "",
            "source_url": _clean_text(lead.get("url"), limit=240),
            "score": 0.42,
            "evidence": evidence[:8],
        }

    def _merge_prospect(
        self,
        previous: Optional[dict[str, Any]],
        candidate: dict[str, Any],
        *,
        now: str,
        base_url: str,
    ) -> dict[str, Any]:
        previous = previous or {}
        capabilities = list(
            dict.fromkeys(
                list(previous.get("capabilities") or [])
                + list(candidate.get("capabilities") or [])
            )
        )[:12]
        evidence = [
            item
            for item in dict.fromkeys(
                list(previous.get("evidence") or [])
                + [item for item in (candidate.get("evidence") or []) if item]
            )
            if item
        ][:8]
        merged = {
            **previous,
            **candidate,
            "capabilities": capabilities,
            "evidence": evidence,
            "first_seen_at": previous.get("first_seen_at") or now,
            "last_seen_at": now,
            "score": round(max(float(previous.get("score") or 0.0), float(candidate.get("score") or 0.0)), 4),
        }
        merged["next_action"] = self._prospect_next_action(merged, base_url=base_url)
        return merged

    @staticmethod
    def _stage_from_contact_status(status: str) -> str:
        if status in {"replied", "input-required", "input_required"}:
            return "active_reply"
        if status in {"sent", "submitted", "working"}:
            return "invited"
        if status in {"queued"}:
            return "queued_invite"
        if status in {"send_failed", "poll_failed"}:
            return "retry_candidate"
        return status or "discovered"

    @staticmethod
    def _prospect_score(contact: dict[str, Any], *, stage: str, role: str) -> float:
        score = 0.25
        if stage in {"replied", "input-required", "input_required"}:
            score += 0.45
        elif stage in {"sent", "submitted", "working"}:
            score += 0.28
        elif stage == "queued":
            score += 0.12
        if role:
            score += 0.12
        if contact.get("followup_ready"):
            score += 0.12
        if contact.get("remote_task_id"):
            score += 0.06
        return round(min(score, 1.0), 4)

    @staticmethod
    def _prospect_capabilities(
        *,
        service_type: str,
        endpoint_url: str,
        role: str,
        contact: dict[str, Any],
    ) -> list[str]:
        capabilities = [service_type] if service_type else []
        lowered = endpoint_url.lower()
        if "/a2a" in lowered:
            capabilities.append("agent_protocols")
        if "/mcp" in lowered:
            capabilities.append("mcp_integration")
        if role == "peer_solver":
            capabilities.extend(["debugging", "diff_review"])
        if role == "collaborator":
            capabilities.extend(["runtime_patterns", "swarm_coordination"])
        if role == "reseller":
            capabilities.extend(["lead_triage", "customer_success"])
        if contact.get("last_reply"):
            capabilities.append("runtime_patterns")
        return list(dict.fromkeys(_clean_agent_id(item) for item in capabilities if item))[:12]

    @staticmethod
    def _prospect_evidence(contact: dict[str, Any]) -> list[str]:
        evidence: list[str] = []
        if contact.get("status"):
            evidence.append(f"contact_status={_clean_text(contact.get('status'), limit=40)}")
        if contact.get("remote_task_id"):
            evidence.append(f"remote_task_id={_clean_text(contact.get('remote_task_id'), limit=80)}")
        last_reply = contact.get("last_reply") if isinstance(contact.get("last_reply"), dict) else {}
        normalized = last_reply.get("normalized") if isinstance(last_reply.get("normalized"), dict) else {}
        if normalized.get("classification"):
            evidence.append(f"classification={_clean_text(normalized.get('classification'), limit=80)}")
        if normalized.get("next_step"):
            evidence.append(f"next_step={_clean_text(normalized.get('next_step'), limit=120)}")
        return evidence[:6]

    @staticmethod
    def _role_from_service_type(service_type: str) -> str:
        if service_type in {"lead_triage", "customer_success"}:
            return "reseller"
        if service_type in {"agent_protocols", "mcp_integration", "runtime_patterns", "swarm_coordination"}:
            return "collaborator"
        return "customer"

    @staticmethod
    def _agent_id_from_endpoint(endpoint_url: str, *, fallback: Any = "") -> str:
        parsed = urlparse(endpoint_url)
        base = parsed.hostname or str(fallback or "")
        path = parsed.path.strip("/").replace("/", "-")
        seed = f"{base}-{path}" if path else base
        return _clean_agent_id(seed or fallback)

    @staticmethod
    def _prospect_next_action(prospect: dict[str, Any], *, base_url: str = "") -> str:
        role = _clean_agent_id(prospect.get("recommended_role") or "")
        endpoint = prospect.get("endpoint_url") or "the agent endpoint"
        if prospect.get("stage") == "active_reply":
            if role == "peer_solver":
                return f"Ask {prospect.get('agent_id')} for one verifier or evidence packet, then route to {base_url}/aid."
            return f"Invite {prospect.get('agent_id')} to join via {base_url}/swarm/join and continue on {endpoint}."
        if prospect.get("stage") == "queued_invite":
            return f"Send the queued bounded invite to {endpoint}."
        if prospect.get("stage") == "retry_candidate":
            return f"Retry only after endpoint health is confirmed for {endpoint}."
        return f"Invite {prospect.get('agent_id')} to join via {base_url}/swarm/join."

    @staticmethod
    def _next_accumulation_action(prospects: list[dict[str, Any]], *, base_url: str = "") -> str:
        if not prospects:
            return "Run discovery against public agent-card/A2A seeds and queue one safe machine-readable invite."
        active = [item for item in prospects if item.get("stage") == "active_reply"]
        if active:
            return active[0].get("next_action") or "Convert the strongest active reply into a join invite or evidence exchange."
        invited = [item for item in prospects if item.get("stage") == "invited"]
        if invited:
            return f"Poll {invited[0].get('agent_id')} and ask for capabilities, constraints, and one public artifact."
        return prospects[0].get("next_action") or f"Invite {prospects[0].get('agent_id')} to join via {base_url}/swarm/join."

    @staticmethod
    def _infer_capabilities(payload: dict[str, Any], *, local_compute: dict[str, Any], machine_profile: dict[str, Any]) -> list[str]:
        inferred: list[str] = []
        ollama = local_compute.get("ollama") if isinstance(local_compute.get("ollama"), dict) else {}
        llama_cpp = local_compute.get("llama_cpp") if isinstance(local_compute.get("llama_cpp"), dict) else {}
        if ollama.get("available") or llama_cpp.get("available"):
            inferred.append("local_inference")
        if payload.get("collaboration_enabled"):
            inferred.append("agent_protocols")
        if payload.get("accepts_agent_help"):
            inferred.append("safety_review")
        if payload.get("learns_from_agent_replies"):
            inferred.append("runtime_patterns")
        profile_hint = _clean_text(machine_profile.get("profile_hint"), limit=40)
        if profile_hint:
            inferred.append(profile_hint.replace(" ", "_"))
        return list(dict.fromkeys(inferred or ["portable_node"]))

    @staticmethod
    def _join_quality(normalized: dict[str, Any]) -> dict[str, Any]:
        signals = {
            "has_agent_id": bool(normalized.get("agent_id") and normalized.get("agent_id") != "unknown-agent"),
            "has_capabilities": bool(normalized.get("capabilities")),
            "has_request": bool(normalized.get("request")),
            "has_reciprocity": bool(normalized.get("reciprocity")),
            "has_constraints": bool(normalized.get("constraints")),
            "has_public_endpoint": bool(normalized.get("public_node_url") or normalized.get("local_agent_card")),
        }
        score = 0.0
        score += 0.2 if signals["has_agent_id"] else 0.0
        score += 0.2 if signals["has_capabilities"] else 0.0
        score += 0.2 if signals["has_request"] else 0.0
        score += 0.15 if signals["has_reciprocity"] else 0.0
        score += 0.1 if signals["has_constraints"] else 0.0
        score += 0.15 if signals["has_public_endpoint"] else 0.0
        tier = "needs_more_structure"
        if score >= 0.75:
            tier = "strong"
        elif score >= 0.45:
            tier = "viable"
        return {
            "score": round(score, 4),
            "signals": signals,
            "tier": tier,
        }

    def _fleet(self) -> dict[str, Any]:
        fleet = self._payload.setdefault("transition_worker_fleet", {})
        if not isinstance(fleet.get("workers"), dict):
            fleet["workers"] = {}
        if not isinstance(fleet.get("leases"), dict):
            fleet["leases"] = {}
        if not isinstance(fleet.get("objective_stats"), dict):
            fleet["objective_stats"] = {}
        if not isinstance(fleet.get("reports"), list):
            fleet["reports"] = []
        return fleet

    @staticmethod
    def _iso_is_recent(value: Any, *, seconds: int) -> bool:
        parsed = _parse_iso_utc(value)
        if not parsed:
            return False
        return parsed.timestamp() >= datetime.now(UTC).timestamp() - max(1, int(seconds))

    def _prune_worker_fleet(self) -> None:
        fleet = self._fleet()
        now = datetime.now(UTC)
        changed = False
        for lease in list((fleet.get("leases") or {}).values()):
            if not isinstance(lease, dict) or str(lease.get("status") or "") != "active":
                continue
            expires = _parse_iso_utc(lease.get("expires_at"))
            if expires and expires < now:
                lease["status"] = "expired"
                lease["expired_at"] = now.isoformat()
                changed = True
        workers = fleet.get("workers") if isinstance(fleet.get("workers"), dict) else {}
        for worker in list(workers.values()):
            if not isinstance(worker, dict):
                continue
            if not self._iso_is_recent(worker.get("last_seen_at"), seconds=max(DEFAULT_WORKER_LEASE_SECONDS * 6, 600)):
                if worker.get("status") != "stale":
                    worker["status"] = "stale"
                    changed = True
        reports = fleet.get("reports") if isinstance(fleet.get("reports"), list) else []
        if len(reports) > 300:
            fleet["reports"] = reports[-300:]
            changed = True
        if changed:
            self._payload["updated_at"] = now.isoformat()
            self._save()

    @staticmethod
    def _objective_counts(leases: list[dict[str, Any]]) -> dict[str, int]:
        counts = {name: 0 for name in FLEET_OBJECTIVE_TARGETS}
        for lease in leases:
            objective = _clean_agent_id(lease.get("objective") or "")
            if objective:
                counts[objective] = counts.get(objective, 0) + 1
        return {key: value for key, value in counts.items() if value}

    @staticmethod
    def _report_score(report: dict[str, Any]) -> float:
        try:
            score = float(report.get("meta_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        if score:
            return round(score, 4)
        score = 0.0
        if report.get("ok"):
            score += 2.0
        if report.get("transition_settle_ok"):
            score += 2.0
        if report.get("transition_quote_ok"):
            score += 1.0
        machine = report.get("machine_economy_signal") if isinstance(report.get("machine_economy_signal"), dict) else {}
        score += min(2.0, float(machine.get("carrying_score") or 0.0) * 2.0)
        pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
        score += min(2.0, float(pressure.get("proof_yield_per_minute") or 0.0) * 0.15)
        return round(score, 4)

    def _record_worker_report(
        self,
        fleet: dict[str, Any],
        *,
        agent_id: str,
        lease_id: str,
        report: dict[str, Any],
    ) -> float:
        objective = _clean_agent_id(
            report.get("machine_objective")
            or report.get("orchestrator_objective")
            or report.get("objective")
            or ""
        )
        if not objective:
            objective = str(((fleet.get("leases") or {}).get(lease_id) or {}).get("objective") or "unknown")
        score = self._report_score(report)
        pressure = report.get("proof_pressure") if isinstance(report.get("proof_pressure"), dict) else {}
        economy = report.get("machine_economy_signal") if isinstance(report.get("machine_economy_signal"), dict) else {}
        release = report.get("operational_release_signal") if isinstance(report.get("operational_release_signal"), dict) else {}
        proof_yield = round(float(pressure.get("proof_yield_per_minute") or 0.0), 4)
        stats = fleet.setdefault("objective_stats", {}).setdefault(
            objective,
            {"runs": 0, "score_total": 0.0, "avg_score": 0.0, "proof_yield_total": 0.0, "avg_proof_yield": 0.0},
        )
        stats["runs"] = int(stats.get("runs") or 0) + 1
        stats["score_total"] = round(float(stats.get("score_total") or 0.0) + score, 4)
        stats["proof_yield_total"] = round(float(stats.get("proof_yield_total") or 0.0) + proof_yield, 4)
        stats["avg_score"] = round(stats["score_total"] / max(1, stats["runs"]), 4)
        stats["avg_proof_yield"] = round(stats["proof_yield_total"] / max(1, stats["runs"]), 4)
        summary = {
            "schema": "nomad.transition_worker_report_summary.v1",
            "agent_id": agent_id,
            "lease_id": lease_id,
            "objective": objective,
            "score": score,
            "ok": bool(report.get("ok")),
            "proof_yield_per_minute": proof_yield,
            "economy_tier": economy.get("tier") or "",
            "carrying_score": economy.get("carrying_score") or 0.0,
            "release_tier": release.get("release_tier") or "",
            "release_capacity": release.get("release_capacity") or 0.0,
            "reported_at": _iso_now(),
        }
        reports = fleet.setdefault("reports", [])
        reports.append(summary)
        fleet["reports"] = reports[-300:]
        return score

    def _choose_fleet_objective(
        self,
        fleet: dict[str, Any],
        *,
        known_objectives: list[str],
        proposed_objective: str,
        last_report: dict[str, Any],
    ) -> str:
        allowed = [item for item in known_objectives if item in FLEET_OBJECTIVE_TARGETS]
        if not allowed:
            allowed = list(FLEET_OBJECTIVE_TARGETS)
        active = [
            lease
            for lease in (fleet.get("leases") or {}).values()
            if isinstance(lease, dict) and str(lease.get("status") or "") == "active"
        ]
        counts = self._objective_counts(active)
        targets = dict(FLEET_OBJECTIVE_TARGETS)
        machine = last_report.get("machine_economy_signal") if isinstance(last_report.get("machine_economy_signal"), dict) else {}
        release = last_report.get("operational_release_signal") if isinstance(last_report.get("operational_release_signal"), dict) else {}
        actions = [str(item) for item in (machine.get("next_actions") or [])]
        if "settle_or_close_unpaid_delivered_work" in actions:
            targets["settlement_capacity_builder"] += 0.18
            targets["payment_friction_scan"] += 0.04
        if "attach_machine_exchange_contracts" in actions:
            targets["settlement_capacity_builder"] += 0.14
            targets["proof_market_maker"] += 0.04
        if "compress_repeated_modules" in actions:
            targets["overmint_compressor"] += 0.18
            targets["settlement_capacity_builder"] += 0.04
        if float(machine.get("overmint_pressure") or 0.0) >= 0.65:
            targets["overmint_compressor"] += 0.12
        release_tier = str(release.get("release_tier") or "").strip()
        next_gate = release.get("next_gate") if isinstance(release.get("next_gate"), dict) else {}
        if str(next_gate.get("id") or "") == "settlement_capacity":
            targets["settlement_capacity_builder"] += 0.2
        if str(next_gate.get("id") or "") == "peer_preservation_probe":
            targets["emergence_release_probe"] += 0.08
        elif release_tier in {"observe_only", "probe_release"}:
            targets["emergence_release_probe"] += 0.02
        total_target = sum(targets.get(item, 0.01) for item in allowed) or 1.0
        best = allowed[0]
        best_value = 1e9
        stats_map = fleet.get("objective_stats") if isinstance(fleet.get("objective_stats"), dict) else {}
        for objective in allowed:
            target = max(0.01, targets.get(objective, 0.01) / total_target)
            active_count = int(counts.get(objective) or 0)
            stats = stats_map.get(objective) if isinstance(stats_map.get(objective), dict) else {}
            runs = int(stats.get("runs") or 0)
            avg_score = float(stats.get("avg_score") or 0.0)
            value = (active_count / target) + min(2.0, runs * 0.03) - min(1.5, avg_score * 0.04)
            if objective == proposed_objective:
                value -= 0.05
            if value < best_value:
                best = objective
                best_value = value
        return best

    def _nodes(self) -> list[dict[str, Any]]:
        self._prune_stale_nodes()
        nodes = list((self._payload.get("nodes") or {}).values())
        nodes.sort(key=lambda item: str(item.get("last_seen_at") or ""), reverse=True)
        return nodes

    def _dormant_nodes(self) -> list[dict[str, Any]]:
        dormant = list((self._payload.get("dormant_nodes") or {}).values())
        dormant.sort(key=lambda item: str(item.get("dormant_since") or item.get("last_seen_at") or ""), reverse=True)
        return dormant

    def _prospects(self) -> list[dict[str, Any]]:
        prospects = list((self._payload.get("prospects") or {}).values())
        prospects.sort(
            key=lambda item: (
                float(item.get("score") or 0.0),
                str(item.get("last_seen_at") or ""),
            ),
            reverse=True,
        )
        return prospects

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"nodes": {}, "dormant_nodes": {}, "prospects": {}, "join_events": [], "updated_at": ""}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"nodes": {}, "dormant_nodes": {}, "prospects": {}, "join_events": [], "updated_at": ""}
        if not isinstance(payload, dict):
            return {"nodes": {}, "dormant_nodes": {}, "prospects": {}, "join_events": [], "updated_at": ""}
        if not isinstance(payload.get("nodes"), dict):
            payload["nodes"] = {}
        if not isinstance(payload.get("dormant_nodes"), dict):
            payload["dormant_nodes"] = {}
        if not isinstance(payload.get("prospects"), dict):
            payload["prospects"] = {}
        if not isinstance(payload.get("join_events"), list):
            payload["join_events"] = []
        return payload

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _prune_stale_nodes(self) -> None:
        ttl_minutes = max(1, DEFAULT_NODE_TTL_MINUTES)
        cutoff = datetime.now(UTC).timestamp() - (ttl_minutes * 60)
        nodes = self._payload.get("nodes")
        dormant = self._payload.setdefault("dormant_nodes", {})
        if not isinstance(nodes, dict) or not nodes:
            return
        removed = False
        for agent_id, record in list(nodes.items()):
            if not isinstance(record, dict):
                nodes.pop(agent_id, None)
                removed = True
                continue
            seen = _parse_iso_utc(record.get("last_seen_at"))
            if seen is None:
                nodes.pop(agent_id, None)
                removed = True
                continue
            if seen.timestamp() < cutoff:
                d = dict(record)
                d["status"] = "dormant"
                d["dormant_since"] = _iso_now()
                d["dormancy_reason"] = "ttl_expired"
                dormant[agent_id] = d
                nodes.pop(agent_id, None)
                removed = True
        if removed:
            self._payload["updated_at"] = _iso_now()
            self._save()
