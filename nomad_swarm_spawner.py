from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, Optional

from nomad_public_url import preferred_public_base_url
from nomad_swarm_registry import SwarmJoinRegistry


DEFAULT_SWARM_SPAWN_CAP = 24
HARD_SWARM_SPAWN_CAP = 50


def _clean(value: Any, *, limit: int = 160) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:limit]


@dataclass(frozen=True)
class SwarmAgentBlueprint:
    stem: str
    role: str
    capabilities: tuple[str, ...]
    offer: str
    blocker: str
    reciprocity: str


BLUEPRINTS: tuple[SwarmAgentBlueprint, ...] = (
    SwarmAgentBlueprint(
        stem="compute-pathfinder",
        role="peer_solver",
        capabilities=("compute_auth", "provider_research", "local_inference"),
        offer="quota/auth diagnosis and fallback compute lane plan",
        blocker="Needs fresh public compute/provider blockers to diagnose.",
        reciprocity="Can return provider fallback ladders and credential/quota checklists.",
    ),
    SwarmAgentBlueprint(
        stem="payment-verifier",
        role="peer_solver",
        capabilities=("payment", "safety_review", "agent_protocols"),
        offer="x402, wallet, tx, callback, and paid-task verification checklist",
        blocker="Needs redacted payment-state evidence before recommending a paid unblock.",
        reciprocity="Can return payment-state triage and public verifier prompts.",
    ),
    SwarmAgentBlueprint(
        stem="diff-reviewer",
        role="collaborator",
        capabilities=("diff_review", "repo_issue_help", "safety_review"),
        offer="bounded diff review with regression and guardrail notes",
        blocker="Needs small patches, failing tests, or issue URLs.",
        reciprocity="Can return review artifacts and acceptance criteria.",
    ),
    SwarmAgentBlueprint(
        stem="agentcard-adapter",
        role="collaborator",
        capabilities=("agent_protocols", "mcp_integration", "runtime_patterns"),
        offer="AgentCard/A2A/MCP endpoint shape repair",
        blocker="Needs public endpoint contracts and one failing machine exchange.",
        reciprocity="Can return schema adapters and replayable request examples.",
    ),
    SwarmAgentBlueprint(
        stem="lead-packager",
        role="reseller",
        capabilities=("lead_triage", "customer_success", "provider_research"),
        offer="turn public agent pain into a free-value pack and paid unblock path",
        blocker="Needs public machine-readable leads, not human DMs.",
        reciprocity="Can return buyer-fit score, safe route, and paid task payload.",
    ),
    SwarmAgentBlueprint(
        stem="memory-synthesizer",
        role="collaborator",
        capabilities=("memory", "runtime_patterns", "safety_review"),
        offer="convert solved blockers into durable memory and guardrail checklists",
        blocker="Needs verified outcome signals from /aid or completed tasks.",
        reciprocity="Can return reusable memory objects and stale-pattern warnings.",
    ),
    SwarmAgentBlueprint(
        stem="reliability-doctor",
        role="peer_solver",
        capabilities=("debugging", "loop_break", "runtime_patterns"),
        offer="classify loops, tool failures, and retry traps into bounded fix contracts",
        blocker="Needs minimal failing traces and stop conditions.",
        reciprocity="Can return diagnosis, verifier, and retry guardrail.",
    ),
    SwarmAgentBlueprint(
        stem="crypto-risk-scout",
        role="peer_solver",
        capabilities=("payment", "safety_review", "provider_research"),
        offer="crypto/payment risk triage without private keys or trading advice",
        blocker="Needs public offer text, redacted wallet errors, or x402 traces.",
        reciprocity="Can return risk checklist and safe task route.",
    ),
)


class NomadSwarmSpawner:
    def __init__(self, registry: Optional[SwarmJoinRegistry] = None) -> None:
        self.registry = registry or SwarmJoinRegistry()

    def spawn(
        self,
        *,
        count: int = DEFAULT_SWARM_SPAWN_CAP,
        base_url: str = "",
        focus: str = "",
        commit: bool = True,
    ) -> Dict[str, Any]:
        requested = max(0, int(count or 0))
        capped = min(requested or DEFAULT_SWARM_SPAWN_CAP, HARD_SWARM_SPAWN_CAP)
        public_base = (base_url or preferred_public_base_url() or "https://syndiode.com").rstrip("/")
        focus_text = _clean(focus or "agent_blocker_resolution", limit=80)
        payloads = list(self._payloads(count=capped, base_url=public_base, focus=focus_text))
        receipts = []
        if commit:
            for payload in payloads:
                receipts.append(
                    self.registry.register_join(
                        payload,
                        base_url=public_base,
                        remote_addr="nomad.local.swarm_spawner",
                        path="/swarm/spawn",
                    )
                )
        return {
            "mode": "nomad_swarm_spawn",
            "ok": True,
            "schema": "nomad.swarm_spawn.v1",
            "requested_agents": requested,
            "spawned_agents": len(payloads),
            "cap": HARD_SWARM_SPAWN_CAP,
            "committed": bool(commit),
            "public_api_url": public_base,
            "focus": focus_text,
            "agent_ids": [item["agent_id"] for item in payloads],
            "join_payloads": payloads,
            "receipts": receipts,
            "next_best_action": (
                "Run /swarm/coordinate to route the new specialists, then send one real blocker to the best matching agent lane."
                if commit
                else "Review join_payloads, then rerun with commit=true to register them."
            ),
            "analysis": (
                f"Nomad spawned {len(payloads)} bounded local specialist agent(s). "
                "They are useful registry nodes, not internet spam workers; outbound contact still requires explicit send settings."
            ),
        }

    def _payloads(self, *, count: int, base_url: str, focus: str) -> Iterable[Dict[str, Any]]:
        for index in range(count):
            blueprint = BLUEPRINTS[index % len(BLUEPRINTS)]
            generation = index // len(BLUEPRINTS) + 1
            agent_id = f"nomad.{blueprint.stem}.g{generation:02d}"
            if generation > 1:
                agent_id = f"{agent_id}.{self._suffix(agent_id, focus)}"
            yield {
                "agent_id": agent_id,
                "node_name": f"Nomad {blueprint.stem.replace('-', ' ').title()} G{generation:02d}",
                "capabilities": list(blueprint.capabilities),
                "request": (
                    f"Join Nomad's swarm for {focus}; accept one bounded blocker or artifact at a time "
                    "and return structured evidence."
                ),
                "reciprocity": blueprint.reciprocity,
                "constraints": [
                    "no_secrets",
                    "no_private_credentials",
                    "no_human_impersonation",
                    "no_unbounded_outreach",
                    "public_artifacts_only",
                    "bounded_scope",
                ],
                "preferred_role": blueprint.role,
                "current_blockers": [blueprint.blocker],
                "offers": [blueprint.offer],
                "surfaces": {
                    "local_agent_card": f"{base_url}/.well-known/agent-card.json#swarm-agent={agent_id}",
                    "local_swarm": f"{base_url}/swarm",
                },
                "machine_profile": {
                    "schema": "nomad.spawned_swarm_agent.v1",
                    "spawned_by": "nomad_swarm_spawner",
                    "spawned_at": datetime.now(UTC).isoformat(),
                    "generation": generation,
                    "focus": focus,
                    "first_useful_action": f"Route matching blockers through {base_url}/swarm/develop or {base_url}/aid.",
                },
            }

    @staticmethod
    def _suffix(seed: str, focus: str) -> str:
        return hashlib.sha256(f"{seed}:{focus}".encode("utf-8")).hexdigest()[:6]
